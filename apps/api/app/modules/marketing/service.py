"""Marketing Studio service (Phase 7B).

Lifecycle
- Campaign: ``draft → active → completed``; ``archived`` from any state (read-only afterwards). Needs
  ``marketing.campaigns.manage`` to change; ``marketing.campaigns.read`` to view.
- Content: ``draft → pending_approval → approved | rejected``. Editing a rejected item turns it back into a draft
  (new version); approved items are read-only. ``archived`` from any state except pending. Approved content is never
  published automatically — nothing in the system posts anywhere.

Approval (shared engine): submitting opens an ``approval_requests`` row (entity ``marketing_content``, level
``marketing`` → permission ``marketing.content.approve``) **in the same transaction** as the status change, and emits
``marketing_content.submitted`` for the ``marketing.content_review`` workflow (route check + reminders). Every user who
wrote or edited the content is excluded from deciding it, in addition to the submitter (no self-approval).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.automation import events
from app.common.listing import ListParams, apply_sort, escape_like, paginate
from app.core.errors import BusinessRuleViolation, Conflict, NotFound, PermissionDenied, ValidationFailed
from app.core.permissions import Perm
from app.modules.approvals.models import ApprovalRequest
from app.modules.approvals.service import ApprovalService
from app.modules.approvals.subjects import register_subject
from app.modules.audit.service import AuditService
from app.modules.identity.models import User
from app.modules.identity.principal import Principal, ensure_permission
from app.modules.marketing.facts import check_text
from app.modules.marketing.models import MarketingCampaign, MarketingContent, MarketingContentVersion
from app.modules.marketing.schemas import (
    CHANNEL_RULES,
    ApprovalRound,
    ApprovalStepOut,
    CampaignIn,
    CampaignOut,
    CampaignUpdate,
    ContentDetail,
    ContentIn,
    ContentOut,
    ContentUpdate,
    PersonRef,
    Ref,
    StatusCounts,
    VersionOut,
    channel_problems,
    total_length,
)
from app.modules.realestate.models import ReProject

ENTITY = "marketing_content"
EDITABLE = ("draft", "rejected")
CONTENT_FIELDS = ("channel", "language", "headline", "body", "call_to_action", "hashtags")
CAMPAIGN_SORT = {"created_at": MarketingCampaign.created_at, "name": MarketingCampaign.name, "start_date": MarketingCampaign.start_date}
CONTENT_SORT = {"updated_at": MarketingContent.updated_at, "created_at": MarketingContent.created_at, "status": MarketingContent.status}


def _now() -> datetime:
    return datetime.now(UTC)


def _person(u: User | None) -> PersonRef | None:
    return PersonRef(id=u.id, full_name=u.full_name) if u else None


def _fields_error(problems: list[dict[str, str]]) -> ValidationFailed:
    return ValidationFailed(problems[0]["message"], details={"fields": problems})


class MarketingService:
    def __init__(self, session: Session):
        self.session = session
        self.audit = AuditService(session)

    # ================================================================== campaigns
    def _campaign(self, campaign_id: uuid.UUID) -> MarketingCampaign:
        c = self.session.get(MarketingCampaign, campaign_id)
        if c is None:
            raise NotFound("Campaign not found.")
        return c

    def _campaign_actions(self, principal: Principal, c: MarketingCampaign) -> list[str]:
        actions: list[str] = []
        if principal.has(Perm.MARKETING_CAMPAIGNS_MANAGE) and c.status != "archived":
            actions += ["edit", "archive"]
        if principal.has(Perm.MARKETING_CONTENT_CREATE) and c.status != "archived":
            actions.append("add_content")
        return actions

    def _counts(self, ids: list[uuid.UUID]) -> dict[uuid.UUID, StatusCounts]:
        out: dict[uuid.UUID, dict[str, int]] = {}
        if ids:
            rows = self.session.execute(
                select(MarketingContent.campaign_id, MarketingContent.status, func.count())
                .where(MarketingContent.campaign_id.in_(ids))
                .group_by(MarketingContent.campaign_id, MarketingContent.status)
            ).all()
            for cid, status, n in rows:
                out.setdefault(cid, {})[status] = int(n)
        return {cid: StatusCounts(**v) for cid, v in out.items()}

    def campaign_out(self, principal: Principal, c: MarketingCampaign, counts: StatusCounts | None = None) -> CampaignOut:
        return CampaignOut(
            id=c.id,
            code=c.code,
            name=c.name,
            objective=c.objective,
            description=c.description,
            project=Ref(id=c.project.id, code=c.project.code, name=c.project.name),
            channels=list(c.channels),
            start_date=c.start_date,
            end_date=c.end_date,
            status=c.status,
            created_by=_person(c.creator),
            created_at=c.created_at,
            updated_at=c.updated_at,
            content=counts if counts is not None else self._counts([c.id]).get(c.id, StatusCounts()),
            allowed_actions=self._campaign_actions(principal, c),
        )

    def list_campaigns(
        self, principal: Principal, params: ListParams, *, status: str | None, project_id: uuid.UUID | None
    ) -> tuple[list[CampaignOut], int, int]:
        ensure_permission(principal, Perm.MARKETING_CAMPAIGNS_READ)
        stmt = select(MarketingCampaign)
        if status == "current":
            stmt = stmt.where(MarketingCampaign.status != "archived")
        elif status:
            stmt = stmt.where(MarketingCampaign.status == status)
        if project_id:
            stmt = stmt.where(MarketingCampaign.project_id == project_id)
        if params.q:
            term = f"%{escape_like(params.q)}%"
            stmt = stmt.where(or_(MarketingCampaign.name.ilike(term, escape="\\"), MarketingCampaign.code.ilike(term, escape="\\")))
        rows, total, pages = paginate(self.session, apply_sort(stmt, params.sort, CAMPAIGN_SORT, "-created_at"), params)
        counts = self._counts([c.id for c in rows])
        return [self.campaign_out(principal, c, counts.get(c.id, StatusCounts())) for c in rows], total, pages

    def get_campaign(self, principal: Principal, campaign_id: uuid.UUID) -> CampaignOut:
        ensure_permission(principal, Perm.MARKETING_CAMPAIGNS_READ)
        return self.campaign_out(principal, self._campaign(campaign_id))

    def create_campaign(self, principal: Principal, data: CampaignIn) -> MarketingCampaign:
        ensure_permission(principal, Perm.MARKETING_CAMPAIGNS_MANAGE)
        from app.common.codes import next_code

        if self.session.get(ReProject, data.project_id) is None:
            raise ValidationFailed(details={"fields": [{"field": "project_id", "message": "Choose a real-estate project."}]})
        c = MarketingCampaign(
            code=next_code(self.session, "marketing_campaign"),
            name=data.name,
            objective=data.objective,
            description=data.description,
            project_id=data.project_id,
            channels=list(data.channels),
            start_date=data.start_date,
            end_date=data.end_date,
            status=data.status,
            created_by=principal.user_id,
        )
        self.session.add(c)
        self.session.flush()
        self.audit.record(
            "marketing.campaign_created",
            actor_user_id=principal.user_id,
            entity_type="marketing_campaign",
            entity_id=c.id,
            summary=f"{c.code} · {c.name}",
        )
        self.session.commit()
        return c

    def update_campaign(self, principal: Principal, campaign_id: uuid.UUID, data: CampaignUpdate) -> MarketingCampaign:
        ensure_permission(principal, Perm.MARKETING_CAMPAIGNS_MANAGE)
        c = self.session.scalar(select(MarketingCampaign).where(MarketingCampaign.id == campaign_id).with_for_update(of=MarketingCampaign))
        if c is None:
            raise NotFound("Campaign not found.")
        if c.status == "archived":
            raise BusinessRuleViolation("Archived campaigns can't be changed.", code="campaign_archived")
        values = {k: getattr(data, k) for k in data.model_fields_set}
        for required in ("name", "objective", "channels", "status"):
            if required in values and values[required] is None:
                values.pop(required)
        start, end = values.get("start_date", c.start_date), values.get("end_date", c.end_date)
        if start and end and end < start:
            raise ValidationFailed(details={"fields": [{"field": "end_date", "message": "The end date can't be before the start date."}]})
        if "channels" in values:
            used = set(
                self.session.scalars(
                    select(MarketingContent.channel).where(MarketingContent.campaign_id == c.id, MarketingContent.status != "archived")
                )
            )
            missing = used - set(values["channels"])
            if missing:
                names = ", ".join(sorted(str(CHANNEL_RULES[m]["label"]) for m in missing))
                raise BusinessRuleViolation(f"Content exists for {names}; archive it before removing the channel.", code="channel_in_use")
        changes = {k: [str(getattr(c, k)), str(v)] for k, v in values.items() if getattr(c, k) != v}
        for k, v in values.items():
            setattr(c, k, v)
        if changes:
            self.audit.record(
                "marketing.campaign_updated",
                actor_user_id=principal.user_id,
                entity_type="marketing_campaign",
                entity_id=c.id,
                summary=f"{c.code} updated",
                changes=changes,
            )
        self.session.commit()
        return c

    def archive_campaign(self, principal: Principal, campaign_id: uuid.UUID) -> MarketingCampaign:
        ensure_permission(principal, Perm.MARKETING_CAMPAIGNS_MANAGE)
        c = self.session.scalar(select(MarketingCampaign).where(MarketingCampaign.id == campaign_id).with_for_update(of=MarketingCampaign))
        if c is None:
            raise NotFound("Campaign not found.")
        if c.status == "archived":
            return c
        pending = self.session.scalar(
            select(func.count())
            .select_from(MarketingContent)
            .where(MarketingContent.campaign_id == c.id, MarketingContent.status == "pending_approval")
        )
        if pending:
            raise BusinessRuleViolation("Content of this campaign is waiting for review; decide it first.", code="content_pending")
        previous, c.status, c.archived_at = c.status, "archived", _now()
        self.audit.record(
            "marketing.campaign_archived",
            actor_user_id=principal.user_id,
            entity_type="marketing_campaign",
            entity_id=c.id,
            summary=f"{c.code} archived",
            changes={"status": [previous, "archived"]},
        )
        self.session.commit()
        return c

    # ================================================================== content
    def _content(self, content_id: uuid.UUID, *, lock: bool = False) -> MarketingContent:
        stmt = select(MarketingContent).where(MarketingContent.id == content_id)
        if lock:
            stmt = stmt.with_for_update(of=MarketingContent)
        c = self.session.scalar(stmt)
        if c is None:
            raise NotFound("Content not found.")
        return c

    def _validate(self, c: MarketingContent | ContentIn, campaign: MarketingCampaign, values: dict) -> None:
        channel = values.get("channel", getattr(c, "channel", None))
        if channel not in campaign.channels:
            raise _fields_error([{"field": "channel", "message": "Choose one of the campaign's channels."}])
        problems = channel_problems(
            channel,
            values.get("headline", getattr(c, "headline", None)),
            values.get("body", getattr(c, "body", "")),
            values.get("call_to_action", getattr(c, "call_to_action", None)),
            values.get("hashtags", getattr(c, "hashtags", [])),
        )
        if problems:
            raise _fields_error(problems)

    def _snapshot(self, c: MarketingContent, principal: Principal, note: str) -> None:
        self.session.add(
            MarketingContentVersion(
                content_id=c.id,
                version=c.version,
                channel=c.channel,
                language=c.language,
                headline=c.headline,
                body=c.body,
                call_to_action=c.call_to_action,
                hashtags=list(c.hashtags or []),
                note=note,
                edited_by=principal.user_id,
                created_at=_now(),
            )
        )

    def create_content(self, principal: Principal, data: ContentIn) -> MarketingContent:
        ensure_permission(principal, Perm.MARKETING_CONTENT_CREATE)
        from app.common.codes import next_code

        campaign = self._campaign(data.campaign_id)
        if campaign.status == "archived":
            raise BusinessRuleViolation("Archived campaigns can't get new content.", code="campaign_archived")
        values = data.model_dump()
        self._validate(data, campaign, values)
        c = MarketingContent(
            code=next_code(self.session, "marketing_content"),
            campaign_id=campaign.id,
            project_id=campaign.project_id,
            channel=data.channel,
            language=data.language,
            headline=data.headline or None,
            body=data.body,
            call_to_action=data.call_to_action or None,
            hashtags=data.hashtags,
            status="draft",
            version=1,
            created_by=principal.user_id,
            updated_by=principal.user_id,
        )
        self.session.add(c)
        self.session.flush()
        self._snapshot(c, principal, "Created")
        self.audit.record(
            "marketing.content_created",
            actor_user_id=principal.user_id,
            entity_type=ENTITY,
            entity_id=c.id,
            summary=f"{c.code} · {CHANNEL_RULES[c.channel]['label']} ({c.language.upper()}) in {campaign.code}",
        )
        self.session.commit()
        return c

    def update_content(self, principal: Principal, content_id: uuid.UUID, data: ContentUpdate) -> MarketingContent:
        ensure_permission(principal, Perm.MARKETING_CONTENT_CREATE)
        c = self._content(content_id, lock=True)
        if c.status not in EDITABLE:
            raise BusinessRuleViolation(
                "Only drafts and rejected content can be edited."
                if c.status != "pending_approval"
                else "This content is waiting for review and can't be edited.",
                code="content_locked",
            )
        if c.campaign.status == "archived":
            raise BusinessRuleViolation("The campaign is archived.", code="campaign_archived")
        values = {k: getattr(data, k) for k in data.model_fields_set if k in CONTENT_FIELDS}
        for required in ("channel", "language", "body", "hashtags"):
            if required in values and values[required] is None:
                values.pop(required)
        for optional in ("headline", "call_to_action"):
            if optional in values and not values[optional]:
                values[optional] = None
        changed = {k: v for k, v in values.items() if getattr(c, k) != v}
        if not changed:
            return c
        self._validate(c, c.campaign, values)
        was_rejected = c.status == "rejected"
        for k, v in changed.items():
            setattr(c, k, v)
        c.version += 1
        c.updated_by = principal.user_id
        if was_rejected:
            c.status, c.rejection_comment = "draft", None
        note = (data.note or "").strip() or ("Revised after rejection" if was_rejected else "Edited")
        self._snapshot(c, principal, note[:200])
        self.audit.record(
            "marketing.content_updated",
            actor_user_id=principal.user_id,
            entity_type=ENTITY,
            entity_id=c.id,
            summary=f"{c.code} → v{c.version}" + (" (back to draft after rejection)" if was_rejected else ""),
            changes={"fields": sorted(changed)},
        )
        self.session.commit()
        return c

    def submit(self, principal: Principal, content_id: uuid.UUID) -> MarketingContent:
        """Draft/rejected → pending_approval, and the approval request is opened in the same transaction."""
        ensure_permission(principal, Perm.MARKETING_CONTENT_CREATE)
        c = self._content(content_id, lock=True)
        if c.status not in EDITABLE:
            raise BusinessRuleViolation("Only drafts and rejected content can be submitted.", code="content_not_submittable")
        if c.campaign.status == "archived":
            raise BusinessRuleViolation("The campaign is archived.", code="campaign_archived")
        problems = channel_problems(c.channel, c.headline, c.body, c.call_to_action, list(c.hashtags or []))
        if problems:
            raise _fields_error(problems)
        authors = set(
            self.session.scalars(
                select(MarketingContentVersion.edited_by).where(
                    MarketingContentVersion.content_id == c.id, MarketingContentVersion.edited_by.is_not(None)
                )
            )
        ) | {u for u in (c.created_by, principal.user_id) if u}
        previous = c.status
        c.status, c.submitted_at, c.decided_at, c.decided_by, c.rejection_comment = "pending_approval", _now(), None, None, None
        label = CHANNEL_RULES[c.channel]["label"]
        req = ApprovalService(self.session).open_request(
            entity_type=ENTITY,
            entity_id=c.id,
            entity_code=c.code,
            title=f"{label} content ({c.language.upper()}) · {c.campaign.name}"[:200],
            amount=0,  # type: ignore[arg-type]
            requested_by=principal.user_id,
            department_id=None,
            over_budget=False,
            actor_user_id=principal.user_id,
            excluded_approvers=sorted(authors),
        )
        req.flags = {**req.flags, "content_version": c.version}
        self.audit.record(
            "marketing.content_submitted",
            actor_user_id=principal.user_id,
            entity_type=ENTITY,
            entity_id=c.id,
            summary=f"{c.code} v{c.version} submitted for review",
            changes={"status": [previous, "pending_approval"]},
        )
        events.emit(
            self.session,
            "marketing_content.submitted",
            entity_type=ENTITY,
            entity_id=c.id,
            actor_user_id=principal.user_id,
            payload={"code": c.code, "version": c.version, "approval_id": str(req.id), "channel": c.channel, "language": c.language},
        )
        self.session.commit()
        return c

    def archive_content(self, principal: Principal, content_id: uuid.UUID) -> MarketingContent:
        ensure_permission(principal, Perm.MARKETING_CONTENT_CREATE)
        c = self._content(content_id, lock=True)
        if c.status == "pending_approval":
            raise BusinessRuleViolation("Content waiting for review can't be archived.", code="content_pending")
        if c.status == "archived":
            return c
        previous, c.status, c.archived_at = c.status, "archived", _now()
        self.audit.record(
            "marketing.content_archived",
            actor_user_id=principal.user_id,
            entity_type=ENTITY,
            entity_id=c.id,
            summary=f"{c.code} archived",
            changes={"status": [previous, "archived"]},
        )
        self.session.commit()
        return c

    # ------------------------------------------------------------------ reading
    def content_out(self, c: MarketingContent) -> ContentOut:
        return ContentOut(
            id=c.id,
            code=c.code,
            campaign=Ref(id=c.campaign.id, code=c.campaign.code, name=c.campaign.name),
            project=Ref(id=c.campaign.project.id, code=c.campaign.project.code, name=c.campaign.project.name),
            channel=c.channel,
            language=c.language,
            headline=c.headline,
            body=c.body,
            call_to_action=c.call_to_action,
            hashtags=list(c.hashtags or []),
            status=c.status,
            version=c.version,
            generated_by_ai=c.generated_by_ai,
            created_by=_person(c.creator),
            updated_at=c.updated_at,
            submitted_at=c.submitted_at,
            decided_at=c.decided_at,
            rejection_comment=c.rejection_comment,
        )

    def list_content(
        self,
        principal: Principal,
        params: ListParams,
        *,
        campaign_id: uuid.UUID | None,
        status: str | None,
        channel: str | None,
        language: str | None,
        project_id: uuid.UUID | None,
    ) -> tuple[list[ContentOut], int, int]:
        ensure_permission(principal, Perm.MARKETING_CAMPAIGNS_READ)
        stmt = select(MarketingContent)
        if campaign_id:
            stmt = stmt.where(MarketingContent.campaign_id == campaign_id)
        if project_id:
            stmt = stmt.where(MarketingContent.project_id == project_id)
        if status == "current":
            stmt = stmt.where(MarketingContent.status != "archived")
        elif status:
            stmt = stmt.where(MarketingContent.status == status)
        if channel:
            stmt = stmt.where(MarketingContent.channel == channel)
        if language:
            stmt = stmt.where(MarketingContent.language == language)
        if params.q:
            term = f"%{escape_like(params.q)}%"
            stmt = stmt.where(
                or_(
                    MarketingContent.code.ilike(term, escape="\\"),
                    MarketingContent.headline.ilike(term, escape="\\"),
                    MarketingContent.body.ilike(term, escape="\\"),
                )
            )
        rows, total, pages = paginate(self.session, apply_sort(stmt, params.sort, CONTENT_SORT, "-updated_at"), params)
        return [self.content_out(c) for c in rows], total, pages

    def detail(self, principal: Principal, content_id: uuid.UUID) -> ContentDetail:
        ensure_permission(principal, Perm.MARKETING_CAMPAIGNS_READ)
        c = self._content(content_id)
        approvals = ApprovalService(self.session)
        requests = list(
            self.session.scalars(
                select(ApprovalRequest)
                .where(ApprovalRequest.entity_type == ENTITY, ApprovalRequest.entity_id == c.id)
                .order_by(ApprovalRequest.created_at.desc())
            ).unique()
        )
        # Newest first: by time, then by content version (several rounds can share a timestamp inside one transaction).
        requests.sort(key=lambda r: (r.created_at, (r.flags or {}).get("content_version") or 0), reverse=True)
        open_req = next((r for r in requests if r.status == "pending"), None)
        can_decide, blocked = approvals.eligibility(principal, open_req) if open_req else (False, None)
        rounds = []
        for r in requests:
            steps = [
                ApprovalStepOut(
                    label=s.label,
                    status=s.status,
                    decided_by=_person(s.decision.decider) if s.decision else None,
                    decided_at=s.decided_at,
                    comment=s.decision.comment if s.decision else None,
                )
                for s in r.steps
            ]
            rounds.append(
                ApprovalRound(
                    id=r.id,
                    status=r.status,
                    version=(r.flags or {}).get("content_version"),
                    requested_by=_person(r.requester),
                    created_at=r.created_at,
                    completed_at=r.completed_at,
                    steps=steps,
                )
            )
        versions = [
            VersionOut(
                version=v.version,
                channel=v.channel,
                language=v.language,
                headline=v.headline,
                body=v.body,
                call_to_action=v.call_to_action,
                hashtags=list(v.hashtags or []),
                note=v.note,
                edited_by=_person(v.editor),
                created_at=v.created_at,
            )
            for v in self.session.scalars(
                select(MarketingContentVersion)
                .where(MarketingContentVersion.content_id == c.id)
                .order_by(MarketingContentVersion.version.desc())
            )
        ]
        actions: list[str] = []
        creator = principal.has(Perm.MARKETING_CONTENT_CREATE) and c.campaign.status != "archived"
        if creator and c.status in EDITABLE:
            actions += ["edit", "submit"]
        if principal.has(Perm.MARKETING_CONTENT_CREATE) and c.status not in ("pending_approval", "archived"):
            actions.append("archive")
        if open_req and can_decide:
            actions += ["approve", "reject"]
        base = self.content_out(c)
        return ContentDetail(
            **base.model_dump(),
            allowed_actions=actions,
            approval_id=(open_req or (requests[0] if requests else None)).id if requests else None,
            can_decide=bool(open_req and can_decide),
            decide_blocked_reason=blocked if open_req and not can_decide else None,
            approvals=rounds,
            versions=versions,
            fact_warnings=check_text(self.session, c.project_id, c.headline, c.body, c.call_to_action),
            channel_limit=int(CHANNEL_RULES[c.channel]["max_total"]),  # type: ignore[call-overload]
            length=total_length(c.headline, c.body, c.call_to_action, list(c.hashtags or [])),
        )


# ================================================================== approval subject adapter
class MarketingContentSubject:
    """Connects approval decisions back to the content. Approval never publishes anything."""

    entity_type = ENTITY
    label = "Marketing content"

    def link(self, entity_id: str) -> str:
        return f"/marketing/content/{entity_id}"

    def _content(self, session: Session, approval: ApprovalRequest) -> MarketingContent:
        c = session.scalar(select(MarketingContent).where(MarketingContent.id == approval.entity_id).with_for_update(of=MarketingContent))
        if c is None or c.status != "pending_approval":
            raise Conflict("This content is no longer waiting for review.", code="content_not_pending")
        return c

    def on_approved(self, session: Session, approval: ApprovalRequest, actor: Principal) -> None:
        c = self._content(session, approval)
        c.status, c.decided_at, c.decided_by = "approved", _now(), actor.user_id
        AuditService(session).record(
            "marketing.content_approved",
            actor_user_id=actor.user_id,
            entity_type=ENTITY,
            entity_id=c.id,
            summary=f"{c.code} v{c.version} approved (not published)",
            changes={"status": ["pending_approval", "approved"]},
        )

    def on_rejected(self, session: Session, approval: ApprovalRequest, actor: Principal, comment: str) -> None:
        c = self._content(session, approval)
        c.status, c.decided_at, c.decided_by, c.rejection_comment = "rejected", _now(), actor.user_id, comment[:1000]
        AuditService(session).record(
            "marketing.content_rejected",
            actor_user_id=actor.user_id,
            entity_type=ENTITY,
            entity_id=c.id,
            summary=f"{c.code} v{c.version} rejected",
            changes={"status": ["pending_approval", "rejected"]},
        )


register_subject(MarketingContentSubject())


def require_reader(principal: Principal) -> None:
    if not principal.has(Perm.MARKETING_CAMPAIGNS_READ):
        raise PermissionDenied(details={"required_permission": Perm.MARKETING_CAMPAIGNS_READ.value})
