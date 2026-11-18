"""/marketing/collateral — brochures (PDF) and social posters (PNG) from verified project data.

Every route needs ``marketing.collateral.generate``. Previews return the exact HTML that the export renders; the
download routes return the file as an attachment and write an audit row. Nothing is stored or published.
"""

from __future__ import annotations

import uuid
from urllib.parse import quote

from fastapi import APIRouter, Response

from app.api.deps import CurrentPrincipal, SessionDep, SettingsDep
from app.modules.marketing.collateral.schemas import (
    BrochureRequest,
    CollateralOptions,
    PosterRequest,
    PreviewOut,
    ProjectChoice,
)
from app.modules.marketing.collateral.service import CollateralService

router = APIRouter(prefix="/marketing/collateral", tags=["marketing"])

NO_STORE = {"Cache-Control": "no-store"}


def _download(content: bytes, filename: str, media_type: str) -> Response:
    disposition = f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}"
    return Response(content, media_type=media_type, headers={"Content-Disposition": disposition, **NO_STORE})


@router.get("/projects", response_model=list[ProjectChoice])
def projects(principal: CurrentPrincipal, session: SessionDep, settings: SettingsDep) -> list[ProjectChoice]:
    """Projects that brochures and posters can be made for (published on the website)."""
    return CollateralService(session, settings).projects(principal)


@router.get("/projects/{project_id}", response_model=CollateralOptions)
def options(project_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep, settings: SettingsDep) -> CollateralOptions:
    """The verified fact sheet (read now from the database), what's missing, and the choices for each generator."""
    return CollateralService(session, settings).options(principal, project_id)


@router.post("/brochure/preview", response_model=PreviewOut)
def brochure_preview(body: BrochureRequest, principal: CurrentPrincipal, session: SessionDep, settings: SettingsDep) -> PreviewOut:
    return PreviewOut(html=CollateralService(session, settings).brochure_html(principal, body), width=794, height=None)


@router.post("/brochure", response_class=Response, responses={200: {"content": {"application/pdf": {}}}})
def brochure(body: BrochureRequest, principal: CurrentPrincipal, session: SessionDep, settings: SettingsDep) -> Response:
    pdf, filename = CollateralService(session, settings).brochure_pdf(principal, body)
    return _download(pdf, filename, "application/pdf")


@router.post("/poster/preview", response_model=PreviewOut)
def poster_preview(body: PosterRequest, principal: CurrentPrincipal, session: SessionDep, settings: SettingsDep) -> PreviewOut:
    html, width, height = CollateralService(session, settings).poster_html(principal, body)
    return PreviewOut(html=html, width=width, height=height)


@router.post("/poster", response_class=Response, responses={200: {"content": {"image/png": {}}}})
def poster(body: PosterRequest, principal: CurrentPrincipal, session: SessionDep, settings: SettingsDep) -> Response:
    png, filename = CollateralService(session, settings).poster_png(principal, body)
    return _download(png, filename, "image/png")
