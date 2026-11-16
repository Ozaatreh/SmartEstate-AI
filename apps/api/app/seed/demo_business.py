"""Fictional demo organisation for development (people, budgets, suppliers, purchase requests).

All names, companies and figures are invented. Purchase requests are created through the real
services (submit → quotations → approval), so budgets, the ledger and the audit trail stay consistent.
Runs only when no departments exist yet.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.approvals.service import ApprovalService
from app.modules.finance.models import Budget, BudgetCategory, OperationalProject
from app.modules.hr.models import Department, Employee
from app.modules.identity.models import User
from app.modules.identity.service import build_principal
from app.modules.procurement.models import Supplier
from app.modules.procurement.schemas import CancelIn, ItemIn, QuotationIn, QuotationItemIn, RequestCreate
from app.modules.procurement.service import ProcurementService

D = Decimal

DEPARTMENTS = (
    ("EXEC", "Executive Office", "Company leadership and strategy"),
    ("FIN", "Finance", "Budgeting, accounting and treasury"),
    ("HR", "Human Resources", "People, hiring and policies"),
    ("CONST", "Construction", "Site delivery for all developments"),
    ("PROC", "Procurement", "Sourcing, suppliers and purchasing"),
    ("SALES", "Sales", "Property sales and customer relations"),
    ("MKT", "Marketing", "Brand, campaigns and launches"),
    ("IT", "Information Technology", "Systems, devices and support"),
)

# (key, full name, title, department, manager key, demo user local-part or None, location)
PEOPLE = (
    ("ceo", "Faisal Al-Rashid", "Chief Executive Officer", "EXEC", None, "ceo", "Riyadh HQ"),
    ("cfo", "Noura Al-Qahtani", "Finance Manager", "FIN", "ceo", "finance", "Riyadh HQ"),
    ("acct", "Mazen Al-Dosari", "Senior Accountant", "FIN", "cfo", None, "Riyadh HQ"),
    ("hrm", "Omar Saleh", "HR Manager", "HR", "ceo", "hr", "Riyadh HQ"),
    ("hrs", "Lama Al-Shehri", "HR Specialist", "HR", "hrm", None, "Riyadh HQ"),
    ("cons", "Reem Al-Otaibi", "Head of Construction", "CONST", "ceo", "construction.head", "NOVA site office"),
    ("eng", "Ahmed Karim", "Site Engineer", "CONST", "cons", "employee", "NOVA site office"),
    ("pm", "Bandar Al-Ghamdi", "Project Manager", "CONST", "cons", None, "NOVA site office"),
    ("qs", "Hessa Al-Amri", "Quantity Surveyor", "CONST", "cons", None, "NOVA site office"),
    ("proc", "Khalid Mansour", "Procurement Officer", "PROC", "ceo", "procurement", "Riyadh HQ"),
    ("buyer", "Rana Al-Juhani", "Buyer", "PROC", "proc", None, "Riyadh HQ"),
    ("salesm", "Sara Al-Harbi", "Sales Manager", "SALES", "ceo", "sales.manager", "NOVA sales gallery"),
    ("agent", "Yousef Nasser", "Sales Consultant", "SALES", "salesm", "sales.agent", "NOVA sales gallery"),
    ("agent2", "Dana Al-Subaie", "Sales Consultant", "SALES", "salesm", None, "NOVA sales gallery"),
    ("mktm", "Huda Al-Zahrani", "Marketing Manager", "MKT", "ceo", "marketing", "Riyadh HQ"),
    ("design", "Nawaf Al-Harthi", "Brand Designer", "MKT", "mktm", None, "Riyadh HQ"),
    ("itm", "Tariq Al-Mutairi", "IT Manager", "IT", "ceo", None, "Riyadh HQ"),
    ("admin", "Layla Haddad", "System Administrator", "IT", "itm", "admin", "Riyadh HQ"),
)
MANAGERS = {"EXEC": "ceo", "FIN": "cfo", "HR": "hrm", "CONST": "cons", "PROC": "proc", "SALES": "salesm", "MKT": "mktm", "IT": "itm"}

PROJECTS = (
    ("NOVA Residences — Phase 1 infrastructure", "Roads, utilities and podium works for Phase 1 (fictional).", "CONST", "pm"),
    ("NOVA sales gallery fit-out", "Interior fit-out of the on-site sales gallery (fictional).", "CONST", "pm"),
    ("Digital workplace rollout", "Devices and collaboration tools for site and office teams.", "IT", "itm"),
)

DEPT_BUDGETS = (
    ("CONST", "EQUIP", "1200000"),
    ("CONST", "OPEX-ADMIN", "150000"),
    ("IT", "IT", "480000"),
    ("MKT", "MKT", "900000"),
    ("SALES", "OPEX-ADMIN", "120000"),
    ("SALES", "MKT", "60000"),
    ("HR", "PROF", "200000"),
    ("FIN", "PROF", "250000"),
    ("PROC", "OPEX-ADMIN", "80000"),
    ("EXEC", "PROF", "300000"),
)
PROJECT_BUDGETS = ((0, "CAPEX-CONSTR", "8500000"), (1, "CAPEX-CONSTR", "1100000"), (2, "IT", "650000"))

SUPPLIERS = (
    ("Al-Nakheel Building Supplies", "Construction materials", "Saad Al-Faraj", "Riyadh", "4.5"),
    ("Najd Safety Equipment Co.", "Safety & PPE", "Fahad Al-Qarni", "Riyadh", "4.2"),
    ("Wadi Readymix Concrete", "Construction materials", "Majed Al-Anazi", "Al-Kharj", "4.0"),
    ("Qimma IT Solutions", "IT & electronics", "Hind Al-Saud", "Riyadh", "4.6"),
    ("Sahra Interiors & Furniture", "Furniture & fit-out", "Ali Al-Hamdan", "Jeddah", "3.8"),
    ("Durrah Print & Signage", "Printing & signage", "Mona Al-Rasheed", "Riyadh", "4.1"),
    ("Falak Engineering Consultants", "Professional services", "Ziad Al-Omari", "Riyadh", "4.4"),
    ("Masar Equipment Rentals", "Equipment rental", "Turki Al-Shammari", "Dammam", "3.9"),
)


def _items(rows):
    return [ItemIn(description=d, quantity=D(q), unit=u, estimated_unit_price=D(p)) for d, q, u, p in rows]


def seed_demo_business(session: Session, email_domain: str) -> bool:
    if session.scalar(select(func.count()).select_from(Department)):
        return False
    users = {u.email.split("@")[0]: u for u in session.scalars(select(User))}
    depts = {code: Department(code=code, name=name, description=desc) for code, name, desc in DEPARTMENTS}
    session.add_all(depts.values())
    session.flush()

    emps: dict[str, Employee] = {}
    n = 0
    for key, name, title, dept, _mgr, login, location in PEOPLE:
        n += 1
        emps[key] = Employee(
            employee_no=f"EMP-{session.execute(select(func.nextval('employee_no_seq'))).scalar_one():04d}",
            full_name=name,
            job_title=title,
            department_id=depts[dept].id,
            email=f"{login or key.replace('_', '.')}@{email_domain}" if login else f"{name.split()[0].lower()}.{key}@{email_domain}",
            location=location,
            hire_date=date(2019 + n % 6, 1 + n % 12, 1 + (n * 3) % 27),
            user_id=users[login].id if login and login in users else None,
        )
    session.add_all(emps.values())
    session.flush()
    for key, *_rest in PEOPLE:
        mgr = dict((p[0], p[4]) for p in PEOPLE)[key]
        emps[key].manager_id = emps[mgr].id if mgr else None
    for code, key in MANAGERS.items():
        depts[code].manager_employee_id = emps[key].id
    session.flush()

    cats = {c.code: c for c in session.scalars(select(BudgetCategory))}
    projects: list[OperationalProject] = []
    for name, desc, dept, mgr in PROJECTS:
        p = OperationalProject(
            code=f"OP-{session.execute(select(func.nextval('operational_project_code_seq'))).scalar_one():04d}",
            name=name,
            description=desc,
            department_id=depts[dept].id,
            manager_employee_id=emps[mgr].id,
            status="active",
            start_date=date(date.today().year, 1, 1),
            end_date=date(date.today().year + 1, 12, 31),
        )
        projects.append(p)
    session.add_all(projects)
    session.flush()
    year = date.today().year
    for dept, cat, amount in DEPT_BUDGETS:
        session.add(Budget(fiscal_year=year, category_id=cats[cat].id, department_id=depts[dept].id, allocated_amount=D(amount)))
    for idx, cat, amount in PROJECT_BUDGETS:
        session.add(Budget(fiscal_year=year, category_id=cats[cat].id, project_id=projects[idx].id, allocated_amount=D(amount)))

    sups: list[Supplier] = []
    for name, category, contact, city, rating in SUPPLIERS:
        sups.append(
            Supplier(
                code=f"SUP-{session.execute(select(func.nextval('supplier_code_seq'))).scalar_one():05d}",
                name=name,
                category=category,
                contact_name=contact,
                city=city,
                rating=D(rating),
                email=f"sales@{name.split()[0].lower().replace('-', '')}.example",
                phone="+966 11 000 0000",
                vat_number=f"3{n:02d}0000000000003",
            )
        )
    session.add_all(sups)
    session.commit()

    _demo_requests(session, users, depts, projects, cats, sups)
    return True


def _demo_requests(session, users, depts, projects, cats, sups) -> None:
    P = lambda login: build_principal(users[login])  # noqa: E731
    svc = lambda: ProcurementService(session)  # noqa: E731
    approvals = lambda: ApprovalService(session)  # noqa: E731
    valid = date.today() + timedelta(days=30)
    year = date.today().year

    def create(login, title, why, dept, cat, items, project=None, priority="normal", days=21):
        return svc().create_request(
            P(login),
            RequestCreate(
                title=title,
                justification=why,
                department_id=depts[dept].id,
                project_id=project.id if project else None,
                category_id=cats[cat].id,
                fiscal_year=year,
                needed_by=date.today() + timedelta(days=days),
                priority=priority,
                items=_items(items),
            ),
        )

    def quote(pr, supplier, prices, days, ref):
        detail = svc().detail(P("procurement"), pr.id)
        svc().add_quotation(
            P("procurement"),
            pr.id,
            QuotationIn(
                supplier_id=supplier.id,
                reference=ref,
                valid_until=valid,
                delivery_days=days,
                payment_terms="30 days net",
                items=[QuotationItemIn(request_item_id=i.id, unit_price=D(p)) for i, p in zip(detail.items, prices, strict=True)],
            ),
        )

    def select_lowest_and_send(pr):
        d = svc().detail(P("procurement"), pr.id)
        svc().select_quotation(P("procurement"), pr.id, d.comparison.lowest_quotation_id)
        svc().send_for_approval(P("procurement"), pr.id)
        return approvals().latest_for_entity("purchase_request", pr.id)

    # 1) Approved and committed (department level only).
    pr1 = create(
        "employee",
        "Site safety barriers — Block A",
        "Temporary barriers and signage for the Block A excavation, required by the site safety plan.",
        "CONST",
        "CAPEX-CONSTR",
        [("Steel crowd-control barriers 2.5 m", "120", "unit", "185.00"), ("Reflective safety signage set", "40", "set", "210.00")],
        project=projects[0],
        priority="high",
        days=7,
    )
    svc().submit(P("employee"), pr1.id)
    quote(pr1, sups[1], ["172.50", "198.00"], 5, "NSE-Q-2291")
    quote(pr1, sups[0], ["189.00", "205.00"], 9, "ANB-7734")
    quote(pr1, sups[7], ["179.00", "221.00"], 12, "MER-0912")
    a1 = select_lowest_and_send(pr1)
    approvals().approve(P("construction.head"), a1.id, "Approved — needed before excavation starts.")

    # 2) Pending at finance (department approved).
    pr2 = create(
        "employee",
        "Concrete pump rental — Q4 pours",
        "Boom pump rental for the podium slab pours scheduled this quarter.",
        "CONST",
        "EQUIP",
        [("Boom concrete pump (36 m) — monthly rental", "3", "month", "52000.00"), ("Operator and mobilisation", "1", "lot", "14500.00")],
        days=30,
    )
    svc().submit(P("employee"), pr2.id)
    quote(pr2, sups[7], ["49500.00", "12000.00"], 3, "MER-1044")
    quote(pr2, sups[2], ["53800.00", "9800.00"], 6, "WRC-552")
    a2 = select_lowest_and_send(pr2)
    approvals().approve(P("construction.head"), a2.id, "Schedule confirmed with the contractor.")

    # 3) Over the executive threshold; requester manages the department → escalated to the CEO.
    pr3 = create(
        "marketing",
        "Launch campaign — Riyadh billboards",
        "Outdoor media for the NOVA Residences launch (fictional campaign).",
        "MKT",
        "MKT",
        [
            ("Digital billboard slots, King Fahd Road (4 weeks)", "4", "week", "68000.00"),
            ("Static billboards — design and print", "6", "unit", "9500.00"),
        ],
        priority="high",
        days=14,
    )
    svc().submit(P("marketing"), pr3.id)
    quote(pr3, sups[5], ["66500.00", "9200.00"], 10, "DPS-3310")
    select_lowest_and_send(pr3)

    # 4) In sourcing with two quotations (not yet selected).
    pr4 = create(
        "sales.agent",
        "Brochure stands for the sales gallery",
        "Floor-standing brochure holders for the new gallery layout.",
        "SALES",
        "OPEX-ADMIN",
        [("Acrylic brochure stand, 4 tiers", "8", "unit", "640.00")],
    )
    svc().submit(P("sales.agent"), pr4.id)
    quote(pr4, sups[4], ["610.00"], 14, "SIF-8821")
    quote(pr4, sups[5], ["655.00"], 7, "DPS-3322")

    # 5) Rejected by the department manager.
    pr5 = create(
        "sales.agent",
        "Branded giveaways for walk-in visitors",
        "Tote bags and notebooks with the NOVA logo for visitors.",
        "SALES",
        "MKT",
        [("Branded tote bag", "500", "unit", "18.00"), ("Branded notebook", "500", "unit", "12.50")],
    )
    svc().submit(P("sales.agent"), pr5.id)
    quote(pr5, sups[5], ["16.50", "11.00"], 10, "DPS-3330")
    a5 = select_lowest_and_send(pr5)
    approvals().reject(
        P("sales.manager"), a5.id, "Marketing is ordering branded items centrally this quarter — please coordinate with Huda."
    )

    # 6) A draft and a cancelled request.
    create(
        "admin",
        "Laptops for site engineers",
        "Replace end-of-life laptops for the NOVA site team.",
        "IT",
        "IT",
        [('14" business laptop, 16 GB RAM', "6", "unit", "4850.00"), ("USB-C docking station", "6", "unit", "690.00")],
        days=45,
    )
    pr7 = create(
        "employee", "Spare hard hats", "Extra helmets for visitors.", "CONST", "EQUIP", [("Hard hat, class E", "30", "unit", "45.00")]
    )
    svc().cancel(P("employee"), pr7.id, CancelIn(reason="Already covered by the safety barriers order."))
