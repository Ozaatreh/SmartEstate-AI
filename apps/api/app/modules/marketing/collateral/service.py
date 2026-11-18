"""Builds brochure and poster pages from the verified fact sheet, checks them, and renders the files."""

from __future__ import annotations

import base64
import uuid
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ValidationFailed
from app.core.permissions import Perm
from app.modules.audit.service import AuditService
from app.modules.identity.principal import Principal, ensure_permission
from app.modules.marketing.collateral import i18n, render
from app.modules.marketing.collateral.facts import FactSheet, approved_images, fact_sheet, key_fact_options, published_projects
from app.modules.marketing.collateral.i18n import Lang
from app.modules.marketing.collateral.schemas import (
    POSTER_FORMATS,
    POSTER_TEMPLATES,
    SECTIONS,
    BrochureRequest,
    CollateralOptions,
    FactSheetOut,
    Option,
    PosterRequest,
    ProjectChoice,
)
from app.modules.marketing.collateral.verify import ensure_verified
from app.modules.realestate.models import ReProject

HERE = Path(__file__).resolve().parent
FONTS = (
    ("Inter", "100 900", "inter-latin-wght-normal.woff2"),
    ("Fraunces", "100 900", "fraunces-latin-wght-normal.woff2"),
    ("IBM Plex Sans Arabic", "400", "ibm-plex-sans-arabic-arabic-400-normal.woff2"),
    ("IBM Plex Sans Arabic", "600", "ibm-plex-sans-arabic-arabic-600-normal.woff2"),
    ("IBM Plex Sans Arabic", "700", "ibm-plex-sans-arabic-arabic-700-normal.woff2"),
)
SECTION_LABELS = {
    "overview": "Overview and description",
    "location": "Location and key facts",
    "amenities": "Amenities and facilities",
    "units": "Available unit types and areas",
    "prices": "Prices (starting price and price per type)",
    "payment_plans": "Payment plans",
    "contact": "Contact and enquiries",
}


@lru_cache(maxsize=1)
def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(HERE / "templates"), autoescape=select_autoescape(["html"]), trim_blocks=True, lstrip_blocks=True
    )


@lru_cache(maxsize=1)
def _font_css() -> str:
    rules = []
    for family, weight, file in FONTS:
        data = base64.b64encode((HERE / "fonts" / file).read_bytes()).decode()
        rules.append(
            f"@font-face{{font-family:'{family}';font-weight:{weight};font-style:normal;font-display:block;"
            f"src:url(data:font/woff2;base64,{data}) format('woff2');}}"
        )
    return "\n".join(rules)


def _data_uri(path: Path) -> str:
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}[path.suffix.lower()]
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


