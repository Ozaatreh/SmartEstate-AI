"""3D property models (Phase 7E): GLB / glTF files attached to a project or one of its units.

A model is shown publicly only when it is ``approved`` (which needs a validated file plus a recorded source and licence),
its project is published, and — for a unit model — the unit is public. Files live under ``MODEL_STORAGE_DIR`` with
random names; paths are never exposed. ``representation`` says what the geometry is, so an illustrative model is never
passed off as the real building.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey, enum_check
from app.modules.realestate.models import ReProject, ReUnit

MODEL_STATUSES = ("draft", "approved", "archived")
MODEL_FORMATS = ("glb", "gltf")
# design: the architect's design model · as_built: captured from the finished building · illustrative: indicative only
REPRESENTATIONS = ("design", "as_built", "illustrative")


class RePropertyModel(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "re_property_models"
    __table_args__ = (
        enum_check("status", MODEL_STATUSES),
        enum_check("format", MODEL_FORMATS),
        enum_check("representation", REPRESENTATIONS),
        CheckConstraint(
            "status <> 'approved' OR (file_key IS NOT NULL AND source IS NOT NULL AND licence IS NOT NULL)", name="approved_complete"
        ),
        CheckConstraint("(file_key IS NULL) = (size_bytes IS NULL)", name="file_fields_paired"),
        Index("ix_re_property_models_project_status", "project_id", "status"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("re_projects.id", ondelete="RESTRICT"), nullable=False)
    unit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("re_units.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    caption: Mapped[str | None] = mapped_column(Text)
    representation: Mapped[str] = mapped_column(String(15), nullable=False)
    source: Mapped[str | None] = mapped_column(String(200))
    licence: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="draft", server_default="draft")
    # file (all null until the first upload)
    file_key: Mapped[str | None] = mapped_column(String(80), unique=True)
    format: Mapped[str | None] = mapped_column(String(4))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(String(64))
    original_filename: Mapped[str | None] = mapped_column(String(200))
    mesh_count: Mapped[int | None] = mapped_column(Integer)
    file_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    project: Mapped[ReProject] = relationship(lazy="joined")
    unit: Mapped[ReUnit | None] = relationship(lazy="joined")
