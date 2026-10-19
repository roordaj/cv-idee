"""Persist experiment lifecycle while reusing the established change evaluator."""

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from cvidee.api.problems import ProblemError, not_found
from cvidee.api.schemas.experiments import (
    ExperimentCreate,
    ExperimentList,
    ExperimentOut,
    ExperimentStatus,
)
from cvidee.changes.evaluation import render_persisted_evaluation
from cvidee.changes.log import ChangeLog, as_change
from cvidee.store.enums import ExperimentStatus as StoredStatus
from cvidee.store.models import Change, Experiment

STATUS_TEXT = {
    ExperimentStatus.RUNNING: "Loopt",
    ExperimentStatus.COMPLETED: "Afgerond",
    ExperimentStatus.ENDED: "Beëindigd",
}


def _utc(timestamp: int | None) -> datetime | None:
    return None if timestamp is None else datetime.fromtimestamp(timestamp / 1000, UTC)


class ExperimentBackend:
    """SQL-backed experiment API; all metrics come from ``ChangeLog.evaluation``."""

    def __init__(self, session: Session, clock: Callable[[], int]) -> None:
        self.session = session
        self.clock = clock
        self.changes = ChangeLog(session, clock)

    def _render(self, experiment: Experiment, *, refresh: bool = True) -> ExperimentOut:
        change = experiment.change
        if refresh and experiment.status is not StoredStatus.ENDED:
            self.changes.evaluation(change.human_id)
            self.session.flush()
        evaluation = change.evaluation
        status = ExperimentStatus(experiment.status.value)
        return ExperimentOut(
            change_id=change.human_id,
            status=status,
            status_text=STATUS_TEXT[status],
            change=as_change(change, self.session),
            evaluation=None if evaluation is None else render_persisted_evaluation(evaluation),
            created_at=datetime.fromtimestamp(experiment.created_at_ts / 1000, UTC),
            updated_at=datetime.fromtimestamp(experiment.updated_at_ts / 1000, UTC),
            last_evaluated_at=None if evaluation is None else _utc(evaluation.computed_at_ts),
            completed_at=_utc(experiment.completed_at_ts),
            ended_at=_utc(experiment.ended_at_ts),
        )

    def list(self, limit: int, offset: int) -> ExperimentList:
        query = select(Experiment).join(Experiment.change).order_by(Change.changed_at_ts.desc())
        total = len(self.session.scalars(select(Experiment.id)).all())
        rows = list(self.session.scalars(query.offset(offset).limit(limit)))
        return ExperimentList(
            items=[self._render(row) for row in rows], total=total, limit=limit, offset=offset
        )

    def get(self, change_id: str) -> ExperimentOut:
        row = self.session.scalar(
            select(Experiment).join(Experiment.change).where(Change.human_id == change_id)
        )
        if row is None:
            raise not_found("Experiment", change_id)
        return self._render(row)

    def create(self, body: ExperimentCreate) -> ExperimentOut:
        change = self.session.scalar(select(Change).where(Change.human_id == body.change_id))
        if change is None:
            raise not_found("Wijziging", body.change_id)
        if len(change.items) != 1:
            raise ProblemError(
                422,
                "Meerdere parameters",
                "Een experiment volgt precies één parameterwijziging.",
            )
        if self.session.scalar(select(Experiment.id).where(Experiment.change_id == change.id)):
            raise ProblemError(
                409, "Experiment bestaat al", "Deze wijziging heeft al een experiment."
            )
        now = self.clock()
        row = Experiment(
            change_id=change.id,
            status=StoredStatus.RUNNING,
            created_at_ts=now,
            updated_at_ts=now,
        )
        self.session.add(row)
        self.session.flush()
        self.changes.evaluation(change.human_id)
        self.session.flush()
        return self._render(row, refresh=False)

    def end(self, change_id: str) -> ExperimentOut:
        row = self.session.scalar(
            select(Experiment).join(Experiment.change).where(Change.human_id == change_id)
        )
        if row is None:
            raise not_found("Experiment", change_id)
        if row.status is StoredStatus.COMPLETED:
            raise ProblemError(409, "Experiment afgerond", "Dit experiment is al afgerond.")
        if row.status is StoredStatus.RUNNING:
            now = self.clock()
            row.status = StoredStatus.ENDED
            row.updated_at_ts = now
            row.ended_at_ts = now
            self.session.flush()
        return self._render(row, refresh=False)
