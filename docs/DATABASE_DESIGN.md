# SmartEstate AI — Database Design

> Status: **Phase 0 design, not yet implemented.** No models or migrations exist. Implementation is
> through SQLAlchemy 2 models + Alembic migrations starting in Phase 1.

## 1. Conventions

| Topic | Rule |
|---|---|
| Primary keys | `id UUID PRIMARY KEY DEFAULT gen_random_uuid()` (D-6) |
| Timestamps | `created_at`, `updated_at` `TIMESTAMPTZ NOT NULL DEFAULT now()` on every table |
| Actors | `created_by UUID NULL REFERENCES users(id)` where useful |
| Money | `NUMERIC(18,2)`, currency is SAR only (no currency column in the prototype) |
| Quantities / areas | `NUMERIC(12,2)` |
| Status / enums | `VARCHAR(30)` + `CHECK (status IN (...))`; not PostgreSQL ENUM types (easier migrations) |
| Codes | Human-readable codes from PostgreSQL sequences (`PR-00001`), never `max()+1` |
| Deletion | Master data is deactivated (`is_active`); transactional and history rows are never deleted |
| Immutability | Ledgers and history tables (`budget_ledger_entries`, `audit_logs`, `approval_decisions`, `wf_step_executions`) are append-only; a trigger rejects `UPDATE`/`DELETE` on the ledger |
| JSON | `JSONB` only for genuinely variable data (payloads, config, AI output) — never for data that is filtered or joined |
| FKs | `ON DELETE RESTRICT` by default; `CASCADE` only for owned child lines (e.g. PR lines) |

## 2. Identity, audit, notifications (module: `identity`, `audit`, `notifications`)

| Table | Key columns | Constraints / notes |
|---|---|---|
| `users` | email, password_hash, full_name, is_active, token_version int, last_login_at, failed_login_count, locked_until | `UNIQUE (lower(email))` |
| `roles` | code, name, description, is_system | `UNIQUE (code)` |
| `permissions` | code, module, description | `UNIQUE (code)`; seeded from the Python catalogue |
| `role_permissions` | role_id → roles, permission_id → permissions | PK `(role_id, permission_id)` |
| `user_roles` | user_id → users, role_id → roles | PK `(user_id, role_id)` |
| `audit_logs` | actor_user_id → users NULL, action, entity_type, entity_id, changes JSONB, request_id, ip_address INET, created_at | Append-only; index `(entity_type, entity_id, created_at DESC)`, `(actor_user_id, created_at DESC)` |
| `notifications` | user_id → users, type, title, body, link, entity_type, entity_id, read_at NULL, source_execution_id → wf_executions NULL | Index `(user_id, read_at, created_at DESC)`; `UNIQUE (user_id, dedupe_key)` where `dedupe_key` is set by workflow actions (idempotency) |

## 3. HR (module: `hr`)

| Table | Key columns | Constraints / notes |
|---|---|---|
| `departments` | code, name, manager_employee_id → employees NULL, is_active | `UNIQUE (code)`; manager FK is `use_alter` (circular with employees) |
| `employees` | employee_no, user_id → users NULL, department_id → departments, full_name, job_title, email, hire_date, is_active | `UNIQUE (employee_no)`, `UNIQUE (user_id) WHERE user_id IS NOT NULL` |
| `leave_requests` (S) | code, employee_id → employees, leave_type, start_date, end_date, days NUMERIC(5,1), reason, status | `CHECK (end_date >= start_date)`; status `draft|pending_approval|approved|rejected|cancelled` |

## 4. Finance & budget (module: `finance`)

| Table | Key columns | Constraints / notes |
|---|---|---|
| `budget_categories` | code, name, is_active | `UNIQUE (code)` (e.g. CAPEX-CONSTR, MARKETING, IT, OPEX-ADMIN) |
| `budgets` | department_id → departments, category_id → budget_categories, fiscal_year int, allocated_amount, status (`draft|active|closed`) | `UNIQUE (department_id, category_id, fiscal_year)`; `CHECK (allocated_amount >= 0)` |
| `budget_ledger_entries` | budget_id → budgets, entry_type (`commitment|release|actual|adjustment`), amount (signed), source_type, source_id, idempotency_key, created_by, created_at | **Append-only.** `UNIQUE (idempotency_key)` (e.g. `po:<id>:commit`); index `(budget_id, entry_type)` |
| `expenses` | code, budget_id → budgets, requested_by → users, amount, description, expense_date, status, receipt_url | status `draft|pending_approval|approved|rejected|recorded`; `CHECK (amount > 0)` |

