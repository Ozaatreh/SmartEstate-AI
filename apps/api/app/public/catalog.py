"""The public property catalogue — the only place that decides what anonymous visitors may see.

Used by the public website API (``app/public/router.py``) and the property assistant's tools
(``app/ai/tools/public.py``), so both expose exactly the same data.

Rules: a project is public only when ``is_published``; a unit only when its project is published *and* the unit
is ``is_public``. Responses are built field by field into dedicated public schemas — never by dumping ORM rows — so
internal fields (notes, costs, ids of people, reservations, other buyers) can't leak when a model gains a column.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from urllib.parse import quote, urlsplit

from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.modules.realestate import media_files
from app.modules.realestate.model3d.models import RePropertyModel
from app.modules.realestate.models import ReBuilding, RePaymentPlan, ReProject, ReUnit
from app.modules.realestate.plans import breakdown

PUBLIC_MEDIA_KINDS = ("image", "video", "brochure", "tour")


# --- public response schemas (explicit allowlists) -------------------------------------------------------------
class PublicMedia(BaseModel):
    url: str
    caption: str | None
    kind: str


class PublicUnit(BaseModel):
    code: str  # building-unit, e.g. A-102
    project: str
    project_code: str
    type: str
    bedrooms: int
    bathrooms: int
    floor: int
    area_sqm: Decimal
    view: str | None
    list_price_sar: Decimal
    status: str


class PublicPlan(BaseModel):
    name: str
    down_payment_pct: Decimal
    installments: int
    installment_frequency: str
    handover_pct: Decimal
    description: str | None


class PublicPlanBreakdown(BaseModel):
    name: str
    down_payment_pct: Decimal
    down_payment_sar: Decimal
    installments: int
    installment_frequency: str
    installment_amount_sar: Decimal | None
    last_installment_amount_sar: Decimal | None
    handover_pct: Decimal
    handover_payment_sar: Decimal
    total_sar: Decimal


class PublicProject(BaseModel):
    code: str
    name: str
    city: str
    district: str | None
    status: str
    handover_date: date | None
    is_demo_data: bool
    available_units: int
    price_from_sar: Decimal | None
    cover_image: str | None


ILLUSTRATIVE_NOTICE = "Illustrative Location — Not the Actual Property Location."


class PublicIllustrativePoint(BaseModel):
    """A labelled reference place shown on the map when the project's own location isn't verified (e.g. a fictional
    demo project). It is never the property's address, and its links lead to the reference place."""

    label: str
    latitude: Decimal
    longitude: Decimal
    notice: str = ILLUSTRATIVE_NOTICE
    directions_url: str
    maps_url: str


class PublicLocation(BaseModel):
    """Phase 7D. Exact location (address, coordinates, map links) only when a person has verified it; otherwise
    just the district / city / country text. Nothing about who verified it or when is public.
    ``illustrative`` (unverified projects only): a separately stored, clearly labelled reference point."""

    district: str | None
    city: str
    country: str | None
    address: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    verified: bool
    directions_url: str | None
    maps_url: str | None
    illustrative: PublicIllustrativePoint | None = None


class PublicModel(BaseModel):
    """Phase 7E: an approved 3D model. The file is served by /public/models/{id}/file — never a storage path."""

    id: uuid.UUID
    title: str
    caption: str | None
    representation: str  # design | as_built | illustrative
    credit: str  # source · licence
    format: str
    size_bytes: int
    file_url: str
    unit_code: str | None


class PublicProjectDetail(PublicProject):
    description: str | None
    amenities: list[str]
    media: list[PublicMedia]
    payment_plans: list[PublicPlan]
    bedroom_options: list[int]
    location: PublicLocation
    models: list[PublicModel]  # approved project-level 3D models


class PublicUnitDetail(PublicUnit):
    project_is_demo_data: bool
    payment_plans: list[PublicPlanBreakdown]
    models: list[PublicModel]  # approved 3D models of this unit


# --- queries -----------------------------------------------------------------------------------------------------
def published_projects() -> Select:
    return select(ReProject).where(ReProject.is_published.is_(True))


