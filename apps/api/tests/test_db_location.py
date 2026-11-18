"""Phase 7D — project location: verified coordinates only, never for fictional projects, public allowlist, permissions."""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.modules.audit.models import AuditLog
from app.modules.realestate.models import ReProject
from app.public import catalog
from tests.business_fixtures import Actor

pytestmark = pytest.mark.db

LOCATION_KEYS = {
    "district",
    "city",
    "country",
    "address",
    "latitude",
    "longitude",
    "verified",
    "directions_url",
    "maps_url",
    "illustrative",
}


@pytest.fixture
def real_project(db) -> ReProject:
    """A published, non-demo project — the only kind whose location may be verified."""
    p = ReProject(code="REAL", name="Real Court", city="Riyadh", district="Al Malqa", status="launched", is_published=True)
    db.add(p)
    db.commit()
    return p


@pytest.fixture
def actors(app, make_user):
    users = {
        "manager": make_user("sales_manager", name="Sara Manager"),
        "agent": make_user("sales_agent", name="Agent One"),
        "marketing": make_user("marketing_manager", name="Mona Marketing"),
    }
    return {k: Actor(app, u) for k, u in users.items()}


def anon(app) -> TestClient:
    return TestClient(app, base_url="http://127.0.0.1")


def test_verified_location_is_public_with_maps_links(app, db, actors, real_project):
    m = actors["manager"]
    r = m.patch(
        f"/realestate/projects/{real_project.id}",
        {
            "address": "  King Salman Rd, Al Malqa  ",
            "country": "Saudi Arabia",
            "latitude": "24.812345",
            "longitude": "46.612345",
            "location_verified": True,
        },
    )
    assert r.status_code == 200, r.text
    detail = m.get(f"/realestate/projects/{real_project.id}").json()
    assert detail["location_verified"] is True and detail["location_verified_by"] == "Sara Manager" and detail["location_verified_at"]
    assert detail["address"] == "King Salman Rd, Al Malqa" and Decimal(detail["latitude"]) == Decimal("24.812345")
    log = db.scalars(
        select(AuditLog).where(AuditLog.action == "realestate.project_updated", AuditLog.entity_id == str(real_project.id))
    ).one()
    assert {"latitude", "longitude", "location_verified", "address", "country"} <= set(log.changes)

    loc = anon(app).get("/api/v1/public/projects/REAL").json()["location"]
    assert set(loc) == LOCATION_KEYS  # nothing about who verified it, or when
    assert loc["verified"] is True and loc["address"] == "King Salman Rd, Al Malqa" and loc["country"] == "Saudi Arabia"
    assert Decimal(loc["latitude"]) == Decimal("24.812345") and Decimal(loc["longitude"]) == Decimal("46.612345")
    assert loc["directions_url"] == "https://www.google.com/maps/dir/?api=1&destination=24.812345%2C46.612345"
    assert loc["maps_url"] == "https://www.google.com/maps/search/?api=1&query=24.812345%2C46.612345"


def test_unverified_coordinates_stay_private(app, db, actors, real_project):
    m = actors["manager"]
    assert (
        m.patch(
            f"/realestate/projects/{real_project.id}", {"address": "Draft address", "latitude": "24.8", "longitude": "46.6"}
        ).status_code
        == 200
    )
    loc = anon(app).get("/api/v1/public/projects/REAL").json()["location"]
    assert loc == {
        "district": "Al Malqa",
        "city": "Riyadh",
        "country": None,
        "address": None,
        "latitude": None,
        "longitude": None,
        "verified": False,
        "directions_url": None,
        "maps_url": None,
        "illustrative": None,
    }
    # verify, then move the pin without confirming again: it goes back to unverified
    assert m.patch(f"/realestate/projects/{real_project.id}", {"location_verified": True}).status_code == 200
    assert m.patch(f"/realestate/projects/{real_project.id}", {"latitude": "24.9", "longitude": "46.7"}).status_code == 200
    db.refresh(real_project)
    assert real_project.location_verified is False and real_project.location_verified_by is None
    assert anon(app).get("/api/v1/public/projects/REAL").json()["location"]["latitude"] is None


