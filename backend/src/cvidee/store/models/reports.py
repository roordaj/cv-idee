"""Immutable generated report documents used by the preview and all exports."""

from typing import Any

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from cvidee.store.base import Base, ts_column


class ReportSnapshotRecord(Base):
    """A validated report snapshot retained so every format exports identical data."""

    __tablename__ = "report_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    generated_at_ts: Mapped[int] = ts_column()
