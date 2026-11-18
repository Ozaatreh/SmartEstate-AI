"""AI gateway endpoints. There is no endpoint that sends a prompt: capabilities call the gateway from service code
(Phase 6B+). These endpoints only report availability and usage, and run the token-free health check."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.ai.gateway import AIGateway, start_of_day
from app.ai.models import AIUsage
from app.ai.repository import AIUsageRepository
from app.api.deps import CurrentPrincipal, SessionDep
from app.common.listing import ListParams, Page, apply_sort, list_params, paginate
from app.core.permissions import Perm
from app.modules.audit.service import AuditService
from app.modules.identity.principal import ensure_permission

router = APIRouter(prefix="/ai", tags=["ai"])
State = Literal["disabled", "misconfigured", "unverified", "operational", "degraded"]


def get_gateway(request: Request) -> AIGateway:
    return request.app.state.ai_gateway


class AIStatusOut(BaseModel):
    state: State
    reason: str
    usable: bool


class ProfileOut(BaseModel):
    capability: str
    model: str
    effort: str
    max_tokens: int
    server_fallback: bool


class UsageSummary(BaseModel):
    requests: int
    succeeded: int
    failed: int
    rejected: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: Decimal


class GatewayOverview(AIStatusOut):
    provider: str
    profiles: list[ProfileOut]
    timeout_seconds: float
    max_retries: int
    max_output_tokens: int
    daily_cost_cap_usd: Decimal
    last_success_at: datetime | None
    last_failure_at: datetime | None
    last_error_category: str | None
    today: UsageSummary


class ModelCheckOut(BaseModel):
    model: str
    ok: bool
    error_category: str | None


class HealthCheckOut(BaseModel):
    checks: list[ModelCheckOut]
    status: AIStatusOut


class UsageOut(BaseModel):
    model_config = {"from_attributes": True}

    request_id: uuid.UUID
    actor_type: str
    actor_user_id: uuid.UUID | None
    capability: str
    provider: str
    model: str | None
    served_model: str | None
    status: str
    error_category: str | None
    stop_reason: str | None
    input_tokens: int | None
    output_tokens: int | None
    cache_read_tokens: int | None
    estimated_cost_usd: Decimal | None
    duration_ms: int
    created_at: datetime


GatewayDep = Depends(get_gateway)


@router.get("/status", response_model=AIStatusOut)
def ai_status(principal: CurrentPrincipal, gateway: AIGateway = GatewayDep) -> AIStatusOut:
    """For any signed-in user: whether AI can be used right now (UI shows 'AI unavailable' otherwise)."""
    a = gateway.availability()
    return AIStatusOut(state=a.state, reason=a.reason, usable=a.usable)


@router.get("/gateway", response_model=GatewayOverview)
def gateway_overview(principal: CurrentPrincipal, session: SessionDep, gateway: AIGateway = GatewayDep) -> GatewayOverview:
    ensure_permission(principal, Perm.AI_GATEWAY_MANAGE)
    a, cfg = gateway.availability(), gateway.config
    summary = AIUsageRepository(session).summary_since(start_of_day(datetime.now(UTC)))
    return GatewayOverview(
        state=a.state,
        reason=a.reason,
        usable=a.usable,
        provider="anthropic",
        profiles=[
            ProfileOut(capability=p.capability, model=p.model, effort=p.effort, max_tokens=p.max_tokens, server_fallback=p.server_fallback)
            for p in gateway.profiles()
        ],
        timeout_seconds=cfg.timeout_seconds,
        max_retries=cfg.max_retries,
        max_output_tokens=cfg.max_output_tokens,
        daily_cost_cap_usd=cfg.daily_cost_cap_usd,
        last_success_at=a.last_success_at,
        last_failure_at=a.last_failure_at,
        last_error_category=a.last_error_category,
        today=UsageSummary(**summary),  # type: ignore[arg-type]
    )


@router.post("/health-check", response_model=HealthCheckOut)
def health_check(principal: CurrentPrincipal, session: SessionDep, gateway: AIGateway = GatewayDep) -> HealthCheckOut:
    """Verifies the key and each configured model through the Models API (no tokens are spent)."""
    ensure_permission(principal, Perm.AI_GATEWAY_MANAGE)
    checks = gateway.check_health(actor_user_id=principal.user_id)
    AuditService(session).record(
        "ai.health_checked",
        actor_user_id=principal.user_id,
        entity_type="ai_gateway",
        entity_id=None,
        summary=f"AI health check: {sum(c.ok for c in checks)}/{len(checks)} model(s) reachable",
        changes={c.model: (c.error_category or "ok") for c in checks},
    )
    session.commit()
    a = gateway.availability()
    return HealthCheckOut(
        checks=[ModelCheckOut(model=c.model, ok=c.ok, error_category=c.error_category) for c in checks],
        status=AIStatusOut(state=a.state, reason=a.reason, usable=a.usable),
    )


@router.get("/usage", response_model=Page[UsageOut])
def usage(
    principal: CurrentPrincipal,
    session: SessionDep,
    params: ListParams = Depends(list_params),
    capability: str | None = None,
    status: Literal["succeeded", "failed", "rejected"] | None = None,
) -> Page[UsageOut]:
    ensure_permission(principal, Perm.AI_GATEWAY_MANAGE)
    stmt = AIUsageRepository(session).list_stmt(capability=capability, status=status)
    rows, total, pages = paginate(session, apply_sort(stmt, params.sort, {"created_at": AIUsage.created_at}, "-created_at"), params)
    return Page(items=[UsageOut.model_validate(r) for r in rows], total=total, page=params.page, page_size=params.page_size, pages=pages)