def test_fictional_projects_are_never_pinned(app, db, actors, inventory):
    m = actors["manager"]
    pid = inventory.project.id  # TST is is_demo_data
    # coordinates may be stored as a draft, but never verified, so no pin, address or directions are public
    assert m.patch(f"/realestate/projects/{pid}", {"latitude": "24.8", "longitude": "46.6", "address": "Somewhere"}).status_code == 200
    r = m.patch(f"/realestate/projects/{pid}", {"location_verified": True})
    assert r.status_code == 422 and r.json()["error"]["code"] == "demo_location"
    loc = catalog.project_detail(db, "TST").location
    assert loc.verified is False and loc.latitude is None and loc.address is None and loc.directions_url is None
    # the database refuses it too, whatever the API does
    inventory.project.location_verified = True
    with pytest.raises(IntegrityError, match="verified_not_demo"):
        db.commit()
    db.rollback()


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"latitude": "95", "longitude": "46"}, "validation_failed"),
        ({"latitude": "24", "longitude": "-181"}, "validation_failed"),
        ({"latitude": "24.1234567", "longitude": "46"}, "validation_failed"),  # more than 6 decimals
        ({"latitude": "abc", "longitude": "46"}, "validation_failed"),
        ({"latitude": "24.5"}, "coordinates_incomplete"),
        ({"location_verified": True}, "location_unverifiable"),
        ({"address": "x" * 251}, "validation_failed"),
        ({"map_embed_key": "whatever"}, "validation_failed"),  # unknown fields are rejected
    ],
)
def test_location_input_is_validated(actors, real_project, body, code):
    r = actors["manager"].patch(f"/realestate/projects/{real_project.id}", body)
    assert r.status_code == 422 and r.json()["error"]["code"] == code, r.text


def test_only_inventory_managers_can_edit_locations(app, actors, real_project):
    body = {"latitude": "24.8", "longitude": "46.6", "location_verified": True}
    for who in ("agent", "marketing"):
        assert actors[who].patch(f"/realestate/projects/{real_project.id}", body).status_code == 403
    assert (
        anon(app)
        .patch(f"/api/v1/realestate/projects/{real_project.id}", json=body, headers={"X-Requested-With": "XMLHttpRequest"})
        .status_code
        == 401
    )
    # the public API has no write route for projects at all
    assert anon(app).post("/api/v1/public/projects/REAL", json=body, headers={"X-Requested-With": "XMLHttpRequest"}).status_code == 405


def test_public_project_lookup_validates_the_code(app, real_project):
    c = anon(app)
    assert c.get("/api/v1/public/projects/real").status_code == 200  # case-insensitive
    for bad in ("NOPE", "REAL%27%20OR%201%3D1", "%3Cscript%3E"):
        assert c.get(f"/api/v1/public/projects/{bad}").status_code == 404


# --- illustrative map point (a labelled reference place, separate from the property location) ------------------------
KC = {
    "illustrative_label": "Kingdom Centre, Riyadh",
    "illustrative_latitude": "24.711389",
    "illustrative_longitude": "46.674439",
    "illustrative_source": "Wikidata Q656743",
}


