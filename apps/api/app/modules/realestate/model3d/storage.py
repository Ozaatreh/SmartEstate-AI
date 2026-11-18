"""Model files on local disk under ``MODEL_STORAGE_DIR``. Names are random (``<uuid>.<format>``); callers only ever
handle the key, and paths never leave the server."""

from __future__ import annotations

import contextlib
import os
import re
import uuid
from pathlib import Path

from app.core.config import Settings

API_ROOT = Path(__file__).resolve().parents[4]  # apps/api
KEY = re.compile(r"^[0-9a-f]{32}\.(glb|gltf)$")


def root(settings: Settings) -> Path:
    base = Path(settings.model_storage_dir)
    return (base if base.is_absolute() else API_ROOT / base).resolve()


def path_for(settings: Settings, key: str) -> Path:
    if not KEY.match(key):  # keys are generated here; anything else is refused
        raise ValueError("invalid model key")
    return root(settings) / key


def save(settings: Settings, data: bytes, fmt: str) -> str:
    folder = root(settings)
    folder.mkdir(parents=True, exist_ok=True)
    key = f"{uuid.uuid4().hex}.{fmt}"
    tmp = folder / f".{key}.part"
    tmp.write_bytes(data)
    os.replace(tmp, folder / key)
    return key


def delete(settings: Settings, key: str | None) -> None:
    if key:
        with contextlib.suppress(ValueError, OSError):
            path_for(settings, key).unlink(missing_ok=True)
