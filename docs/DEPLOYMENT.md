# Deploying SmartEstate AI for $0

Status: **prepared and tested locally, not yet deployed** — deployment needs the owner's own (free) accounts.
Every service below is used on its free plan; no payment details are needed for the parts described, and nothing
here should ever be upgraded. If any platform asks for payment or an upgrade, stop.

## Architecture

```
Visitor ─► smartestate-website.pages.dev   (Cloudflare Pages, free)
             static React site + Pages Function: /api/v1/public/* ─┐
Staff   ─► smartestate-dashboard.pages.dev (Cloudflare Pages, free) │   same-origin proxy (first-party cookies,
             static React app  + Pages Function: /api/*  ───────────┤   no CORS, no internal API on the website)
                                                                    ▼
                      smartestate-api.onrender.com  (Render free Docker web service)
                      ├─ start: alembic upgrade head → app.seed (demo data once) → worker → uvicorn
                      ├─ FastAPI API
                      └─ automation worker (second process, auto-restarts; PostgreSQL queue unchanged)
                                         │ TLS
                                         ▼
                      Neon PostgreSQL (free)                 Anthropic API — off unless a key is added
Optional: smartestate-keepalive (Cloudflare Worker cron, free) pings /api/v1/health every 10 min, 08:00–20:00 Riyadh
```

Files: `render.yaml` (API), `apps/api/Dockerfile` + `apps/api/deploy/start.sh`, `apps/*/functions/` (Pages
Functions proxies), `apps/*/public/_headers` (security headers), `infrastructure/cloudflare/keepalive/`.

### Why the worker is genuinely free and unchanged
Render's free plan has no background-worker type, so the existing worker runs as a **second process inside the API
container** and restarts itself if it exits. The job queue, `FOR UPDATE SKIP LOCKED` claiming, leases, retries with
backoff and idempotency keys are exactly the same code; only the process placement differs. The trade-off: when the
free instance sleeps, the worker sleeps too. Jobs are not lost — they stay in PostgreSQL and run on wake; schedules
(SLA checks, reservation expiry, every 15 min) catch up.

## Free-plan limits (checked Nov 2026)

| Service | Free limit | Effect here |
|---|---|---|
| Render web service | 750 instance-hours/month per workspace, 512 MB RAM, sleeps after 15 min without requests, ~1 min wake | First visit after a pause is slow; one always-on service would fit in 750 h |
| Neon | 100 CU-hours/month per project (≈ 400 h at 0.25 CU), 1 GB storage, scales to zero after 5 min idle | The worker polls the DB while the API is awake, so the DB is active whenever the API is. 24/7 would need ≈ 182 CU-hours → **too much**; the keep-alive is limited to 12 h/day (≈ 90 CU-hours). Set Neon's max autoscaling to 0.25 CU. If the monthly quota is used up, Neon suspends the compute until the next month (data is kept). |
| Cloudflare Pages | Static requests free/unlimited; Pages Functions share the Workers Free quota (100,000 requests/day, 10 ms CPU each) | Only `/api` calls count; the proxy uses almost no CPU |
| Cloudflare Workers cron | Included in Workers Free | ~72 pings/day |
| Storage | Render free has **no persistent disk** | Lost on every restart/redeploy: dashboard image uploads (`var/media`), uploaded 3D model files (`var/models`), brochure-only images. The website's 3D villa and images are in the static build and always available. |

## Steps (owner)

1. **GitHub** — push the repository to a **private** repo. Render and Cloudflare get read access via their GitHub apps.
2. **Neon** — create a project, set autoscaling to a fixed 0.25 CU, and copy the **pooled** connection string as-is
   (`postgresql://…?sslmode=require` is accepted and mapped to the psycopg driver). Deploy Render in the same region
   (this deployment: AWS US East 2 / Render "ohio").
3. **Render** — New → Blueprint → the repo → `render.yaml` (Free plan). Enter `DATABASE_URL` and
   `SEED_DEMO_PASSWORD` (≥ 12 characters, shared privately with evaluators). Leave `ANTHROPIC_API_KEY` empty and
   `AI_ENABLED=false` unless a key is deliberately added (cost cap `AI_DAILY_COST_CAP_USD=1`). Wait for
   `https://smartestate-api.onrender.com/api/v1/health` → `"database":"ok"`. If the hostname differs, use it below.
4. **Cloudflare Pages — website**: Create → Pages → connect the repo. Root directory `apps/marketing`, build
   `npm ci && npm run build`, output `dist`. Environment variables: `API_ORIGIN=https://smartestate-api.onrender.com`
   (used by the Function at runtime), `VITE_DASHBOARD_URL=https://smartestate-dashboard.pages.dev`,
   `VITE_GOOGLE_MAPS_API_KEY` (browser key restricted to the website URL), `VITE_GOOGLE_MAPS_MAP_ID=DEMO_MAP_ID`,
   `VITE_GOOGLE_MAPS_STREET_VIEW=disabled`, `NODE_VERSION=22`.
5. **Cloudflare Pages — dashboard**: root `apps/dashboard`, same build/output, `API_ORIGIN` as above, `NODE_VERSION=22`.
6. **Optional keep-alive** — `cd infrastructure/cloudflare/keepalive && npx wrangler deploy` (Workers Free).

Demo data: with `APP_ENV=staging` and `SEED_DEMO_DATA=true` the first boot creates the fictional demo accounts
(all with `SEED_DEMO_PASSWORD`) and the fictional NOVA organisation; later boots skip it, so restarts never re-create
data evaluators changed. `SEED_DEMO_DATA` is refused when `APP_ENV=production`.

## After the first boot (owner, in the dashboard — audited, no code)
The demo seed creates NOVA **unpublished** (as in development). Sign in as the demo Super Admin and, in
Property Portfolio → NOVA → Edit project: tick "Published on the marketing website"; optionally set the illustrative
map point (e.g. Kingdom Centre, Riyadh — 24.711389, 46.674439, labelled as a reference point, not the property).

## Verification checklist
* Website pages, NOVA (3D viewer, illustrative map), Arabic, dark mode; contact form with fictional details.
* `https://smartestate-website.pages.dev/api/v1/realestate/projects` returns the website HTML (never API JSON);
  the same path on the dashboard origin returns 401.
* Dashboard sign-in as Super Admin and as Sales Agent (RBAC difference visible); purchase request → approvals →
  PO; Automation → executions show the runs; Audit log records the actions.
* Health: `"environment":"staging","database":"ok"`; AI shows "disabled" unless configured.
* Secrets: none in the repo (`.env` ignored), the Docker image, or the static builds (only the restricted Maps browser
  key, by design).
