from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Representation = Literal["design", "as_built", "illustrative"]


def _clean(v: str | None) -> str | None:
    if v is None:
        return None
    v = " ".join(v.split())
    return v or None


class ModelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=2, max_length=150)
    unit_id: uuid.UUID | None = None
    representation: Representation
    caption: str | None = Field(default=None, max_length=500)
    source: str | None = Field(default=None, max_length=200)
    licence: str | None = Field(default=None, max_length=200)

    @field_validator("title", "caption", "source", "licence", mode="before")
    @classmethod
    def _strip(cls, v: object) -> object:
        return _clean(v) if isinstance(v, str) else v


class ModelUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=2, max_length=150)
    unit_id: uuid.UUID | None = None
    representation: Representation | None = None
    caption: str | None = Field(default=None, max_length=500)
    source: str | None = Field(default=None, max_length=200)
    licence: str | None = Field(default=None, max_length=200)

    @field_validator("title", "caption", "source", "licence", mode="before")
    @classmethod
    def _strip(cls, v: object) -> object:
        return _clean(v) if isinstance(v, str) else v


class PersonRef(BaseModel):
    id: uuid.UUID
    full_name: str


class ModelOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    unit_id: uuid.UUID | None
    unit_code: str | None
    title: str
    caption: str | None
    representation: str
    source: str | None
    licence: str | None
    status: str
    format: str | None
    size_bytes: int | None
    sha256: str | None
    original_filename: str | None
    mesh_count: int | None
    file_version: int
    uploaded_at: datetime | None
    uploaded_by: PersonRef | None
    approved_at: datetime | None
    approved_by: PersonRef | None
    created_at: datetime
    updated_at: datetime
    publicly_visible: bool  # approved, project published and (unit) public
    allowed_actions: list[str]


class UploadLimits(BaseModel):
    formats: list[str]
    max_bytes: int
