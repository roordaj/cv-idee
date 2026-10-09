"""Persist onboarding completion alongside immutable settings revisions.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("settings_revisions") as batch_op:
        batch_op.add_column(sa.Column("onboarding_completed_at_ts", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("settings_revisions") as batch_op:
        batch_op.drop_column("onboarding_completed_at_ts")