def public_units() -> Select:
    return (
        select(ReUnit)
        .join(ReProject, ReProject.id == ReUnit.project_id)
        .join(ReBuilding, ReBuilding.id == ReUnit.building_id)
        .where(ReUnit.is_public.is_(True), ReProject.is_published.is_(True))
    )


def unit_code(u: ReUnit) -> str:
    return f"{u.building.code}-{u.unit_number}"


def to_public_unit(u: ReUnit) -> PublicUnit:
    return PublicUnit(
        code=unit_code(u),
        project=u.project.name,
        project_code=u.project.code,
        type=u.unit_type,
        bedrooms=u.bedrooms,
        bathrooms=u.bathrooms,
        floor=u.floor,
        area_sqm=u.area_sqm,
        view=u.view,
        list_price_sar=u.list_price,
        status=u.status,
    )


def _media(p: ReProject) -> list[PublicMedia]:
    """Public media in the project's own order: web links, and approved uploaded images (served by
    ``GET /public/projects/{code}/images/{id}``; never the file path)."""
    out = []
    for m in p.media or []:
        if not isinstance(m, dict):
            continue
        caption = m.get("caption") if isinstance(m.get("caption"), str) else None
        url = m.get("url")
        if isinstance(url, str) and url.startswith(("https://", "http://")):
            kind = m.get("kind") if m.get("kind") in PUBLIC_MEDIA_KINDS else "image"
            out.append(PublicMedia(url=url, caption=caption, kind=kind))
        elif _public_local_image(m):
            url = f"{PUBLIC_IMAGE_PATH}/{quote(p.code)}/images/{media_files.image_id(m['file'])}"
            out.append(PublicMedia(url=url, caption=caption, kind="image"))
    return out


PUBLIC_IMAGE_PATH = "/api/v1/public/projects"


def _public_local_image(m: dict) -> bool:
    """An uploaded image is public only once approved with a recorded source and licence."""
    return (
        m.get("kind") == "image"
        and m.get("approved") is True
        and all(isinstance(m.get(k), str) and m[k].strip() for k in ("file", "source", "licence"))
    )


def public_image_path(settings, session: Session, code: str, image_id: str):
    """Path of an approved uploaded image of a published project, or NotFound."""
    project = get_published_project(session, code)
    for found_id, _m, path in media_files.approved_project_images(settings, project):
        if found_id == image_id:
            return path
    raise NotFound("Image not found.")


# A cover must be an image entry. Links to documents, videos or pages are never used as the hero image, even when a
# media entry is mislabelled "image" (an earlier dashboard edit relabelled NOVA's brochure PDF this way).
_NOT_IMAGE_SUFFIXES = (".pdf", ".doc", ".docx", ".ppt", ".pptx", ".zip", ".mp4", ".mov", ".webm", ".html", ".htm")


def _is_cover_candidate(m: PublicMedia) -> bool:
    return m.kind == "image" and not urlsplit(m.url).path.lower().endswith(_NOT_IMAGE_SUFFIXES)


def marketing_plans(session: Session, project_id) -> list[RePaymentPlan]:
    """Payment plans any marketing output may show: active AND explicitly classified "cleared" (Phase 7C).

    Unreviewed or excluded plans (e.g. test plans) never reach the website, the assistant, brochures or posters.
    """
    return list(
        session.scalars(
            select(RePaymentPlan)
            .where(
                RePaymentPlan.project_id == project_id,
                RePaymentPlan.is_active.is_(True),
                RePaymentPlan.marketing_status == "cleared",
            )
            .order_by(RePaymentPlan.name)
        )
    )


_active_plans = marketing_plans


def _project_stats(session: Session, ids: list) -> dict:
    if not ids:
        return {}
    rows = session.execute(
        select(ReUnit.project_id, func.count(), func.min(ReUnit.list_price))
        .where(ReUnit.project_id.in_(ids), ReUnit.is_public.is_(True), ReUnit.status == "available")
        .group_by(ReUnit.project_id)
    ).all()
    return {pid: (int(n), price) for pid, n, price in rows}


