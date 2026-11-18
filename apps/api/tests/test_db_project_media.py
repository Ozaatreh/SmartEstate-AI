"""Project media: kinds survive edits, local approved-image references round-trip, and only real images become the
public cover (the NOVA broken-hero bug: a brochure PDF relabelled "image" was served as the cover)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.modules.realestate import media_files
from app.modules.realestate.models import ReProject
from tests.business_fixtures import Actor

pytestmark = pytest.mark.db

LOCAL = {
    "kind": "image",
    "file": "real/hero.jpg",
    "approved": True,
    "source": "Studio X",
    "licence": "Licensed for marketing",
    "caption": "Illustrative render",
}


@pytest.fixture
def real_project(db) -> ReProject:
    p = ReProject(code="REAL", name="Real Court", city="Riyadh", status="launched", is_published=True)
    db.add(p)
    db.commit()
    return p


@pytest.fixture
def manager(app, make_user) -> Actor:
    return Actor(app, make_user("sales_manager", name="Sara Manager"))


def public(app) -> dict:
    return TestClient(app, base_url="http://127.0.0.1").get("/api/v1/public/projects/REAL").json()


def test_media_kinds_and_local_references_round_trip(app, manager, real_project):
    media = [
        {"url": "https://example.com/real/brochure.pdf", "kind": "brochure", "caption": "Brochure"},
        {"url": "https://example.com/real/tour", "kind": "tour", "caption": None},
        LOCAL,
    ]
    r = manager.patch(f"/realestate/projects/{real_project.id}", {"media": media})
    assert r.status_code == 200, r.text
    stored = manager.get(f"/realestate/projects/{real_project.id}").json()["media"]
    assert stored == [
        {"url": "https://example.com/real/brochure.pdf", "kind": "brochure", "caption": "Brochure"},
        {"url": "https://example.com/real/tour", "kind": "tour"},
        LOCAL,
    ]
    # saving the same list again (what the dashboard does) changes nothing
    assert manager.patch(f"/realestate/projects/{real_project.id}", {"media": stored}).status_code == 200
    assert manager.get(f"/realestate/projects/{real_project.id}").json()["media"] == stored
    # an approved uploaded image is public through the image route (never by its file path) and is the cover
    body = public(app)
    image_url = f"/api/v1/public/projects/REAL/images/{media_files.image_id('real/hero.jpg')}"
    assert body["cover_image"] == image_url
    assert [m["url"] for m in body["media"]] == ["https://example.com/real/brochure.pdf", "https://example.com/real/tour", image_url]
    assert "real/hero.jpg" not in str(body)


def test_only_image_links_become_the_cover(app, manager, real_project):
    media = [
        {"url": "https://example.com/real/brochure.pdf", "kind": "image", "caption": "mislabelled"},
        {"url": "https://example.com/real/front.webp", "kind": "image"},
    ]
    assert manager.patch(f"/realestate/projects/{real_project.id}", {"media": media}).status_code == 200
    assert public(app)["cover_image"] == "https://example.com/real/front.webp"
    assert manager.patch(f"/realestate/projects/{real_project.id}", {"media": media[:1]}).status_code == 200
    assert public(app)["cover_image"] is None  # a PDF is never served as the hero image


@pytest.mark.parametrize(
    "item",
    [
        {"url": "https://example.com/a.jpg", "file": "a.jpg"},  # both
        {"caption": "nothing"},  # neither
        {"file": "../secrets/x.jpg"},
        {"file": "/etc/x.jpg"},
        {"file": "real/hero.svg"},
        {"file": "real/brochure.pdf", "kind": "brochure"},
        {"file": "real/hero.jpg", "approved": True},  # approved without source/licence
        {"url": "javascript:alert(1)"},
        {"url": "https://example.com/a.jpg", "kind": "panorama"},
        {"url": "https://example.com/a.jpg", "secret": "x"},
    ],
)
def test_media_items_are_validated(manager, real_project, item):
    r = manager.patch(f"/realestate/projects/{real_project.id}", {"media": [item]})
    assert r.status_code == 422, r.text
