"""Project facts for marketing writers, and a check that content doesn't invent them.

``project_facts`` gathers what content may claim about a project — location, status, handover, amenities, real
unit availability and price ranges, payment plans — straight from the real-estate tables.

``check_text`` flags figures in a draft that don't match those facts: money amounts that aren't a real list price
(or the project's "from" price), percentages that aren't in a payment plan, and bedroom counts with no available
unit. Warnings are advisory — shown to the writer while editing and to the manager at review — because only a person
can judge wording; they never change or block content by themselves.
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.modules.marketing.schemas import FactWarning, ProjectFacts, Ref
from app.modules.realestate.models import ReProject, ReUnit
from app.public.catalog import marketing_plans

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,")
CURRENCY = r"(?:SAR|SR|ريال|ر\.س)"
MONEY = re.compile(
    rf"(?:{CURRENCY}\s*)?(?P<num>\d{{1,3}}(?:,\d{{3}})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*(?:(?P<unit>k|K|m|M|million|mn|ألف|مليون)\b)?(?:\s*{CURRENCY})?"
)
PERCENT = re.compile(r"(?P<num>\d{1,3}(?:\.\d+)?)\s*(?:%|٪|percent|بالمئة|في المئة)")
BEDROOMS = re.compile(r"(?P<num>\d{1,2})\s*(?:-\s*)?(?:bed(?:room)?s?|BR|bd)\b", re.IGNORECASE)
MULTIPLIER = {
    "k": 1_000,
    "K": 1_000,
    "ألف": 1_000,
    "m": 1_000_000,
    "M": 1_000_000,
    "million": 1_000_000,
    "mn": 1_000_000,
    "مليون": 1_000_000,
}


def project_facts(session: Session, project_id: uuid.UUID) -> ProjectFacts:
    p = session.get(ReProject, project_id)
    if p is None:
        raise NotFound("Project not found.")
    units = list(session.scalars(select(ReUnit).where(ReUnit.project_id == p.id)))
    available = [u for u in units if u.status == "available"]
    by_beds: dict[int, list[Decimal]] = defaultdict(list)
    for u in available:
        by_beds[u.bedrooms].append(u.list_price)
    plans = marketing_plans(session, p.id)
    return ProjectFacts(
        project=Ref(id=p.id, code=p.code, name=p.name),
        city=p.city,
        district=p.district,
        status=p.status,
        handover_date=p.handover_date,
        is_published=p.is_published,
        is_demo_data=p.is_demo_data,
        amenities=list(p.amenities or []),
        available_units=len(available),
        bedroom_options=[
            {"bedrooms": b, "available": len(prices), "price_from_sar": str(min(prices)), "price_to_sar": str(max(prices))}
            for b, prices in sorted(by_beds.items())
        ],
        price_from_sar=str(min(u.list_price for u in available)) if available else None,
        payment_plans=[
            {
                "name": pl.name,
                "down_payment_pct": str(pl.down_payment_pct.normalize()),
                "installments": pl.installments,
                "installment_frequency": pl.installment_frequency,
                "handover_pct": str(pl.handover_pct.normalize()),
            }
            for pl in plans
        ],
        description=p.description,
    )


def _decimal(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace(",", ""))
    except InvalidOperation:
        return None


def check_text(session: Session, project_id: uuid.UUID, *texts: str | None) -> list[FactWarning]:
    text = "\n".join(t for t in texts if t).translate(ARABIC_DIGITS)
    if not text.strip():
        return []
    units = list(session.scalars(select(ReUnit).where(ReUnit.project_id == project_id)))
    plans = marketing_plans(session, project_id)
    prices = {u.list_price for u in units}
    available = [u for u in units if u.status == "available"]
    if available:
        prices.add(min(u.list_price for u in available))
    percents = set()
    for pl in plans:
        percents |= {pl.down_payment_pct, pl.handover_pct, Decimal(100) - pl.down_payment_pct - pl.handover_pct}
    bedrooms = {u.bedrooms for u in available}

    warnings: list[FactWarning] = []
    seen: set[str] = set()

    def warn(kind: str, snippet: str, message: str) -> None:
        if snippet not in seen:
            seen.add(snippet)
            warnings.append(FactWarning(kind=kind, text=snippet, message=message))

    pct_spans = [m.span() for m in PERCENT.finditer(text)]
    for m in PERCENT.finditer(text):
        value = _decimal(m.group("num"))
        if value is not None and value not in percents:
            warn("percentage", m.group(0).strip(), "No active payment plan of this project uses this percentage.")
    for m in MONEY.finditer(text):
        if any(a <= m.start() < b for a, b in pct_spans):
            continue
        snippet, unit = m.group(0).strip(), m.group("unit")
        has_currency = re.search(CURRENCY, snippet) is not None
        has_separator = "," in m.group("num")
        if not (unit or has_currency or has_separator):
            continue  # plain numbers (years, floors, unit numbers) aren't prices
        value = _decimal(m.group("num"))
        if value is None:
            continue
        amount = value * MULTIPLIER.get(unit or "", 1)
        if amount < 10_000:
            continue
        if amount not in prices:
            warn("price", snippet, "This amount isn't the list price of any unit in this project (nor its starting price).")
    for m in BEDROOMS.finditer(text):
        n = int(m.group("num"))
        if n not in bedrooms:
            warn("bedrooms", m.group(0).strip(), "No unit with this number of bedrooms is available in this project.")
    return warnings
