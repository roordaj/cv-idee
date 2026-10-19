"""Persist the exact report snapshot used by preview and all export formats.

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "report_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("generated_at_ts", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_report_snapshots")),
    )


def downgrade() -> None:
    op.drop_table("report_snapshots")