def test_fictional_project_can_show_a_labelled_illustrative_point(app, db, actors, inventory):
    m = actors["manager"]
    pid = inventory.project.id  # TST: fictional demo data, published by the fixture
    inventory.project.is_published = True
    db.commit()
    r = m.patch(f"/realestate/projects/{pid}", KC)
    assert r.status_code == 200, r.text
    detail = m.get(f"/realestate/projects/{pid}").json()
    assert detail["illustrative_label"] == "Kingdom Centre, Riyadh" and detail["illustrative_source"] == "Wikidata Q656743"
    assert detail["is_demo_data"] is True and detail["location_verified"] is False
    assert detail["latitude"] is None and detail["address"] is None  # the property-location fields are untouched

    loc = anon(app).get("/api/v1/public/projects/TST").json()["location"]
    # the property itself stays unlocated: no address, coordinates or directions of its own
    assert loc["verified"] is False and loc["address"] is None and loc["latitude"] is None and loc["directions_url"] is None
    ill = loc["illustrative"]
    assert set(ill) == {"label", "latitude", "longitude", "notice", "directions_url", "maps_url"}  # no source, no people
    assert ill["label"] == "Kingdom Centre, Riyadh"
    assert ill["notice"] == "Illustrative Location — Not the Actual Property Location."
    assert Decimal(ill["latitude"]) == Decimal("24.711389") and Decimal(ill["longitude"]) == Decimal("46.674439")
    assert ill["directions_url"] == "https://www.google.com/maps/dir/?api=1&destination=24.711389%2C46.674439"
    # still never verifiable
    assert m.patch(f"/realestate/projects/{pid}", {"location_verified": True}).status_code == 422
    # removing it clears it publicly
    clear = {k: None for k in KC}
    assert m.patch(f"/realestate/projects/{pid}", clear).status_code == 200
    assert anon(app).get("/api/v1/public/projects/TST").json()["location"]["illustrative"] is None


def test_unpublished_projects_expose_nothing(app, db, actors, real_project):
    real_project.is_published = False
    db.commit()
    assert actors["manager"].patch(f"/realestate/projects/{real_project.id}", KC).status_code == 200
    assert anon(app).get("/api/v1/public/projects/REAL").status_code == 404


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"illustrative_latitude": "24.7"}, "illustrative_coordinates_incomplete"),
        ({"illustrative_latitude": "24.7", "illustrative_longitude": "46.6"}, "illustrative_label_required"),
        ({**KC, "illustrative_label": "   "}, "illustrative_label_required"),
        ({**KC, "illustrative_latitude": "91"}, "validation_failed"),
        ({**KC, "illustrative_label": "x" * 121}, "validation_failed"),
    ],
)
def test_illustrative_point_is_validated(actors, real_project, body, code):
    r = actors["manager"].patch(f"/realestate/projects/{real_project.id}", body)
    assert r.status_code == 422 and r.json()["error"]["code"] == code, r.text


def test_illustrative_point_never_coexists_with_a_verified_location(app, db, actors, real_project):
    m = actors["manager"]
    verified = {"latitude": "24.812345", "longitude": "46.612345", "location_verified": True}
    assert m.patch(f"/realestate/projects/{real_project.id}", verified).status_code == 200
    r = m.patch(f"/realestate/projects/{real_project.id}", KC)
    assert r.status_code == 422 and r.json()["error"]["code"] == "illustrative_with_verified"
    # and the database refuses it too
    real_project.illustrative_label, real_project.illustrative_latitude, real_project.illustrative_longitude = "X", Decimal(1), Decimal(1)
    with pytest.raises(IntegrityError, match="illustrative_not_with_verified"):
        db.commit()
    db.rollback()


def test_database_requires_label_and_pairs(db, real_project):
    real_project.illustrative_latitude, real_project.illustrative_longitude = Decimal(1), Decimal(1)
    with pytest.raises(IntegrityError, match="illustrative_needs_label"):
        db.commit()
    db.rollback()


def test_only_inventory_managers_can_set_illustrative_points(app, actors, real_project):
    for who in ("agent", "marketing"):
        assert actors[who].patch(f"/realestate/projects/{real_project.id}", KC).status_code == 403
    assert (
        anon(app)
        .patch(f"/api/v1/realestate/projects/{real_project.id}", json=KC, headers={"X-Requested-With": "XMLHttpRequest"})
        .status_code
        == 401
    )
