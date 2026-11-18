from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Request, status

from app.ai.router import get_gateway
from app.api.deps import CurrentPrincipal, SessionDep
from app.common.listing import ListParams, Page, list_params
from app.core.permissions import Perm
from app.modules.identity.principal import ensure_permission
from app.modules.marketing.facts import check_text, project_facts
from app.modules.marketing.schemas import (
    CHANNEL_RULES,
    CampaignIn,
    CampaignOut,
    CampaignUpdate,
    ContentDetail,
    ContentIn,
    ContentOut,
    ContentUpdate,
    FactsCheckIn,
    FactWarning,
    MarketingAIStatus,
    ProjectFacts,
)
from app.modules.marketing.service import MarketingService

router = APIRouter(prefix="/marketing", tags=["marketing"])
ChannelQ = Literal["instagram", "x", "linkedin", "email", "website", "whatsapp"]


# --- campaigns ------------------------------------------------------------------------------------
@router.get("/campaigns", response_model=Page[CampaignOut])
def list_campaigns(
    principal: CurrentPrincipal,
    session: SessionDep,
    params: ListParams = Depends(list_params),
    status: Literal["draft", "active", "completed", "archived", "current"] | None = None,
    project_id: uuid.UUID | None = None,
) -> Page[CampaignOut]:
    items, total, pages = MarketingService(session).list_campaigns(principal, params, status=status, project_id=project_id)
    return Page(items=items, total=total, page=params.page, page_size=params.page_size, pages=pages)


@router.post("/campaigns", response_model=CampaignOut, status_code=status.HTTP_201_CREATED)
def create_campaign(body: CampaignIn, principal: CurrentPrincipal, session: SessionDep) -> CampaignOut:
    svc = MarketingService(session)
    return svc.campaign_out(principal, svc.create_campaign(principal, body))


@router.get("/campaigns/{campaign_id}", response_model=CampaignOut)
def get_campaign(campaign_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep) -> CampaignOut:
    return MarketingService(session).get_campaign(principal, campaign_id)


@router.patch("/campaigns/{campaign_id}", response_model=CampaignOut)
def update_campaign(campaign_id: uuid.UUID, body: CampaignUpdate, principal: CurrentPrincipal, session: SessionDep) -> CampaignOut:
    svc = MarketingService(session)
    return svc.campaign_out(principal, svc.update_campaign(principal, campaign_id, body))


@router.post("/campaigns/{campaign_id}/archive", response_model=CampaignOut)
def archive_campaign(campaign_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep) -> CampaignOut:
    svc = MarketingService(session)
    return svc.campaign_out(principal, svc.archive_campaign(principal, campaign_id))


# --- content ----------------------------------------------------------------------------------------
@router.get("/content", response_model=Page[ContentOut])
def list_content(
    principal: CurrentPrincipal,
    session: SessionDep,
    params: ListParams = Depends(list_params),
    campaign_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    status: Literal["draft", "pending_approval", "approved", "rejected", "archived", "current"] | None = None,
    channel: ChannelQ | None = None,
    language: Literal["en", "ar"] | None = None,
) -> Page[ContentOut]:
    items, total, pages = MarketingService(session).list_content(
        principal, params, campaign_id=campaign_id, status=status, channel=channel, language=language, project_id=project_id
    )
    return Page(items=items, total=total, page=params.page, page_size=params.page_size, pages=pages)


@router.post("/content", response_model=ContentDetail, status_code=status.HTTP_201_CREATED)
def create_content(body: ContentIn, principal: CurrentPrincipal, session: SessionDep) -> ContentDetail:
    svc = MarketingService(session)
    return svc.detail(principal, svc.create_content(principal, body).id)


@router.get("/content/{content_id}", response_model=ContentDetail)
def get_content(content_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep) -> ContentDetail:
    return MarketingService(session).detail(principal, content_id)


@router.patch("/content/{content_id}", response_model=ContentDetail)
def update_content(content_id: uuid.UUID, body: ContentUpdate, principal: CurrentPrincipal, session: SessionDep) -> ContentDetail:
    svc = MarketingService(session)
    svc.update_content(principal, content_id, body)
    return svc.detail(principal, content_id)


@router.post("/content/{content_id}/submit", response_model=ContentDetail)
def submit_content(content_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep) -> ContentDetail:
    """Opens the review (approval request) in the same transaction. Decisions go through /approvals/{id}/approve|reject."""
    svc = MarketingService(session)
    svc.submit(principal, content_id)
    return svc.detail(principal, content_id)


@router.post("/content/{content_id}/archive", response_model=ContentDetail)
def archive_content(content_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep) -> ContentDetail:
    svc = MarketingService(session)
    svc.archive_content(principal, content_id)
    return svc.detail(principal, content_id)


# --- facts, channels and AI ---------------------------------------------------------------------------
@router.get("/projects/{project_id}/facts", response_model=ProjectFacts)
def get_project_facts(project_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep) -> ProjectFacts:
    ensure_permission(principal, Perm.MARKETING_CAMPAIGNS_READ)
    return project_facts(session, project_id)


@router.post("/facts-check", response_model=list[FactWarning])
def facts_check(body: FactsCheckIn, principal: CurrentPrincipal, session: SessionDep) -> list[FactWarning]:
    ensure_permission(principal, Perm.MARKETING_CAMPAIGNS_READ)
    return check_text(session, body.project_id, body.headline, body.body, body.call_to_action)


@router.get("/channels", response_model=dict[str, dict])
def channels(principal: CurrentPrincipal) -> dict[str, dict]:
    ensure_permission(principal, Perm.MARKETING_CAMPAIGNS_READ)
    return CHANNEL_RULES  # type: ignore[return-value]


@router.get("/ai-status", response_model=MarketingAIStatus)
def ai_status(request: Request, principal: CurrentPrincipal) -> MarketingAIStatus:
    ensure_permission(principal, Perm.MARKETING_CAMPAIGNS_READ)
    cfg = get_gateway(request).config
    if cfg.capability_enabled("marketing_studio"):
        return MarketingAIStatus(enabled=True, reason="AI drafting is available.")
    why = "AI_MARKETING_STUDIO_ENABLED=false" if cfg.enabled else cfg.reason
    return MarketingAIStatus(enabled=False, reason=f"AI drafting is turned off ({why}). Write and edit content manually.")


@router.post("/content/generate")
def generate_content(request: Request, principal: CurrentPrincipal) -> None:
    """Reserved for AI drafting. Refused while the feature flag is off — the provider is never called."""
    ensure_permission(principal, Perm.MARKETING_CONTENT_CREATE)
    get_gateway(request).ensure_enabled("marketing_studio", actor_user_id=principal.user_id)
    from app.core.errors import BusinessRuleViolation

    raise BusinessRuleViolation("AI drafting is not available in this release.", code="ai_generation_not_available")
