"""Image uploads from the dashboard (raw request body, original name in ``X-Filename`` — no multipart parser).

* ``PUT /realestate/projects/{id}/media/images`` — a project image (``realestate.inventory.manage``). The file is
  stored; it becomes part of the project when the project's media list is saved with it (audited as a project update).
* ``GET /realestate/projects/{id}/media/file?file=…`` — staff preview of one of the project's local images.
* ``PUT /marketing/collateral/projects/{id}/images`` — a brochure/poster-only image (``marketing.collateral.generate``),
  with its source, licence and optional caption; it never changes the project or the website.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Header, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.deps import CurrentPrincipal, SessionDep, SettingsDep
from app.core.config import Settings
from app.core.errors import NotFound, ValidationFailed
from app.core.permissions import Perm
from app.modules.audit.service import AuditService
from app.modules.identity.principal import Principal, ensure_permission
from app.modules.realestate import media_files
from app.modules.realestate.model3d.router import clean_filename
from app.modules.realestate.models import ReProject

router = APIRouter(tags=["realestate"])


class UploadedImage(BaseModel):
    file: str
    id: str
    size_bytes: int


class CollateralImageOut(BaseModel):
    id: str
    caption: str | None
    source: str
    licence: str


async def _read_image(request: Request) -> bytes:
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type not in media_files.ACCEPTED_UPLOAD_TYPES:
        raise ValidationFailed("Send the image as application/octet-stream.", code="unsupported_image")
    limit = media_files.MAX_IMAGE_BYTES
    declared = request.headers.get("content-length")
    too_big = ValidationFailed(f"Images can be at most {limit // (1024 * 1024)} MB.", code="image_too_large")
    if declared and declared.isdigit() and int(declared) > limit:
        raise too_big
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise too_big
        chunks.append(chunk)
    return b"".join(chunks)


def _project(session, project_id: uuid.UUID) -> ReProject:
    project = session.get(ReProject, project_id)
    if project is None:
        raise NotFound("Project not found.")
    return project


def _store_project_image(session, settings: Settings, principal: Principal, project_id: uuid.UUID, data: bytes, name: str) -> UploadedImage:
    ensure_permission(principal, Perm.REALESTATE_INVENTORY_MANAGE)
    project = _project(session, project_id)
    media_files.check(data)  # validate before anything is written
    file = media_files.save(settings, media_files.project_folder(project), data)
    AuditService(session).record(
        "realestate.media_image_uploaded",
        actor_user_id=principal.user_id,
        entity_type="re_project",
        entity_id=project.id,
        summary=f"{project.code}: image uploaded ({name[-80:]}, {len(data):,} bytes) as {file}",
    )
    session.commit()
    return UploadedImage(file=file, id=media_files.image_id(file), size_bytes=len(data))


@router.put("/realestate/projects/{project_id}/media/images", response_model=UploadedImage, status_code=status.HTTP_201_CREATED)
async def upload_project_image(
    project_id: uuid.UUID,
    request: Request,
    principal: CurrentPrincipal,
    session: SessionDep,
    settings: SettingsDep,
    x_filename: str = Header(..., max_length=600),
) -> UploadedImage:
    ensure_permission(principal, Perm.REALESTATE_INVENTORY_MANAGE)  # before reading the body
    name = clean_filename(x_filename)
    data = await _read_image(request)
    return await run_in_threadpool(_store_project_image, session, settings, principal, project_id, data, name)


@router.get("/realestate/projects/{project_id}/media/file", response_class=FileResponse)
def project_image_file(
    project_id: uuid.UUID,
    principal: CurrentPrincipal,
    session: SessionDep,
    settings: SettingsDep,
    file: str = Query(..., max_length=200),
) -> FileResponse:
    """Staff preview: one of this project's images (listed in its media, or uploaded for it and not yet saved)."""
    ensure_permission(principal, Perm.REALESTATE_INVENTORY_READ)
    project = _project(session, project_id)
    listed = any(isinstance(m, dict) and m.get("file") == file for m in project.media or [])
    if not (listed or file.startswith(media_files.project_folder(project) + "/")):
        raise NotFound("Image not found.")
    path = media_files.resolve(settings, file)
    if path is None:
        raise NotFound("Image not found.")
    return FileResponse(
        path,
        media_type=media_files.IMAGE_TYPES[path.suffix.lower()],
        headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"},
    )


def _store_collateral_image(
    session, settings: Settings, principal: Principal, project_id: uuid.UUID, data: bytes, meta: dict
) -> CollateralImageOut:
    ensure_permission(principal, Perm.MARKETING_COLLATERAL_GENERATE)
    project = _project(session, project_id)
    if not project.is_published:
        raise ValidationFailed("Brochures and posters can only be made for published projects.", code="project_not_published")
    media_files.check(data)
    file = media_files.save_collateral_image(settings, project.id, data, uploaded_by=principal.user_id, **meta)
    AuditService(session).record(
        "marketing.collateral_image_uploaded",
        actor_user_id=principal.user_id,
        entity_type="re_project",
        entity_id=project.id,
        summary=f"{project.code}: brochure/poster image uploaded ({len(data):,} bytes) · source {meta['source']}",
        changes={"source": [None, meta["source"]], "licence": [None, meta["licence"]]},
    )
    session.commit()
    return CollateralImageOut(id=media_files.image_id(file), **meta)


@router.put("/marketing/collateral/projects/{project_id}/images", response_model=CollateralImageOut, status_code=status.HTTP_201_CREATED)
async def upload_collateral_image(
    project_id: uuid.UUID,
    request: Request,
    principal: CurrentPrincipal,
    session: SessionDep,
    settings: SettingsDep,
    source: str = Query(..., min_length=1, max_length=150),
    licence: str = Query(..., min_length=1, max_length=150),
    caption: str | None = Query(default=None, max_length=150),
    x_filename: str = Header(..., max_length=600),
) -> CollateralImageOut:
    """An image used only by this project's brochures and posters (never on the website)."""
    ensure_permission(principal, Perm.MARKETING_COLLATERAL_GENERATE)
    clean_filename(x_filename)
    meta = {"source": source.strip(), "licence": licence.strip(), "caption": (caption or "").strip() or None}
    if not meta["source"] or not meta["licence"]:
        raise ValidationFailed("Record the image's source and licence.", code="image_rights_required")
    data = await _read_image(request)
    return await run_in_threadpool(_store_collateral_image, session, settings, principal, project_id, data, meta)
