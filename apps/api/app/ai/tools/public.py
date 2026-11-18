"""Public tools for the property assistant (anonymous visitors).

They return **public fields only** (via ``app/public/catalog.py``): units flagged ``is_public`` in published
projects, with list price, size and status — never notes, costs, internal flags or anything about other buyers. The single writing tool,
``create_lead_with_consent``, creates a lead only when

- the visitor ticked the consent box (recorded on the conversation from the visitor's own request), and
- the name and contact details it receives appear in the visitor's own messages (so the model can't invent them),

and at most once per conversation. The lead then follows the normal lead workflow (score, assign, notify).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.ai.tools.registry import Tool, ToolContext, ToolInput, ToolResult
from app.core.errors import BusinessRuleViolation
from app.public import catalog

ARABIC = re.compile(r"[؀-ۿ]")
UnitType = Literal["studio", "apartment", "duplex", "penthouse", "townhouse"]


@dataclass
class VisitorContext:
    """Attached to ``ToolContext.visitor`` by the property assistant. ``texts`` are the visitor's own messages."""

    conversation: object  # AIConversation
    texts: list[str] = field(default_factory=list)


def _json(model) -> dict:
    return model.model_dump(mode="json")


# --- search_units ----------------------------------------------------------------------------------------------
class SearchUnitsIn(ToolInput):
    bedrooms: int | None = Field(default=None, ge=0, le=10, description="Exact number of bedrooms (0 = studio).")
    min_price_sar: Decimal | None = Field(default=None, ge=0, description="Minimum list price in SAR.")
    max_price_sar: Decimal | None = Field(default=None, ge=0, description="Maximum list price in SAR.")
    unit_type: UnitType | None = None
    project_code: str | None = Field(default=None, max_length=20)
    limit: int = Field(default=6, ge=1, le=10)


def search_units(ctx: ToolContext, data: SearchUnitsIn) -> ToolResult:
    units = [
        _json(u)
        for u in catalog.search_units(
            ctx.session,
            project_code=data.project_code,
            bedrooms=data.bedrooms,
            min_price=data.min_price_sar,
            max_price=data.max_price_sar,
            unit_type=data.unit_type,
            limit=data.limit,
        )
    ]
    return ToolResult(
        {"available_units": units, "count": len(units)},
        f"{len(units)} available units found",
        [{"kind": "units", "units": units}] if units else None,
    )


# --- get_unit -------------------------------------------------------------------------------------------------
class GetUnitIn(ToolInput):
    unit_code: str = Field(min_length=3, max_length=30, description="Unit code such as A-102.")


def get_unit(ctx: ToolContext, data: GetUnitIn) -> ToolResult:
    unit = catalog.find_unit(ctx.session, data.unit_code)
    public = _json(catalog.to_public_unit(unit))
    breakdowns = [_json(b) for b in catalog.plan_breakdowns(ctx.session, unit)]
    return ToolResult({"unit": public, "payment_plans": breakdowns}, f"Unit {public['code']}", [{"kind": "units", "units": [public]}])


# --- get_payment_plans ----------------------------------------------------------------------------------------
class PaymentPlansIn(ToolInput):
    project_code: str | None = Field(default=None, max_length=20, description="Project code; defaults to the first public project.")


def get_payment_plans(ctx: ToolContext, data: PaymentPlansIn) -> ToolResult:
    detail = catalog.project_detail(ctx.session, catalog.get_published_project(ctx.session, data.project_code).code)
    plans = [_json(p) for p in detail.payment_plans]
    return ToolResult({"project": detail.name, "payment_plans": plans}, f"{len(plans)} payment plans for {detail.code}")


# --- get_project_info -----------------------------------------------------------------------------------------
class ProjectInfoIn(ToolInput):
    project_code: str | None = Field(default=None, max_length=20, description="Project code; omit to list public projects.")


def get_project_info(ctx: ToolContext, data: ProjectInfoIn) -> ToolResult:
    codes = [data.project_code] if data.project_code else [p.code for p in catalog.list_projects(ctx.session)]
    out = []
    for code in codes:
        d = catalog.project_detail(ctx.session, code)
        out.append(
            {
                k: v
                for k, v in _json(d).items()
                if k
                in (
                    "code",
                    "name",
                    "city",
                    "district",
                    "status",
                    "description",
                    "amenities",
                    "handover_date",
                    "available_units",
                    "price_from_sar",
                )
            }
        )
    return ToolResult({"projects": out}, f"{len(out)} public projects")


