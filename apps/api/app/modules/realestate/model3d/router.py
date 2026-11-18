"""Internal routes for 3D property models (staff only; RBAC in the service).

Upload is a raw request body (``Content-Type: application/octet-stream`` or a glTF type) with the original file name in
``X-Filename`` — no multipart parser needed. The body is read with a hard size cap before any validation.
"""

from __future__ import annotations

import uuid
from urllib.parse import unquote

from fastapi import APIRouter, Header, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from app.api.deps import CurrentPrincipal, SessionDep, SettingsDep
from app.core.errors import ValidationFailed
from app.modules.realestate.model3d.schemas import ModelIn, ModelOut, ModelUpdate, UploadLimits
from app.modules.realestate.model3d.service import PropertyModelService
from app.modules.realestate.model3d.validate import InvalidModel

router = APIRouter(prefix="/realestate", tags=["realestate"])

MEDIA_TYPES = {"glb": "model/gltf-binary", "gltf": "model/gltf+json"}
ACCEPTED_CONTENT_TYPES = {"application/octet-stream", "model/gltf-binary", "model/gltf+json", "application/json", ""}


async def read_capped(request: Request, max_bytes: int) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > max_bytes:
        raise InvalidModel(f"The file is larger than the {max_bytes // (1024 * 1024)} MB limit.", code="model_too_large")
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > max_bytes:
            raise InvalidModel(f"The file is larger than the {max_bytes // (1024 * 1024)} MB limit.", code="model_too_large")
        chunks.append(chunk)
    return b"".join(chunks)


def clean_filename(raw: str) -> str:
    name = unquote(raw).replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not name or len(name) > 200 or any(ord(c) < 32 for c in name):
        raise ValidationFailed("Send the file name in the X-Filename header.", code="invalid_filename")
    return name


@router.get("/models/limits", response_model=UploadLimits)
def limits(principal: CurrentPrincipal, session: SessionDep, settings: SettingsDep) -> UploadLimits:
    return PropertyModelService(session, settings).limits()


@router.get("/projects/{project_id}/models", response_model=list[ModelOut])
def list_models(project_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep, settings: SettingsDep) -> list[ModelOut]:
    return PropertyModelService(session, settings).list_for_project(principal, project_id)


@router.post("/projects/{project_id}/models", response_model=ModelOut, status_code=status.HTTP_201_CREATED)
def create_model(project_id: uuid.UUID, body: ModelIn, principal: CurrentPrincipal, session: SessionDep, settings: SettingsDep) -> ModelOut:
    return PropertyModelService(session, settings).create(principal, project_id, body)


@router.get("/models/{model_id}", response_model=ModelOut)
def get_model(model_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep, settings: SettingsDep) -> ModelOut:
    return PropertyModelService(session, settings).get(principal, model_id)


@router.patch("/models/{model_id}", response_model=ModelOut)
def update_model(
    model_id: uuid.UUID, body: ModelUpdate, principal: CurrentPrincipal, session: SessionDep, settings: SettingsDep
) -> ModelOut:
    return PropertyModelService(session, settings).update(principal, model_id, body)


@router.put("/models/{model_id}/file", response_model=ModelOut)
async def upload_model_file(
    model_id: uuid.UUID,
    request: Request,
    principal: CurrentPrincipal,
    session: SessionDep,
    settings: SettingsDep,
    x_filename: str = Header(..., max_length=600),
) -> ModelOut:
    """Upload or replace the file (raw body). Validated server-side; the model goes back to draft for review."""
    svc = PropertyModelService(session, settings)
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type not in ACCEPTED_CONTENT_TYPES:
        raise InvalidModel("Send the file as application/octet-stream (or a glTF media type).", code="unsupported_model_type")
    filename = clean_filename(x_filename)
    data = await read_capped(request, svc.max_bytes)
    return await run_in_threadpool(svc.upload, principal, model_id, data, filename)


@router.get("/models/{model_id}/file")
def download_model_file(model_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep, settings: SettingsDep) -> FileResponse:
    """Staff download (any status) to check a model before approving it."""
    path, m = PropertyModelService(session, settings).file(principal, model_id)
    return FileResponse(
        path,
        media_type=MEDIA_TYPES[m.format or "glb"],
        filename=f"{m.project.code}-model-v{m.file_version}.{m.format}",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/models/{model_id}/approve", response_model=ModelOut)
def approve_model(model_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep, settings: SettingsDep) -> ModelOut:
    return PropertyModelService(session, settings).approve(principal, model_id)


@router.post("/models/{model_id}/archive", response_model=ModelOut)
def archive_model(model_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep, settings: SettingsDep) -> ModelOut:
    return PropertyModelService(session, settings).archive(principal, model_id)


@router.post("/models/{model_id}/restore", response_model=ModelOut)
def restore_model(model_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep, settings: SettingsDep) -> ModelOut:
    return PropertyModelService(session, settings).restore(principal, model_id)


@router.delete("/models/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model(model_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep, settings: SettingsDep) -> Response:
    PropertyModelService(session, settings).delete(principal, model_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
