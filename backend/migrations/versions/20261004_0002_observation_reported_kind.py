"""Add observations.reported_kind (#16).

The kind as reported by ingest, next to the stored classification ``kind``: needed to
reclassify a successor (change vs. confirm) when late data is inserted before it.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-04 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KIND = sa.Enum(
    "change",
    "confirm",
    "poll",
    name="reported_kind",
    native_enum=False,
    create_constraint=False,
    length=32,
)


def upgrade() -> None:
    with op.batch_alter_table("observations") as batch_op:
        batch_op.add_column(sa.Column("reported_kind", _KIND, nullable=True))
    op.execute("UPDATE observations SET reported_kind = kind")
    with op.batch_alter_table("observations") as batch_op:
        batch_op.alter_column("reported_kind", existing_type=_KIND, nullable=False)
        batch_op.create_check_constraint(
            op.f("ck_observations_reported_kind"), "reported_kind IN ('change', 'confirm', 'poll')"
        )


def downgrade() -> None:
    with op.batch_alter_table("observations") as batch_op:
        batch_op.drop_constraint(op.f("ck_observations_reported_kind"), type_="check")
        batch_op.drop_column("reported_kind")