# --- create_lead_with_consent --------------------------------------------------------------------------------
class CreateLeadIn(ToolInput):
    full_name: str = Field(min_length=2, max_length=150, description="The visitor's name exactly as they wrote it.")
    phone: str | None = Field(default=None, max_length=40, description="Phone exactly as the visitor wrote it.")
    email: str | None = Field(default=None, max_length=254, description="E-mail exactly as the visitor wrote it.")
    interested_unit_code: str | None = Field(default=None, max_length=30)
    bedrooms_wanted: int | None = Field(default=None, ge=0, le=10)
    budget_max_sar: Decimal | None = Field(default=None, ge=0)
    timeline: Literal["immediate", "within_3_months", "within_6_months", "over_6_months"] | None = None
    interest: str | None = Field(default=None, max_length=300, description="One line on what the visitor is looking for.")


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def create_lead_with_consent(ctx: ToolContext, data: CreateLeadIn) -> ToolResult:
    from app.modules.crm.schemas import LeadCreate
    from app.modules.crm.service import CRMService

    visitor: VisitorContext = ctx.visitor
    conversation = visitor.conversation
    if getattr(conversation, "lead_id", None):
        return ToolResult({"status": "already_registered"}, "Contact details were already shared in this conversation")
    if not getattr(conversation, "contact_consent_at", None):
        raise BusinessRuleViolation(
            "The visitor has not ticked the consent box. Ask them to tick it before sharing contact details.", code="consent_required"
        )
    if not data.phone and not data.email:
        raise BusinessRuleViolation("A phone number or e-mail is required.", code="contact_required")
    said = "\n".join(visitor.texts)
    said_digits = _digits(said)
    lowered = said.lower()
    if data.full_name.strip().lower() not in lowered:
        raise BusinessRuleViolation("Use the name exactly as the visitor wrote it.", code="unverified_contact")
    if data.phone and (len(_digits(data.phone)) < 7 or _digits(data.phone) not in said_digits):
        raise BusinessRuleViolation("Use the phone number exactly as the visitor wrote it.", code="unverified_contact")
    if data.email and data.email.strip().lower() not in lowered:
        raise BusinessRuleViolation("Use the e-mail exactly as the visitor wrote it.", code="unverified_contact")
    unit = catalog.find_unit(ctx.session, data.interested_unit_code) if data.interested_unit_code else None
    try:
        lead_in = LeadCreate(
            full_name=data.full_name.strip(),
            phone=data.phone.strip() if data.phone else None,
            email=data.email.strip() if data.email else None,
            preferred_language="ar" if ARABIC.search(said) else "en",
            source="property_assistant",
            interest=data.interest,
            budget_max=data.budget_max_sar.quantize(Decimal("0.01")) if data.budget_max_sar is not None else None,
            bedrooms_wanted=data.bedrooms_wanted,
            consent=True,
            notes="Registered through the AI property assistant with the visitor's consent.",
            interested_unit_id=unit.id if unit else None,
            timeline=data.timeline,
        )
    except ValueError as exc:
        raise BusinessRuleViolation("The contact details are not valid. Ask the visitor to check them.", code="invalid_contact") from exc
    lead = CRMService(ctx.session).create_lead_from_assistant(lead_in)  # commits; emits lead.created
    conversation.lead_id = lead.id  # type: ignore[attr-defined]
    conversation.updated_at = datetime.now(UTC)  # type: ignore[attr-defined]
    return ToolResult(
        {"status": "registered", "next_step": "A sales advisor will contact the visitor."},
        "Visitor registered as a lead (with consent)",
        [{"kind": "lead_created"}],
    )


CONTACT_FIELDS = frozenset({"full_name", "phone", "email"})

PUBLIC_TOOLS = [
    Tool(
        "search_units",
        "Searched available units",
        "Search AVAILABLE public units by bedrooms, price range (SAR), unit type and project. Returns public fields only.",
        SearchUnitsIn,
        "public",
        search_units,
    ),
    Tool(
        "get_unit",
        "Looked up a unit",
        "Public details of one unit (by code such as A-102) with its payment plan breakdowns.",
        GetUnitIn,
        "public",
        get_unit,
    ),
    Tool(
        "get_payment_plans",
        "Checked payment plans",
        "Active payment plans of a public project.",
        PaymentPlansIn,
        "public",
        get_payment_plans,
    ),
    Tool(
        "get_project_info",
        "Checked project information",
        "Public project information: location, status, amenities, handover.",
        ProjectInfoIn,
        "public",
        get_project_info,
    ),
    Tool(
        "create_lead_with_consent",
        "Shared contact details with sales",
        "Register the visitor as a sales lead. Only after the visitor has written their name and phone or e-mail in this "
        "conversation AND ticked the consent box. Copy their details exactly as written.",
        CreateLeadIn,
        "public",
        create_lead_with_consent,
        redact_fields=CONTACT_FIELDS,
    ),
]
