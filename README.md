# SmartEstate AI

AI-powered real estate business platform: internal operations, process automation, CRM and
marketing, in one modular monolith. **Prototype.** NOVA Residences, Riyadh, and all demo data are fictional.

**Status: Phase 6 complete** — AI gateway (6A), AI lead summaries (6B), tool registry, BI agent and public property assistant (6C).
See [docs/](docs/) for the specification, architecture, database design, automation engine, UI/UX
design system and plan.

### AI gateway (Phase 6A)

All Claude API traffic goes through `app/ai/gateway.py`; only `app/ai/provider.py` imports the official `anthropic` SDK.
AI is **off by default** and its availability never affects startup or the rest of the app.

| Variable | Purpose |
|---|---|
| `AI_ENABLED` | Kill switch (`false` by default) |
| `ANTHROPIC_API_KEY` | Backend-only secret; never logged, returned or stored |
| `AI_DEFAULT_MODEL` | Default model for every capability |
| `AI_MODEL_<CAPABILITY>` / `AI_EFFORT_<CAPABILITY>` | Optional per-capability overrides |
| `AI_REQUEST_TIMEOUT_SECONDS`, `AI_MAX_RETRIES`, `AI_MAX_OUTPUT_TOKENS`, `AI_DAILY_COST_CAP_USD` | Limits (invalid values disable AI, not the app) |

`GET /ai/status` (any signed-in user) reports `disabled | misconfigured | unverified | operational | degraded`.
`GET /ai/gateway`, `GET /ai/usage` and `POST /ai/health-check` need `ai.gateway.manage` (Super Admin by default).
With a key configured, `.venv/Scripts/python -m app.ai.smoke` runs a real check (a few tokens) through the gateway.

### Marketing Studio (Phase 7B)

Dashboard → **Marketing** (`/marketing/campaigns`, `/marketing/content`). A **Marketing Specialist** creates campaigns
(project, channels, dates, status), writes English/Arabic content per channel (Arabic renders right-to-left in IBM Plex
Sans Arabic), edits drafts (every save is a version), and submits for review. A **Marketing Manager** approves or
requests changes through the shared approval engine (Approvals inbox or the content page). Nobody can approve content
they wrote, edited or submitted. Rejected content is revised and resubmitted; approved content is never published
automatically. The editor shows live project facts and flags prices, percentages and bedroom counts that don't match
them. AI drafting is off (`AI_MARKETING_STUDIO_ENABLED=false`).
Demo specialist account (development only, insert-only): `.venv/Scripts/python -m app.seed.demo_marketing`.

### Brochures & posters (Phase 7C)

Dashboard → **Marketing → Brochures & posters** (`/marketing/collateral`, permission `marketing.collateral.generate`:
Marketing Manager and Marketing Specialist). Pick a published project and English/Arabic, then download an **A4 brochure
(PDF)** or a **social poster (PNG)** — Instagram post 1080×1080, Instagram story 1080×1920, LinkedIn 1200×627,
Facebook 1200×630, in three layouts. Every figure is read from the database when the file is generated, and the page is
scanned before export: any number that isn't a project fact stops the download. Missing data is left out. Payment plans
appear only when classified **Cleared for marketing** (Real estate → plan → Marketing use). Nothing is published.
Rendering uses headless Chromium — install once: `cd apps/api && .venv/Scripts/python -m playwright install --only-shell chromium`.
Images: see [docs/MARKETING_ASSETS.md](docs/MARKETING_ASSETS.md) (no approved images yet → neutral placeholder).

### Maps (Phase 7D)

Each public project page has a **Location** section. With a *verified* location (Real estate → project → Edit →
Location) it shows Get directions / Open in Google Maps links (no key needed) and, when
`VITE_GOOGLE_MAPS_API_KEY` is set in `apps/marketing/.env.local`, an interactive Google map (Maps JavaScript API) with a
Map / Street View switch (Street View needs a billed key). Otherwise it shows the
district/city only. Fictional demo projects (NOVA) are never pinned. Setup and rules: [docs/MAPS.md](docs/MAPS.md).

### 3D property models (Phase 7E)

Dashboard → Real estate → project → **3D models**: add a model, upload a `.glb` or self-contained `.gltf` (validated on
the server, 50 MB max), record its source and licence, approve it. Approved models of published projects (and public
units) appear on the website in an interactive three.js viewer (orbit, zoom, reset). No models exist yet — none were
supplied, and none are generated. See [docs/3D_MODELS.md](docs/3D_MODELS.md).

### Two applications, one backend (Phase 7A)

