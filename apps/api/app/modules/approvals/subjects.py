"""Approvable document types register an adapter here, so approvals never imports business modules."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from app.modules.approvals.models import ApprovalRequest
    from app.modules.identity.principal import Principal


class ApprovalSubject(Protocol):
    entity_type: str
    label: str

    def link(self, entity_id: str) -> str: ...

    def on_approved(self, session: Session, approval: ApprovalRequest, actor: Principal) -> None:
        """Called inside the decision transaction after the final step is approved."""

    def on_rejected(self, session: Session, approval: ApprovalRequest, actor: Principal, comment: str) -> None:
        """Called inside the decision transaction when any step rejects."""


SUBJECTS: dict[str, ApprovalSubject] = {}


def register_subject(subject: ApprovalSubject) -> None:
    SUBJECTS[subject.entity_type] = subject


def subject_for(entity_type: str) -> ApprovalSubject:
    try:
        return SUBJECTS[entity_type]
    except KeyError as exc:  # pragma: no cover - programming error
        raise RuntimeError(f"No approval subject registered for {entity_type!r}") from exc