**Derived values (view `v_budget_position`, not stored):**
`committed = SUM(commitment + release)`, `actual = SUM(actual)`,
`available = allocated + SUM(adjustment) − committed − actual`, `utilisation_pct`.

**Concurrency rule:** budget check + commitment run under `SELECT … FOR UPDATE` on the `budgets`
row, so two approvals cannot both spend the same remaining budget.

## 5. Procurement (module: `procurement`)

| Table | Key columns | Constraints / notes |
|---|---|---|
| `suppliers` | code, name, category, contact_name, email, phone, vat_number, rating NUMERIC(2,1), status (`active|blocked|inactive`) | `UNIQUE (code)`; `CHECK (rating BETWEEN 0 AND 5)` |
| `purchase_requests` | code, requested_by → users, department_id → departments, budget_id → budgets, title, justification, total_amount, needed_by, status, budget_check_result (`ok|over_budget`), budget_checked_at | status `draft|pending_approval|approved|rejected|cancelled|ordered`; index `(status, department_id)` |
| `purchase_request_lines` | request_id → purchase_requests (CASCADE), line_no, description, quantity, unit_price, line_total | `UNIQUE (request_id, line_no)`; `CHECK (quantity > 0 AND unit_price >= 0)`; `line_total` computed in the service with Decimal and checked by `CHECK (line_total = round(quantity*unit_price, 2))` |
| `purchase_orders` | code (`PO-00001`, sequence), request_id → purchase_requests, quotation_id → supplier_quotations, supplier_id → suppliers, budget_id → budgets, replaces_order_id → purchase_orders, total_amount, payment_terms, expected_delivery_date, delivery_address, notes, created/issued/cancelled by + at, cancel_reason, budget_released | status `draft|issued|cancelled` (no approval chain, D-16); `UNIQUE (request_id) WHERE status <> 'cancelled'` (one active PO per PR); CHECKs: issued ⇒ issued_at, cancelled ⇒ cancelled_at + reason, total ≥ 0. Never writes a commitment; the request's single release is written when an order is cancelled with "release" |
| `purchase_order_lines` | order_id → purchase_orders (CASCADE), request_item_id → purchase_request_items, line_no, description, quantity, unit, unit_price, line_total | frozen copy of the selected quotation; CHECK `line_total = round(quantity × unit_price, 2)` |

## 6. Approvals (module: `approvals`)

| Table | Key columns | Constraints / notes |
|---|---|---|
| `approval_policies` | entity_type, name, min_amount, max_amount NULL, is_active, priority | Non-overlapping bands per entity type are checked in the service; index `(entity_type, is_active)` |
| `approval_policy_steps` | policy_id → approval_policies, step_order, required_permission, approver_scope (`department_manager|permission_holder`), label | `UNIQUE (policy_id, step_order)` |
| `approval_requests` | entity_type, entity_id, policy_id, requested_by → users, amount, status (`pending|approved|rejected|cancelled`), current_step, flags JSONB (e.g. `over_budget`) , completed_at | **`UNIQUE (entity_type, entity_id) WHERE status = 'pending'`** (one open approval per document); index `(status, entity_type)` |
| `approval_steps` | approval_request_id → approval_requests (CASCADE), step_order, required_permission, approver_scope, assigned_user_id NULL, status (`waiting|pending|approved|rejected|skipped`) | `UNIQUE (approval_request_id, step_order)` |
| `approval_decisions` | approval_step_id → approval_steps, decided_by → users, decision (`approved|rejected`), comment, decided_at | Append-only; `UNIQUE (approval_step_id)`; service rejects `decided_by = requested_by` and duplicate deciders across steps |

`entity_type` + `entity_id` is a polymorphic reference (no FK), validated by the registered
`ApprovalSubject` adapter for that type.

## 7. Real estate (module: `realestate`)

| Table | Key columns | Constraints / notes |
|---|---|---|
| `re_projects` | code, name (NOVA Residences), city, district, description, status (`planning|launched|under_construction|completed`), launch_date, handover_date, amenities JSONB, media JSONB, is_demo_data bool | `UNIQUE (code)` |
| `re_buildings` | project_id → re_projects, code, name, floors int | `UNIQUE (project_id, code)` |
| `re_units` | project_id → re_projects, building_id → re_buildings, unit_number, unit_type (`studio|apartment|duplex|penthouse|townhouse`), bedrooms, bathrooms, floor, area_sqm, view, list_price, status (`available|reserved|sold|blocked`), is_public bool | `UNIQUE (building_id, unit_number)`; `CHECK (area_sqm > 0 AND list_price > 0)`; index `(project_id, status, bedrooms, list_price)` for assistant search |
| `re_payment_plans` | project_id → re_projects, name, down_payment_pct, installments int, installment_frequency, handover_pct, description, is_active | `CHECK (down_payment_pct BETWEEN 0 AND 100)` |

