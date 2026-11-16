"""Supplier analysis — deterministic, advisory only. It recommends; people select the supplier."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.automation.contracts import ActionContext
from app.automation.registry import action
from app.core.permissions import Perm
from app.modules.identity.repository import IdentityRepository
from app.modules.notifications.service import NotificationService
from app.modules.procurement.models import PurchaseRequest


class AnalyseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: uuid.UUID
    weight_price: float = Field(ge=0, le=1)
    weight_delivery: float = Field(ge=0, le=1)
    weight_rating: float = Field(ge=0, le=1)
    expiry_warning_days: int = Field(ge=0)


def rank_quotations(quotes: list[dict], weights: tuple[float, float, float]) -> list[dict]:
    """Pure scoring: price share of the lowest total, delivery share of the fastest, rating out of 5."""
    wp, wd, wr = weights
    total_w = (wp + wd + wr) or 1.0
    lowest = min(q["total"] for q in quotes)
    times = [q["delivery_days"] for q in quotes if q["delivery_days"] is not None]
    fastest = min(times) if times else None
    ranked = []
    for q in quotes:
        price = float(lowest / q["total"]) if q["total"] > 0 else 1.0
        # (fastest + 1) / (days + 1): 1.0 for the fastest quote, smoothly lower for slower ones, safe for 0 days.
        delivery = 0.5 if q["delivery_days"] is None or fastest is None else (fastest + 1) / (q["delivery_days"] + 1)
        rating = float(q["rating"]) / 5 if q["rating"] is not None else 0.5
        score = round(100 * (wp * price + wd * delivery + wr * rating) / total_w, 1)
        ranked.append(
            {
                **q,
                "score": score,
                "price_score": round(price * 100, 1),
                "delivery_score": round(delivery * 100, 1),
                "rating_score": round(rating * 100, 1),
            }
        )
    ranked.sort(key=lambda r: (-r["score"], r["total"]))
    return ranked


@action(
    "procurement.analyse_quotations",
    label="Analyse supplier quotations",
    input_model=AnalyseIn,
    advisory=True,
    description="Scores quotations on price, delivery and supplier rating and flags risks. Advisory: never selects a supplier.",
)
def analyse(ctx: ActionContext, data: AnalyseIn) -> dict:
    pr = ctx.session.get(PurchaseRequest, data.request_id)
    if pr is None or not pr.quotations:
        return {"quotations": 0}
    quotes = [
        {
            "quotation_id": str(q.id),
            "supplier": q.supplier.name,
            "supplier_code": q.supplier.code,
            "total": q.total_amount,
            "delivery_days": q.delivery_days,
            "rating": q.supplier.rating,
            "valid_until": q.valid_until,
        }
        for q in pr.quotations
    ]
    ranked = rank_quotations(quotes, (data.weight_price, data.weight_delivery, data.weight_rating))
    lowest = min(q["total"] for q in quotes)
    highest = max(q["total"] for q in quotes)
    warnings: list[str] = []
    if len(quotes) == 1:
        warnings.append("Only one quotation — consider asking another supplier.")
    today = date.today()
    for q in quotes:
        if q["valid_until"] and q["valid_until"] < today:
            warnings.append(f"{q['supplier']}: quotation expired on {q['valid_until']:%d %b %Y}.")
        elif q["valid_until"] and q["valid_until"] <= today + timedelta(days=data.expiry_warning_days):
            warnings.append(f"{q['supplier']}: quotation expires on {q['valid_until']:%d %b %Y}.")
    spread = float((highest - lowest) / lowest * 100) if lowest > 0 else 0.0
    if spread >= 20:
        warnings.append(f"Prices differ by {spread:.0f}% — check the scopes are comparable.")
    best = ranked[0]
    note = "also the lowest price" if best["total"] == lowest else f"SAR {best['total'] - lowest:,.2f} above the lowest price"
    recommendation = f"{best['supplier']} scores best ({best['score']}/100) — {note}."
    ctx.log.info(recommendation)
    for w in warnings:
        ctx.log.warning(w)
    return {
        "advisory": True,
        "request_code": pr.code,
        "quotations": len(quotes),
        "recommended_quotation_id": best["quotation_id"],
        "recommendation": recommendation,
        "price_spread_pct": round(spread, 1),
        "warnings": warnings,
        "ranking": [{k: (str(v) if isinstance(v, Decimal | date) else v) for k, v in r.items()} for r in ranked],
    }


class ShareIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: uuid.UUID
    request_code: str
    quotations: int
    recommendation: str


@action(
    "procurement.share_supplier_analysis",
    label="Share analysis with procurement",
    input_model=ShareIn,
    description="Sends the recommendation to procurement officers (once per number of quotations).",
)
def share(ctx: ActionContext, data: ShareIn) -> dict:
    recipients = IdentityRepository(ctx.session).users_with_permission(Perm.PROCUREMENT_QUOTATIONS_MANAGE.value)
    for uid in recipients:
        NotificationService(ctx.session).notify(
            uid,
            type="procurement.supplier_analysis",
            level="info",
            title=f"Supplier analysis ready: {data.request_code}",
            body=f"{data.quotations} quotations compared. {data.recommendation}",
            link=f"/procurement/requests/{data.request_id}",
            entity_type="purchase_request",
            entity_id=str(data.request_id),
            dedupe_key=f"pr:{data.request_id}:analysis:{data.quotations}",
        )
    return {"notified": len(recipients)}
