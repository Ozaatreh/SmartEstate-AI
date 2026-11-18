"""project location (maps)

Phase 7D. Additive columns on re_projects, all empty by default — no coordinates or addresses are filled in:
- address, country (text), latitude / longitude NUMERIC(9,6);
- location_verified (default false) + location_verified_at / location_verified_by: a person confirms the location
  before it is shown publicly (map, pin, directions).
CHECKs: latitude -90..90, longitude -180..180, both coordinates or neither, verified only with coordinates, and never
verified on fictional demo projects (a fictional project must not be pinned to a real place).

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-17 14:00:00

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = '0013'
down_revision: str | Sequence[str] | None = '0012'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECKS = (
    ("latitude_range", "latitude BETWEEN -90 AND 90"),
    ("longitude_range", "longitude BETWEEN -180 AND 180"),
    ("coordinates_paired", "(latitude IS NULL) = (longitude IS NULL)"),
    ("verified_needs_coordinates", "NOT location_verified OR latitude IS NOT NULL"),
    ("verified_not_demo", "NOT (location_verified AND is_demo_data)"),
)


def upgrade() -> None:
    op.add_column("re_projects", sa.Column("address", sa.String(length=250), nullable=True))
    op.add_column("re_projects", sa.Column("country", sa.String(length=80), nullable=True))
    op.add_column("re_projects", sa.Column("latitude", sa.Numeric(9, 6), nullable=True))
    op.add_column("re_projects", sa.Column("longitude", sa.Numeric(9, 6), nullable=True))
    op.add_column("re_projects", sa.Column("location_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("re_projects", sa.Column("location_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("re_projects", sa.Column("location_verified_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        op.f("fk_re_projects_location_verified_by_users"), "re_projects", "users", ["location_verified_by"], ["id"], ondelete="SET NULL"
    )
    for name, expr in CHECKS:
        op.create_check_constraint(name, "re_projects", expr)


def downgrade() -> None:
    for name, _ in reversed(CHECKS):
        op.drop_constraint(name, "re_projects", type_="check")
    op.drop_constraint(op.f("fk_re_projects_location_verified_by_users"), "re_projects", type_="foreignkey")
    for col in ("location_verified_by", "location_verified_at", "location_verified", "longitude", "latitude", "country", "address"):
        op.drop_column("re_projects", col)