def _project_out(p: ReProject, stats: dict) -> dict:
    n, price = stats.get(p.id, (0, None))
    images = [m for m in _media(p) if _is_cover_candidate(m)]
    return {
        "code": p.code,
        "name": p.name,
        "city": p.city,
        "district": p.district,
        "status": p.status,
        "handover_date": p.handover_date,
        "is_demo_data": p.is_demo_data,
        "available_units": n,
        "price_from_sar": price,
        "cover_image": images[0].url if images else None,
    }


def get_published_project(session: Session, code: str | None) -> ReProject:
    stmt = published_projects()
    if code:
        stmt = stmt.where(ReProject.code == code.strip().upper())
    project = session.scalars(stmt.order_by(ReProject.code).limit(1)).first()
    if project is None:
        raise NotFound("Project not found.")
    return project


def list_projects(session: Session) -> list[PublicProject]:
    projects = list(session.scalars(published_projects().order_by(ReProject.name)))
    stats = _project_stats(session, [p.id for p in projects])
    return [PublicProject(**_project_out(p, stats)) for p in projects]


def project_detail(session: Session, code: str) -> PublicProjectDetail:
    p = get_published_project(session, code)
    stats = _project_stats(session, [p.id])
    bedrooms = sorted(
        set(
            session.scalars(
                select(ReUnit.bedrooms).where(ReUnit.project_id == p.id, ReUnit.is_public.is_(True), ReUnit.status == "available")
            )
        )
    )
    return PublicProjectDetail(
        **_project_out(p, stats),
        description=p.description,
        amenities=list(p.amenities or []),
        media=_media(p),
        payment_plans=[public_plan(pl) for pl in _active_plans(session, p.id)],
        bedroom_options=bedrooms,
        location=public_location(p),
        models=public_models(session, p),
    )


def _maps_links(point: str) -> tuple[str, str]:
    # Google Maps URLs (no API key): https://developers.google.com/maps/documentation/urls/get-started
    q = quote(point, safe="")
    return f"https://www.google.com/maps/dir/?api=1&destination={q}", f"https://www.google.com/maps/search/?api=1&query={q}"


def public_illustrative(p: ReProject, exact: bool) -> PublicIllustrativePoint | None:
    lat, lng = p.illustrative_latitude, p.illustrative_longitude
    if exact or lat is None or lng is None or not p.illustrative_label:
        return None
    directions, maps = _maps_links(f"{lat:f},{lng:f}")
    return PublicIllustrativePoint(label=p.illustrative_label, latitude=lat, longitude=lng, directions_url=directions, maps_url=maps)


def public_location(p: ReProject) -> PublicLocation:
    exact = bool(p.location_verified and not p.is_demo_data and p.latitude is not None and p.longitude is not None)
    point = f"{p.latitude:f},{p.longitude:f}" if exact else None
    return PublicLocation(
        illustrative=public_illustrative(p, exact),
        district=p.district,
        city=p.city,
        country=p.country,
        address=p.address if exact else None,
        latitude=p.latitude if exact else None,
        longitude=p.longitude if exact else None,
        verified=exact,
        # Google Maps URLs (no API key): https://developers.google.com/maps/documentation/urls/get-started
        directions_url=f"https://www.google.com/maps/dir/?api=1&destination={quote(point, safe='')}" if point else None,
        maps_url=f"https://www.google.com/maps/search/?api=1&query={quote(point, safe='')}" if point else None,
    )


def public_plan(pl: RePaymentPlan) -> PublicPlan:
    return PublicPlan(
        name=pl.name,
        down_payment_pct=pl.down_payment_pct,
        installments=pl.installments,
        installment_frequency=pl.installment_frequency,
        handover_pct=pl.handover_pct,
        description=pl.description,
    )


def search_units(
    session: Session,
    *,
    project_code: str | None = None,
    bedrooms: int | None = None,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    unit_type: str | None = None,
    available_only: bool = True,
    limit: int = 50,
) -> list[PublicUnit]:
    stmt = public_units()
    if available_only:
        stmt = stmt.where(ReUnit.status == "available")
    if project_code:
        stmt = stmt.where(ReProject.code == project_code.strip().upper())
    if bedrooms is not None:
        stmt = stmt.where(ReUnit.bedrooms == bedrooms)
    if min_price is not None:
        stmt = stmt.where(ReUnit.list_price >= min_price)
    if max_price is not None:
        stmt = stmt.where(ReUnit.list_price <= max_price)
    if unit_type:
        stmt = stmt.where(ReUnit.unit_type == unit_type)
    rows = session.scalars(stmt.order_by(ReUnit.list_price, ReBuilding.code, ReUnit.unit_number).limit(limit))
    return [to_public_unit(u) for u in rows]


