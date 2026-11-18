"""Phase 7E — 3D property models: upload validation, lifecycle and RBAC, public read-only access.

The files used here are synthetic test geometry (one triangle) generated in code — test data only, never a property.
"""

from __future__ import annotations

import base64
import json
import struct

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.modules.audit.models import AuditLog
from app.modules.realestate.model3d import storage
from tests.business_fixtures import CSRF, Actor

pytestmark = pytest.mark.db


# ------------------------------------------------------------------ synthetic glTF test files
def _triangle_bin() -> bytes:
    return struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)


def _doc(buffer: dict, **extra) -> dict:
    doc = {
        "asset": {"version": "2.0", "generator": "SmartEstate test"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3", "min": [0, 0, 0], "max": [1, 1, 0]}],
        "bufferViews": [{"buffer": 0, "byteLength": 36}],
        "buffers": [buffer],
    }
    doc.update(extra)
    return doc


def glb(**extra) -> bytes:
    j = json.dumps(_doc({"byteLength": 36}, **extra)).encode()
    j += b" " * (-len(j) % 4)
    b = _triangle_bin()
    body = struct.pack("<II", len(j), 0x4E4F534A) + j + struct.pack("<II", len(b), 0x004E4942) + b
    return b"glTF" + struct.pack("<II", 2, 12 + len(body)) + body


def gltf(uri: str | None = None, **extra) -> bytes:
    uri = uri or "data:application/octet-stream;base64," + base64.b64encode(_triangle_bin()).decode()
    return json.dumps(_doc({"byteLength": 36, "uri": uri}, **extra)).encode()


# ------------------------------------------------------------------ fixtures
@pytest.fixture
def store(app, tmp_path):
    settings = get_settings().model_copy(update={"model_storage_dir": str(tmp_path / "models"), "model_max_upload_mb": 1})
    app.dependency_overrides[get_settings] = lambda: settings
    return settings


@pytest.fixture
def people(app, make_user):
    users = {"manager": make_user("sales_manager", name="Sara Manager"), "agent": make_user("sales_agent", name="Agent One"),
             "marketing": make_user("marketing_manager", name="Mona Marketing")}
    return {k: Actor(app, u) for k, u in users.items()}


def anon(app) -> TestClient:
    return TestClient(app, base_url="http://127.0.0.1")


def put_file(actor: Actor, model_id: str, data: bytes, name: str = "model.glb", content_type: str = "application/octet-stream"):
    return actor.client.put(f"/api/v1/realestate/models/{model_id}/file", content=data,
                            headers={**CSRF, "Content-Type": content_type, "X-Filename": name})


def new_model(actor: Actor, project_id, **kw) -> dict:
    body = {"title": "Tower A design model", "representation": "design", "source": "Studio Example (test)", "licence": "Test licence", **kw}
    r = actor.post(f"/realestate/projects/{project_id}/models", body)
    assert r.status_code == 201, r.text
    return r.json()


def approved(actor: Actor, project_id, data: bytes | None = None, name: str = "model.glb", **kw) -> dict:
    m = new_model(actor, project_id, **kw)
    assert put_file(actor, m["id"], data or glb(), name).status_code == 200
    r = actor.post(f"/realestate/models/{m['id']}/approve")
    assert r.status_code == 200, r.text
    return r.json()


# ================================================================== upload validation
@pytest.mark.parametrize(("data", "name", "ctype", "code"), [
    (b"x" * 200, "model.obj", "application/octet-stream", "unsupported_model_type"),
    (glb(), "model.glb", "text/html", "unsupported_model_type"),
    (gltf(), "model.glb", "application/octet-stream", "model_content_mismatch"),
    (glb(), "model.gltf", "application/octet-stream", "model_content_mismatch"),
    (glb()[:-8], "model.glb", "application/octet-stream", "invalid_model"),  # truncated
    (glb() + b"\0" * 8, "model.glb", "application/octet-stream", "invalid_model"),  # trailing data
    (b"glTF" + struct.pack("<II", 1, 80) + b"\0" * 68, "model.glb", "application/octet-stream", "unsupported_gltf_version"),
    (gltf(asset={"version": "1.0"}), "model.gltf", "application/octet-stream", "unsupported_gltf_version"),
    (gltf(uri="tower.bin"), "model.gltf", "application/octet-stream", "external_resources"),
    (gltf(uri="https://cdn.example.com/tower.bin"), "model.gltf", "application/octet-stream", "external_resources"),
    (glb(images=[{"uri": "../../etc/passwd"}]), "model.glb", "application/octet-stream", "external_resources"),
    (glb(meshes=[]), "model.glb", "application/octet-stream", "model_has_no_geometry"),
    (glb(extensionsRequired=["KHR_draco_mesh_compression"]), "model.glb", "application/octet-stream", "unsupported_extension"),
    (b"{not json" + b" " * 80, "model.gltf", "application/octet-stream", "invalid_model"),
    (b"glTF" * 4, "model.glb", "application/octet-stream", "invalid_model"),  # too small
])
def test_uploads_are_validated_server_side(store, people, inventory, data, name, ctype, code):
    m = new_model(people["manager"], inventory.project.id)
    r = put_file(people["manager"], m["id"], data, name, ctype)
    assert r.status_code == 422 and r.json()["error"]["code"] == code, r.text
    folder = storage.root(store)
    assert not folder.exists() or not list(folder.glob("*"))  # nothing stored


def test_size_limit_and_filename_are_enforced(store, people, inventory):
    m = new_model(people["manager"], inventory.project.id)
    big = glb(extras={"pad": "x" * (1024 * 1024)})
    r = put_file(people["manager"], m["id"], big)
    assert r.status_code == 422 and r.json()["error"]["code"] == "model_too_large"
    r = people["manager"].client.put(f"/api/v1/realestate/models/{m['id']}/file", content=glb(),
                                     headers={**CSRF, "Content-Type": "application/octet-stream"})
    assert r.status_code == 422  # X-Filename is required
    r = put_file(people["manager"], m["id"], glb(), "C:\\Users\\me\\Desktop\\tower%20A.glb")
    assert r.status_code == 200 and r.json()["original_filename"] == "tower A.glb"  # path parts dropped


def test_valid_glb_and_embedded_gltf_are_accepted(store, people, inventory):
    for data, name, fmt in ((glb(), "tower.glb", "glb"), (gltf(), "tower.gltf", "gltf")):
        m = new_model(people["manager"], inventory.project.id)
        r = put_file(people["manager"], m["id"], data, name)
        assert r.status_code == 200, r.text
        out = r.json()
        assert (out["format"], out["size_bytes"], out["mesh_count"], out["file_version"], out["status"]) == (fmt, len(data), 1, 1, "draft")
        assert "file_key" not in out and str(storage.root(store)) not in r.text  # no internal paths


# ================================================================== lifecycle + RBAC
def test_lifecycle_replace_and_review_rules(db, store, people, inventory):
    mgr = people["manager"]
    m = new_model(mgr, inventory.project.id, source=None, licence=None)
    assert mgr.post(f"/realestate/models/{m['id']}/approve").json()["error"]["code"] == "model_file_missing"
    put_file(mgr, m["id"], glb())
    assert mgr.post(f"/realestate/models/{m['id']}/approve").json()["error"]["code"] == "model_provenance_missing"
    mgr.patch(f"/realestate/models/{m['id']}", {"source": "Architect (test)", "licence": "Licensed for marketing"})
    out = mgr.post(f"/realestate/models/{m['id']}/approve").json()
    assert out["status"] == "approved" and out["approved_by"]["full_name"] == "Sara Manager" and out["publicly_visible"] is True
    first_files = set(storage.root(store).glob("*.glb"))
    # replacing the file sends it back to review, and the old file is removed
    out = put_file(mgr, m["id"], gltf(), "v2.gltf").json()
    assert (out["status"], out["file_version"], out["approved_by"], out["format"]) == ("draft", 2, None, "gltf")
    assert not (first_files & set(storage.root(store).glob("*")))
    mgr.post(f"/realestate/models/{m['id']}/approve")
    # editing what the public sees also needs a new review
    assert mgr.patch(f"/realestate/models/{m['id']}", {"title": "Renamed"}).json()["status"] == "draft"
    mgr.post(f"/realestate/models/{m['id']}/approve")
    assert mgr.delete(f"/realestate/models/{m['id']}").json()["error"]["code"] == "model_approved"
    assert mgr.post(f"/realestate/models/{m['id']}/archive").json()["status"] == "archived"
    assert mgr.post(f"/realestate/models/{m['id']}/restore").json()["status"] == "draft"
    assert mgr.delete(f"/realestate/models/{m['id']}").status_code == 204
    assert not list(storage.root(store).glob("*.gl*"))
    actions = set(db.scalars(select(AuditLog.action).where(AuditLog.entity_id == m["id"])))
    assert {"realestate.model_created", "realestate.model_file_uploaded", "realestate.model_approved", "realestate.model_archived",
            "realestate.model_restored", "realestate.model_deleted", "realestate.model_updated"} <= actions


def test_units_must_belong_to_the_project(db, store, people, inventory):
    from app.modules.realestate.models import ReProject

    other = ReProject(code="OTH", name="Other", city="Jeddah", status="planning")
    db.add(other)
    db.commit()
    r = people["manager"].post(f"/realestate/projects/{other.id}/models",
                               {"title": "Wrong unit", "representation": "design", "unit_id": str(inventory.units["A-101"].id)})
    assert r.status_code == 422 and r.json()["error"]["code"] == "unit_not_in_project"


def test_only_inventory_managers_manage_models(app, store, people, inventory):
    m = approved(people["manager"], inventory.project.id)
    for who in ("agent", "marketing"):
        a = people[who]
        assert a.get(f"/realestate/projects/{inventory.project.id}/models").status_code == 200  # staff may look
        assert a.get(f"/realestate/models/{m['id']}/file").status_code == 200
        assert "approve" not in a.get(f"/realestate/models/{m['id']}").json()["allowed_actions"]
        assert a.post(f"/realestate/projects/{inventory.project.id}/models", {"title": "x y", "representation": "design"}).status_code == 403
        assert put_file(a, m["id"], glb()).status_code == 403
        for action in ("approve", "archive", "restore"):
            assert a.post(f"/realestate/models/{m['id']}/{action}").status_code == 403
        assert a.patch(f"/realestate/models/{m['id']}", {"title": "Hijack"}).status_code == 403
        assert a.delete(f"/realestate/models/{m['id']}").status_code == 403
    c = anon(app)
    assert c.get(f"/api/v1/realestate/projects/{inventory.project.id}/models").status_code == 401
    assert c.get(f"/api/v1/realestate/models/{m['id']}/file").status_code == 401
    assert c.put(f"/api/v1/realestate/models/{m['id']}/file", content=glb(), headers={**CSRF, "X-Filename": "a.glb"}).status_code == 401


# ================================================================== public access
def test_public_sees_only_approved_models_of_published_projects(app, db, store, people, inventory):
    mgr, c = people["manager"], anon(app)
    data = glb()
    project_model = approved(mgr, inventory.project.id, data, title="Masterplan model", representation="illustrative")
    unit_model = approved(mgr, inventory.project.id, unit_id=str(inventory.units["A-102"].id), title="A-102 interior")
    draft = new_model(mgr, inventory.project.id, title="Unreviewed")
    put_file(mgr, draft["id"], glb())

    detail = c.get("/api/v1/public/projects/TST").json()
    assert [m["title"] for m in detail["models"]] == ["Masterplan model"]  # project-level, approved only
    pm = detail["models"][0]
    assert set(pm) == {"id", "title", "caption", "representation", "credit", "format", "size_bytes", "file_url", "unit_code"}
    assert pm["representation"] == "illustrative" and pm["credit"] == "Studio Example (test) · Test licence"
    assert pm["file_url"] == f"/api/v1/public/models/{project_model['id']}/file?v=1"
    unit = c.get("/api/v1/public/projects/TST/units/A-102").json()
    assert [m["title"] for m in unit["models"]] == ["A-102 interior"] and unit["models"][0]["unit_code"] == "A-102"

    r = c.get(pm["file_url"])
    assert r.status_code == 200 and r.content == data
    assert r.headers["content-type"] == "model/gltf-binary" and r.headers["x-content-type-options"] == "nosniff"
    assert "inline" in r.headers["content-disposition"] and str(store.model_storage_dir) not in str(r.headers)
    assert c.get(f"/api/v1/public/models/{unit_model['id']}/file").status_code == 200
    # drafts, archived, unknown ids: the same 404
    assert c.get(f"/api/v1/public/models/{draft['id']}/file").status_code == 404
    assert c.get("/api/v1/public/models/00000000-0000-0000-0000-000000000000/file").status_code == 404
    assert c.get("/api/v1/public/models/not-a-uuid/file").status_code == 422
    mgr.post(f"/realestate/models/{unit_model['id']}/archive")
    assert c.get(f"/api/v1/public/models/{unit_model['id']}/file").status_code == 404
    assert c.get("/api/v1/public/projects/TST/units/A-102").json()["models"] == []
    # public is read-only
    assert c.put(f"/api/v1/public/models/{project_model['id']}/file", content=b"x", headers=CSRF).status_code == 405
    assert c.delete(f"/api/v1/public/models/{project_model['id']}/file", headers=CSRF).status_code == 405


def test_unpublished_projects_and_private_units_stay_private(app, db, store, people, inventory):
    mgr, c = people["manager"], anon(app)
    inventory.units["A-101"].is_public = False  # an internal-only unit
    db.commit()
    project_model = approved(mgr, inventory.project.id)
    hidden_unit = approved(mgr, inventory.project.id, unit_id=str(inventory.units["A-101"].id))
    assert c.get(f"/api/v1/public/models/{hidden_unit['id']}/file").status_code == 404
    assert mgr.get(f"/realestate/models/{hidden_unit['id']}").json()["publicly_visible"] is False
    inventory.project.is_published = False
    db.commit()
    assert c.get(f"/api/v1/public/models/{project_model['id']}/file").status_code == 404
    assert c.get("/api/v1/public/projects/TST").status_code == 404
    assert mgr.get(f"/realestate/models/{project_model['id']}").json()["publicly_visible"] is False


def test_projects_without_models_return_an_empty_list(app, inventory):
    assert anon(app).get("/api/v1/public/projects/TST").json()["models"] == []
