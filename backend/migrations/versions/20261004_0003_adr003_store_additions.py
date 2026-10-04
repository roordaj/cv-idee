"""ADR-003 store additions (#77).

* ``connection_events.source`` accepts ``history`` (HA history import range).
* ``quality_events``: ``source``, ``other_signal``, ``count``; unique key becomes
  ``(kind, signal, other_signal, coalesce(source, ''), start_ts)``.
* ``mode_segments.device_code`` (boiler fault/blocking code).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-04 19:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SOURCE_OLD = "source IN ('ws', 'can_gateway')"
_SOURCE_NEW = "source IN ('ws', 'can_gateway', 'history')"
_QUALITY_SOURCE = sa.Enum(
    "ws",
    "can_gateway",
    "history",
    name="source",
    native_enum=False,
    create_constraint=False,
    length=32,
)


def upgrade() -> None:
    with op.batch_alter_table("connection_events") as batch_op:
        batch_op.drop_constraint(op.f("ck_connection_events_source"), type_="check")
        batch_op.create_check_constraint(op.f("ck_connection_events_source"), _SOURCE_NEW)

    with op.batch_alter_table("mode_segments") as batch_op:
        batch_op.add_column(sa.Column("device_code", sa.String(length=64), nullable=True))

    op.drop_index("uq_quality_events_key", table_name="quality_events")
    with op.batch_alter_table("quality_events") as batch_op:
        batch_op.add_column(sa.Column("source", _QUALITY_SOURCE, nullable=True))
        batch_op.add_column(
            sa.Column("other_signal", sa.String(length=160), server_default="", nullable=False)
        )
        batch_op.add_column(sa.Column("count", sa.Integer(), nullable=True))
        batch_op.create_check_constraint(op.f("ck_quality_events_source"), _SOURCE_NEW)
    op.create_index(
        "uq_quality_events_key",
        "quality_events",
        ["kind", "signal", "other_signal", sa.text("coalesce(source, '')"), "start_ts"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_quality_events_key", table_name="quality_events")
    # Rows the old key cannot hold (several per kind/signal/start) are collapsed.
    op.execute(
        "DELETE FROM quality_events WHERE id NOT IN "
        "(SELECT MIN(id) FROM quality_events GROUP BY kind, signal, start_ts)"
    )
    with op.batch_alter_table("quality_events") as batch_op:
        batch_op.drop_constraint(op.f("ck_quality_events_source"), type_="check")
        batch_op.drop_column("count")
        batch_op.drop_column("other_signal")
        batch_op.drop_column("source")
    op.create_index(
        "uq_quality_events_key", "quality_events", ["kind", "signal", "start_ts"], unique=True
    )

    with op.batch_alter_table("mode_segments") as batch_op:
        batch_op.drop_column("device_code")

    op.execute("DELETE FROM connection_events WHERE source = 'history'")
    with op.batch_alter_table("connection_events") as batch_op:
        batch_op.drop_constraint(op.f("ck_connection_events_source"), type_="check")
        batch_op.create_check_constraint(op.f("ck_connection_events_source"), _SOURCE_OLD)