def find_unit(session: Session, code: str, project_code: str | None = None) -> ReUnit:
    parts = code.strip().upper().split("-", 1)
    if len(parts) != 2:
        raise NotFound("Unit codes look like A-102.")
    stmt = public_units().where(ReBuilding.code == parts[0], ReUnit.unit_number == parts[1])
    if project_code:
        stmt = stmt.where(ReProject.code == project_code.strip().upper())
    unit = session.scalars(stmt.order_by(ReProject.code).limit(1)).first()
    if unit is None:
        raise NotFound("Unit not found.")
    return unit


def plan_breakdowns(session: Session, unit: ReUnit) -> list[PublicPlanBreakdown]:
    out = []
    for pl in _active_plans(session, unit.project_id):
        b = breakdown(unit.list_price, pl.down_payment_pct, pl.installments, pl.handover_pct)
        out.append(
            PublicPlanBreakdown(
                name=pl.name,
                down_payment_pct=pl.down_payment_pct,
                down_payment_sar=b.down_payment,
                installments=b.installments,
                installment_frequency=pl.installment_frequency,
                installment_amount_sar=b.installment_amount,
                last_installment_amount_sar=b.last_installment_amount,
                handover_pct=pl.handover_pct,
                handover_payment_sar=b.handover_payment,
                total_sar=b.total,
            )
        )
    return out


def unit_detail(session: Session, project_code: str, code: str) -> PublicUnitDetail:
    unit = find_unit(session, code, project_code)
    return PublicUnitDetail(
        **to_public_unit(unit).model_dump(),
        project_is_demo_data=unit.project.is_demo_data,
        payment_plans=plan_breakdowns(session, unit),
        models=public_models(session, unit.project, unit),
    )


# --- 3D models (Phase 7E) ------------------------------------------------------------------------------------------
def _public_model_stmt() -> Select:
    """Approved models of published projects; unit models only for public units of that project."""
    return (
        select(RePropertyModel)
        .join(ReProject, ReProject.id == RePropertyModel.project_id)
        .outerjoin(ReUnit, ReUnit.id == RePropertyModel.unit_id)
        .where(
            RePropertyModel.status == "approved",
            RePropertyModel.file_key.is_not(None),
            ReProject.is_published.is_(True),
            (RePropertyModel.unit_id.is_(None)) | ((ReUnit.is_public.is_(True)) & (ReUnit.project_id == RePropertyModel.project_id)),
        )
    )


def to_public_model(m: RePropertyModel) -> PublicModel:
    return PublicModel(
        id=m.id,
        title=m.title,
        caption=m.caption,
        representation=m.representation,
        credit=f"{m.source} · {m.licence}",
        format=m.format or "glb",
        size_bytes=m.size_bytes or 0,
        file_url=f"/api/v1/public/models/{m.id}/file?v={m.file_version}",
        unit_code=unit_code(m.unit) if m.unit else None,
    )


def public_models(session: Session, project: ReProject, unit: ReUnit | None = None) -> list[PublicModel]:
    stmt = _public_model_stmt().where(RePropertyModel.project_id == project.id)
    stmt = stmt.where(RePropertyModel.unit_id == unit.id) if unit else stmt.where(RePropertyModel.unit_id.is_(None))
    return [to_public_model(m) for m in session.scalars(stmt.order_by(RePropertyModel.approved_at, RePropertyModel.id))]


def public_model(session: Session, model_id: uuid.UUID) -> RePropertyModel:
    m = session.scalars(_public_model_stmt().where(RePropertyModel.id == model_id)).first()
    if m is None:
        raise NotFound("3D model not found.")  # same answer for missing, draft, archived or unpublished
    return m
