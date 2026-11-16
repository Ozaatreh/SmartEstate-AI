# SmartEstate AI

AI-powered real estate business platform: internal operations, process automation, CRM and
marketing, in one modular monolith. **Prototype.** NOVA Residences, Riyadh, and all demo data are fictional.

**Status: Phase 3 (Python automation engine + worker, four workflows, Automation UI) complete.**
See [docs/](docs/) for the specification, architecture, database design, automation engine, UI/UX
design system and plan.

### Purchase-request lifecycle (Phase 2)

`draft → sourcing → pending_approval → approved | rejected` (or `cancelled` before approval).
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
cd apps/web
npm install
npm run dev                                           # http://localhost:5173 (proxies /api → :8000)
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
- **Design system** (`apps/web/src`): tokens in `styles/tokens.css`; themed primitives in `components/ui`; system
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
| CRM (foundation) | `POST /crm/leads`, `GET /crm/leads`, `GET /crm/leads/{id}` |

### Phase 2 endpoints

| Area | Endpoints |
|---|---|
| HR | `GET/POST /hr/departments`, `GET/PATCH /hr/departments/{id}`, `GET/POST /hr/employees`, `GET/PATCH /hr/employees/{id}` |
| Finance | `GET /finance/categories`, `GET/POST /finance/projects`, `GET/PATCH /finance/projects/{id}`, `GET /finance/budgets/summary`, `GET/POST /finance/budgets`, `GET/PATCH /finance/budgets/{id}` (includes ledger) |
| Procurement | `GET/POST /procurement/suppliers`, `GET /procurement/suppliers/categories`, `GET/PATCH /procurement/suppliers/{id}`, `GET/POST /procurement/requests`, `GET /procurement/requests/stats`, `POST /procurement/requests/budget-preview`, `GET/PATCH /procurement/requests/{id}`, `GET …/{id}/activity`, `POST …/{id}/submit`, `POST …/{id}/cancel`, `POST …/{id}/send-for-approval`, `POST …/{id}/quotations`, `PUT/DELETE …/{id}/quotations/{qid}`, `POST …/{id}/quotations/{qid}/select` |
| Approvals | `GET /approvals?box=pending\|decided\|mine\|all`, `GET /approvals/pending-count`, `GET /approvals/policies`, `GET /approvals/{id}`, `POST /approvals/{id}/approve`, `POST /approvals/{id}/reject` (comment required) |

Interactive docs: <http://127.0.0.1:8000/docs> (disabled in production).

## Tests & checks

```bash
cd apps/api
.venv/Scripts/python -m pytest          # unit + PostgreSQL integration (TEST_DATABASE_URL must end in _test)
.venv/Scripts/ruff check app tests alembic
.venv/Scripts/alembic check             # models and migrations in sync

cd apps/web
npm test && npm run typecheck && npm run lint && npm run build
```
