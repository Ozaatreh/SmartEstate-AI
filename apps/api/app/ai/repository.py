from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.models import AIUsage


class AIUsageRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, row: AIUsage) -> None:
        self.session.add(row)

    def cost_since(self, since: datetime) -> Decimal:
        return Decimal(
            self.session.scalar(select(func.coalesce(func.sum(AIUsage.estimated_cost_usd), 0)).where(AIUsage.created_at >= since))
        )

    def last_outcomes(self) -> tuple[AIUsage | None, AIUsage | None]:
        """Latest provider-reaching success and failure (rejections such as 'disabled' never reached the provider)."""
        base = select(AIUsage).order_by(AIUsage.created_at.desc()).limit(1)
        success = self.session.scalar(base.where(AIUsage.status == "succeeded"))
        failure = self.session.scalar(base.where(AIUsage.status == "failed"))
        return success, failure

    def summary_since(self, since: datetime) -> dict[str, object]:
        row = self.session.execute(
            select(
                func.count(),
                func.count().filter(AIUsage.status == "succeeded"),
                func.count().filter(AIUsage.status == "failed"),
                func.count().filter(AIUsage.status == "rejected"),
                func.coalesce(func.sum(AIUsage.input_tokens), 0),
                func.coalesce(func.sum(AIUsage.output_tokens), 0),
                func.coalesce(func.sum(AIUsage.estimated_cost_usd), 0),
            ).where(AIUsage.created_at >= since)
        ).one()
        keys = ("requests", "succeeded", "failed", "rejected", "input_tokens", "output_tokens", "estimated_cost_usd")
        return dict(zip(keys, row, strict=True))

    def list_stmt(self, *, capability: str | None, status: str | None):
        stmt = select(AIUsage)
        if capability:
            stmt = stmt.where(AIUsage.capability == capability)
        if status:
            stmt = stmt.where(AIUsage.status == status)
        return stmt
