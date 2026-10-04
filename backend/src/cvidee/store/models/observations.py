"""Raw data: observations and connection events (FR-06, FR-08)."""

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from cvidee.store.base import Base, enum_column, ts_column
from cvidee.store.enums import ConnectionSource, ObservationKind, ObservationOrigin


class Observation(Base):
    """One raw HA state for a source entity. Dedupe key: (source_entity_id, ts, state).

    ``reported_kind`` is the kind as delivered by ingest (merged over duplicates: change >
    confirm > poll); ``kind`` is the stored classification: a reported ``change`` whose
    state equals the previous stored state of the entity is a ``confirm`` (FR-08). Keeping
    both lets the store reclassify a successor when late data arrives, so the stored
    result does not depend on arrival order (#16).
    """

    __tablename__ = "observations"
    __table_args__ = (
        # Doubles as the range index (source_entity_id, ts).
        UniqueConstraint("source_entity_id", "ts", "state"),
        Index("ix_observations_ts", "ts"),  # retention purge
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_entity_id: Mapped[int] = mapped_column(ForeignKey("source_entities.id"))
    ts: Mapped[int] = ts_column()
    state: Mapped[str] = mapped_column(String(255))  # raw HA state, incl. 'unavailable'
    value_num: Mapped[float | None] = mapped_column(Float)  # parsed; NULL if not numeric
    kind: Mapped[ObservationKind] = enum_column(ObservationKind, "kind")
    reported_kind: Mapped[ObservationKind] = enum_column(ObservationKind, "reported_kind")
    last_reported_ts: Mapped[int | None] = ts_column(nullable=True)  # HA last_reported
    origin: Mapped[ObservationOrigin] = enum_column(ObservationOrigin, "origin")
    received_at_ts: Mapped[int] = ts_column()


class ConnectionEvent(Base):
    """Input connectivity (our WebSocket, HA's CAN gateway) going up or down."""

    __tablename__ = "connection_events"
    __table_args__ = (UniqueConstraint("source", "ts", "up"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[ConnectionSource] = enum_column(ConnectionSource, "source")
    ts: Mapped[int] = ts_column()
    up: Mapped[bool] = mapped_column(Boolean)
    detail: Mapped[str | None] = mapped_column(Text)
