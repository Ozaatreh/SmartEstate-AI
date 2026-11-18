"""brochure and poster generator

Phase 7C. Additive:
- re_payment_plans.marketing_status ('unreviewed' | 'cleared' | 'excluded', default 'unreviewed'): an explicit
  data classification. Marketing outputs (brochures, posters, the public website and assistant, Marketing Studio
  facts) use only 'cleared' plans, so anything unclassified is left out (fail closed).
  Backfill: plans that belong to the seeded demo dataset (plan AND project flagged is_demo_data) become 'cleared';
  every other existing plan keeps the default 'unreviewed' and stays out until someone clears it. No row is deleted
  or deactivated.
- permission marketing.collateral.generate, granted to marketing_manager and marketing_specialist.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-17 12:00:00

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0012'
down_revision: str | Sequence[str] | None = '0011'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSION = ("marketing.collateral.generate", "Generate brochures and social posters from verified project data")
GRANTED_TO = ["marketing_manager", "marketing_specialist"]


def upgrade() -> None:
    op.add_column(
        "re_payment_plans",
        sa.Column("marketing_status", sa.String(length=12), server_default="unreviewed", nullable=False),
    )
    op.create_check_constraint(
        "marketing_status_allowed", "re_payment_plans", "marketing_status IN ('unreviewed', 'cleared', 'excluded')"
    )
    op.execute(
        "UPDATE re_payment_plans pl SET marketing_status = 'cleared' FROM re_projects p "
        "WHERE p.id = pl.project_id AND pl.is_demo_data AND p.is_demo_data"
    )
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "INSERT INTO permissions (id, code, module, description) VALUES (gen_random_uuid(), :c, 'marketing', :d) "
            "ON CONFLICT (code) DO NOTHING"
        ).bindparams(c=PERMISSION[0], d=PERMISSION[1])
    )
    conn.execute(
        sa.text(
            "INSERT INTO role_permissions (role_id, permission_id) SELECT r.id, p.id FROM roles r, permissions p "
            "WHERE r.code = ANY(:roles) AND p.code = :c ON CONFLICT DO NOTHING"
        ).bindparams(c=PERMISSION[0], roles=GRANTED_TO)
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code = :c)").bindparams(c=PERMISSION[0])
    )
    conn.execute(sa.text("DELETE FROM permissions WHERE code = :c").bindparams(c=PERMISSION[0]))
    op.drop_constraint("marketing_status_allowed", "re_payment_plans", type_="check")
    op.drop_column("re_payment_plans", "marketing_status")
