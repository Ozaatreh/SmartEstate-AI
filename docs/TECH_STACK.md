# Technology stack

Versions are those installed in the working tree on 18 Nov 2026 (`package.json`, `pyproject.toml`, the API virtualenv).

| Layer | Technology | Where / why |
|---|---|---|
| Internal dashboard | React 19, TypeScript 6, Vite 8, Tailwind CSS 4 | `apps/dashboard` — staff app (operations, real estate, CRM, approvals, automation, marketing, AI) |
| UI primitives | Radix UI + class-variance-authority (shadcn/ui pattern), lucide-react icons, sonner toasts | Accessible dialogs, menus, selects, tabs |
| Data & forms | TanStack Query 5, TanStack Table 8, React Hook Form 7 + Zod 4 | Server state, tables, validated forms |
| Charts | Recharts 3 | Budgets and dashboards (theme-aware colours) |
| Routing | React Router 7 | Both frontends |
| Public website | React 19, TypeScript, Vite, Tailwind CSS 4 | `apps/marketing` — projects, units, viewing requests, assistant; English/Arabic (RTL), light/dark |
| 3D | three.js 0.181, React Three Fiber 9, Drei 10 | Interactive property viewer (lazy-loaded); GLB built with Blender 5.3 (`assets/3d/smartestate-villa`) |
| Maps | Google Maps JavaScript API (Maps Demo Key) | Map rendering works; Street View disabled (requires billing) — see `docs/MAPS.md` |
| API | Python 3.14 (3.12+ supported), FastAPI 0.163, Pydantic 2.14, uvicorn 0.54 | `apps/api` — modular monolith: route → service → repository |
| ORM & migrations | SQLAlchemy 2.1, Alembic 1.20 (15 migrations) | Exact NUMERIC money, CHECK constraints, row locks |
| Database | PostgreSQL 18 (16+ supported), psycopg 3.3 | Also the automation job queue |
| Automation | Custom Python engine + worker (`app/automation`) | PostgreSQL-backed queue, `FOR UPDATE SKIP LOCKED`, leases, retries with backoff, execution history |
| AI | Anthropic Claude via official SDK `anthropic` 2.9, central AI Gateway (`app/ai`) | Capability-based model config, usage/cost logging, daily cost cap, kill switch |
| Documents | Jinja2 templates + Playwright (headless Chromium) | Brochure PDFs and social posters from verified facts |
| Security | argon2-cffi password hashing, PyJWT session tokens in HttpOnly cookies | See `docs/SECURITY.md` |
| Tests & quality | pytest (+ real PostgreSQL), Vitest + Testing Library, Ruff, ESLint, TypeScript `tsc -b` | 469 automated tests passing (18 Nov 2026) |
| Deployment (prepared, $0) | Cloudflare Pages + Pages Functions (website, dashboard), Render free Docker service (API + worker), Neon PostgreSQL | `render.yaml`, `apps/api/Dockerfile`, `apps/*/functions/`, `docs/DEPLOYMENT.md` |
