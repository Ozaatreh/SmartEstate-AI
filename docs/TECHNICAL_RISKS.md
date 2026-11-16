# SmartEstate AI — Technical Risk Assessment

Likelihood (L) and Impact (I): H / M / L.

| # | Risk | L | I | Mitigation |
|---|---|---|---|---|
| R1 | **72-hour delivery:** 11 modules is a lot of scope for the time | H | H | Strict phase order with demo-able increments; M/S/C priorities with a pre-agreed cut list (marketing studio, leave, digest, reservation expiry go first); a shared module template so each CRUD module is mechanical; 2 h buffer; no gold-plating of admin screens |
| R2 | **Scope creep** (dynamic workflows, real channels, accounting) | M | H | Out-of-scope list in the spec; any addition needs your approval and a matching cut |
| R3 | **Claude API availability / rate limits** during the demo | M | H | Kill switch + graceful "AI unavailable" UI; SDK retries; streaming; every non-AI flow works without AI; optional pre-recorded fallback answers for the demo script (clearly labelled) |
| R4 | **Claude API cost** (public endpoint abuse, long tool loops) | M | M | Daily cost cap checked before each call; per-visitor and per-IP rate limits; tool-call cap per turn; bounded history; prompt caching of stable system prompts/tools; per-feature model choice (D-4) |
| R5 | **No API key configured yet** (`ANTHROPIC_API_KEY` is empty in the only existing `.env`) | H | M | Build and test entirely against the fake client; real-API smoke test once a key is provided |
| R6 | **External API failures** in workflow steps | M | M | Transient/permanent classification, backoff retries, step resume, `on_error=continue` for advisory AI steps, admin retry button |
| R7 | **Financial data integrity** (double commit, float rounding, edited history) | M | H | `Decimal`/`NUMERIC`; append-only ledger with DB trigger; idempotency keys with UNIQUE; row locks on budget during check+commit; approval + commit in one transaction; concurrency tests |
| R8 | **Permission enforcement gaps** (UI-only checks, AI or workflow bypass) | M | H | Checks inside services (shared by REST, AI tools, workflows); system principal with minimal permissions; route-level tests for 401/403 per module; data scoping tests |
| R9 | **AI hallucination** (wrong prices, invented units, made-up KPIs) | H | M | Tools are the only data source; prompts require tool-grounded answers; numbers in UI come from tool results; property tools return only existing public units; marketing grounded on DB facts with human approval; "AI-generated" labels |
| R10 | **Prompt injection** (visitor or data text tries to make the agent act) | M | H | No tool can approve/post/pay; public tools are read-only + consented lead creation; permission checks outside the model; tool results marked untrusted; injection test cases |
| R11 | **Workflow execution failures** (stuck runs, duplicates, storms after downtime) | M | M | Outbox in the same transaction; `SKIP LOCKED`; idempotency keys; reaper for stale `running`; collapsed missed schedule slots; history UI |
| R12 | **In-process worker limits** (blocking the event loop, multiple uvicorn workers) | M | L | Run DB work in a thread; single uvicorn worker for the demo (documented); `SKIP LOCKED` keeps it safe if more run |
| R13 | **Environment:** Docker daemon not running; native PostgreSQL 18 on 5432 shared with other work | M | M | Use dedicated `smartestate` / `smartestate_test` databases and role; test suite refuses DB names not ending in `_test`; optional compose file on another port |
| R14 | **Confusion with the existing MADAR ERP project** in `D:\Projects` (uncommitted, similar stack) | M | M | Separate repository and database names; never modify `madar-erp`; recommend you commit MADAR's work so it is safe |
| R15 | **Personal data** (lead contact info sent to the model or logs) | L | M | Explicit consent capture; no PII in logs or usage rows; PII sent to Claude only inside the visitor's own conversation |
| R16 | **Demo data mistaken for real** | L | M | `is_demo_data` flag, "Fictional demo data" banner, fictional names/figures only |
| R17 | **Premium UI vs. 72 h:** a high design bar across 11 modules competes with feature scope | H | H | Build the design system and a `/_design` reference page first (Phase 1); feature pages only compose shared components; a UI quality gate in every phase's definition of done; cut S/C features before cutting UI quality |
| R18 | **Opus cost and latency** (Opus by default for every agent, including the public assistant) | M | M | Per-agent `effort` tuning; streaming; prompt caching; tool-call caps; daily cost cap; per-agent model override in `.env` if needed, with no code change |
| R19 | **Model ID changes or retirement** | L | M | ID only in config/env; startup Models API check; `claude-opus-5-5` retirement is not before 22 Sep 2027 (official models page, checked 2026-11-16) |
| R20 | **Imagery licensing** for a fictional project | L | M | Freely licensed or user-supplied images only, credited, labelled "Illustrative image" (D-14) |
