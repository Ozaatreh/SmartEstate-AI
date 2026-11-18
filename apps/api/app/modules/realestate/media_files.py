"""Project image files on local disk under ``COLLATERAL_MEDIA_DIR`` (uploaded from the dashboard).

Files get random names (``<folder>/<uuid hex>.<ext>``); the type is decided by the file's signature, never by its name
or the declared content type. Only JPEG, PNG and WebP are accepted, up to ``MAX_IMAGE_BYTES``.

* Project images (``projects/<code>/…``) are referenced from a project's ``media`` list as ``{"kind": "image", "file":
  …}``. Once **approved** (with source and licence) they are used by brochures/posters and served publicly by
  ``GET /public/projects/{code}/images/{id}`` for published projects.
* Brochure-only images (``collateral/<project id>/…``) carry a ``.json`` sidecar with their source, licence and caption;
  they are offered by the brochure/poster generator for that project only and are never public.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import Settings
from app.core.errors import ValidationFailed
from app.modules.realestate.models import ReProject

API_ROOT = Path(__file__).resolve().parents[3]  # apps/api
IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024
ACCEPTED_UPLOAD_TYPES = {"application/octet-stream", "image/jpeg", "image/png", "image/webp", ""}


def media_root(settings: Settings) -> Path:
    base = Path(settings.collateral_media_dir)
    return (base if base.is_absolute() else API_ROOT / base).resolve()


def resolve(settings: Settings, file: str) -> Path | None:
    """The image's path if ``file`` is a readable image inside the media folder; otherwise None."""
    root = media_root(settings)
    path = (root / file).resolve()
    if not path.is_relative_to(root) or path.suffix.lower() not in IMAGE_TYPES or not path.is_file():
        return None
    return path


def image_id(file: str) -> str:
    return hashlib.sha256(file.encode()).hexdigest()[:12]


def sniff(data: bytes) -> str:
    """The file extension from the content's signature; anything else is refused."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    raise ValidationFailed("Upload a JPEG, PNG or WebP image.", code="unsupported_image")


def check(data: bytes) -> str:
    if not data:
        raise ValidationFailed("The file is empty.", code="empty_image")
    if len(data) > MAX_IMAGE_BYTES:
        raise ValidationFailed(f"Images can be at most {MAX_IMAGE_BYTES // (1024 * 1024)} MB.", code="image_too_large")
    return sniff(data)


def save(settings: Settings, folder: str, data: bytes) -> str:
    """Write the image (atomically) and return its media path relative to the media folder."""
    ext = check(data)
    target = media_root(settings) / folder
    target.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{ext}"
    tmp = target / f".{name}.part"
    tmp.write_bytes(data)
    os.replace(tmp, target / name)
    return f"{folder}/{name}"


def project_folder(project: ReProject) -> str:
    return f"projects/{''.join(c for c in project.code.lower() if c.isalnum()) or 'project'}"


def approved_project_images(settings: Settings, project: ReProject) -> list[tuple[str, dict, Path]]:
    """``(id, media entry, path)`` for the project's approved local images, in media-list order."""
    out = []
    for m in project.media or []:
        if not isinstance(m, dict) or m.get("kind") != "image" or m.get("approved") is not True:
            continue
        file, source, licence = m.get("file"), m.get("source"), m.get("licence")
        if not all(isinstance(x, str) and x.strip() for x in (file, source, licence)):
            continue
        path = resolve(settings, file)
        if path is not None:
            out.append((image_id(file), m, path))
    return out


# ---------------------------------------------------------------- brochure-only images
def collateral_folder(project_id: uuid.UUID) -> str:
    return f"collateral/{project_id.hex}"


def save_collateral_image(
    settings: Settings, project_id: uuid.UUID, data: bytes, *, source: str, licence: str, caption: str | None, uploaded_by: uuid.UUID | None
) -> str:
    file = save(settings, collateral_folder(project_id), data)
    meta = {
        "source": source,
        "licence": licence,
        "caption": caption,
        "uploaded_by": str(uploaded_by) if uploaded_by else None,
        "uploaded_at": datetime.now(UTC).isoformat(),
    }
    (media_root(settings) / file).with_suffix(".json").write_text(json.dumps(meta), encoding="utf-8")
    return file


def collateral_images(settings: Settings, project_id: uuid.UUID) -> list[tuple[str, dict, Path]]:
    """``(id, metadata, path)`` for the brochure-only images uploaded for this project, newest first."""
    folder = media_root(settings) / collateral_folder(project_id)
    if not folder.is_dir():
        return []
    out = []
    for path in folder.iterdir():
        if path.suffix.lower() not in IMAGE_TYPES or path.name.startswith("."):
            continue
        try:
            meta = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not all(isinstance(meta.get(k), str) and meta[k].strip() for k in ("source", "licence")):
            continue
        file = f"{collateral_folder(project_id)}/{path.name}"
        out.append((image_id(file), meta, path))
    out.sort(key=lambda x: x[1].get("uploaded_at") or "", reverse=True)
    return out
