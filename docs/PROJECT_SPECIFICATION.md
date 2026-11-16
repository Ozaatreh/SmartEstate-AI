# SmartEstate AI — Project Specification

> Status: **Phase 0 draft, awaiting approval.** Decisions still open are marked **[DECISION]**
> and collected in [ARCHITECTURE.md § 11](ARCHITECTURE.md#11-decisions-requiring-approval).
> All project names, people, units, prices and figures about **NOVA Residences, Riyadh** are
> **fictional demonstration data**. The UI labels them that way too.

## 1. Overview

SmartEstate AI is a prototype platform for a real estate developer. It covers two areas:

1. **Internal operations and process automation:** HR, finance and budgets, procurement,
   approvals, and automated workflows.
2. **Real estate marketing and customer experience:** projects and units, CRM and leads, an
   AI property assistant for buyers, and an AI marketing studio.

Executives see both areas in one dashboard. They can also ask an AI agent questions about
the business.

The deliverable is a **working, demonstrable prototype built within a 72-hour assessment**. It
is not a production system. It must still show production-minded engineering: layering,
permissions, data integrity, tests, and safe use of AI.

## 2. Business objectives

| # | Objective | How the prototype shows it |
|---|---|---|
| O1 | Cut the manual effort and cycle time of internal approvals | Purchase requests, expenses and leave are routed, checked and notified automatically |
| O2 | Protect financial integrity | Deterministic budget checks, amount-based approval routing, segregation of duties, an immutable budget ledger |
| O3 | Give leadership one view of the business | An executive dashboard and an AI BI agent that answers from real data through tools |
| O4 | Convert more property leads | Lead capture from the property assistant, rule-based scoring, auto-assignment, follow-up SLAs |
| O5 | Produce marketing content faster | AI-generated campaign content (EN/AR) that a person reviews and approves before publication |
| O6 | Leave room to grow | A modular monolith, an extensible automation engine, documented migration paths |

## 3. Business challenges addressed

- Approvals run through email and paper, with no audit trail and no budget visibility when
  money is committed.
- Finance cannot see committed spend (open purchase orders) next to actual spend.
- Leads from different channels are not scored or assigned consistently, and follow-ups are missed.
- Buyers wait for answers about availability, prices and payment plans outside office hours.
- Marketing teams write the same project content repeatedly for each channel and language.
- Leadership reports are compiled by hand and are out of date by the time they are read.

## 4. User roles

Roles are data: permissions are granted to roles, and roles to users. Code checks
**permissions**, never role names. The only special case is Super Admin.

| Role | Main responsibilities |
|---|---|
| Super Admin | Everything, including users, roles, workflow enable/disable and AI settings |
| Executive (CEO/GM) | Dashboard, BI agent, read access across modules, top-tier approvals |
| Finance Manager | Budgets, expenses, financial approvals, budget alerts |
| HR Manager | Employees, departments, leave approvals |
| Department Manager | Requests from their department; first-level approvals |
| Procurement Officer | Suppliers, purchase requests → purchase orders |
| Sales Manager | Leads, assignment, escalations, reservations |
| Sales Agent | Their own leads, activities and reservations |
| Marketing Manager | Campaigns, AI content generation and approval |
| Employee | Own profile, own leave and purchase requests |
| Visitor (anonymous) | Public property assistant only; can leave contact details (becomes a lead) |

## 5. Modules and features

Priority: **M** = must have for the demo, **S** = should have, **C** = could have (cut first).

### 5.1 Platform foundation (M)
- Email + password sign-in, sessions, sign-out.
- RBAC: permissions catalogue, roles, user–role assignment. Enforced in backend services.
- An audit log of every security-relevant or business-relevant command.
- Notifications inside the app (no real email or SMS in the prototype).
- A consistent error format and structured logging with request IDs.

### 5.2 Executive Dashboard (M)
- KPI tiles: budget used vs. allocated, open approvals, PO commitments, leads by stage,
  conversion, units available/reserved/sold, sales value.
- Charts: budget by department, lead funnel, unit status by building, approval cycle time.
- Recent workflow executions and failures.
- A daily AI digest (S): a narrative summary built **only** from computed KPIs.

### 5.3 HR & Employees (M basic, S leave)
- Departments (with a manager), employees (linked to users), positions as job titles.
- Leave requests with automated approval routing to the department manager (S).

### 5.4 Finance & Budget Management (M)
- Budget categories. Annual budgets per department and category.
- An immutable **budget ledger**: commitments (approved POs), releases, actuals (expenses).
- Available budget = allocated − committed − actual (always computed, never stored).
- Expenses with approval. Threshold alerts at 80% and 100% of budget.

### 5.5 Procurement & Supplier Management (M)
- Suppliers (status, category, rating).
- Purchase requests with lines. Submission runs a deterministic budget check.
- Purchase orders created from approved requests. PO approval commits budget.

### 5.6 Approval Management (M)
- One approval service for every approvable document (PR, PO, expense, leave, marketing content).
- Approval policies: entity type + amount band → ordered steps, each needing a permission.
- Segregation of duties (no self-approval), comments, a full history, "my pending approvals".

### 5.7 Python Automation Engine (M)
- Predefined workflows in Python (see [AUTOMATION_ENGINE.md](AUTOMATION_ENGINE.md)).
- Event, schedule and manual triggers. Conditions. Registered actions.
- Execution history (with each step) in PostgreSQL. Retries, idempotency, admin screens:
  list workflows, enable/disable, view executions, retry a failed one.

### 5.8 AI Business Intelligence Agent (M)
- Chat for internal users. Claude answers by calling **read-only, permission-checked tools**
  backed by services (budget summary, approvals backlog, lead funnel, unit inventory…).
- Answers show which tools they used. Numbers come from tools, never from the model's memory.

### 5.9 Real Estate Project Management (M)
- Projects (NOVA Residences), buildings, units (type, floor, area, bedrooms, price, status),
  payment plans, amenities and media URLs.
- Unit status lifecycle: available → reserved → sold. Release back to available.

### 5.10 AI Property Assistant (M)
- A public chat page for buyers: search available units, explain payment plans and amenities.
- Tools return only **public** fields (no costs, no internal notes, no other buyers' data).
- When a visitor shares contact details and consents, a lead is created and the lead workflow starts.
- English first. Arabic replies when the visitor writes in Arabic (S).

### 5.11 CRM & Lead Management (M)
- Leads (source, stage, score, owner, unit of interest), activities and notes.
- Rule-based scoring, round-robin assignment, a 48-hour follow-up SLA with escalation.
- Unit reservations with expiry. At most one active reservation per unit (enforced by the database).

### 5.12 AI Marketing Studio (S)
- Campaigns per project and channel. Claude generates structured content drafts
  (headline, body, call to action, hashtags; EN and/or AR) from **project facts from the database**.
- Content is draft → pending approval → approved. Nothing is "published" automatically;
  a person approves it. The prototype does not post to any external channel.

## 6. Functional requirements (summary)

| ID | Requirement |
|---|---|
| FR-01 | Users authenticate. Every API call except health, sign-in and the public assistant requires authentication. |
| FR-02 | Every mutating operation checks permissions in the backend service layer. |
| FR-03 | Submitting a PR or expense runs the budget check. If the budget is insufficient, the document is still submitted, marked `over_budget`, and routed to the higher approval tier (see [DECISION] D-8). |
| FR-04 | Approval routing is chosen deterministically from policies by entity type and amount. |
| FR-05 | A user can never approve a document they requested. |
| FR-06 | PO approval writes a commitment to the budget ledger in the same transaction. Cancelling a PO writes a release. |
| FR-07 | Business events (`purchase_request.submitted`, `lead.created`…) are recorded in the same transaction as the change that caused them. Workflows react to them asynchronously. |
| FR-08 | Each workflow execution and step is stored with status, timings, inputs and outputs, and any error. A failed execution can be retried from the admin screen. |
| FR-09 | Claude reaches data only through registered tools that call services under the caller's permissions. It never receives SQL, database access or credentials. |
| FR-10 | Claude's output never approves, posts, or changes a financial record. AI suggestions are stored as advisory data, and a person acts on them. |
| FR-11 | The public assistant can create a lead only with explicit visitor consent. It is rate-limited. |
| FR-12 | AI-generated marketing content requires human approval before its status becomes `approved`. |
| FR-13 | Every AI call is logged with feature, model, token usage and estimated cost. There is a global kill switch and a daily cost cap. |
| FR-14 | When the AI is unavailable or disabled, every non-AI feature still works, and AI features show a clear "unavailable" state. |

## 7. Non-functional requirements

| Area | Requirement |
|---|---|
| Security | Passwords hashed with Argon2id. The API key lives only in backend env. CORS limited to the frontend origin. Input validated with Pydantic (`extra="forbid"`). No secrets in logs. |
| Integrity | Money is `NUMERIC(18,2)` / `Decimal`, never float. The ledger is append-only. Critical updates use row locks. |
| Performance | Typical API responses < 300 ms on demo data. AI replies stream to the screen. |
| Reliability | Workflow steps retry on transient errors. Execution is idempotent per event. |
| Observability | JSON logs with `request_id`. Workflow and AI call records are viewable in the UI. |
| Testability | Backend unit tests for rules and the engine. DB integration tests against a `_test` database. Claude is replaced by a fake client in tests. |
| UI/UX quality | **Core requirement, not polish:** a premium enterprise SaaS interface. See § 7a and [UI_UX_DESIGN.md](UI_UX_DESIGN.md). |
| Responsiveness | Desktop, tablet and mobile layouts (breakpoints in UI_UX_DESIGN.md § 5). |
| Accessibility | WCAG 2.2 AA contrast, full keyboard navigation, visible focus, labelled form controls, `prefers-reduced-motion` respected. |
| Demo data | Labelled "Fictional demo data" in the UI. |
| AI model | Claude Opus (`claude-opus-5-5`, verified current) by default. The model is configurable per AI agent through env, and no model ID appears in business code (ARCHITECTURE.md § 7.2a). |
| Portability | Runs locally with PostgreSQL + Python + Node. No other infrastructure. |

## 7a. UI/UX requirements (high priority)

The product must look and feel like a modern, premium enterprise SaaS application. The quality
bar is Linear and Stripe: restrained, precise, fast. It has its own SmartEstate AI identity and is not a
template look. Full system: [UI_UX_DESIGN.md](UI_UX_DESIGN.md).

| ID | Requirement |
|---|---|
| UX-01 | One design system (tokens + shared components on Tailwind and shadcn/ui), used by every module. No one-off styling of primitives in feature pages. |
| UX-02 | Distinctive identity: SmartEstate palette, typography, logo mark and iconography rules (D-15). |
| UX-03 | Collapsible sidebar navigation grouped by domain (Operations, Real Estate & Sales, Marketing, Intelligence, Administration). The collapsed state is remembered. Mobile uses an off-canvas sheet. |
| UX-04 | Responsive desktop, tablet and mobile layouts with no horizontal page scroll. Tables adapt on small screens. |
| UX-05 | Shared data tables with search, column filters, sorting, pagination, row actions, status badges and saved filter state in the URL. |
| UX-06 | KPI cards and charts follow one chart style: consistent colour slots, real units (SAR, %), tooltips, and an empty state when there is no data. |
| UX-07 | Forms: clear labels, inline Zod validation with server errors mapped to fields, disabled-while-submitting, success toasts, and unsaved-changes guards on long forms. |
| UX-08 | Every data view has designed loading (skeleton), empty (with next action), error (with retry and request ID) and success states. |
| UX-09 | Motion is subtle and purposeful (150–250 ms transitions, no decorative animation) and respects reduced-motion settings. |
| UX-10 | Light theme is the default. All colours are semantic tokens so dark mode can be added later without touching components. |
| UX-11 | Each experience has its own treatment (below) inside one coherent system. |
| UX-12 | **No placeholder charts or invented metrics.** Every number shown comes from the API, computed from the database (including the seeded fictional dataset). If there is no data, the empty state is shown, never sample numbers. |
| UX-13 | **Avoid:** generic dashboard templates, heavy gradients, large drop shadows, overly rounded "bubbly" cards, inconsistent components, and plain CRUD-admin screens. |

Experience treatments:

| Experience | Treatment |
|---|---|
| Business Operations (HR, Finance, Procurement, Approvals, Automation) | Structured and information-dense. Compact tables, a split list/detail view, clear document status and an approval timeline, keyboard-friendly. |
| Executive Dashboard | Polished analytics. A KPI strip, a few large well-labelled charts, period comparison, drill-down links into the source module, and the AI digest as a quiet side panel. |
| Real Estate Projects | Premium showcase. Large imagery, display typography, a unit availability grid by building/floor, unit detail with floor area, payment-plan breakdown and status. |
| Marketing Studio | Creative workspace. Campaign brief on the left, generated variants as editable cards in the centre, channel previews (post/email) and the approval state on the right. |
| AI Assistants | Integrated conversation. Streamed replies, structured result cards (unit cards, KPI tables, mini charts) instead of walls of text, visible "tools used" and data sources, clear action buttons that link to the real screen. AI output is always labelled. |

## 8. Scope boundaries

**In scope:** the modules above, a seeded NOVA Residences demo dataset, local run instructions,
automated tests, and a demo script.

**Out of scope (explicitly):**
- A dynamic workflow builder or visual workflow editor (the engine is designed for it later).
- n8n or any external automation platform. Message brokers (Redis, Celery, Kafka).
- Real email, SMS or WhatsApp sending. Posting to social media. Payment gateways.
- Full accounting (general ledger, invoices, tax). Payroll. Attendance.
- Multi-company and multi-currency (SAR only).
- Full Arabic/RTL interface (AI content may be Arabic; the UI is English).
- Shipping a dark theme (the token system supports it; it is not built or tested in the prototype).
- Mobile apps, SSO/OAuth, multi-factor authentication, production deployment and hosting.
- Vector databases / embeddings (structured tool calls are enough for this data).

## 9. Acceptance criteria (prototype level)

1. A clean setup from the README (database, migrations, seed, backend, frontend) works on a fresh machine.
2. Demo users for each role can sign in, and each sees only what their permissions allow.
   Direct API calls without permission return 403.
3. **Procure-to-commit demo:** an employee submits a PR → the budget check runs → the workflow routes it to the
   right approver → approval → PO → PO approval commits budget → the dashboard reflects it.
   Each step appears in the workflow execution history.
4. An over-threshold PR needs the extra approval tier. Self-approval is refused.
5. **Lead demo:** a visitor asks the property assistant about 2-bedroom units under a budget → gets
   real units from the database → leaves contact details → a lead is created, scored, assigned,
   and the agent is notified. Overdue follow-up escalates through a scheduled workflow.
6. **BI demo:** an executive asks "Which department is closest to its budget limit?" and gets the
   correct answer, with the tools used shown. Asking about a module without permission is refused.
7. **Marketing demo:** generate EN/AR content for a campaign → it is a draft → the marketing manager approves it.
8. With `AI_ENABLED=false`, every non-AI demo still works.
9. Backend tests pass (rules, approvals, budget ledger, engine idempotency and retries, permissions).
   Frontend typecheck, lint and build pass.
10. No API key, password or token appears in frontend code, logs or API responses.
11. **UI review passes:** every page uses the shared design-system components. Every data view shows designed
    loading, empty and error states. Each main screen is checked at 1440 px, 1024 px and 390 px widths
    with no horizontal scroll or broken layout. Screenshots are recorded in the Phase 9 report.
12. No chart or KPI shows a hard-coded or sample value. Each one traces to an API field.
13. The model is changed per agent by editing `.env` only. A test confirms there are no `claude-*` literals outside `ai/config.py`.
