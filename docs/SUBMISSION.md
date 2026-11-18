# SmartEstate AI — assessment submission

Business Transformation & AI Specialist assessment. Everything here is editable source material; all business data
shown is **fictional demo data**.

| Folder | Contents |
|---|---|
| `01-presentation/` | `index.html` (animated deck, open in a browser; arrows/space, F for full screen), `SmartEstate-AI-presentation.pdf`, `SmartEstate-AI-presentation.pptx` (editable PowerPoint) |
| `02-source-code/` | `smartestate-ai-source.zip` — complete source (API, dashboard, website, tests, migrations, docs). Secrets are not included; `.env.example` lists the settings |
| `03-documentation/` | Project README and `docs/`: architecture, database design, automation engine, AI, maps, 3D models, marketing assets, technology stack, security, workflows, evaluator guide, deployment |
| `04-screenshots/` | Real screenshots of the running dashboard and website |
| `05-marketing-deliverables/` | 3D villa source (Blender `.blend`, `create_model.py`, `.glb`, renders), website imagery, brochures/posters |
| `06-deployment/` | `render.yaml`, `Dockerfile`, `start.sh`, deployment and evaluator guides, `.env.example` |

Start with `03-documentation/docs/EVALUATOR_GUIDE.md` (links, accounts, a 15-minute tour, known limitations).

## Run locally (summary)
Requirements: Python 3.12+, Node 20+, PostgreSQL 16+. Full steps: `03-documentation/PROJECT_README.md` → Quick start.

```bash
cp .env.example .env            # fill in the placeholders (database, SECRET_KEY, SEED_DEMO_PASSWORD; AI optional)
cd apps/api && python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"   # macOS/Linux: .venv/bin/pip
.venv/Scripts/python -m alembic upgrade head && .venv/Scripts/python -m app.seed
.venv/Scripts/python -m uvicorn app.main:app --port 8000          # API
.venv/Scripts/python -m app.automation.worker                     # worker (second terminal)
cd ../dashboard && npm ci && npm run dev                          # http://localhost:5174
cd ../marketing && npm ci && npm run dev                          # http://localhost:5173
```
