"""project illustrative map point

Additive, all empty by default. A labelled *reference* point for the website map of a project whose own location is
not verified (e.g. the fictional NOVA). Separate from address / latitude / longitude / location_verified, which keep
their Phase 7D rules unchanged.
CHECKs: ranges, both coordinates or neither, a label whenever coordinates are set, and never together with a verified
property location (a verified location is always shown instead).

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-17 18:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015"
down_revision: str | Sequence[str] | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECKS = (
    ("illustrative_latitude_range", "illustrative_latitude BETWEEN -90 AND 90"),
    ("illustrative_longitude_range", "illustrative_longitude BETWEEN -180 AND 180"),
    ("illustrative_paired", "(illustrative_latitude IS NULL) = (illustrative_longitude IS NULL)"),
    ("illustrative_needs_label", "illustrative_latitude IS NULL OR illustrative_label IS NOT NULL"),
    ("illustrative_not_with_verified", "NOT (location_verified AND illustrative_latitude IS NOT NULL)"),
)
COLUMNS = ("illustrative_label", "illustrative_latitude", "illustrative_longitude", "illustrative_source")


def upgrade() -> None:
    op.add_column("re_projects", sa.Column("illustrative_label", sa.String(length=120), nullable=True))
    op.add_column("re_projects", sa.Column("illustrative_latitude", sa.Numeric(9, 6), nullable=True))
    op.add_column("re_projects", sa.Column("illustrative_longitude", sa.Numeric(9, 6), nullable=True))
    op.add_column("re_projects", sa.Column("illustrative_source", sa.String(length=250), nullable=True))
    for name, expr in CHECKS:
        op.create_check_constraint(name, "re_projects", expr)


def downgrade() -> None:
    for name, _ in reversed(CHECKS):
        op.drop_constraint(name, "re_projects", type_="check")
    for col in reversed(COLUMNS):
        op.drop_column("re_projects", col)
