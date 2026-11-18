from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import text

from app.api.deps import SessionDep, SettingsDep

router = APIRouter(tags=["health"])


class AIHealth(BaseModel):
    state: Literal["disabled", "misconfigured", "unverified", "operational", "degraded"]
    reason: str


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    environment: str
    database: Literal["ok", "unavailable"]
    ai: AIHealth


@router.get("/health", response_model=HealthOut)
def health(request: Request, session: SessionDep, settings: SettingsDep) -> HealthOut:
    try:
        session.execute(text("SELECT 1"))
        db = "ok"
    except Exception:
        db = "unavailable"
    ai = request.app.state.ai_gateway.availability()  # configuration + last real outcome; never raises, no network call
    return HealthOut(
        status="ok" if db == "ok" else "degraded",
        version=settings.app_version,
        environment=settings.app_env,
        database=db,  # type: ignore[arg-type]
        ai=AIHealth(state=ai.state, reason=ai.reason),
    )
