"""Phase 7C — brochure and poster generator.

Facts are checked against the database independently of the generator (plain SQL here), every rendered page is
scanned for numbers that aren't facts, test/unreviewed payment plans never appear, missing data is omitted, and
the real files (PDF, PNG at exact sizes) are produced by headless Chromium.
"""

from __future__ import annotations

import re
import struct
import zlib
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.modules.audit.models import AuditLog
from app.modules.marketing.collateral.verify import UnverifiedFact, ensure_verified, numbers_in, visible_text
from app.modules.realestate.models import RePaymentPlan, ReProject, ReUnit
from app.public import catalog
from tests.business_fixtures import Actor

pytestmark = pytest.mark.db

SIZES = {"instagram_post": (1080, 1080), "instagram_story": (1080, 1920), "linkedin": (1200, 627), "facebook": (1200, 630)}


@pytest.fixture
def people(app, make_user):
    users = {
        "huda": make_user("marketing_manager", name="Huda Manager"),
        "lina": make_user("marketing_specialist", name="Lina Specialist"),
        "ceo": make_user("executive", name="Faisal Exec"),
        "agent": make_user("sales_agent", name="Yousef Agent"),
    }
    cache: dict[str, Actor] = {}

    def get(key: str) -> Actor:
        if key not in cache:
            cache[key] = Actor(app, users[key])
        return cache[key]

    return get


@pytest.fixture
def test_plan(db, inventory) -> RePaymentPlan:
    """An active plan nobody has classified — like the real "Test 10/90". Its name gives no hint on purpose."""
    plan = RePaymentPlan(
        project_id=inventory.project.id, name="Flexible 15/85", down_payment_pct=Decimal("15"), installments=17, installment_frequency="monthly"
    )
    db.add(plan)
    db.commit()
    assert plan.marketing_status == "unreviewed"
    return plan


def use_settings(app, **values):
    app.dependency_overrides[get_settings] = lambda: get_settings().model_copy(update=values)


def db_facts(db, project_id) -> dict:
    """What the documents must show, computed here with plain SQL — not through the generator's code."""
    rows = db.execute(
        select(ReUnit.bedrooms, func.count(), func.min(ReUnit.area_sqm), func.max(ReUnit.area_sqm), func.min(ReUnit.list_price))
        .where(ReUnit.project_id == project_id, ReUnit.is_public.is_(True), ReUnit.status == "available")
        .group_by(ReUnit.bedrooms)
        .order_by(ReUnit.bedrooms)
    ).all()
    plans = db.scalars(
        select(RePaymentPlan).where(
            RePaymentPlan.project_id == project_id, RePaymentPlan.is_active.is_(True), RePaymentPlan.marketing_status == "cleared"
        )
    ).all()
    return {"types": rows, "plans": plans, "from": min(r[4] for r in rows) if rows else None}


def fmt(v: Decimal) -> str:
    return f"{int(v):,}"


def png_size(data: bytes) -> tuple[int, int]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


def tiny_png() -> bytes:
    raw = b"\x00\xff\xff\xff"
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))  # noqa: E731
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


# ================================================================== facts = database
def test_fact_sheet_and_brochure_match_the_database(app, db, people, inventory, test_plan):
    # Make availability non-trivial: one unit sold, one hidden from the public — both must disappear from the facts.
    inventory.units["A-501"].status = "sold"
    inventory.units["B-101"].is_public = False
    db.commit()
    huda = people("huda")
    pid = str(inventory.project.id)
    expected = db_facts(db, inventory.project.id)

    o = huda.get(f"/marketing/collateral/projects/{pid}")
    assert o.status_code == 200, o.text
    facts = o.json()["facts"]
    assert Decimal(facts["price_from_sar"]) == expected["from"] == Decimal("650000")  # the hidden studio (420,000) isn't used
    assert [(u["bedrooms"], u["available"], Decimal(u["area_min_sqm"]), Decimal(u["area_max_sqm"]), Decimal(u["price_from_sar"])) for u in facts["unit_types"]] == [
        (b, n, lo, hi, p) for b, n, lo, hi, p in expected["types"]
    ]
    assert 4 not in [u["bedrooms"] for u in facts["unit_types"]]  # the sold penthouse
    assert {p["name"] for p in facts["payment_plans"]} == {p.name for p in expected["plans"]} == {"10/90 over 36 months", "20/50/30"}
    assert facts["excluded_plans"] == 1  # the unclassified plan, counted but not shown
    assert set(facts["missing"]) >= {"images", "contact"}

    for lang in ("en", "ar"):
        r = huda.post("/marketing/collateral/brochure/preview", {"project_id": pid, "language": lang})
        assert r.status_code == 200, r.text
        html = r.json()["html"]
        text = visible_text(html)
        # every price, area range and count in the table, exactly as stored
        for _b, _n, lo, hi, price in expected["types"]:
            assert fmt(price) in text
            assert (f"{fmt(lo)}–{fmt(hi)}" if lo != hi else fmt(lo)) in text
        assert fmt(expected["from"]) in text
        for p in expected["plans"]:
            assert p.name in text
        # nothing from the unclassified plan, and no figure that isn't a fact
        assert "Flexible 15/85" not in text and "15%" not in text and "17 ×" not in text
        allowed = {Decimal(x) for x in ("650000", "900000", "1250000", "1800000", "75", "110", "150", "210", "1", "2", "3", "10", "36", "20", "8", "30", "50", "90")}
        for n in numbers_in(text):
            if n not in allowed:
                # only dates may add numbers: handover/as-of day and year
                assert re.search(rf"\b{n}\b", text) and (n >= 2000 or n <= 31), n
        assert 'lang="' + lang + '"' in html and ('dir="rtl"' in html) == (lang == "ar")
    assert "استوديو" not in text  # the only studio is hidden from the public
    assert "غرفة نوم واحدة" in text and "خطط الدفع" in text


