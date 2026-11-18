"""Image uploads from the device: project images (website cover, brochures) and brochure/poster-only images.

Files are checked by their signature, size-capped and stored under random names; an uploaded project image is public
only after it is saved in the project's media as approved (with source and licence); brochure-only images never reach
the website; every upload is permission-checked and audited.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.modules.audit.models import AuditLog
from app.modules.realestate import media_files
from app.modules.realestate.models import ReProject
from tests.business_fixtures import CSRF, Actor
from tests.test_db_collateral import tiny_png

pytestmark = pytest.mark.db


@pytest.fixture
def media_dir(app, tmp_path):
    app.dependency_overrides[get_settings] = lambda: get_settings().model_copy(update={"collateral_media_dir": str(tmp_path)})
    return tmp_path


@pytest.fixture
def project(db) -> ReProject:
    p = ReProject(code="REAL", name="Real Court", city="Riyadh", status="launched", is_published=True)
    db.add(p)
    db.commit()
    return p


@pytest.fixture
def actors(app, make_user):
    made: dict[str, Actor] = {}

    def get(role: str) -> Actor:
        if role not in made:
            made[role] = Actor(app, make_user(role, name=f"{role} user"))
        return made[role]

    return get


def upload(actor: Actor, path: str, data: bytes, name: str = "hero.png"):
    return actor.client.put(
        "/api/v1" + path, content=data, headers={**CSRF, "Content-Type": "application/octet-stream", "X-Filename": name}
    )


def anon(app) -> TestClient:
    return TestClient(app, base_url="http://127.0.0.1")


def test_project_image_upload_becomes_the_website_cover_once_approved(app, db, media_dir, project, actors):
    manager = actors("sales_manager")
    r = upload(manager, f"/realestate/projects/{project.id}/media/images", tiny_png(), "My Render.PNG")
    assert r.status_code == 201, r.text
    up = r.json()
    assert up["file"].startswith("projects/real/") and up["file"].endswith(".png") and up["size_bytes"] == len(tiny_png())
    assert (media_dir / up["file"]).read_bytes() == tiny_png()
    assert db.scalar(select(AuditLog).where(AuditLog.action == "realestate.media_image_uploaded")).entity_id == str(project.id)

    # Staff can preview it before saving; the website can't see it yet.
    assert manager.get(f"/realestate/projects/{project.id}/media/file", params={"file": up["file"]}).status_code == 200
    assert anon(app).get(f"/api/v1/public/projects/REAL/images/{up['id']}").status_code == 404

    link = {"url": "https://example.com/old.jpg", "kind": "image"}
    entry = {"kind": "image", "file": up["file"], "approved": False, "caption": "Entrance"}
    assert manager.patch(f"/realestate/projects/{project.id}", {"media": [entry, link]}).status_code == 200
    public = anon(app).get("/api/v1/public/projects/REAL").json()
    assert public["cover_image"] == link["url"]  # not approved: not public, the link is the cover
    assert anon(app).get(f"/api/v1/public/projects/REAL/images/{up['id']}").status_code == 404

    approved = {**entry, "approved": True, "source": "Studio X", "licence": "Licensed for marketing"}
    assert manager.patch(f"/realestate/projects/{project.id}", {"media": [approved, link]}).status_code == 200
    public = anon(app).get("/api/v1/public/projects/REAL").json()
    cover = f"/api/v1/public/projects/REAL/images/{up['id']}"
    assert public["cover_image"] == cover and public["media"][0] == {"url": cover, "caption": "Entrance", "kind": "image"}
    assert up["file"] not in str(public)  # the storage path is never public
    assert [p["cover_image"] for p in anon(app).get("/api/v1/public/projects").json()] == [cover]
    img = anon(app).get(cover)
    assert img.status_code == 200 and img.headers["content-type"] == "image/png" and img.content == tiny_png()
    assert img.headers["x-content-type-options"] == "nosniff"

    # Changing the order changes the cover immediately; unpublishing hides the file.
    assert manager.patch(f"/realestate/projects/{project.id}", {"media": [link, approved]}).status_code == 200
    assert anon(app).get("/api/v1/public/projects/REAL").json()["cover_image"] == link["url"]
    project.is_published = False
    db.commit()
    assert anon(app).get(cover).status_code == 404


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"<html>not an image</html>", "unsupported_image"),
        (b"GIF89a" + b"\x00" * 20, "unsupported_image"),
        (b"", "empty_image"),
        (b"\xff\xd8\xff" + b"\x00" * (10 * 1024 * 1024), "image_too_large"),
    ],
)
def test_only_real_images_within_the_size_limit_are_stored(media_dir, project, actors, data, code):
    r = upload(actors("sales_manager"), f"/realestate/projects/{project.id}/media/images", data, "photo.jpg")
    assert r.status_code == 422 and r.json()["error"]["code"] == code
    assert not any(media_dir.rglob("*.*"))


def test_upload_and_preview_permissions(app, db, media_dir, project, actors):
    path = f"/realestate/projects/{project.id}/media/images"
    for role in ("sales_agent", "marketing_manager"):
        assert upload(actors(role), path, tiny_png()).status_code == 403
    assert anon(app).put("/api/v1" + path, content=tiny_png(), headers={**CSRF, "X-Filename": "a.png"}).status_code == 401
    up = upload(actors("sales_manager"), path, tiny_png()).json()
    other = ReProject(code="OTHR", name="Other", city="Riyadh", status="launched", is_published=True)
    db.add(other)
    db.commit()
    viewer = actors("sales_agent")  # can read inventory
    assert viewer.get(f"/realestate/projects/{project.id}/media/file", params={"file": up["file"]}).status_code == 200
    # A file of another project, or outside the folder, is never served through this project.
    assert viewer.get(f"/realestate/projects/{other.id}/media/file", params={"file": up["file"]}).status_code == 404
    assert viewer.get(f"/realestate/projects/{project.id}/media/file", params={"file": "projects/real/../../x.png"}).status_code == 404


def test_brochure_only_image_is_offered_to_the_generator_and_never_public(app, db, media_dir, project, actors):
    huda = actors("marketing_manager")
    path = f"/marketing/collateral/projects/{project.id}/images"
    r = huda.client.put(
        "/api/v1" + path,
        params={"source": "Agency photo shoot", "licence": "Licensed for print and social", "caption": "Lobby"},
        content=tiny_png(),
        headers={**CSRF, "Content-Type": "application/octet-stream", "X-Filename": "lobby.png"},
    )
    assert r.status_code == 201, r.text
    image = r.json()
    assert image == {"id": image["id"], "caption": "Lobby", "source": "Agency photo shoot", "licence": "Licensed for print and social"}

    images = huda.get(f"/marketing/collateral/projects/{project.id}").json()["facts"]["images"]
    assert [(i["id"], i["origin"]) for i in images] == [(image["id"], "upload")]
    html = huda.post("/marketing/collateral/brochure/preview", {"project_id": str(project.id), "image_id": image["id"]}).json()["html"]
    assert "data:image/png;base64," in html and "Agency photo shoot" in html

    # Not part of the project, the website or the public image route.
    db.refresh(project)
    assert project.media in ([], None)
    assert anon(app).get("/api/v1/public/projects/REAL").json()["cover_image"] is None
    assert anon(app).get(f"/api/v1/public/projects/REAL/images/{image['id']}").status_code == 404
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "marketing.collateral_image_uploaded"))
    assert audit.changes == {"source": [None, "Agency photo shoot"], "licence": [None, "Licensed for print and social"]}

    # Rights are required, only marketing roles may upload, and only for published projects.
    no_licence = huda.client.put(
        "/api/v1" + path, params={"source": "x", "licence": " "}, content=tiny_png(), headers={**CSRF, "X-Filename": "a.png"}
    )
    assert no_licence.status_code == 422
    missing = huda.client.put("/api/v1" + path, params={"source": "x"}, content=tiny_png(), headers={**CSRF, "X-Filename": "a.png"})
    assert missing.status_code == 422
    agent = actors("sales_agent").client.put(
        "/api/v1" + path, params={"source": "x", "licence": "y"}, content=tiny_png(), headers={**CSRF, "X-Filename": "a.png"}
    )
    assert agent.status_code == 403
    project.is_published = False
    db.commit()
    r = huda.client.put(
        "/api/v1" + path, params={"source": "x", "licence": "y"}, content=tiny_png(), headers={**CSRF, "X-Filename": "a.png"}
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "project_not_published"
    assert len(media_files.collateral_images(get_settings().model_copy(update={"collateral_media_dir": str(media_dir)}), project.id)) == 1
