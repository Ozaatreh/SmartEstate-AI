"""Shared FastAPI dependencies: settings, DB session, client IP and the authenticated principal."""

from __future__ import annotations

import ipaddress
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import NotAuthenticated
from app.core.security import SessionClaims, decode_session_token
from app.db.session import get_session
from app.modules.identity.principal import Principal
from app.modules.identity.service import AuthService
from app.modules.identity.throttle import IpThrottle

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[Session, Depends(get_session)]


def client_ip(request: Request) -> str | None:
    host = request.client.host if request.client else None
    try:
        return str(ipaddress.ip_address(host)) if host else None
    except ValueError:
        return None  # e.g. "testclient"; audit ip_address is INET


def get_ip_throttle(request: Request) -> IpThrottle:
    return request.app.state.ip_throttle


def get_auth_service(session: SessionDep, settings: SettingsDep, throttle: IpThrottle = Depends(get_ip_throttle)) -> AuthService:
    return AuthService(session, settings, throttle)


def session_claims(request: Request, settings: SettingsDep) -> SessionClaims:
    token = request.cookies.get(settings.cookie_name)
    claims = decode_session_token(settings, token) if token else None
    if claims is None:
        raise NotAuthenticated()
    return claims


def current_principal(
    request: Request,
    claims: SessionClaims = Depends(session_claims),
    auth: AuthService = Depends(get_auth_service),
) -> Principal:
    principal = auth.principal_from_claims(claims)
    request.state.principal = principal
    return principal


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]
ClientIp = Annotated[str | None, Depends(client_ip)]