class CollateralService:
    def __init__(self, session: Session, settings: Settings):
        self.session = session
        self.settings = settings
        self.audit = AuditService(session)

    # ------------------------------------------------------------------ choices
    def projects(self, principal: Principal) -> list[ProjectChoice]:
        ensure_permission(principal, Perm.MARKETING_COLLATERAL_GENERATE)
        return [ProjectChoice(id=p.id, code=p.code, name=p.name, is_demo_data=p.is_demo_data) for p in published_projects(self.session)]

    def options(self, principal: Principal, project_id: uuid.UUID) -> CollateralOptions:
        ensure_permission(principal, Perm.MARKETING_COLLATERAL_GENERATE)
        sheet = fact_sheet(self.session, self.settings, project_id)
        data = sheet.model_dump()
        data["handover_date"] = sheet.handover_date.isoformat() if sheet.handover_date else None
        return CollateralOptions(
            facts=FactSheetOut(**data),
            key_facts={lang: [Option(id=i, label=text) for i, text in key_fact_options(sheet, lang)] for lang in ("en", "ar")},
            sections=[Option(id=s, label=SECTION_LABELS[s]) for s in SECTIONS],
            formats=[{"id": k, "label": v[0], "width": v[1], "height": v[2]} for k, v in POSTER_FORMATS.items()],
            templates=[Option(id=k, label=v) for k, v in POSTER_TEMPLATES.items()],
            ctas={lang: [Option(id=k, label=v[lang]) for k, v in i18n.CTAS.items()] for lang in ("en", "ar")},
        )

    # ------------------------------------------------------------------ pages
    def _hero(self, sheet: FactSheet, image_id: str | None) -> str | None:
        if image_id is None:
            return None
        project = self.session.get(ReProject, sheet.project_id)
        images = approved_images(self.settings, project) if project else {}
        if image_id not in images:
            raise ValidationFailed("Choose one of the project's approved images.", code="image_not_approved")
        return _data_uri(images[image_id][1])

    def _common(self, sheet: FactSheet, lang: Lang) -> dict:
        return {
            "lang": lang,
            "dir": "rtl" if lang == "ar" else "ltr",
            "t": lambda key: i18n.t(key, lang),
            "font_css": _font_css(),
            "name": sheet.name,
            "location": ", ".join(x for x in (sheet.district, sheet.city) if x),
            "status": i18n.STATUS[sheet.status][lang],
            "handover": i18n.month_year(sheet.handover_date, lang) if sheet.handover_date else None,
            "is_demo": sheet.is_demo_data,
            "as_of": i18n.day_month_year(sheet.as_of.date(), lang),
        }

    def brochure_html(self, principal: Principal, req: BrochureRequest) -> str:
        ensure_permission(principal, Perm.MARKETING_COLLATERAL_GENERATE)
        sheet = fact_sheet(self.session, self.settings, req.project_id)
        lang: Lang = req.language
        on = set(req.sections)
        prices = "prices" in on
        ctx = self._common(sheet, lang) | {
            "hero": self._hero(sheet, req.image_id),
            "price_from": i18n.money(sheet.price_from_sar, lang) if prices and sheet.price_from_sar is not None else None,
            "description": sheet.description if "overview" in on else None,
            "key_facts": (
                [
                    (i18n.t(k, lang), v, data)
                    for k, v, data in (
                        ("city", sheet.city, True),
                        ("district", sheet.district, True),
                        ("status", i18n.STATUS[sheet.status][lang], False),
                        ("handover", i18n.month_year(sheet.handover_date, lang) if sheet.handover_date else None, False),
                        ("available_homes", str(sheet.available_units) if sheet.unit_types else None, False),
                    )
                    if v
                ]
                if "location" in on
                else []
            ),
            "amenities": sheet.amenities if "amenities" in on else [],
            "units": (
                [
                    {
                        "type": i18n.bedrooms(u.bedrooms, lang),
                        "area_nums": i18n.area_range(u.area_min_sqm, u.area_max_sqm, lang).rsplit(" ", 1)[0],
                        "area_unit": "m²" if lang == "en" else "م²",
                        "available": u.available,
                        "price": i18n.money(u.price_from_sar, lang) if prices else None,
                    }
                    for u in sheet.unit_types
                ]
                if "units" in on
                else []
            ),
            "show_prices": prices,
            "plans": (
                [
                    {
                        "name": p.name,
                        "down": i18n.pct(p.down_payment_pct),
                        "installments": (f"{p.installments} × {i18n.FREQUENCY[p.installment_frequency][lang]}" if p.installments else None),
                        "handover": i18n.pct(p.handover_pct) if p.handover_pct else None,
                    }
                    for p in sheet.payment_plans
                ]
                if "payment_plans" in on
                else []
            ),
            "highlights": [
                (label, value)
                for label, value in (
                    (i18n.t("available_homes", lang), str(sheet.available_units) if sheet.unit_types and "units" in on else None),
                    (i18n.t("starting_from", lang), i18n.money(sheet.price_from_sar, lang) if prices and sheet.price_from_sar else None),
                    (i18n.t("handover", lang), i18n.month_year(sheet.handover_date, lang) if sheet.handover_date else None),
                )
                if value
            ]
            if ("units" in on or "payment_plans" in on)
            else [],
            "contact": sheet.contact if "contact" in on and sheet.contact.any else None,
            "credits": [i for i in sheet.images if i.id == req.image_id],
        }
        html = _env().get_template("brochure.html").render(**ctx)
        ensure_verified(html, sheet.allowed_numbers())
        return html

    def poster_html(self, principal: Principal, req: PosterRequest) -> tuple[str, int, int]:
        ensure_permission(principal, Perm.MARKETING_COLLATERAL_GENERATE)
        sheet = fact_sheet(self.session, self.settings, req.project_id)
        lang: Lang = req.language
        options = dict(key_fact_options(sheet, lang))
        unknown = [f for f in req.facts if f not in options]
        if unknown:
            raise ValidationFailed("Pick key facts from the project's verified facts.", code="unknown_fact", details={"facts": unknown})
        _, width, height = POSTER_FORMATS[req.format]
        ctx = self._common(sheet, lang) | {
            "hero": self._hero(sheet, req.image_id),
            "width": width,
            "height": height,
            "scale": round(min(width, height) / 1080, 4),
            "orientation": "landscape" if width > height else ("portrait" if height > width else "square"),
            "template": req.template,
            "price_from": i18n.money(sheet.price_from_sar, lang) if req.show_price and sheet.price_from_sar is not None else None,
            "facts": [options[f] for f in dict.fromkeys(req.facts)],
            "cta": i18n.CTAS[req.cta][lang],
            "website": sheet.contact.website,
        }
        html = _env().get_template("poster.html").render(**ctx)
        ensure_verified(html, sheet.allowed_numbers())
        return html, width, height

    # ------------------------------------------------------------------ files
    def brochure_pdf(self, principal: Principal, req: BrochureRequest) -> tuple[bytes, str]:
        html = self.brochure_html(principal, req)
        pdf = render.render_pdf(html)
        code = self._code(req.project_id)
        self.audit.record(
            "marketing.brochure_generated",
            actor_user_id=principal.user_id,
            entity_type="re_project",
            entity_id=req.project_id,
            summary=f"{code} brochure ({req.language.upper()}) · {', '.join(req.sections) or 'cover only'}",
        )
        self.session.commit()
        return pdf, f"{code}-brochure-{req.language}.pdf"

    def poster_png(self, principal: Principal, req: PosterRequest) -> tuple[bytes, str]:
        html, width, height = self.poster_html(principal, req)
        png = render.render_png(html, width, height)
        code = self._code(req.project_id)
        self.audit.record(
            "marketing.poster_generated",
            actor_user_id=principal.user_id,
            entity_type="re_project",
            entity_id=req.project_id,
            summary=f"{code} {POSTER_FORMATS[req.format][0]} {width}×{height} ({req.language.upper()}, {req.template})",
        )
        self.session.commit()
        return png, f"{code}-{req.format.replace('_', '-')}-{width}x{height}-{req.language}.png"

    def _code(self, project_id: uuid.UUID) -> str:
        p = self.session.get(ReProject, project_id)
        return p.code if p else "project"
