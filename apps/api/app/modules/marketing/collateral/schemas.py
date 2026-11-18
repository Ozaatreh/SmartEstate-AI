from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.marketing.collateral.facts import ContactFact, ImageFact, PlanFact, UnitTypeFact

Language = Literal["en", "ar"]
Section = Literal["overview", "location", "amenities", "units", "prices", "payment_plans", "contact"]
PosterFormat = Literal["instagram_post", "instagram_story", "linkedin", "facebook"]
PosterTemplate = Literal["classic", "split", "minimal"]
Cta = Literal["book_viewing", "register_interest", "enquire_now", "visit_sales"]

SECTIONS: tuple[str, ...] = ("overview", "location", "amenities", "units", "prices", "payment_plans", "contact")
POSTER_FORMATS: dict[str, tuple[str, int, int]] = {
    "instagram_post": ("Instagram post", 1080, 1080),
    "instagram_story": ("Instagram story", 1080, 1920),
    "linkedin": ("LinkedIn post", 1200, 627),
    "facebook": ("Facebook post", 1200, 630),
}
POSTER_TEMPLATES = {"classic": "Classic — full image", "split": "Split — image and panel", "minimal": "Minimal — type-led"}


class BrochureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: uuid.UUID
    language: Language = "en"
    sections: list[Section] = Field(default_factory=lambda: list(SECTIONS), max_length=len(SECTIONS))
    image_id: str | None = Field(default=None, max_length=40)


class PosterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: uuid.UUID
    language: Language = "en"
    format: PosterFormat = "instagram_post"
    template: PosterTemplate = "classic"
    image_id: str | None = Field(default=None, max_length=40)
    show_price: bool = True
    facts: list[str] = Field(default_factory=list, max_length=3)
    cta: Cta = "book_viewing"


class PreviewOut(BaseModel):
    html: str
    width: int
    height: int | None  # None for multi-page brochures


class Option(BaseModel):
    id: str
    label: str


class ProjectChoice(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    is_demo_data: bool


class FactSheetOut(BaseModel):
    project_id: uuid.UUID
    code: str
    name: str
    city: str
    district: str | None
    status: str
    handover_date: str | None
    description: str | None
    is_demo_data: bool
    amenities: list[str]
    available_units: int
    price_from_sar: Decimal | None
    unit_types: list[UnitTypeFact]
    payment_plans: list[PlanFact]
    excluded_plans: int
    images: list[ImageFact]
    contact: ContactFact
    as_of: datetime
    missing: list[str]


class CollateralOptions(BaseModel):
    facts: FactSheetOut
    key_facts: dict[str, list[Option]]  # per language
    sections: list[Option]
    formats: list[dict]
    templates: list[Option]
    ctas: dict[str, list[Option]]
