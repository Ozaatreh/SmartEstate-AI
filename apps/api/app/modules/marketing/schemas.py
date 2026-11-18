from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Channel = Literal["instagram", "x", "linkedin", "email", "website", "whatsapp"]
Language = Literal["en", "ar"]
CampaignStatus = Literal["draft", "active", "completed", "archived"]

# Channel rules (length limits follow each platform's practical limits; hashtags only where they're used).
CHANNEL_RULES: dict[str, dict[str, object]] = {
    "instagram": {"label": "Instagram", "max_total": 2200, "hashtags": True, "headline_required": False},
    "x": {"label": "X", "max_total": 280, "hashtags": True, "headline_required": False},
    "linkedin": {"label": "LinkedIn", "max_total": 3000, "hashtags": True, "headline_required": False},
    "email": {"label": "Email", "max_total": 5000, "hashtags": False, "headline_required": True},
    "website": {"label": "Website", "max_total": 5000, "hashtags": False, "headline_required": True},
    "whatsapp": {"label": "WhatsApp", "max_total": 1000, "hashtags": False, "headline_required": False},
}
MAX_HASHTAGS = 30
HASHTAG = re.compile(r"^#?[\w؀-ۿ]{1,50}$")


def total_length(headline: str | None, body: str, call_to_action: str | None, hashtags: list[str]) -> int:
    """What the audience reads, as published: headline, body, CTA and hashtags separated by spaces/newlines."""
    parts = [p for p in (headline, body, call_to_action, " ".join(hashtags)) if p]
    return len("\n".join(parts))


def channel_problems(
    channel: str, headline: str | None, body: str, call_to_action: str | None, hashtags: list[str]
) -> list[dict[str, str]]:
    rules = CHANNEL_RULES[channel]
    problems: list[dict[str, str]] = []
    if rules["headline_required"] and not (headline or "").strip():
        problems.append({"field": "headline", "message": f"{rules['label']} content needs a headline (the subject / page title)."})
    if hashtags and not rules["hashtags"]:
        problems.append({"field": "hashtags", "message": f"{rules['label']} content doesn't use hashtags."})
    n, limit = total_length(headline, body, call_to_action, hashtags), int(rules["max_total"])  # type: ignore[call-overload]
    if n > limit:
        problems.append({"field": "body", "message": f"{rules['label']} allows {limit} characters; this is {n}."})
    return problems


class CampaignIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=3, max_length=150)
    objective: str = Field(min_length=3, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    project_id: uuid.UUID
    channels: list[Channel] = Field(min_length=1, max_length=6)
    start_date: date | None = None
    end_date: date | None = None
    status: Literal["draft", "active", "completed"] = "draft"

    @field_validator("channels")
    @classmethod
    def _unique(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(v))

    @model_validator(mode="after")
    def _dates(self) -> CampaignIn:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("The end date can't be before the start date.")
        return self


class CampaignUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=3, max_length=150)
    objective: str | None = Field(default=None, min_length=3, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    channels: list[Channel] | None = Field(default=None, min_length=1, max_length=6)
    start_date: date | None = None
    end_date: date | None = None
    status: Literal["draft", "active", "completed"] | None = None

    @field_validator("channels")
    @classmethod
    def _unique(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else list(dict.fromkeys(v))


class Ref(BaseModel):
    id: uuid.UUID
    code: str
    name: str


class PersonRef(BaseModel):
    id: uuid.UUID
    full_name: str


class StatusCounts(BaseModel):
    draft: int = 0
    pending_approval: int = 0
    approved: int = 0
    rejected: int = 0
    archived: int = 0


class CampaignOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    objective: str
    description: str | None
    project: Ref
    channels: list[str]
    start_date: date | None
    end_date: date | None
    status: str
    created_by: PersonRef | None
    created_at: datetime
    updated_at: datetime
    content: StatusCounts
    allowed_actions: list[str]


class ContentIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    campaign_id: uuid.UUID
    channel: Channel
    language: Language
    headline: str | None = Field(default=None, max_length=150)
    body: str = Field(min_length=1, max_length=5000)
    call_to_action: str | None = Field(default=None, max_length=120)
    hashtags: list[str] = Field(default_factory=list, max_length=MAX_HASHTAGS)

    @field_validator("hashtags")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        return normalise_hashtags(v)


class ContentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    channel: Channel | None = None
    language: Language | None = None
    headline: str | None = Field(default=None, max_length=150)
    body: str | None = Field(default=None, min_length=1, max_length=5000)
    call_to_action: str | None = Field(default=None, max_length=120)
    hashtags: list[str] | None = Field(default=None, max_length=MAX_HASHTAGS)
    note: str | None = Field(default=None, max_length=200)

    @field_validator("hashtags")
    @classmethod
    def _tags(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else normalise_hashtags(v)


def normalise_hashtags(v: list[str]) -> list[str]:
    out: list[str] = []
    for raw in v:
        tag = raw.strip()
        if not tag:
            continue
        if not HASHTAG.match(tag):
            raise ValueError(f"'{tag[:30]}' isn't a valid hashtag (letters, digits and _ only).")
        tag = tag if tag.startswith("#") else f"#{tag}"
        if tag.lower() not in {t.lower() for t in out}:
            out.append(tag)
    return out


class FactWarning(BaseModel):
    kind: str  # price | percentage | bedrooms
    text: str
    message: str


class VersionOut(BaseModel):
    version: int
    channel: str
    language: str
    headline: str | None
    body: str
    call_to_action: str | None
    hashtags: list[str]
    note: str
    edited_by: PersonRef | None
    created_at: datetime


class ApprovalStepOut(BaseModel):
    label: str
    status: str
    decided_by: PersonRef | None
    decided_at: datetime | None
    comment: str | None


class ApprovalRound(BaseModel):
    id: uuid.UUID
    status: str
    version: int | None
    requested_by: PersonRef | None
    created_at: datetime
    completed_at: datetime | None
    steps: list[ApprovalStepOut]


class ContentOut(BaseModel):
    id: uuid.UUID
    code: str
    campaign: Ref
    project: Ref
    channel: str
    language: str
    headline: str | None
    body: str
    call_to_action: str | None
    hashtags: list[str]
    status: str
    version: int
    generated_by_ai: bool
    created_by: PersonRef | None
    updated_at: datetime
    submitted_at: datetime | None
    decided_at: datetime | None
    rejection_comment: str | None


class ContentDetail(ContentOut):
    allowed_actions: list[str]
    approval_id: uuid.UUID | None  # the open (or latest) approval request
    can_decide: bool
    decide_blocked_reason: str | None
    approvals: list[ApprovalRound]
    versions: list[VersionOut]
    fact_warnings: list[FactWarning]
    channel_limit: int
    length: int


class FactsCheckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: uuid.UUID
    headline: str | None = Field(default=None, max_length=150)
    body: str = Field(default="", max_length=5000)
    call_to_action: str | None = Field(default=None, max_length=120)


class ProjectFacts(BaseModel):
    project: Ref
    city: str
    district: str | None
    status: str
    handover_date: date | None
    is_published: bool
    is_demo_data: bool
    amenities: list[str]
    available_units: int
    bedroom_options: list[dict[str, object]]  # [{bedrooms, available, price_from_sar, price_to_sar}]
    price_from_sar: str | None
    payment_plans: list[dict[str, object]]
    description: str | None


class MarketingAIStatus(BaseModel):
    enabled: bool
    reason: str
