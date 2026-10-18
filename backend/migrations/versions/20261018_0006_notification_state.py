"""Persist the notification observer cursor across restarts.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_states",
        sa.Column(
            "finding_id",
            sa.Integer(),
            sa.ForeignKey("findings.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "severity",
            sa.Enum(
                "high",
                "medium",
                "low",
                "info",
                name="severity",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "lifecycle",
            sa.Enum(
                "active",
                "resolved",
                name="lifecycle",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("updated_at_ts", sa.BigInteger(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("notification_states")