| App | Folder | Dev URL | Audience |
|---|---|---|---|
| Marketing website | `apps/marketing` | http://localhost:5173 | Public: projects, units, payment plans, contact / viewing requests, AI property assistant |
| Internal dashboard | `apps/dashboard` | http://localhost:5174 | Staff (sign-in): CRM, finance, procurement, approvals, BI agent… |
| API (shared) | `apps/api` | http://localhost:8000 | Both apps; PostgreSQL on 127.0.0.1:5434 (project-local cluster) |

- **Public API** (`/api/v1/public/*`, no sign-in, `app/public/`): published projects, public units and payment plans,
  inquiry form token, inquiries, and the property assistant. Responses use dedicated public schemas (explicit field
  allowlists). A project appears only when **Published** is ticked in the dashboard (`re_projects.is_published`).
- **Internal API**: every other endpoint requires a signed-in user. `tests/test_public_api.py` checks this over the
  whole route table, independently of either frontend.
- **Inquiries → CRM:** server-side validation, honeypot + signed form token (minimum fill time), rate limits per IP and
  per contact, then — under one PostgreSQL advisory lock — either a new `website` lead (scored and assigned by the
  existing lead workflow) or a timeline entry on a matching open lead from the last 24 h. Same response either way.
- **Marketing AI** stays off: `AI_MARKETING_STUDIO_ENABLED=false` (separate from `AI_ENABLED`).

### BI agent and property assistant (Phase 6C)

- **BI agent** (`/intelligence/bi-agent`, permission `ai.bi_agent.use`, granted to Executive): a streamed chat over six
  read-only tools — budget positions, approvals backlog, purchase orders, lead funnel, unit inventory, workflow failures.
  Each tool also needs its module permission, checked under the signed-in user; refused tools are shown as such.
  Answers list the tools used. Conversations are private to their owner. API: `GET /ai/bi/conversations`,
  `GET /ai/bi/conversations/{id}`, `POST /ai/bi/messages` (server-sent events).
- **Property assistant** (`/assistant`, public, no sign-in): searches available public units and explains payment plans and
  projects (public fields only). With the visitor's consent checkbox and the details they typed, it registers a
  `property_assistant` lead, which then runs the normal lead workflow. Rate-limited per IP and per visitor cookie, with a
  per-conversation message cap. API: `GET /public/assistant/status`, `POST /public/assistant/messages` (SSE).
- **Tool registry** (`app/ai/tools/`): strict Pydantic inputs (unknown fields rejected), audience (internal/public),
  permission checks, one `ai_tool_calls` row per request (contact fields redacted). No tool approves, posts, pays or
  changes financial data. Max 8 tool calls per question.

### Real estate & CRM (Phase 5)

NOVA Residences and all its units, prices and payment plans are **fictional** (every screen shows *Illustrative / Fictional Demo Data*). Add the demo inventory to a development database with `.venv/Scripts/python -m app.seed.demo_realestate` — it only inserts what is missing and never changes existing rows.

- **Leads:** `new → contacted → qualified → viewing → negotiation → won | lost` (forward moves; `lost` from any open stage; reopen only from `lost`; `won`/`lost` need a reason). New leads are scored by transparent rules (source, contact completeness, budget, high budget, bedrooms, interest, consent, **timeline**, **budget fit against available units**), assigned round-robin per project and get a 48-hour follow-up. `crm.follow_up_sla` escalates overdue follow-ups to sales managers once per lead per day.
- **Reservations:** one active reservation per unit (database-enforced), 72 hours by default, optional informational deposit (no ledger posting). Reserving moves the unit to `reserved` and the lead to `negotiation`; cancel/expiry releases the unit; conversion sells it and wins the lead — all in one transaction. `crm.reservation_expiry` runs every 15 minutes.
- **Permissions:** `realestate.inventory.read` (all staff), `realestate.inventory.manage` + `crm.leads.manage` (sales manager), `crm.reservations.manage` (sales agent for own leads, sales manager for all). Agents see only their own leads.

### Purchase orders (Phase 4) and where the budget is committed

**Deliberate deviation (D-16):** the budget is committed **once, at the purchase request's final approval**, not at
purchase-order approval. Procurement (`procurement.orders.manage`) creates a PO from a fully approved request; supplier,
lines, quantities and agreed prices are copied from the selected quotation, so the PO total always equals the commitment.
`draft → issued → cancelled`, no second approval chain, and creating or issuing a PO writes nothing to the ledger. One active PO
per request (database-enforced). Cancelling asks what happens to the budget: **release** (one release entry, the request becomes
`closed`; refused while another active PO needs the commitment) or **keep** (commitment stays, a replacement PO can be created and
is linked to the cancelled one). Requests approved before Phase 4 keep their commitments untouched until one of their orders is
cancelled with release.

### Purchase-request lifecycle (Phase 2)

