from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.api.deps import CurrentPrincipal, SessionDep
from app.common.listing import ListParams, Page, list_params
from app.modules.notifications.service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    level: str
    title: str
    body: str | None
    link: str | None
    entity_type: str | None
    entity_id: str | None
    read_at: datetime | None
    created_at: datetime


class UnreadCount(BaseModel):
    unread: int


class MarkedCount(BaseModel):
    marked: int


@router.get("", response_model=Page[NotificationOut])
def list_notifications(principal: CurrentPrincipal, session: SessionDep, params: ListParams = Depends(list_params),
                       unread_only: bool = False) -> Page[NotificationOut]:
    rows, total, pages = NotificationService(session).list(principal, params, unread_only=unread_only)
    return Page(items=[NotificationOut.model_validate(r) for r in rows], total=total,
                page=params.page, page_size=params.page_size, pages=pages)


@router.get("/unread-count", response_model=UnreadCount)
def unread_count(principal: CurrentPrincipal, session: SessionDep) -> UnreadCount:
    return UnreadCount(unread=NotificationService(session).unread_count(principal))


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(notification_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep) -> NotificationOut:
    return NotificationOut.model_validate(NotificationService(session).mark_read(principal, notification_id))


@router.post("/read-all", response_model=MarkedCount)
def mark_all_read(principal: CurrentPrincipal, session: SessionDep) -> MarkedCount:
    return MarkedCount(marked=NotificationService(session).mark_all_read(principal))