## 8. CRM (module: `crm`)

> **As built (Phase 5, migrations `0006` real estate and `0007` CRM).** Every real-estate table also has `is_demo_data`; `re_payment_plans` adds `UNIQUE (project_id, name)` and `CHECK (down_payment_pct + handover_pct <= 100)`. `leads` keeps its Phase 3 columns (`grade`, `interest`, `notes`, `assigned_at`) and adds `project_id`, `interested_unit_id`, `timeline` (`immediate|within_3_months|within_6_months|over_6_months`), `last_activity_at`, `stage_changed_at`, `close_reason` (`CHECK stage NOT IN ('won','lost') OR close_reason IS NOT NULL`). `lead_activities` adds `reservation_id`; its types are `note|call|email|whatsapp|viewing|system|assignment|stage_change`; `unit_reservations` adds `code` (`RSV-00001`, sequence), cancel/convert/expire columns and CHECKs. `sales_assignment_state` is keyed by `pool` (project code, else `default`) instead of `project_id` (decision C3). Deposits are informational only — never posted to a ledger.

| Table | Key columns | Constraints / notes |
|---|---|---|
| `leads` | code, project_id → re_projects, full_name, phone, email, preferred_language, source (`property_assistant|website|walk_in|referral|campaign|phone`), campaign_id → marketing_campaigns NULL, stage (`new|contacted|qualified|viewing|negotiation|won|lost`), score int, score_reasons JSONB, budget_min, budget_max, bedrooms_wanted, interested_unit_id → re_units NULL, owner_user_id → users NULL, consent_given_at, consent_text_version, last_activity_at, next_follow_up_at, ai_summary TEXT NULL | `CHECK (score BETWEEN 0 AND 100)`; `CHECK (phone IS NOT NULL OR email IS NOT NULL)`; index `(owner_user_id, stage)`, `(stage, next_follow_up_at)` |
| `lead_activities` | lead_id → leads, type (`note|call|email|whatsapp|viewing|stage_change|system`), body, performed_by → users NULL, occurred_at | Append-only; index `(lead_id, occurred_at DESC)` |
| `unit_reservations` | unit_id → re_units, lead_id → leads, reserved_by → users, status (`active|expired|cancelled|converted`), reserved_at, expires_at, deposit_amount | **`UNIQUE (unit_id) WHERE status = 'active'`** (one active reservation per unit); index `(status, expires_at)` |
| `sales_assignment_state` | project_id → re_projects PK, last_assigned_user_id | Round-robin cursor; updated under row lock |

## 9. Marketing (module: `marketing`)

| Table | Key columns | Constraints / notes |
|---|---|---|
| `marketing_campaigns` | code, project_id → re_projects, name, objective, channels JSONB, target_audience, start_date, end_date, budget_id → budgets NULL, status (`draft|active|completed|cancelled`) | `CHECK (end_date >= start_date)` |
| `marketing_contents` | campaign_id → marketing_campaigns, channel (`instagram|x|linkedin|email|website|whatsapp`), language (`en|ar`), title, body, call_to_action, hashtags JSONB, status (`draft|pending_approval|approved|rejected|archived`), generated_by_ai bool, ai_generation_id → ai_generations NULL, version int, created_by | Index `(campaign_id, status)` |

## 10. Automation engine (module: `automation`)

| Table | Key columns | Constraints / notes |
|---|---|---|
| `wf_definitions` | key, version int, name, description, trigger_type (`event|schedule|manual`), trigger_config JSONB (event types or interval/cron), is_enabled, parameters JSONB, registered_at | `UNIQUE (key, version)`; rows are upserted at startup from the Python registry; `is_enabled`/`parameters` are editable |
| `automation_events` | event_type, entity_type, entity_id, payload JSONB, actor_user_id NULL, occurred_at, status (`pending|processing|processed|failed`), attempts, available_at, locked_at, locked_by, processed_at, last_error | Index `(status, available_at)` for polling; partial index `WHERE status = 'pending'` |
| `wf_executions` | definition_id → wf_definitions, workflow_key, workflow_version, trigger_type, event_id → automation_events NULL, idempotency_key, status (`pending|running|succeeded|failed|skipped|cancelled`), attempt int, max_attempts, next_retry_at, context JSONB, started_at, finished_at, error_code, error_message, triggered_by_user_id NULL | **`UNIQUE (idempotency_key)`**; index `(status, next_retry_at)`, `(workflow_key, created_at DESC)` |
| `wf_step_executions` | execution_id → wf_executions, step_index, step_key, action_key, attempt, status (`succeeded|failed|skipped`), input JSONB, output JSONB, started_at, finished_at, error_message | `UNIQUE (execution_id, step_key, attempt)`; append-only |
| `wf_schedule_state` | definition_id → wf_definitions PK, last_fired_at, next_fire_at | Updated under row lock so a schedule fires once per slot |

