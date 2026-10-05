"""SQL repository for findings and their recommendation (#34). Nothing here commits."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from cvidee.store.enums import FindingLifecycle
from cvidee.store.models import Finding, Recommendation

__all__ = ["SqlFindingRepository", "format_human_id"]

HUMAN_ID_PREFIX = "B-"


def format_human_id(number: int) -> str:
    return f"{HUMAN_ID_PREFIX}{number:03d}"


def _number(human_id: str) -> int:
    try:
        return int(human_id.removeprefix(HUMAN_ID_PREFIX))
    except ValueError:
        return 0


class SqlFindingRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, finding_id: int) -> Finding | None:
        return self._session.get(Finding, finding_id)

    def by_human_id(self, human_id: str) -> Finding | None:
        return self._session.scalars(select(Finding).where(Finding.human_id == human_id)).first()

    def active_by_key(self, rule_id: str, scope_key: str) -> Finding | None:
        return self._session.scalars(
            select(Finding).where(
                Finding.rule_id == rule_id,
                Finding.scope_key == scope_key,
                Finding.lifecycle == FindingLifecycle.ACTIVE,
            )
        ).first()

    def active_for_rule(self, rule_id: str) -> list[Finding]:
        return list(
            self._session.scalars(
                select(Finding)
                .where(Finding.rule_id == rule_id, Finding.lifecycle == FindingLifecycle.ACTIVE)
                .order_by(Finding.scope_key)
            )
        )

    def list_findings(self, *, include_resolved: bool = False) -> list[Finding]:
        """Highest priority first; ties by first seen, then id (deterministic)."""
        stmt = select(Finding)
        if not include_resolved:
            stmt = stmt.where(Finding.lifecycle == FindingLifecycle.ACTIVE)
        stmt = stmt.order_by(Finding.priority_score.desc(), Finding.first_seen_ts, Finding.id)
        return list(self._session.scalars(stmt))

    def next_human_id(self) -> str:
        """Next free ``B-nnn``; resolved findings keep theirs, so ids are never reused."""
        numbers = [_number(h) for h in self._session.scalars(select(Finding.human_id))]
        return format_human_id(max(numbers, default=0) + 1)

    def add(self, finding: Finding) -> Finding:
        finding.human_id = self.next_human_id()
        self._session.add(finding)
        self._session.flush()
        return finding

    def recommendation_of(self, finding: Finding) -> Recommendation | None:
        return self._session.scalars(
            select(Recommendation)
            .where(Recommendation.finding_id == finding.id)
            .order_by(Recommendation.id.desc())
        ).first()

    def add_recommendation(self, recommendation: Recommendation) -> Recommendation:
        self._session.add(recommendation)
        self._session.flush()
        return recommendation