`draft → sourcing → pending_approval → approved | rejected` (or `cancelled` before approval; `approved → closed` when its PO is cancelled with budget release).
The employee creates the request (budget checked live). Submitting resolves the department or project budget, and
procurement then records supplier quotations and selects one. Sending it for approval routes it by amount (D-11: ≤ SAR 50k
department manager · ≤ 250k + finance · above + executive; over-budget always adds finance and executive, D-8).
The final approval commits the amount to the append-only budget ledger in the same transaction. Every step is audited and
notifies the next people involved. Escalation: when the requester manages the department (or there is no manager with an
account), the department step moves up the reporting line, or to holders of `approvals.department.approve` if nobody is found.

| Layer | Technology |
|---|---|
| Frontend | React 19 · TypeScript · Vite · Tailwind CSS 4 · shadcn/ui (Radix) · TanStack Query & Table · React Hook Form + Zod · Recharts |
| Backend | Python 3.12+ · FastAPI · SQLAlchemy 2 · Pydantic 2 · Alembic · psycopg 3 · Argon2 · PyJWT |
| Database | PostgreSQL 16+ (developed on 18) |
| AI | Anthropic Claude API, default `claude-opus-5-5`, configured only through `.env` (Phase 6) |

## Quick start (Windows, Git Bash; macOS/Linux are the same apart from venv paths)

```bash
cp .env.example .env              # then replace every <generate: …> value
bash infrastructure/scripts/dev-db.sh init   # project-local PostgreSQL on 127.0.0.1:5434
```

`dev-db.sh` creates a private cluster in `apps/api/var/pgdata` with the installed PostgreSQL
binaries, so no superuser password or Docker is needed. To use an existing server instead, create the `smartestate`
and `smartestate_test` databases there and point `DATABASE_URL` / `TEST_DATABASE_URL` at it.