def test_unclassified_plans_stay_out_of_every_marketing_output(db, inventory, test_plan, app, people):
    names = {p.name for p in catalog.project_detail(db, inventory.project.code).payment_plans}
    assert names == {"10/90 over 36 months", "20/50/30"}  # public website and assistant
    from app.modules.marketing.facts import project_facts

    assert {p["name"] for p in project_facts(db, inventory.project.id).payment_plans} == names  # Marketing Studio
    # Clearing it explicitly is what makes it appear; excluding it keeps it out.
    test_plan.marketing_status = "cleared"
    db.commit()
    assert "Flexible 15/85" in {p.name for p in catalog.project_detail(db, inventory.project.code).payment_plans}
    test_plan.marketing_status = "excluded"
    db.commit()
    html = people("lina").post("/marketing/collateral/brochure/preview", {"project_id": str(inventory.project.id)}).json()["html"]
    assert "Flexible 15/85" not in html


def test_a_figure_that_is_not_a_fact_stops_the_export():
    allowed = {Decimal("435000"), Decimal("10")}
    ensure_verified("<p>From SAR 435,000 · 10% down</p><style>.a{width:750px}</style>", allowed)  # CSS numbers aren't shown
    with pytest.raises(UnverifiedFact) as e:
        ensure_verified("<p>Starting from SAR 750,000</p>", allowed)
    assert e.value.details == {"numbers": ["750,000"]}
    with pytest.raises(UnverifiedFact):
        ensure_verified("<p>تبدأ من ٧٥٠٬٠٠٠ ريال</p>", allowed)  # Arabic digits are checked too


# ================================================================== files
def test_brochure_pdf_downloads_in_both_languages_and_is_audited(app, db, people, inventory):
    lina = people("lina")
    for lang in ("en", "ar"):
        r = lina.post("/marketing/collateral/brochure", {"project_id": str(inventory.project.id), "language": lang})
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/pdf"
        assert r.headers["content-disposition"].startswith(f'attachment; filename="TST-brochure-{lang}.pdf"')
        assert r.headers["cache-control"] == "no-store"
        assert r.content[:5] == b"%PDF-" and len(r.content) > 20_000
        assert r.content.count(b"/Type /Page") - r.content.count(b"/Type /Pages") >= 3  # cover, details, prices, back
    logs = db.scalars(select(AuditLog).where(AuditLog.action == "marketing.brochure_generated")).all()
    assert len(logs) == 2 and all(log.actor_user_id == people("lina").user.id for log in logs)


def test_every_poster_format_downloads_at_its_exact_size(app, db, people, inventory):
    huda = people("huda")
    pid = str(inventory.project.id)
    options = huda.get(f"/marketing/collateral/projects/{pid}").json()
    assert {f["id"]: (f["width"], f["height"]) for f in options["formats"]} == SIZES
    key_facts = [o["id"] for o in options["key_facts"]["en"]][:3]
    for i, (fmt_id, size) in enumerate(SIZES.items()):
        body = {"project_id": pid, "format": fmt_id, "template": ("classic", "split", "minimal")[i % 3], "facts": key_facts,
                "language": ("en", "ar")[i % 2], "cta": "register_interest"}
        r = huda.post("/marketing/collateral/poster", body)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "image/png"
        assert png_size(r.content) == size
        assert f"{size[0]}x{size[1]}" in r.headers["content-disposition"]
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "marketing.poster_generated")) == 4


