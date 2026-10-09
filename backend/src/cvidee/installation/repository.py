"""SQL implementation of :class:`~cvidee.store.repositories.InstallationProfileRepository`.

Copy-on-edit: a save closes the current version at ``valid_from_ts`` and adds the new one;
old versions are immutable so analyses and advice snapshots can keep referring to them.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from cvidee.installation.defaults import default_profile
from cvidee.store.models import InstallationProfile

_LOAD = (
    selectinload(InstallationProfile.circuits),
    selectinload(InstallationProfile.zones),
    selectinload(InstallationProfile.rooms),
    selectinload(InstallationProfile.specs),
)


class SqlInstallationProfileRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def current(self) -> InstallationProfile | None:
        stmt = (
            select(InstallationProfile)
            .where(InstallationProfile.valid_to_ts.is_(None))
            .order_by(InstallationProfile.id.desc())
            .options(*_LOAD)
        )
        return self._session.scalars(stmt).first()

    def current_or_default(self, now_ts: int) -> InstallationProfile:
        """The current version; the default profile is stored on first use."""
        profile = self.current()
        if profile is None:
            profile = default_profile(now_ts)
            self._session.add(profile)
            self._session.flush()
        return profile

    def at(self, ts: int) -> InstallationProfile | None:
        stmt = (
            select(InstallationProfile)
            .where(
                InstallationProfile.valid_from_ts <= ts,
                (InstallationProfile.valid_to_ts.is_(None))
                | (InstallationProfile.valid_to_ts > ts),
            )
            .order_by(InstallationProfile.valid_from_ts.desc(), InstallationProfile.id.desc())
            .options(*_LOAD)
        )
        return self._session.scalars(stmt).first()

    def get(self, profile_id: int) -> InstallationProfile | None:
        stmt = select(InstallationProfile).where(InstallationProfile.id == profile_id)
        return self._session.scalars(stmt.options(*_LOAD)).first()

    def save_new_version(self, profile: InstallationProfile) -> InstallationProfile:
        current = self.current()
        if current is not None:
            current.valid_to_ts = max(profile.valid_from_ts, current.valid_from_ts)
        self._session.add(profile)
        self._session.flush()
        return profile
