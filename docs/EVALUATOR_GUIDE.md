# Evaluator guide

> All people, companies, projects, units and prices are **fictional demo data** (e-mail domain `.demo`, projects
> flagged `is_demo_data`, labelled "Illustrative / Fictional Demo Data" on the website). NOVA Residences is not a real
> development; its 3D model is an original illustrative concept and its map pin is an illustrative reference point.

## Links

| What | URL |
|---|---|
| Public website | _to be added after deployment_ |
| Staff dashboard | _to be added after deployment_ |
| Source code | _repository link to be added_ |
| Presentation | `presentation/` (HTML, PDF, editable PPTX) |

Free hosting sleeps when idle: the first page after a pause can take about a minute.

## Accounts

The website needs no account. The dashboard requires signing in; demo accounts (one per role) and their password are
provided **separately with the submission**, never in this repository.

| Role | Try this |
|---|---|
| Super Admin | Everything, including Automation, AI Gateway, Audit log, Design system |
| Executive | BI agent (AI, if enabled), approvals at executive level, dashboards |
| Finance Manager | Budgets, committed vs. spent, finance-level approvals |
| Procurement Officer | Purchase requests, quotations, purchase orders |
| Department Manager | Department-level approvals |
| Sales Manager | Property portfolio (edit projects, units, media), all leads, reservations |
| Sales Agent | Own leads only, follow-ups, reservations — compare with Sales Manager to see RBAC |
| Marketing Manager / Specialist | Content review workflow, brochures & posters |

## Suggested tour (15 minutes)

1. **Website** — home, Projects, NOVA (3D viewer: drag, zoom, reset, full screen; illustrative map), switch to Arabic
   and dark mode, submit a contact form with obviously fictional details.
2. **Dashboard as Sales Agent** — the inquiry appears as a scored lead assigned round-robin; log a follow-up.
3. **As Procurement Officer** — create and submit a purchase request; watch the approval route and budget check.
4. **As the approvers** — approve step by step (the requester cannot approve their own request); after final
   approval the budget is committed and a purchase order can be issued.
5. **As Super Admin** — Automation → executions show each workflow run with steps, logs and retries; Audit log shows
   who changed what.
6. **As Marketing** — submit content, request changes as the manager, resubmit, approve; generate a brochure PDF.

## Known limitations

* AI features depend on the configured Anthropic key and a US$2/day cost cap; when unavailable they say so and the
  rest of the system works. Marketing AI drafting is deliberately switched off.
* Google Maps runs on a demo key: map works, Street View is disabled.
* On free hosting, uploaded images/3D files are not persistent and the worker sleeps with the service.
* Company contact details and About-page copy are placeholders; there are no Privacy/Terms pages yet.
* Payments, e-signature, social-media publishing and the executive KPI dashboard (Phase 8) are not implemented.
