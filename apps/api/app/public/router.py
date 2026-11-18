"""Public API for the marketing website — anonymous, read-mostly, explicitly allowlisted.

Every route here is reachable without signing in, so each one returns only the dedicated public schemas from
``app/public/catalog.py`` (or accepts a validated inquiry). Nothing in this router reads the session cookie or a
principal. All other routes of the API require authentication; ``tests/test_public_api.py`` enforces that boundary
over the whole route table, independently of either frontend.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import FileResponse

from app.api.deps import ClientIp, SessionDep, SettingsDep
from app.core.errors import TooManyRequests, ValidationFailed
from app.modules.identity.throttle import IpThrottle
from app.modules.realestate import media_files
from app.modules.realestate.model3d import storage
from app.public import catalog
from app.public.inquiries import FormToken, InquiryAccepted, InquiryIn, InquiryService, contact_keys, issue_token, token_verdict

router = APIRouter(prefix="/public", tags=["public"])

RATE_WINDOW_SECONDS = 10 * 60
MAX_INQUIRIES_PER_IP = 5  # per window
MAX_INQUIRIES_PER_CONTACT = 3  # per window, per e-mail / phone


@router.get("/projects", response_model=list[catalog.PublicProject])
def list_projects(session: SessionDep) -> list[catalog.PublicProject]:
    return catalog.list_projects(session)


@router.get("/projects/{code}", response_model=catalog.PublicProjectDetail)
def get_project(code: str, session: SessionDep) -> catalog.PublicProjectDetail:
    return catalog.project_detail(session, code)


@router.get("/projects/{code}/units", response_model=list[catalog.PublicUnit])
def list_units(
    code: str,
    session: SessionDep,
    bedrooms: int | None = Query(default=None, ge=0, le=10),
    min_price: Decimal | None = Query(default=None, ge=0),
    max_price: Decimal | None = Query(default=None, ge=0),
    unit_type: Literal["studio", "apartment", "duplex", "penthouse", "townhouse"] | None = None,
) -> list[catalog.PublicUnit]:
    """Available public units of a published project."""
    project = catalog.get_published_project(session, code)
    return catalog.search_units(
        session, project_code=project.code, bedrooms=bedrooms, min_price=min_price, max_price=max_price, unit_type=unit_type, limit=200
    )


@router.get("/projects/{code}/units/{unit_code}", response_model=catalog.PublicUnitDetail)
def get_unit(code: str, unit_code: str, session: SessionDep) -> catalog.PublicUnitDetail:
    return catalog.unit_detail(session, code, unit_code)


@router.get("/projects/{code}/images/{image_id}", response_class=FileResponse, responses={200: {"content": {"image/jpeg": {}}}})
def get_project_image(code: str, image_id: str, session: SessionDep, settings: SettingsDep) -> FileResponse:
    """An approved uploaded image of a published project (e.g. its website cover). Read-only; 404 for anything else."""
    if not image_id.isalnum() or len(image_id) != 12:
        raise catalog.NotFound("Image not found.")
    path = catalog.public_image_path(settings, session, code, image_id)
    return FileResponse(
        path,
        media_type=media_files.IMAGE_TYPES[path.suffix.lower()],
        headers={"Cache-Control": "public, max-age=300", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/models/{model_id}/file", response_class=FileResponse, responses={200: {"content": {"model/gltf-binary": {}}}})
def get_model_file(model_id: uuid.UUID, session: SessionDep, settings: SettingsDep) -> FileResponse:
    """An approved 3D model of a published project (and public unit). Read-only; 404 for anything else."""
    m = catalog.public_model(session, model_id)
    path = storage.path_for(settings, m.file_key) if m.file_key else None
    if path is None or not path.is_file():
        raise catalog.NotFound("3D model not found.")
    return FileResponse(
        path,
        media_type="model/gltf-binary" if m.format == "glb" else "model/gltf+json",
        headers={
            "Cache-Control": "public, max-age=300",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'inline; filename="{m.project.code.lower()}-model.{m.format}"',
            "ETag": f'"{m.sha256}"',
        },
    )


# --- inquiries ----------------------------------------------------------------------------------------------------
def _limiters(request: Request) -> tuple[IpThrottle, IpThrottle]:
    state = request.app.state
    if not hasattr(state, "inquiry_ip_limiter"):
        state.inquiry_ip_limiter = IpThrottle(MAX_INQUIRIES_PER_IP, RATE_WINDOW_SECONDS)
        state.inquiry_contact_limiter = IpThrottle(MAX_INQUIRIES_PER_CONTACT, RATE_WINDOW_SECONDS)
    return state.inquiry_ip_limiter, state.inquiry_contact_limiter


@router.get("/inquiries/form-token", response_model=FormToken)
def inquiry_form_token(settings: SettingsDep) -> FormToken:
    """Issued when the form is shown; a submission must come at least a few seconds later (bots are faster)."""
    return issue_token(settings)


@router.post("/inquiries", response_model=InquiryAccepted, status_code=status.HTTP_202_ACCEPTED)
def submit_inquiry(body: InquiryIn, request: Request, session: SessionDep, settings: SettingsDep, ip: ClientIp) -> InquiryAccepted:
    """Contact / viewing request → CRM lead (or a timeline entry on a recent matching lead). Same answer either way."""
    by_ip, by_contact = _limiters(request)
    ip_key = ip or (request.client.host if request.client else "unknown")
    if by_ip.is_blocked(ip_key):
        raise TooManyRequests("Too many requests from your network. Please try again later.", code="inquiry_rate_limited")
    by_ip.record_failure(ip_key)  # IpThrottle counts events in a sliding window
    verdict = token_verdict(settings, body.form_token)
    if body.website or verdict in ("too_fast", "invalid"):
        return InquiryAccepted()  # spam signal: look successful, store nothing
    if verdict == "expired":
        raise ValidationFailed(
            "This form has expired. Please reload the page and try again.",
            details={"fields": [{"field": "form_token", "message": "The form expired."}]},
        )
    keys = contact_keys(body)
    if any(by_contact.is_blocked(k) for k in keys):
        raise TooManyRequests("We've already received several requests from you. Our team will be in touch.", code="inquiry_rate_limited")
    for k in keys:
        by_contact.record_failure(k)
    InquiryService(session).submit(body)
    return InquiryAccepted()
