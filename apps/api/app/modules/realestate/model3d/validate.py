"""Server-side validation of uploaded 3D models (glTF 2.0: binary .glb or self-contained .gltf).

Checks, in order: size limits, extension ↔ content (the bytes decide, not the browser's Content-Type), GLB header and
chunk layout, glTF JSON structure and ``asset.version`` 2.x, at least one mesh, no external resources (every buffer
or image must be inside the file — the public viewer never fetches anything else), and no required extensions the
viewer can't decode (Draco, meshopt, KTX2/Basis). Anything else is rejected with a specific error code.
"""

from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass

from app.core.errors import ValidationFailed

GLB_MAGIC = b"glTF"
CHUNK_JSON = 0x4E4F534A
CHUNK_BIN = 0x004E4942
MIN_BYTES = 64
UNSUPPORTED_REQUIRED = {
    "KHR_draco_mesh_compression",
    "EXT_meshopt_compression",
    "KHR_texture_basisu",
    "EXT_texture_webp",
    "EXT_texture_avif",
}
EXTENSIONS = {".glb": "glb", ".gltf": "gltf"}


class InvalidModel(ValidationFailed):
    code = "invalid_model"
    message = "The file isn't a valid glTF 2.0 model."


@dataclass(frozen=True)
class ModelFile:
    format: str
    size_bytes: int
    sha256: str
    mesh_count: int


def _fail(message: str, code: str) -> InvalidModel:
    return InvalidModel(message, code=code)


def format_for(filename: str) -> str:
    name = filename.strip().lower()
    for ext, fmt in EXTENSIONS.items():
        if name.endswith(ext):
            return fmt
    raise _fail("Upload a .glb or .gltf file.", "unsupported_model_type")


def _check_document(doc: object, *, has_bin_chunk: bool) -> int:
    if not isinstance(doc, dict):
        raise _fail("The glTF JSON must be an object.", "invalid_model")
    asset = doc.get("asset")
    version = asset.get("version") if isinstance(asset, dict) else None
    if not isinstance(version, str) or not version.startswith("2."):
        raise _fail("Only glTF 2.0 models are supported.", "unsupported_gltf_version")
    required = doc.get("extensionsRequired") or []
    if not isinstance(required, list):
        raise _fail("extensionsRequired must be a list.", "invalid_model")
    blocked = sorted(set(map(str, required)) & UNSUPPORTED_REQUIRED)
    if blocked:
        raise _fail(
            f"The viewer can't decode these required extensions: {', '.join(blocked)}. Export without compression.",
            "unsupported_extension",
        )
    meshes = doc.get("meshes")
    if not isinstance(meshes, list) or not meshes:
        raise _fail("The model has no geometry (no meshes).", "model_has_no_geometry")
    for kind in ("buffers", "images"):
        items = doc.get(kind) or []
        if not isinstance(items, list):
            raise _fail(f"{kind} must be a list.", "invalid_model")
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                raise _fail(f"{kind}[{i}] is invalid.", "invalid_model")
            uri = item.get("uri")
            if uri is None:
                # GLB: buffer 0 is the BIN chunk; images then point at a bufferView
                if kind == "buffers" and not (i == 0 and has_bin_chunk):
                    raise _fail("A buffer has no data.", "invalid_model")
                continue
            if not isinstance(uri, str) or not uri.startswith("data:"):
                raise _fail(
                    "The model refers to external files. Export a single .glb, or a .gltf with embedded data.", "external_resources"
                )
    return len(meshes)


def validate_model(data: bytes, filename: str, *, max_bytes: int) -> ModelFile:
    fmt = format_for(filename)
    size = len(data)
    if size > max_bytes:
        raise _fail(f"The file is larger than the {max_bytes // (1024 * 1024)} MB limit.", "model_too_large")
    if size < MIN_BYTES:
        raise _fail("The file is too small to be a 3D model.", "invalid_model")
    is_glb = data[:4] == GLB_MAGIC
    if fmt == "glb" and not is_glb:
        raise _fail("This .glb file isn't binary glTF.", "model_content_mismatch")
    if fmt == "gltf" and is_glb:
        raise _fail("This is a binary glTF file; name it .glb.", "model_content_mismatch")

    if is_glb:
        version, length = struct.unpack_from("<II", data, 4)
        if version != 2:
            raise _fail("Only glTF 2.0 models are supported.", "unsupported_gltf_version")
        if length != size:
            raise _fail("The file is truncated or has trailing data.", "invalid_model")
        offset, json_doc, has_bin = 12, None, False
        while offset < size:
            if offset + 8 > size:
                raise _fail("A chunk header is cut off.", "invalid_model")
            chunk_len, chunk_type = struct.unpack_from("<II", data, offset)
            start, end = offset + 8, offset + 8 + chunk_len
            if end > size or chunk_len % 4:
                raise _fail("A chunk is out of bounds or misaligned.", "invalid_model")
            if offset == 12:
                if chunk_type != CHUNK_JSON:
                    raise _fail("The first chunk must be JSON.", "invalid_model")
                try:
                    json_doc = json.loads(data[start:end].decode("utf-8").rstrip(" \x00"))
                except (UnicodeDecodeError, ValueError) as e:
                    raise _fail("The model's JSON chunk can't be read.", "invalid_model") from e
            elif chunk_type == CHUNK_BIN:
                if has_bin:
                    raise _fail("More than one binary chunk.", "invalid_model")
                has_bin = True
            offset = end
        meshes = _check_document(json_doc, has_bin_chunk=has_bin)
    else:
        try:
            doc = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as e:
            raise _fail("This .gltf file isn't valid JSON.", "invalid_model") from e
        meshes = _check_document(doc, has_bin_chunk=False)

    return ModelFile(format=fmt, size_bytes=size, sha256=hashlib.sha256(data).hexdigest(), mesh_count=meshes)