def test_poster_shows_only_verified_facts_and_its_choices(app, people, inventory):
    huda = people("huda")
    pid = str(inventory.project.id)
    html = huda.post("/marketing/collateral/poster/preview", {"project_id": pid, "facts": ["bedrooms", "plan:0"], "cta": "book_viewing"}).json()["html"]
    text = visible_text(html)
    assert "SAR 420,000" in text and "Studio to 4 bedrooms" in text and "10% down payment · 36 monthly instalments" in text
    assert "Book a viewing" in text and "Fictional demo project" in text
    no_price = visible_text(huda.post("/marketing/collateral/poster/preview", {"project_id": pid, "show_price": False}).json()["html"])
    assert "SAR" not in no_price
    r = huda.post("/marketing/collateral/poster/preview", {"project_id": pid, "facts": ["Sea views"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "unknown_fact"  # free text can't be passed off as a fact
    r = huda.post("/marketing/collateral/poster/preview", {"project_id": pid, "facts": ["bedrooms", "status", "location", "handover"]})
    assert r.status_code == 422  # at most three


# ================================================================== missing images / data
def test_missing_data_is_omitted_not_invented(app, db, people):
    bare = ReProject(code="BARE", name="Bare Court", city="Jeddah", status="planning", is_published=True)
    db.add(bare)
    db.commit()
    huda = people("huda")
    facts = huda.get(f"/marketing/collateral/projects/{bare.id}").json()["facts"]
    assert facts["price_from_sar"] is None and facts["unit_types"] == [] and facts["payment_plans"] == []
    assert set(facts["missing"]) == {"images", "description", "amenities", "units", "payment_plans", "handover_date", "contact"}
    html = huda.post("/marketing/collateral/brochure/preview", {"project_id": str(bare.id)}).json()["html"]
    text = visible_text(html)
    for absent in ("Starting from", "Available homes", "Payment plans", "Amenities", "Handover", "SAR", "Phone", "Fictional demo"):
        assert absent not in text, absent
    assert "Bare Court" in text and 'class="ph"' in html  # neutral placeholder art instead of a photo
    poster = visible_text(huda.post("/marketing/collateral/poster/preview", {"project_id": str(bare.id), "format": "linkedin"}).json()["html"])
    assert "Starting from" not in poster
    r = huda.post("/marketing/collateral/poster", {"project_id": str(bare.id), "format": "linkedin"})
    assert r.status_code == 200 and png_size(r.content) == (1200, 627)


def test_only_approved_licensed_local_images_are_offered(app, db, people, inventory, tmp_path):
    (tmp_path / "tst").mkdir()
    (tmp_path / "tst" / "hero.png").write_bytes(tiny_png())
    (tmp_path / "tst" / "draft.png").write_bytes(tiny_png())
    (tmp_path / "outside.png").write_bytes(tiny_png())
    inventory.project.media = [
        {"kind": "image", "file": "tst/hero.png", "approved": True, "source": "Studio Example renders", "licence": "Commissioned, all rights"},
        {"kind": "image", "file": "tst/draft.png", "approved": False, "source": "x", "licence": "y"},  # not approved
        {"kind": "image", "file": "tst/hero.png", "approved": True, "source": "No licence given", "licence": ""},  # no licence
        {"kind": "image", "file": "../outside.png", "approved": True, "source": "x", "licence": "y"},  # escapes the folder
        {"kind": "image", "url": "https://example.com/photo.jpg", "approved": True, "source": "x", "licence": "y"},  # remote
    ]
    db.commit()
    use_settings(app, collateral_media_dir=str(tmp_path / "tst" / ".."), collateral_website_url="https://example.test/nova")
    huda = people("huda")
    pid = str(inventory.project.id)
    facts = huda.get(f"/marketing/collateral/projects/{pid}").json()["facts"]
    assert [i["source"] for i in facts["images"]] == ["Studio Example renders"]
    assert "images" not in facts["missing"] and facts["contact"]["website"] == "https://example.test/nova"
    image_id = facts["images"][0]["id"]
    html = huda.post("/marketing/collateral/brochure/preview", {"project_id": pid, "image_id": image_id}).json()["html"]
    assert "data:image/png;base64," in html and "Studio Example renders" in visible_text(html) and "https://example.test/nova" in html
    r = huda.post("/marketing/collateral/poster/preview", {"project_id": pid, "image_id": "0123456789ab"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "image_not_approved"


# ================================================================== access
def test_only_marketing_roles_can_generate(app, db, people, inventory, client):
    pid = str(inventory.project.id)
    for who in ("ceo", "agent"):
        a = people(who)
        assert a.get("/marketing/collateral/projects").status_code == 403
        assert a.get(f"/marketing/collateral/projects/{pid}").status_code == 403
        assert a.post("/marketing/collateral/brochure", {"project_id": pid}).status_code == 403
        assert a.post("/marketing/collateral/poster", {"project_id": pid}).status_code == 403
    assert client.get("/api/v1/marketing/collateral/projects").status_code == 401
    listed = people("lina").get("/marketing/collateral/projects").json()
    assert [p["code"] for p in listed] == ["TST"]
    inventory.project.is_published = False
    db.commit()
    r = people("lina").get(f"/marketing/collateral/projects/{pid}")
    assert r.status_code == 409 and r.json()["error"]["code"] == "project_not_published"
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action.like("marketing.%_generated"))) == 0
