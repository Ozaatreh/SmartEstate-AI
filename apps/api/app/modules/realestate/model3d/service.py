"""Managing 3D property models (Phase 7E). Uses the existing real-estate permissions:
``realestate.inventory.read`` to list and download, ``realestate.inventory.manage`` for everything else.

Lifecycle: draft → approved → archived (→ draft again). Approval needs a validated file plus a source and licence.
Uploading a new file, or editing an approved model, sends it back to draft so the public never sees an unreviewed
change. Every action is audited.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import BusinessRuleViolation, Conflict, NotFound, ValidationFailed
from app.core.permissions import Perm
from app.modules.audit.service import AuditService
from app.modules.identity.models import User
from app.modules.identity.principal import Principal, ensure_permission
from app.modules.realestate.model3d import storage
from app.modules.realestate.model3d.models import RePropertyModel
from app.modules.realestate.model3d.schemas import ModelIn, ModelOut, ModelUpdate, PersonRef, UploadLimits
from app.modules.realestate.model3d.validate import EXTENSIONS, validate_model
from app.modules.realestate.models import ReProject, ReUnit

PUBLIC_FIELDS = ("title", "unit_id", "representation", "caption", "source", "licence")


def publicly_visible(m: RePropertyModel) -> bool:
    if m.status != "approved" or not m.project.is_published:
        return False
    return m.unit is None or (m.unit.is_public and m.unit.project_id == m.project_id)


class PropertyModelService:
    def __init__(self, session: Session, settings: Settings):
        self.session = session
        self.settings = settings
        self.audit = AuditService(session)

    # ------------------------------------------------------------------ helpers
    @property
    def max_bytes(self) -> int:
        return int(self.settings.model_max_upload_mb) * 1024 * 1024

    def limits(self) -> UploadLimits:
        return UploadLimits(formats=sorted(EXTENSIONS), max_bytes=self.max_bytes)

    def _get(self, model_id: uuid.UUID, lock: bool = False) -> RePropertyModel:
        stmt = select(RePropertyModel).where(RePropertyModel.id == model_id)
        if lock:
            stmt = stmt.with_for_update(of=RePropertyModel)
        m = self.session.scalars(stmt).first()
        if m is None:
            raise NotFound("3D model not found.")
        return m

    def _unit(self, project_id: uuid.UUID, unit_id: uuid.UUID | None) -> ReUnit | None:
        if unit_id is None:
            return None
        unit = self.session.get(ReUnit, unit_id)
        if unit is None or unit.project_id != project_id:
            raise ValidationFailed("Choose a unit of this project.", code="unit_not_in_project")
        return unit

    def _record(self, principal: Principal, action: str, m: RePropertyModel, summary: str, changes: dict | None = None) -> None:
        self.audit.record(
            f"realestate.model_{action}",
            actor_user_id=principal.user_id,
            entity_type="re_property_model",
            entity_id=m.id,
            summary=f"{m.project.code} · {m.title}: {summary}",
            changes=changes,
        )

    def _person(self, user_id: uuid.UUID | None) -> PersonRef | None:
        user = self.session.get(User, user_id) if user_id else None
        return PersonRef(id=user.id, full_name=user.full_name) if user else None

    def to_out(self, principal: Principal, m: RePropertyModel) -> ModelOut:
        manage = principal.has(Perm.REALESTATE_INVENTORY_MANAGE)
        actions = []
        if m.file_key:
            actions.append("download")
        if manage:
            actions += ["edit", "upload"]
            if m.status == "draft" and m.file_key and m.source and m.licence:
                actions.append("approve")
            if m.status in ("draft", "approved"):
                actions.append("archive")
            if m.status == "archived":
                actions.append("restore")
            if m.status != "approved":
                actions.append("delete")
        return ModelOut(
            id=m.id,
            project_id=m.project_id,
            unit_id=m.unit_id,
            unit_code=f"{m.unit.building.code}-{m.unit.unit_number}" if m.unit else None,
            title=m.title,
            caption=m.caption,
            representation=m.representation,
            source=m.source,
            licence=m.licence,
            status=m.status,
            format=m.format,
            size_bytes=m.size_bytes,
            sha256=m.sha256,
            original_filename=m.original_filename,
            mesh_count=m.mesh_count,
            file_version=m.file_version,
            uploaded_at=m.uploaded_at,
            uploaded_by=self._person(m.uploaded_by),
            approved_at=m.approved_at,
            approved_by=self._person(m.approved_by),
            created_at=m.created_at,
            updated_at=m.updated_at,
            publicly_visible=publicly_visible(m),
            allowed_actions=actions,
        )

    # ------------------------------------------------------------------ read
    def list_for_project(self, principal: Principal, project_id: uuid.UUID) -> list[ModelOut]:
        ensure_permission(principal, Perm.REALESTATE_INVENTORY_READ)
        if self.session.get(ReProject, project_id) is None:
            raise NotFound("Project not found.")
        rows = self.session.scalars(
            select(RePropertyModel).where(RePropertyModel.project_id == project_id).order_by(RePropertyModel.created_at.desc())
        )
        return [self.to_out(principal, m) for m in rows]

    def get(self, principal: Principal, model_id: uuid.UUID) -> ModelOut:
        ensure_permission(principal, Perm.REALESTATE_INVENTORY_READ)
        return self.to_out(principal, self._get(model_id))

    def file(self, principal: Principal, model_id: uuid.UUID) -> tuple[Path, RePropertyModel]:
        ensure_permission(principal, Perm.REALESTATE_INVENTORY_READ)
        m = self._get(model_id)
        path = storage.path_for(self.settings, m.file_key) if m.file_key else None
        if path is None or not path.is_file():
            raise NotFound("This model has no file yet.")
        return path, m

    # ------------------------------------------------------------------ write
    def create(self, principal: Principal, project_id: uuid.UUID, data: ModelIn) -> ModelOut:
        ensure_permission(principal, Perm.REALESTATE_INVENTORY_MANAGE)
        project = self.session.get(ReProject, project_id)
        if project is None:
            raise NotFound("Project not found.")
        self._unit(project.id, data.unit_id)
        m = RePropertyModel(project_id=project.id, created_by=principal.user_id, status="draft", **data.model_dump())
        self.session.add(m)
        self.session.flush()
        self.session.refresh(m)
        self._record(principal, "created", m, "created (no file yet)")
        self.session.commit()
        return self.to_out(principal, m)

    def update(self, principal: Principal, model_id: uuid.UUID, data: ModelUpdate) -> ModelOut:
        ensure_permission(principal, Perm.REALESTATE_INVENTORY_MANAGE)
        m = self._get(model_id, lock=True)
        values = {k: getattr(data, k) for k in data.model_fields_set}
        for required in ("title", "representation"):
            if values.get(required, "") is None:
                values.pop(required)
        if "unit_id" in values:
            self._unit(m.project_id, values["unit_id"])
        changes = {}
        for k, v in values.items():
            if getattr(m, k) != v:
                changes[k] = [str(getattr(m, k)) if getattr(m, k) is not None else None, str(v) if v is not None else None]
                setattr(m, k, v)
        if changes:
            if m.status == "approved":  # what the public sees changed: review it again
                m.status, m.approved_at, m.approved_by = "draft", None, None
                changes["status"] = ["approved", "draft"]
            self._record(principal, "updated", m, "details updated", changes)
        self.session.commit()
        self.session.refresh(m)
        return self.to_out(principal, m)

    def upload(self, principal: Principal, model_id: uuid.UUID, data: bytes, filename: str) -> ModelOut:
        ensure_permission(principal, Perm.REALESTATE_INVENTORY_MANAGE)
        m = self._get(model_id, lock=True)
        info = validate_model(data, filename, max_bytes=self.max_bytes)
        new_key = storage.save(self.settings, data, info.format)
        old_key, was = m.file_key, m.status
        try:
            m.file_key, m.format, m.size_bytes, m.sha256, m.mesh_count = new_key, info.format, info.size_bytes, info.sha256, info.mesh_count
            m.original_filename = filename.strip()[-200:]
            m.file_version += 1
            m.uploaded_at, m.uploaded_by = datetime.now(UTC), principal.user_id
            m.status, m.approved_at, m.approved_by = "draft", None, None
            self._record(
                principal,
                "file_uploaded",
                m,
                f"file v{m.file_version} ({info.format.upper()}, {info.size_bytes:,} bytes, {info.mesh_count} meshes)",
                {"status": [was, "draft"]} if was != "draft" else None,
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            storage.delete(self.settings, new_key)
            raise
        storage.delete(self.settings, old_key)  # only after the new file is committed
        self.session.refresh(m)
        return self.to_out(principal, m)

    def approve(self, principal: Principal, model_id: uuid.UUID) -> ModelOut:
        ensure_permission(principal, Perm.REALESTATE_INVENTORY_MANAGE)
        m = self._get(model_id, lock=True)
        if m.status != "draft":
            raise Conflict("Only draft models can be approved.", code="invalid_status")
        if not m.file_key:
            raise BusinessRuleViolation("Upload the model file first.", code="model_file_missing")
        if not (m.source and m.licence):
            raise BusinessRuleViolation("Record the model's source and licence before approving it.", code="model_provenance_missing")
        m.status, m.approved_at, m.approved_by = "approved", datetime.now(UTC), principal.user_id
        self._record(principal, "approved", m, f"approved (file v{m.file_version}, {m.representation})")
        self.session.commit()
        self.session.refresh(m)
        return self.to_out(principal, m)

    def archive(self, principal: Principal, model_id: uuid.UUID) -> ModelOut:
        ensure_permission(principal, Perm.REALESTATE_INVENTORY_MANAGE)
        m = self._get(model_id, lock=True)
        if m.status == "archived":
            raise Conflict("The model is already archived.", code="invalid_status")
        was = m.status
        m.status = "archived"
        self._record(principal, "archived", m, f"archived (was {was})")
        self.session.commit()
        self.session.refresh(m)
        return self.to_out(principal, m)

    def restore(self, principal: Principal, model_id: uuid.UUID) -> ModelOut:
        ensure_permission(principal, Perm.REALESTATE_INVENTORY_MANAGE)
        m = self._get(model_id, lock=True)
        if m.status != "archived":
            raise Conflict("Only archived models can be restored.", code="invalid_status")
        m.status, m.approved_at, m.approved_by = "draft", None, None
        self._record(principal, "restored", m, "restored to draft")
        self.session.commit()
        self.session.refresh(m)
        return self.to_out(principal, m)

    def delete(self, principal: Principal, model_id: uuid.UUID) -> None:
        ensure_permission(principal, Perm.REALESTATE_INVENTORY_MANAGE)
        m = self._get(model_id, lock=True)
        if m.status == "approved":
            raise Conflict("Archive an approved model before deleting it.", code="model_approved")
        key = m.file_key
        self._record(principal, "deleted", m, "deleted")
        self.session.delete(m)
        self.session.commit()
        storage.delete(self.settings, key)