```bash
cd apps/api
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"      # macOS/Linux: .venv/bin/python
.venv/Scripts/alembic upgrade head
.venv/Scripts/python -m app.seed                      # permissions, roles, demo accounts (idempotent)
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

```bash
cd apps/dashboard                                     # internal system (staff sign-in)
npm install
npm run dev                                           # http://localhost:5174 (proxies /api → :8000)
```

```bash
cd apps/marketing                                     # public website (no sign-in)
npm install
npm run dev                                           # http://localhost:5173 (proxies only /api/v1/public → :8000)
```

### Demo accounts (development only)

`python -m app.seed` creates one fictional account per role. They all use the password in
`SEED_DEMO_PASSWORD` in your `.env`.

| Email | Role |
|---|---|
| `admin@smartestate.demo` | Super Admin |
| `ceo@smartestate.demo` | Executive |
| `finance@smartestate.demo` | Finance Manager |
| `hr@smartestate.demo` | HR Manager |
| `construction.head@smartestate.demo` | Department Manager |
| `procurement@smartestate.demo` | Procurement Officer |
| `sales.manager@smartestate.demo` | Sales Manager |
| `sales.agent@smartestate.demo` | Sales Agent |
| `marketing@smartestate.demo` | Marketing Manager |
| `employee@smartestate.demo` | Employee |

## What Phase 1 contains

- **Platform:** app factory, settings from `.env` (startup refuses placeholder secrets in staging/production),
  JSON logs with request IDs and secret redaction, a single error shape
  `{"error": {code, message, request_id, details}}`, health endpoint.
- **Identity & RBAC:** Argon2id passwords; signed session JWT in an HttpOnly, SameSite=Lax cookie (8 h);
  `X-Requested-With` CSRF header on every mutating request; sign-out and deactivation revoke all
  sessions (`token_version`); per-account lockout (5 failures → 15 min) and per-IP throttling;
  permission catalogue in `app/core/permissions.py`, checked inside services.
- **Audit log:** append-only (a database trigger rejects UPDATE/DELETE); searchable, filterable, sortable list.
- **Notifications:** in-app, private per user, idempotent via `dedupe_key`.
- **AI startup resilience:** AI settings are never fatal. `app/ai/status.py` turns them into
  `enabled | disabled | misconfigured` with a reason (see `GET /api/v1/health`); everything else keeps working.
- **Design system** (`apps/dashboard/src`; the marketing site copies `styles/tokens.css`): tokens in `styles/tokens.css`; themed primitives in `components/ui`; system
  components in `components/system` (PageHeader, Panel, DataTable, StatusBadge, KpiCard, ChartCard,
  FormField, ConfirmDialog, Empty/Error/Permission/Loading states, MoneyText, Meter, AiBadge); app shell with
  a collapsible sidebar (`[` toggles), tablet icon rail and mobile sheet. The reference page is at `/_design` (Super Admin).

## API (Phase 1)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/health` | Database + AI status |
| POST | `/api/v1/auth/login` | Sets the session cookie |
| POST | `/api/v1/auth/logout` | Revokes all sessions of the user |
| GET | `/api/v1/auth/me` | Current user, roles, permissions |
| GET | `/api/v1/notifications` | `q, sort, page, page_size, unread_only` |
| GET | `/api/v1/notifications/unread-count` | |
| POST | `/api/v1/notifications/{id}/read`, `/read-all` | |
| GET | `/api/v1/audit-logs` | `audit.logs.read`; `q, sort, page, page_size, action, entity_type, actor_user_id` |

### Automation worker (Phase 3)

Workflows run in a separate process. Start it next to the API (any number of workers is safe):

```bash
cd apps/api
.venv/Scripts/python -m app.automation.worker          # Ctrl+C to stop; --once drains the queue and exits
```

Without a worker, business events queue up in PostgreSQL and the Automation page shows "No worker running".
Workflows, executions, step details, logs and retries are at `/automation` (permission `automation.workflows.read`).
Design and guarantees: [docs/AUTOMATION_ENGINE.md](docs/AUTOMATION_ENGINE.md).

| Area | Endpoints |
|---|---|
| Automation | `GET /automation/overview`, `GET /automation/workflows`, `GET/PATCH /automation/workflows/{key}`, `POST /automation/workflows/{key}/run`, `GET /automation/executions`, `GET /automation/executions/{id}`, `POST …/{id}/retry`, `POST …/{id}/cancel` |
| CRM (Phase 5) | `POST /crm/leads`, `GET /crm/leads` (`scope=mine\|all, stage, owner_user_id, project_id, overdue, grade`), `GET /crm/leads/stats`, `GET/PATCH /crm/leads/{id}`, `POST …/{id}/stage` (`{stage, reason}`), `POST …/{id}/assign`, `GET/POST …/{id}/activities`, `GET /crm/sales-users`, `POST/GET /crm/reservations`, `GET /crm/reservations/{id}`, `POST …/{id}/cancel`, `POST …/{id}/convert`, `GET /crm/units/{id}/reservation` |
| Real estate (Phase 5) | `GET/POST /realestate/projects`, `GET/PATCH /realestate/projects/{id}`, `GET …/{id}/availability`, `POST …/{id}/buildings`, `PATCH/DELETE /realestate/buildings/{id}`, `POST …/projects/{id}/payment-plans`, `PATCH /realestate/payment-plans/{id}`, `GET/POST /realestate/units` (filters: project, building, status, type, bedrooms, min_bedrooms, price range), `GET/PATCH/DELETE /realestate/units/{id}` |

### Phase 2 endpoints

| Area | Endpoints |
|---|---|
| HR | `GET/POST /hr/departments`, `GET/PATCH /hr/departments/{id}`, `GET/POST /hr/employees`, `GET/PATCH /hr/employees/{id}` |
| Finance | `GET /finance/categories`, `GET/POST /finance/projects`, `GET/PATCH /finance/projects/{id}`, `GET /finance/budgets/summary`, `GET/POST /finance/budgets`, `GET/PATCH /finance/budgets/{id}` (includes ledger) |
| Procurement | `GET/POST /procurement/suppliers`, `GET /procurement/suppliers/categories`, `GET/PATCH /procurement/suppliers/{id}`, `GET/POST /procurement/requests`, `GET /procurement/requests/stats`, `POST /procurement/requests/budget-preview`, `GET/PATCH /procurement/requests/{id}`, `GET …/{id}/activity`, `POST …/{id}/submit`, `POST …/{id}/cancel`, `POST …/{id}/send-for-approval`, `POST …/{id}/quotations`, `PUT/DELETE …/{id}/quotations/{qid}`, `POST …/{id}/quotations/{qid}/select` |
| Purchase orders (Phase 4) | `POST /procurement/requests/{id}/purchase-orders`, `GET /procurement/purchase-orders` (`q, sort, page, page_size, status, request_id`), `GET/PATCH /procurement/purchase-orders/{id}`, `POST …/{id}/issue`, `POST …/{id}/cancel` (`{reason, release_budget}`) |
| Approvals | `GET /approvals?box=pending\|decided\|mine\|all`, `GET /approvals/pending-count`, `GET /approvals/policies`, `GET /approvals/{id}`, `POST /approvals/{id}/approve`, `POST /approvals/{id}/reject` (comment required) |

Interactive docs: <http://127.0.0.1:8000/docs> (disabled in production).

## Tests & checks

```bash
cd apps/api
.venv/Scripts/python -m pytest          # unit + PostgreSQL integration (TEST_DATABASE_URL must end in _test)
.venv/Scripts/ruff check app tests alembic
.venv/Scripts/alembic check             # models and migrations in sync

cd apps/dashboard   # and the same in apps/marketing
npm test && npm run typecheck && npm run lint && npm run build
```
