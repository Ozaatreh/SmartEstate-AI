# Security, governance and reliability

Every control below is implemented in the code; file references point to where it lives.

## 1. Identity and sessions
* Passwords hashed with **Argon2** (`app/core/security.py`); minimum length 12.
* Session = signed JWT in an **HttpOnly** cookie, `SameSite=Lax`, scoped to `/api`, `Secure` outside development;
  the server refuses to start in staging/production with a weak `SECRET_KEY` or insecure cookies (`app/core/config.py`).
* **Lockout**: 5 failed sign-ins lock the account for 15 minutes; per-IP failure throttling as well.
* **CSRF**: every mutating `/api` request must carry `X-Requested-With: XMLHttpRequest` (`CsrfHeaderMiddleware`);
  with SameSite cookies and CORS this blocks cross-site requests.

## 2. Authorization (enforced on the server)
* Role-based access control with a central permission catalogue (`app/core/permissions.py`); services call
  `ensure_permission` on every operation — frontend hiding is only convenience.
* Ownership rules where it matters (e.g. sales agents see their own leads).
* `tests/test_public_api.py` walks the **entire route table**: only an explicit allowlist of `/api/v1/public/*`
  endpoints is reachable without signing in, and public responses use dedicated public schemas (no internal fields).

## 3. Approvals and financial controls
* Multi-level approval routing with **self-approval blocked** and separation between requester and approvers.
* Budget validation before commitment; purchase orders commit, release or replace budget **inside one transaction**
  with row locks (`SELECT … FOR UPDATE`).
* **Decimal** money end-to-end (NUMERIC in PostgreSQL, `Decimal` in Python, strings in JSON) — never floats.
* Append-only **budget ledger** and **audit log** (database-level protection in the migrations); every significant
  change is audited with actor, entity and field-level diff.
* Idempotency keys and unique constraints prevent double submission and double execution.

## 4. Automation reliability
* Jobs live in PostgreSQL; workers claim with `FOR UPDATE SKIP LOCKED`, hold **leases**, retry transient errors with
  exponential backoff and jitter, and fail permanent errors at once; every step and log is kept (execution history).
* Business events are written in the same transaction as the change that caused them (outbox pattern).

## 5. AI governance
* All model calls go through one **AI Gateway** (`app/ai`): model names live only in `app/ai/config.py`, every call is
  logged in `ai_usage` with cost, a **daily cost cap** applies, and `AI_ENABLED=false` is a global **kill switch**;
  if AI is misconfigured the rest of the application keeps working.
* AI agents use **read-only tools** that re-check the signed-in user's permissions; they cannot approve, post or change
  financial records (FR-10). Prompt-injection tests confirm no state change.
* The public assistant sees only public fields; a lead is created only when the visitor ticks the consent box
  (taken from the request, never from model output). Marketing AI generation is switched off by a separate flag.

## 6. Data and secrets
* Secrets only in the git-ignored `.env` (locally) or the host's secret store; never sent to the browser, API responses
  or logs (`tests/test_unit_ai.py::test_secrets_never_leak_through_errors_logs_or_config`).
* The Google Maps browser key is the only key in frontend code by nature; it must be restricted to the site's domain.
* Fictional demo data is flagged (`is_demo_data`) and labelled on every public page; demo accounts are created only in
  development/test.

## 7. Input, uploads and public forms
* Pydantic validation with `extra="forbid"` on write schemas; consistent error envelope without stack traces.
* Uploads (images, 3D models) are read with a hard size cap, validated by **file signature** (not name), stored under
  random names, and never served by path; uploaded images become public only after approval with source and licence.
* Public inquiry form: per-IP and per-contact **rate limits**, a timed form token and a hidden honeypot field.
