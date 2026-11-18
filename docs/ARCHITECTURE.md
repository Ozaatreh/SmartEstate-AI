# SmartEstate AI — Architecture

> Status: **Phase 0 draft, awaiting approval.** The confirmed stack is fixed: React + TypeScript,
> Tailwind + shadcn/ui, FastAPI, PostgreSQL, SQLAlchemy, Alembic, the Claude API, and a custom Python
> automation engine. Anything this document adds beyond that is listed in
> [§ 11](#11-decisions-requiring-approval).

## 1. High-level system

```
 Browser (React SPA)                         FastAPI process (modular monolith)
 ┌───────────────────────┐   HTTPS/JSON    ┌───────────────────────────────────────────────┐
 │ Internal app (auth)   │ ──────────────▶ │ API routers (/api/v1/...)  thin: validate→call │
 │ Public property chat  │ ◀── SSE stream ─│ Services  (business rules, permissions, tx)    │
 └───────────────────────┘                 │ Repositories (SQLAlchemy queries, no commit)   │
                                           │ Automation Engine  ◀─ outbox events / schedule │
                                           │   └─ background worker loop (in-process)       │
                                           │ AI Gateway ──────────────────────────────┐     │
                                           └───────────────┬──────────────────────────┼─────┘
                                                           │ SQLAlchemy (psycopg 3)   │ HTTPS
                                                    ┌──────▼──────┐          ┌────────▼────────┐
                                                    │ PostgreSQL  │          │ Anthropic API   │
                                                    └─────────────┘          └─────────────────┘
```

- **Three deployables, one repository (Phase 7A):** `apps/marketing` (public website, Vite SPA), `apps/dashboard`
  (internal system, Vite SPA) and `apps/api` (FastAPI, shared by both). The marketing app reaches only
  `/api/v1/public/*`; the API enforces the boundary itself (public schemas; every other route needs a session).
- **One backend process** serves the API and runs the automation worker as a background task
  started in FastAPI's lifespan. There is no broker. PostgreSQL is the queue (see § 6).
- The frontend never calls Anthropic. All AI goes through the backend AI Gateway.

### Repository layout (proposed)

```
smartestate-ai/
├── apps/
│   ├── api/
│   │   ├── app/
│   │   │   ├── main.py              app factory, lifespan (starts the worker)
│   │   │   ├── core/                config, security, permissions, errors, logging
│   │   │   ├── db/                  base, session, mixins
│   │   │   ├── modules/
│   │   │   │   ├── identity/        users, roles, permissions, auth
│   │   │   │   ├── audit/
│   │   │   │   ├── notifications/
│   │   │   │   ├── hr/
│   │   │   │   ├── finance/
│   │   │   │   ├── procurement/
│   │   │   │   ├── approvals/
│   │   │   │   ├── realestate/
│   │   │   │   ├── crm/
│   │   │   │   ├── marketing/
│   │   │   │   └── dashboard/       read-only aggregation
│   │   │   ├── automation/          engine (see AUTOMATION_ENGINE.md)
│   │   │   │   └── workflows/       predefined workflow definitions
│   │   │   ├── ai/                  gateway, tools, prompts, features (bi, property, marketing)
│   │   │   └── seed/                RBAC catalogue, NOVA demo data
│   │   ├── alembic/
│   │   └── tests/{unit,integration}
│   └── web/
│       └── src/{app,components/{ui,common,layout,charts},features/<module>,lib,hooks,types}
├── docs/
├── .env.example
└── README.md
```

Each backend module has the same internal shape:

```
modules/<name>/
  models.py       SQLAlchemy models (owned tables)
  schemas.py      Pydantic request/response models
  repository.py   queries only, never commits
  service.py      business rules, permission checks, transaction boundary, event emission
  router.py       FastAPI routes: parse → call one service method → return schema
  events.py       event type constants this module emits
```

## 2. Frontend architecture

UI/UX quality is a **core requirement** (see [UI_UX_DESIGN.md](UI_UX_DESIGN.md) for the design system).

- **React 19 + TypeScript + Vite**, **Tailwind CSS + shadcn/ui**.
- **Proposed supporting libraries** (standard companions, not new infrastructure; approval D-12):
  React Router (routing), TanStack Query (server state and caching), TanStack Table (headless
  sorting/filtering/pagination under the shared `DataTable`), React Hook Form + Zod (forms),
  Recharts (charts), lucide-react (icons, ships with shadcn), Sonner (toasts, the shadcn default),
  self-hosted fonts via `@fontsource` (no runtime calls to font CDNs).
- **Layered UI code:**
  ```
  src/
    styles/tokens.css        design tokens as CSS variables (semantic names; light now, .dark later)
    components/ui/           shadcn/ui primitives, themed by tokens (owned source, not a dependency)
    components/system/       SmartEstate design-system components built on ui/: AppShell, Sidebar,
                             PageHeader, DataTable, FilterBar, StatusBadge, KpiCard, ChartCard,
                             EmptyState, ErrorState, LoadingSkeleton, FormField, MoneyText,
                             ConfirmDialog, AiBadge, ChatPanel, ToolResultCard
    components/layout/       experience shells: OpsLayout, ExecutiveLayout, ShowcaseLayout (property),
                             StudioLayout (marketing), PublicLayout (visitor assistant)
    features/<module>/       api.ts (query hooks), schemas.ts (Zod), components/, pages/
  ```
  Feature pages compose `components/system` and never style primitives ad hoc. That keeps
  modules consistent and makes a dark theme a token change only.
- **Feature folders:** `src/features/<module>/{api.ts, schemas.ts, components/, pages/}`.
  `api.ts` holds TanStack Query hooks that call a single `lib/api-client.ts`.
- **List endpoints** support server-side `search`, `filter[...]`, `sort`, `page`, `page_size` and return
  `{items, total, page, page_size}`, so `DataTable` behaves the same across modules.
- **Responsive:** desktop ≥ 1280 (full sidebar), tablet 768–1279 (collapsed icon rail), mobile < 768
  (off-canvas sheet navigation; tables collapse to stacked rows; primary actions in a bottom bar).
- **No business logic in components.** Components render data and call hooks. Totals, statuses
  and allowed actions come from the API. The backend returns `allowed_actions` per document,
  and the UI renders only those buttons.
- **Permissions in the UI are for usability only:** `useCan("procurement.requests.approve")` hides
  controls. The backend is the enforcement point.
- **Money:** amounts arrive as decimal strings and are formatted, never computed with floats.
- **AI UI:** streamed chat (SSE via `fetch` + `ReadableStream`), a "tools used" panel, an
  "AI-generated" badge, and model output rendered as safe Markdown (no raw HTML).
- **Public area:** `/explore/nova` (property assistant + unit browser) needs no sign-in and uses a
  separate, minimal API surface.

## 3. Backend architecture

### 3.1 Modular monolith rules
1. A module owns its tables. Only its repository writes them.
2. Modules call **each other's services**, never each other's repositories or models.
   Example: procurement calls `finance.BudgetService.check_availability()` and
   `approvals.ApprovalService.open_request()`.
3. Cross-module side effects that do not need to be in the same transaction go through
   **events** handled by the automation engine (for example, notify an approver).
   Effects that must be atomic (final purchase-request approval → budget commitment, D-16; PO cancel → release) are direct service calls inside
   one transaction.
4. Dependencies point one way (see § 9). Shared kernels (`core`, `db`, `identity`, `audit`,
   `notifications`) depend on no business module.

### 3.2 Request flow
`router` → `Depends(current_principal)` → `service.method(principal, payload)` →
`ensure_permission(principal, "<module>.<action>")` → business rules → repositories → emit
outbox events → `audit.record(...)` → `commit` → response schema.

### 3.3 Error handling
- Domain exceptions in `core/errors.py`: `NotFound`, `PermissionDenied`, `ValidationFailed`,
  `Conflict`, `BusinessRuleViolation`, `ExternalServiceUnavailable`.
- Global handlers map them to HTTP codes and one body shape:
  `{"error": {"code": "budget_insufficient", "message": "...", "request_id": "...", "details": {...}}}`.
- Unexpected exceptions → 500 with a generic message. The stack trace goes only to the log.
- Pydantic validation errors → 422 in the same shape.

### 3.4 Logging
- Python `logging` with a JSON formatter. Middleware assigns a `request_id`, which is in every log line
  and response header (`X-Request-ID`).
- Workflow logs carry `execution_id` and `step`. AI logs carry `feature`, `model`, tokens and latency,
  never prompt content containing personal data, and never keys.
- A redaction filter for keys named `password|token|secret|api_key|authorization`.

### 3.5 Configuration
`pydantic-settings` reads `.env`. Everything is configurable: database URL, JWT secret, CORS origin,
`AI_ENABLED`, `ANTHROPIC_API_KEY`, model per feature, AI daily cost cap, worker poll interval,
approval thresholds come from the database (policies), not env. Startup refuses placeholder
secrets outside `development`/`test`.

## 4. Database architecture

- PostgreSQL (version ≥ 16; the machine has 18). One database `smartestate`, plus
  `smartestate_test` for integration tests. Single `public` schema; table names are prefixed
  only where needed for clarity (`wf_*`, `ai_*`).
- SQLAlchemy 2.0 typed models; Alembic migrations are the **only** way the schema changes
  (tests build their schema by running migrations).
- Conventions: UUID primary keys (D-6), `created_at`/`updated_at timestamptz`, `NUMERIC(18,2)` money,
  status columns as `VARCHAR` + `CHECK`, soft deactivation (`is_active`) for master data,
  append-only ledgers and history tables.
- Full table design: [DATABASE_DESIGN.md](DATABASE_DESIGN.md).

## 5. Authentication and RBAC

- **Authentication (D-2):** email + password (Argon2id). On sign-in the API sets a signed JWT
  (8 h, contains `sub`, `sid`, `token_version`) in an **HttpOnly, SameSite=Lax** cookie. Mutating
  requests also need a custom header `X-Requested-With` (CSRF defence for cookie auth).
  Sign-out and deactivation increment `users.token_version`, which invalidates existing tokens.
  No refresh-token rotation in the prototype (it is a documented hardening step).
- **Principal:** `Principal(user_id, permissions: frozenset[str], employee_id, department_id)` is
  loaded once per request from the database (not trusted from the token), so permission changes
  apply immediately.
- **RBAC:** permission codes `<module>.<resource>.<action>` are declared in one Python catalogue and
  seeded to the database. Roles and grants are data. Services call `ensure_permission()`.
  **Data scoping** is in services as well: a Sales Agent sees `leads.owner_id = me` unless they
  hold `crm.leads.read_all`; a Department Manager sees their department's requests.
- **Segregation of duties:** the approval service rejects decisions by the requester, and the
  same person cannot approve two steps of one request.
- **Public visitors:** an anonymous `visitor_session` id (random, stored in a cookie) identifies
  a property assistant conversation. It carries no permissions beyond the public tools.

## 6. Automation engine (summary)

Full design: [AUTOMATION_ENGINE.md](AUTOMATION_ENGINE.md).

- Services write **events** to `automation_events` inside their own transaction (transactional outbox).
- A **worker loop** (asyncio task in the API process) claims events with
  `SELECT … FOR UPDATE SKIP LOCKED`, finds matching workflows, evaluates conditions, and runs
  steps through registered **actions** that call services.
- A **scheduler** in the same loop fires schedule triggers (for example every 15 min: overdue lead
  follow-ups, expiring reservations).
- Every run is a `wf_executions` row with `wf_step_executions`. It is idempotent per
  (workflow, version, event), retried with backoff on transient errors, and visible in the UI.
- Workflows are Python classes registered in code. Their enable flag and parameters live in
  `wf_definitions` so they can change without a deploy, which is also the first step toward a dynamic engine.

## 7. Claude API integration

### 7.1 Components
```
ai/
  gateway.py        the only module that imports `anthropic`; client, retries, timeouts,
                    kill switch, cost cap, usage logging, fake client for tests
  tools/            tool registry: name, description, strict JSON schema, required permission,
                    audience (internal|public), handler → calls a service
  features/
    bi_agent.py     internal chat, tool loop, streaming
    property.py     public chat, public tools only, lead capture
    marketing.py    structured content generation
    digest.py       daily KPI narrative
  prompts/*.md      byte-stable system prompts (good for prompt caching)
```

**As built (Phase 6A).** The gateway is split by responsibility, and only one file imports the SDK (enforced by
`tests/test_unit_ai.py`):

```
ai/
  config.py      capabilities → ModelProfile (model, effort, max_tokens); limits; price table — the only place
                 model IDs appear in app/
  provider.py    the ONLY importer of `anthropic`: one Messages request (adaptive thinking, explicit effort,
                 server-side refusal fallback on current models, structured output via `beta.messages.parse`),
                 response-shape validation, SDK exception → AIError category; no tools, no DB access
  gateway.py     AIGateway: kill switch, input validation, daily cost cap (fail-closed), stop-reason handling,
                 usage tracking, availability (disabled | misconfigured | unverified | operational | degraded)
  errors.py      AIError categories → 503 + safe code/message (never provider bodies, prompts or keys)
  models.py / repository.py   `ai_usage` (append-only, metadata only)
  router.py      GET /ai/status · GET /ai/gateway · GET /ai/usage · POST /ai/health-check
  smoke.py       opt-in real-API smoke test (`python -m app.ai.smoke`)
```

**As built (Phase 6C).** `provider.py` also streams a tool-using turn (`stream_turn`: strict tools, `eager_input_streaming`,
adaptive thinking, refusal fallback) but never runs a tool. `gateway.stream_turn` applies the same kill switch, cost cap,
refusal handling and usage row per model call. `tools/registry.py` validates, permission-checks, runs and records tools;
`tools/internal.py` (BI, read-only) and `tools/public.py` (visitor, public fields + consent-gated lead capture).
`chat.py` is the shared streamed tool loop (≤ 8 tool calls per question; a turn is stored only when complete).
`features/bi_agent.py` (`/ai/bi/*`) and `features/property_assistant.py` (`/public/assistant/*`) stream server-sent events
(`start · text · tool · done | error`). Prompts are inline constants rather than `prompts/*.md`.

### 7.2 Request shape (by feature)
| Feature | Pattern | Notes |
|---|---|---|
| BI agent | Messages API + tool use (manual loop or SDK tool runner), streamed | Read-only tools; max 8 tool calls per turn; tool results wrapped as untrusted data |
| Property assistant | Messages API + tool use, streamed | Public tools only (`search_units`, `get_unit`, `get_payment_plans`, `get_project_info`, `create_lead_with_consent`) |
| Marketing studio | Single call with **structured outputs** (`client.messages.parse` + Pydantic schema) | Grounded on project facts passed in the prompt; result saved as a draft |
| Daily digest | Single call; input = computed KPI JSON | Output is narrative only; numbers are shown from the KPI data, not from the text |

### 7.2a Model strategy (D-4: approved, Opus by default)

- **Default model: Claude Opus 5.5, `claude-opus-5-5`.** Verified on 2026-11-16 against Anthropic's
  official models overview (platform.claude.com/docs/en/models/overview): it is the current Opus
  model, a pinned (dateless) snapshot, with a 1M context window, 128K max output and a retirement
  date no sooner than 22 Sep 2027.
- **One place for model selection:** `app/ai/config.py` defines a `ModelProfile` per AI feature
  (agent):
  ```python
  class ModelProfile(BaseModel):
      model: str          # from env, never a literal elsewhere
      effort: Literal["low", "medium", "high", "xhigh", "max"]
      max_tokens: int
      stream: bool
  # features: bi_agent, property_assistant, marketing_studio, lead_summary, daily_digest
  ```
  Resolution order: `AI_MODEL_<FEATURE>` (e.g. `AI_MODEL_PROPERTY_ASSISTANT`) → `AI_DEFAULT_MODEL`
  → startup error. `.env.example` sets `AI_DEFAULT_MODEL=claude-opus-5-5`; per-feature effort
  (`AI_EFFORT_<FEATURE>`) is also env-driven, defaulting to `high` for the BI agent and marketing and `medium` for
  the property assistant and summaries.
- **Business services never see a model ID.** They call feature functions
  (`ai.features.marketing.generate(...)`), and only `ai/gateway.py` reads the profile and calls the SDK.
  Changing a model, or giving one agent a different model, is an `.env` change with no code change.
- **No hard-coded model IDs:** a unit test fails if the string `claude-` appears in `app/` outside
  `ai/config.py` defaults or in `apps/dashboard` / `apps/marketing` at all.
- **Model check (as built, Phase 6A):** startup makes **no** network call (a provider outage must never affect startup).
  The token-free check — `client.models.retrieve` for each configured model — runs on demand through
  `POST /ai/health-check` (permission `ai.gateway.manage`) or `python -m app.ai.smoke`. A valid configuration is reported as
  `unverified` until a real request or check succeeds; availability is derived from the latest outcome in `ai_usage`.
- **Opus 5.5 specifics to respect:** thinking cannot be disabled (adaptive is always on; depth is set
  by `effort`, which defaults to `medium`, so set it explicitly); forced `tool_choice`
  (`any`/`tool`) returns 400; the server-side refusal fallback is enabled; thinking blocks are passed back
  unchanged within a conversation.

- **Current API specifics to respect (all features):** adaptive thinking with an explicit
  `output_config.effort` from the feature profile; forced `tool_choice`
  (`any`/`tool`) is rejected on current models, so use `auto` + `strict: true` tools + prompt
  instructions; no assistant prefill; check `stop_reason` (including `refusal`) before reading
  content; enable the server-side refusal fallback on current models; stream long
  replies; keep system prompts and tool lists byte-stable for prompt caching.
- **Tool calls** with streaming set `eager_input_streaming: true` and **validate every tool input
  with Pydantic** before running it.

### 7.3 Safety boundaries (non-negotiable)
1. Claude has no database access and no SQL. Tools are fixed functions with typed inputs.
2. Every tool runs under the **caller's principal** and checks its required permission. Public tools
   run under a fixed "visitor" principal with only public fields.
3. **No tool approves, rejects, posts, pays or changes financial data.** AI may create
   *drafts* (marketing content) or *advisory* records (lead summary). A person acts on them.
4. Identity and permissions come from the authenticated session, never from model output or prompt text.
5. Tool results are passed as data. The system prompt tells the model to ignore instructions
   inside them, and security never depends on the prompt.
6. Output rendering is safe Markdown only.
7. The API key stays in backend env. It is never returned, logged or stored.

### 7.4 Cost, availability, fallback
- `AI_ENABLED` kill switch (default `false` until a key is configured); `DisabledClient` raises
  `ExternalServiceUnavailable` → the UI shows "AI unavailable" and non-AI features keep working.
- SDK retries (429/5xx/connection, max 2) and a per-request timeout (60 s; streaming for chats).
- `ai_usage` row per call (tokens, estimated cost). A **daily cost cap** and per-visitor message cap
  are checked before each call. Public endpoint rate limit per IP + session.
- Tests use a scripted **fake client**; CI never calls the real API.

## 8. Security architecture

| Threat | Control |
|---|---|
| Broken access control | Permission checks in services (covers REST, AI tools, workflows); data scoping; tests for 403 paths |
| Privilege escalation | Users can grant only permissions they hold; Super Admin role protected |
| CSRF on cookie auth | SameSite=Lax + required custom header on mutating requests; strict CORS origin |
| XSS | React escaping; safe Markdown renderer for AI output; no `dangerouslySetInnerHTML` |
| Injection | SQLAlchemy parameterised queries; no raw SQL from input; Claude has no SQL |
| Prompt injection | Tools are read-only/draft-only; permission checks outside the model; tool results marked untrusted; visitor tools expose public fields only |
| Secrets exposure | Env only; redaction filter; `.env` git-ignored; key never sent to frontend |
| Brute force / abuse | Sign-in throttling per account + IP; public assistant rate limit + cost cap |
| Financial tampering | Ledger append-only (DB trigger blocks UPDATE/DELETE); approvals and commits in one transaction with row locks |
| Personal data | Visitor consent recorded with the lead; leads visible only to permitted users; no personal data in logs |

## 9. Module dependencies

```
core, db ──▶ identity ──▶ audit, notifications
                 │
     ┌───────────┼──────────────┬───────────────┬───────────────┐
     ▼           ▼              ▼               ▼               ▼
    hr ──▶ finance ◀── procurement          realestate ──▶ crm ──▶ marketing
     │         ▲            │                  ▲            │
     └──▶ approvals ◀───────┘ (and expenses, leave, marketing content)
                 ▲
 automation ─────┴── calls module services through registered actions (depends on all; nothing depends on it except via events)
 ai ─────────────── calls module services through tools (read/draft only)
 dashboard ──────── read-only queries over module services
```

- `approvals` knows nothing about procurement. It stores `(entity_type, entity_id)`, and each
  approvable module registers a small **ApprovalSubject** adapter (load amount/requester, apply decision).
  This keeps the dependency pointing from business modules to approvals.
- `automation` and `ai` sit at the top: they may call any service; business modules never import them.
  Modules only write events.

## 10. Future extensibility

- **Dynamic workflow engine:** definitions move from Python classes to versioned JSON in
  `wf_definitions`; the trigger/condition/action contracts stay the same (see AUTOMATION_ENGINE.md § 11).
- **Scale-out worker:** the worker loop can move to a separate process unchanged (it already uses
  `SKIP LOCKED`); later a broker can replace the outbox poller behind the same interface.
- **Real channels:** a `NotificationChannel` interface (in-app now; email/SMS/WhatsApp later).
- **MCP server:** the AI tool registry is designed so the same tools can later be served over MCP.
- **Multi-project / multi-company:** `project_id` already on real estate, CRM and marketing tables;
  adding `company_id` is an additive migration.
- **Refresh-token rotation, MFA, SSO:** auth module boundary allows replacing the cookie session.

## 11. Decisions requiring approval

| ID | Decision | Recommendation | Why it needs you |
|---|---|---|---|
| D-1 | Where SmartEstate lives, and whether to reuse MADAR ERP code | New repo `D:\Projects\smartestate-ai`; write it fresh, borrowing *patterns* (layering, RBAC catalogue, error shape, AI tool executor) but not copying modules | The assessment may require original work; MADAR is a different product (construction ERP) and is uncommitted |
| D-2 | Auth mechanism | JWT in HttpOnly cookie (8 h) + CSRF header + `token_version` revocation; no refresh rotation | Simpler than production-grade sessions; trade-off to accept |
| D-3 | Async execution | In-process asyncio worker over a PostgreSQL outbox; no Redis/Celery | Adds no infrastructure; limits throughput (fine for a demo) |
| D-4 | Claude model per feature | **Approved:** Opus (`claude-opus-5-5`, verified) by default; per-feature env override; IDs only in config (§ 7.2a) | Resolved |
| D-5 | Public property assistant | Unauthenticated page with rate limits, cost cap and consent-based lead capture | Exposes a public, cost-bearing endpoint |
| D-6 | Primary keys | UUID (`gen_random_uuid()`) | No guessable ids on the public surface; slightly larger indexes |
| D-7 | PostgreSQL runtime | Native PostgreSQL 18 already listening on 5432 (Docker daemon is not running); provide an optional `docker-compose.yml` on 5434 | Which one you will use for the demo |
| D-8 | Over-budget requests | Allow submission, flag `over_budget`, require Finance Manager **and** Executive approval | Alternative is a hard block |
| D-9 | Language | English UI; AI replies in the visitor's language; marketing content EN + AR | Full RTL is out of scope |
| D-10 | Notifications | In-app only (plus a dev "outbox" log) | No real email/SMS |
| D-11 | Approval thresholds (fictional, SAR, editable data) | ≤ 50,000: department manager · 50,000–250,000: + finance manager · > 250,000: + executive | Business values |
| D-12 | Frontend companions | Vite, React Router, TanStack Query, TanStack Table, React Hook Form + Zod, Recharts, Sonner, `@fontsource` fonts | Not in the confirmed list, though standard |
| D-13 | Demo hosting | Local only (README + demo script) | If the assessor needs a hosted URL, plan changes |
| D-14 | Property imagery for fictional NOVA Residences | Freely licensed architectural stock photos (Unsplash licence), stored locally in the repo, each labelled "Illustrative image"; you can swap in your own renders | Real photos of real buildings would misrepresent a fictional project; downloading assets needs your OK |
| D-15 | Visual identity | "Najd" palette (ink navy + desert-clay accent + a restrained AI violet), Inter for UI, Fraunces for property display headings, IBM Plex Sans Arabic for Arabic content (UI_UX_DESIGN.md § 2) | Brand taste is yours |
| D-16 | Where the budget commitment happens (**approved before Phase 4 — deliberate deviation**) | Commit once at the purchase request's **final approval** (built in Phase 2), not at PO approval. POs (`draft → issued → cancelled`) have no approval chain and never commit; cancelling one either releases the request's commitment exactly once (ledger key `purchase_request:<id>:release`) and closes the request, or keeps it for a replacement PO | Resolved: avoids a second approval chain and a duplicate commitment; existing approved requests keep their commitments untouched |
| D-17 | Phase 5 decisions (**approved before Phase 5**: C1–C5, D1–D3) | C1 keep workflow key `crm.lead_registration` (implements `crm.new_lead`); C2 add timeline + budget-fit scoring without re-scoring existing leads; C3 round-robin pool = project code (else `default`); C4 no AI in Phase 5; C5 real-estate projects stay separate from finance projects (`/realestate`); D1 permissions `realestate.inventory.read` (all staff), `realestate.inventory.manage` and `crm.leads.manage` (sales manager), `crm.reservations.manage` (agent: own leads; manager: all); D2 additive idempotent fictional seed (1 project, 2 buildings, 20 units, 2 plans); D3 stage transitions forward / lost from open / reopen from lost, 72 h default reservation, informational deposit | Resolved |
