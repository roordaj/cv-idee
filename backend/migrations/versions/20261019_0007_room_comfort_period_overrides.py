"""Store room comfort overrides on existing special periods.

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("special_periods") as batch_op:
        batch_op.add_column(
            sa.Column("room_overrides", sa.JSON(), server_default="[]", nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("special_periods") as batch_op:
        batch_op.drop_column("room_overrides")
