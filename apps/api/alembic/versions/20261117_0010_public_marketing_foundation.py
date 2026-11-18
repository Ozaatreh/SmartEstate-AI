"""public marketing foundation

Phase 7A. Additive: one new column, ``re_projects.is_published`` (default false), which decides what the public
marketing website and the public property assistant may show.

Backfill: projects that were already public through the assistant (status launched / under construction / completed)
are marked published, so the assistant keeps showing exactly what it showed before. Planning projects stay private.
Downgrade drops the column (no other data is touched).

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-17

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0010'
down_revision: str | Sequence[str] | None = '0009'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('re_projects', sa.Column('is_published', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.execute("UPDATE re_projects SET is_published = true WHERE status IN ('launched', 'under_construction', 'completed')")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('re_projects', 'is_published')
