"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.ai.features.bi_agent import router as bi_agent_router
from app.ai.features.property_assistant import router as property_assistant_router
from app.ai.gateway import AIGateway
from app.ai.router import router as ai_router
from app.ai.status import log_ai_status, resolve_ai_status
from app.automation.router import router as automation_router
from app.core.config import Settings, get_settings
from app.core.handlers import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import CsrfHeaderMiddleware, RequestContextMiddleware
from app.modules.approvals.router import router as approvals_router
from app.modules.audit.router import router as audit_router
from app.modules.crm.router import router as crm_router
from app.modules.finance.router import router as finance_router
from app.modules.health.router import router as health_router
from app.modules.hr.router import router as hr_router
from app.modules.identity.router import router as auth_router
from app.modules.identity.throttle import IpThrottle
from app.modules.marketing.collateral.router import router as collateral_router
from app.modules.marketing.router import router as marketing_router
from app.modules.notifications.router import router as notifications_router
from app.modules.procurement.router import router as procurement_router  # also registers the purchase-request approval subject
from app.modules.realestate.media_router import router as media_router
from app.modules.realestate.model3d.router import router as model3d_router
from app.modules.realestate.router import router as realestate_router
from app.public.router import router as public_router

log = logging.getLogger(__name__)
API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        log.info("Starting %s %s (%s)", settings.app_name, settings.app_version, settings.app_env)
        log_ai_status(app.state.ai_status)
        yield

    docs = settings.app_env != "production"
    app = FastAPI(
        title=f"{settings.app_name} API",
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
    )
    # Startup resilience: computed eagerly, never raises.
    app.state.ai_status = resolve_ai_status(settings)
    app.state.ai_gateway = AIGateway(settings)  # no network call; the provider client is created on first use
    app.state.ip_throttle = IpThrottle(settings.login_ip_max_failures, settings.login_ip_window_minutes * 60)

    register_exception_handlers(app)
    app.add_middleware(CsrfHeaderMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-Requested-With", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestContextMiddleware)

    api = APIRouter(prefix=API_PREFIX)
    for r in (
        health_router,
        auth_router,
        notifications_router,
        audit_router,
        hr_router,
        finance_router,
        procurement_router,
        approvals_router,
        crm_router,
        automation_router,
        realestate_router,
        ai_router,
        bi_agent_router,
        property_assistant_router,
        public_router,
        marketing_router,
        collateral_router,
        model3d_router,
        media_router,
    ):
        api.include_router(r)
    app.include_router(api)
    return app


app = create_app()
