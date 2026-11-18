"""The verified fact sheet behind every brochure and poster, read from the database at generation time.

Scope matches the public website (``app.public.catalog``): only published projects, only units marked public and
currently available, only payment plans that are active and explicitly classified ``cleared`` for marketing. Nothing
internal (costs, notes, reservations, buyers, unpublished projects, finance or procurement records) is read.

Images: a project ``media`` entry is usable only when it is an approved local file with a recorded source and
licence — ``{"kind": "image", "file": "nova/hero.jpg", "approved": true, "source": "...", "licence": "..."}`` under
``COLLATERAL_MEDIA_DIR``. Remote URLs are never fetched. Without one, layouts use a neutral placeholder.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import Conflict, NotFound
from app.modules.marketing.collateral import i18n
from app.modules.marketing.collateral.i18n import Lang
from app.modules.realestate import media_files
from app.modules.realestate.models import RePaymentPlan, ReProject, ReUnit
from app.public.catalog import marketing_plans

API_ROOT = Path(__file__).resolve().parents[4]  # apps/api
IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


class UnitTypeFact(BaseModel):
    bedrooms: int
    available: int
    area_min_sqm: Decimal
    area_max_sqm: Decimal
    price_from_sar: Decimal


class PlanFact(BaseModel):
    name: str
    down_payment_pct: Decimal
    installments: int
    installment_frequency: str
    handover_pct: Decimal


class ImageFact(BaseModel):
    id: str
    caption: str | None
    source: str
    licence: str
    origin: Literal["project", "upload"] = "project"  # project media, or uploaded for brochures/posters only


class ContactFact(BaseModel):
    phone: str | None
    email: str | None
    website: str | None

    @property
    def any(self) -> bool:
        return bool(self.phone or self.email or self.website)


class FactSheet(BaseModel):
    project_id: uuid.UUID
    code: str
    name: str
    city: str
    district: str | None
    status: str
    handover_date: date | None
    description: str | None
    is_demo_data: bool
    amenities: list[str]
    available_units: int
    price_from_sar: Decimal | None
    unit_types: list[UnitTypeFact]
    payment_plans: list[PlanFact]
    excluded_plans: int  # active plans left out because they aren't cleared for marketing
    images: list[ImageFact]
    contact: ContactFact
    as_of: datetime
    missing: list[str]  # what a writer should know is absent (and therefore omitted)

    def allowed_numbers(self) -> set[Decimal]:
        """Every number the documents may print. Anything else in a rendered page is a defect."""
        nums: set[Decimal] = set()

        def add(v: Decimal | int | None) -> None:
            if v is not None:
                nums.add(Decimal(v).normalize())

        add(self.available_units)
        add(self.price_from_sar)
        for u in self.unit_types:
            for v in (u.bedrooms, u.available, u.area_min_sqm, u.area_max_sqm, u.price_from_sar):
                add(v)
        for p in self.payment_plans:
            for v in (p.down_payment_pct, p.installments, p.handover_pct):
                add(v)
        for d in (self.handover_date, self.as_of.date()):
            if d:
                add(d.year)
                add(d.day)
        # Numbers that are part of stored text (names, amenities such as "24/7 security", contact lines) are facts too.
        texts = [self.name, self.city, self.district, self.description, *self.amenities, *(p.name for p in self.payment_plans)]
        texts += [self.contact.phone, self.contact.email, self.contact.website]
        texts += [i.caption for i in self.images] + [i.source for i in self.images] + [i.licence for i in self.images]
        from app.modules.marketing.collateral.verify import numbers_in

        for text in texts:
            for n in numbers_in(text or ""):
                nums.add(n)
        return nums


def approved_images(settings: Settings, project: ReProject) -> dict[str, tuple[ImageFact, Path]]:
    """Images a brochure/poster may use: the project's approved images (media-list order), then images uploaded in the
    generator for this project only (newest first). All have a recorded source and licence."""
    out: dict[str, tuple[ImageFact, Path]] = {}
    for image_id, m, path in media_files.approved_project_images(settings, project):
        caption = m.get("caption") if isinstance(m.get("caption"), str) else None
        out[image_id] = (ImageFact(id=image_id, caption=caption, source=m["source"], licence=m["licence"], origin="project"), path)
    for image_id, meta, path in media_files.collateral_images(settings, project.id):
        caption = meta.get("caption") if isinstance(meta.get("caption"), str) else None
        out[image_id] = (ImageFact(id=image_id, caption=caption, source=meta["source"], licence=meta["licence"], origin="upload"), path)
    return out


def published_projects(session: Session) -> list[ReProject]:
    return list(session.scalars(select(ReProject).where(ReProject.is_published.is_(True)).order_by(ReProject.name)))


def fact_sheet(session: Session, settings: Settings, project_id: uuid.UUID) -> FactSheet:
    p = session.get(ReProject, project_id)
    if p is None:
        raise NotFound("Project not found.")
    if not p.is_published:
        raise Conflict("Brochures and posters can only be made for projects published on the website.", code="project_not_published")
    rows = session.execute(
        select(ReUnit.bedrooms, func.count(), func.min(ReUnit.area_sqm), func.max(ReUnit.area_sqm), func.min(ReUnit.list_price))
        .where(ReUnit.project_id == p.id, ReUnit.is_public.is_(True), ReUnit.status == "available")
        .group_by(ReUnit.bedrooms)
        .order_by(ReUnit.bedrooms)
    ).all()
    unit_types = [
        UnitTypeFact(bedrooms=b, available=int(n), area_min_sqm=lo, area_max_sqm=hi, price_from_sar=price) for b, n, lo, hi, price in rows
    ]
    plans = marketing_plans(session, p.id)
    active = session.scalar(
        select(func.count()).select_from(RePaymentPlan).where(RePaymentPlan.project_id == p.id, RePaymentPlan.is_active.is_(True))
    )
    images = approved_images(settings, p)
    contact = ContactFact(
        phone=settings.collateral_contact_phone.strip() or None,
        email=settings.collateral_contact_email.strip() or None,
        website=settings.collateral_website_url.strip() or None,
    )
    missing = [
        name
        for name, absent in (
            ("images", not images),
            ("description", not p.description),
            ("amenities", not p.amenities),
            ("units", not unit_types),
            ("payment_plans", not plans),
            ("handover_date", p.handover_date is None),
            ("contact", not contact.any),
        )
        if absent
    ]
    return FactSheet(
        project_id=p.id,
        code=p.code,
        name=p.name,
        city=p.city,
        district=p.district,
        status=p.status,
        handover_date=p.handover_date,
        description=p.description,
        is_demo_data=p.is_demo_data,
        amenities=[a for a in (p.amenities or []) if isinstance(a, str) and a.strip()],
        available_units=sum(u.available for u in unit_types),
        price_from_sar=min((u.price_from_sar for u in unit_types), default=None),
        unit_types=unit_types,
        payment_plans=[
            PlanFact(
                name=pl.name,
                down_payment_pct=pl.down_payment_pct,
                installments=pl.installments,
                installment_frequency=pl.installment_frequency,
                handover_pct=pl.handover_pct,
            )
            for pl in plans
        ],
        excluded_plans=int(active or 0) - len(plans),
        images=[img for img, _ in images.values()],
        contact=contact,
        as_of=datetime.now(UTC),
        missing=missing,
    )


def key_fact_options(sheet: FactSheet, lang: Lang) -> list[tuple[str, str]]:
    """Short verified facts a poster may show, as (id, text). Absent facts simply produce no option."""
    out: list[tuple[str, str]] = []
    if sheet.available_units:
        out.append(("available", f"{sheet.available_units} {i18n.t('homes', lang)} {'available' if lang == 'en' else 'متاحة'}"))
    if sheet.unit_types:
        out.append(("bedrooms", i18n.bedroom_span([u.bedrooms for u in sheet.unit_types], lang)))
    if sheet.handover_date:
        out.append(("handover", f"{i18n.t('handover', lang)} {i18n.month_year(sheet.handover_date, lang)}"))
    out.append(("status", i18n.STATUS[sheet.status][lang]))
    location = ", ".join(x for x in (sheet.district, sheet.city) if x)
    out.append(("location", location))
    for i, p in enumerate(sheet.payment_plans):
        out.append((f"plan:{i}", i18n.plan_summary(p.down_payment_pct, p.installments, p.installment_frequency, p.handover_pct, lang)))
    for i, a in enumerate(sheet.amenities):
        out.append((f"amenity:{i}", a))
    return out
