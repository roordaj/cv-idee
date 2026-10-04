"""Application settings as immutable, append-only revisions (history + optimistic locking)."""

from typing import Any

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from cvidee.store.base import Base, ts_column


class SettingsRevision(Base):
    """One saved state of all settings. The current revision is the one with the max id.

    ``values`` only holds keys that differ from the code defaults (the settings schema in
    code is the source of defaults and validation). A ``PUT`` carries the revision id it
    was based on; if that is no longer current the API answers 409 (aanvullingen §1.6).
    """

    __tablename__ = "settings_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    values: Mapped[dict[str, Any]] = mapped_column(default=dict)
    config_hash: Mapped[str] = mapped_column(String(64))
    created_at_ts: Mapped[int] = ts_column()
    changed_by: Mapped[str | None] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(Text)
