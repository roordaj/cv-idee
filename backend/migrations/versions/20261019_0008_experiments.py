"""Persist lifecycle state for experiments linked to one recorded change.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "experiments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("change_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "running",
                "completed",
                "ended",
                name="status",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("created_at_ts", sa.BigInteger(), nullable=False),
        sa.Column("updated_at_ts", sa.BigInteger(), nullable=False),
        sa.Column("completed_at_ts", sa.BigInteger(), nullable=True),
        sa.Column("ended_at_ts", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'ended')",
            name=op.f("ck_experiments_status"),
        ),
        sa.ForeignKeyConstraint(
            ["change_id"],
            ["changes.id"],
            name=op.f("fk_experiments_change_id_changes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_experiments")),
        sa.UniqueConstraint("change_id", name=op.f("uq_experiments_change_id")),
    )


def downgrade() -> None:
    op.drop_table("experiments")
