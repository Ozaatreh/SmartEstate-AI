from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import ClientIp, CurrentPrincipal, SessionDep, SettingsDep, get_auth_service, session_claims
from app.core.config import Settings
from app.core.errors import NotAuthenticated
from app.core.security import SessionClaims
from app.modules.identity.repository import IdentityRepository
from app.modules.identity.schemas import LoginRequest, MeResponse
from app.modules.identity.service import AuthService, build_principal, me_response

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        settings.cookie_name,
        token,
        max_age=settings.session_ttl_minutes * 60,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/api",
    )


@router.post("/login", response_model=MeResponse)
def login(body: LoginRequest, response: Response, ip: ClientIp, settings: SettingsDep,
          auth: AuthService = Depends(get_auth_service)) -> MeResponse:
    user, token, claims = auth.login(body.email, body.password, ip)
    _set_cookie(response, settings, token)
    return me_response(user, build_principal(user), claims.expires_at)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, principal: CurrentPrincipal, ip: ClientIp, settings: SettingsDep,
           auth: AuthService = Depends(get_auth_service)) -> Response:
    auth.logout(principal, ip)
    response.status_code = status.HTTP_204_NO_CONTENT
    response.delete_cookie(settings.cookie_name, path="/api", secure=settings.secure_cookies, httponly=True, samesite="lax")
    return response


@router.get("/me", response_model=MeResponse)
def me(principal: CurrentPrincipal, session: SessionDep, claims: SessionClaims = Depends(session_claims)) -> MeResponse:
    user = IdentityRepository(session).get_user(principal.user_id)
    if user is None:  # deleted between principal resolution and now
        raise NotAuthenticated()
    return me_response(user, principal, claims.expires_at)