## 11. AI (module: `ai`)

| Table | Key columns | Constraints / notes |
|---|---|---|
| `ai_conversations` | feature (`bi_agent|property_assistant`), user_id → users NULL, visitor_session_id NULL, lead_id → leads NULL, title, status | `CHECK (user_id IS NOT NULL OR visitor_session_id IS NOT NULL)`; index `(user_id, updated_at DESC)` |
| `ai_messages` | conversation_id → ai_conversations, role (`user|assistant`), content JSONB (API content blocks), created_at | Append-only |
| `ai_tool_calls` | conversation_id NULL, message_id NULL, tool_name, input JSONB, status (`ok|denied|error`), result_summary, duration_ms | Index `(tool_name, created_at)` |
| `ai_generations` | feature (`marketing|digest|lead_summary`), input_ref JSONB, output JSONB, model, prompt_version, created_by NULL | Traceability of generated drafts |
| `ai_usage` | feature, model, user_id NULL, visitor_session_id NULL, input_tokens, output_tokens, cache_read_tokens, estimated_cost NUMERIC(12,6), latency_ms, status, stop_reason, created_at | Index `(created_at)`, `(feature, created_at)` — daily cost cap = `SUM(estimated_cost) WHERE created_at >= today` |

## 12. Relationships overview

```
users 1─* user_roles *─1 roles 1─* role_permissions *─1 permissions
users 1─0..1 employees *─1 departments (manager → employees)
departments 1─* budgets *─1 budget_categories ; budgets 1─* budget_ledger_entries
budgets 1─* purchase_requests 1─* purchase_request_lines
purchase_requests 1─0..1 purchase_orders(live) *─1 suppliers ; purchase_orders 1─* purchase_order_lines
budgets 1─* expenses
approval_policies 1─* approval_policy_steps ; approval_requests 1─* approval_steps 1─0..1 approval_decisions
approval_requests ─(entity_type, entity_id)→ PR | PO | expense | leave_request | marketing_content
re_projects 1─* re_buildings 1─* re_units ; re_projects 1─* re_payment_plans
re_projects 1─* leads 1─* lead_activities ; re_units 1─* unit_reservations *─1 leads
re_projects 1─* marketing_campaigns 1─* marketing_contents
wf_definitions 1─* wf_executions 1─* wf_step_executions ; automation_events 1─* wf_executions
ai_conversations 1─* ai_messages ; leads 0..1─* ai_conversations
```

## 13. Indexing recommendations (beyond PK/UNIQUE)

- Every FK column used in joins or filters gets a B-tree index (PostgreSQL does not create them automatically).
- Queue polling: `automation_events (available_at) WHERE status = 'pending'`;
  `wf_executions (next_retry_at) WHERE status = 'failed' AND attempt < max_attempts`.
- Dashboards: `budget_ledger_entries (budget_id, entry_type)`, `leads (project_id, stage)`,
  `re_units (project_id, status)`, `approval_requests (status, created_at)`.
- Search: `re_units (project_id, status, bedrooms, list_price)`; `leads` trigram index on name/phone is a *could*.
- Avoid premature indexes on JSONB.

## 14. Data ownership and access

| Owner module | Tables it writes | Who may read (through services) |
|---|---|---|
| identity | users, roles, permissions, role_permissions, user_roles | admins; self for own profile |
| audit | audit_logs | `audit.read` (admins, executives) |
| notifications | notifications | the recipient only |
| hr | departments, employees, leave_requests | HR; managers for their department; self |
| finance | budget_*, expenses | finance; executives; department managers for their department |
| procurement | suppliers, purchase_* | procurement; requester; approvers of that document |
| approvals | approval_* | requester, assigned approvers, `approvals.read_all` |
| realestate | re_* | everyone internal; **public tools see only `is_public` units and public columns** |
| crm | leads, lead_activities, unit_reservations, sales_assignment_state | sales manager (all); sales agent (own leads) |
| marketing | marketing_* | marketing roles; executives |
| automation | wf_*, automation_events (others *insert* events only through `EventBus.emit`) | `automation.read`, admins |
| ai | ai_* | own conversations; `ai.admin` for usage |

Rules: only the owner module's repository writes its tables; other modules go through its
service. Personal data (lead contact details) is never written to logs or `ai_usage`; it is
sent to Claude only inside the property assistant conversation in which the visitor gave it.
