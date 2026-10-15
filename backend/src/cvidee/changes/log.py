"""Persist changes made by people; never send device commands (FR-29)."""

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from cvidee.api.findings_read import FindingsReadModel
from cvidee.api.problems import ProblemError, not_found
from cvidee.api.schemas.changes import Change as ChangeOut
from cvidee.api.schemas.changes import ChangeCreate, ChangeEvaluation, ChangeList
from cvidee.api.schemas.data import ChangeMarker, ChangeRef
from cvidee.api.schemas.findings import FindingStatusUpdate
from cvidee.findings.repository import SqlFindingRepository
from cvidee.store.enums import EvaluationVerdict
from cvidee.store.models import Change, ChangeItem, Recommendation

PARAMETERS = {
    "Maximale CV-aanvoer": "max_ch_flow_temperature",
    "Pompstand": "pump_setting",
    "Stooklijn eTwist": "etwist_heating_curve",
    "Thermostaatprogramma": "thermostat_schedule",
    "Verdeler: lusdebiet": "manifold_loop_flow",
}
VERDICTS = {
    EvaluationVerdict.PENDING: "Evaluatie loopt",
    EvaluationVerdict.IMPROVED: "Verbeterd",
    EvaluationVerdict.WORSENED: "Verslechterd",
    EvaluationVerdict.TRADE_OFF: "Afweging",
    EvaluationVerdict.NOT_ATTRIBUTABLE: "Niet toe te schrijven",
    EvaluationVerdict.INSUFFICIENT_EVIDENCE: "Onvoldoende bewijs",
}


def as_change(row: Change, session: Session) -> ChangeOut:
    rec = (
        None
        if row.recommendation_id is None
        else session.get(Recommendation, row.recommendation_id)
    )
    evaluation = row.evaluation
    verdict = EvaluationVerdict.PENDING if evaluation is None else evaluation.verdict
    return ChangeOut(
        id=row.human_id,
        at=datetime.fromtimestamp(row.changed_at_ts / 1000, UTC),
        actor=row.performed_by,
        parameter=" + ".join(item.parameter_label for item in row.items),
        old_value=" + ".join(item.old_value for item in row.items),
        new_value=" + ".join(item.new_value for item in row.items),
        reason=row.reason or "",
        finding_id=None if rec is None else rec.finding.human_id,
        verdict=verdict,
        verdict_text=VERDICTS[verdict],
        rollback_advised=False if evaluation is None else evaluation.rollback_triggered,
    )


class ChangeLog:
    def __init__(self, session: Session, clock: Callable[[], int]) -> None:
        self.session = session
        self.clock = clock

    def change_list(self) -> ChangeList:
        rows = self.session.scalars(
            select(Change).order_by(Change.changed_at_ts.desc(), Change.id.desc())
        )
        return ChangeList(items=[as_change(row, self.session) for row in rows])

    def create_change(self, body: ChangeCreate) -> ChangeOut:
        self.session.execute(text("BEGIN IMMEDIATE"))
        parameter, new_value = body.parameter.strip(), body.new_value.strip()
        if not parameter or not new_value:
            raise ProblemError(422, "Ongeldige wijziging", "Vul een parameter en nieuwe waarde in.")
        now = self.clock()
        if body.at.timestamp() * 1000 > now:
            raise ProblemError(
                422, "Ongeldig tijdstip", "Een uitgevoerde wijziging ligt niet in de toekomst."
            )
        rec = None
        if body.finding_id is not None:
            repo = SqlFindingRepository(self.session)
            finding = repo.by_human_id(body.finding_id)
            if finding is None:
                raise not_found("Bevinding", body.finding_id)
            rec = repo.recommendation_of(finding)
            if rec is None:
                raise ProblemError(
                    422, "Geen aanbeveling", "Deze bevinding heeft geen aanbeveling."
                )
        numbers = [
            int(ident.removeprefix("W-")) for ident in self.session.scalars(select(Change.human_id))
        ]
        row = Change(
            human_id=f"W-{max(numbers, default=0) + 1:02d}",
            changed_at_ts=int(body.at.timestamp() * 1000),
            recorded_at_ts=now,
            performed_by=body.actor,
            reason=body.reason.strip(),
            recommendation_id=None if rec is None else rec.id,
            items=[
                ChangeItem(
                    ordinal=1,
                    parameter_key=PARAMETERS.get(parameter, "custom"),
                    parameter_label=parameter,
                    old_value=body.old_value.strip(),
                    new_value=new_value,
                )
            ],
        )
        self.session.add(row)
        if body.finding_id is not None:
            FindingsReadModel(self.session, self.clock).set_finding_status(
                body.finding_id, FindingStatusUpdate(status="done")
            )
        self.session.flush()
        return as_change(row, self.session)

    def markers(
        self, start: datetime, end: datetime
    ) -> tuple[list[ChangeMarker], ChangeRef | None]:
        rows = self.change_list().items
        markers = [
            ChangeMarker(
                **{
                    key: value
                    for key, value in row.model_dump().items()
                    if key in ChangeMarker.model_fields
                }
            )
            for row in reversed(rows)
            if start <= row.at < end
        ]
        before = next((row for row in rows if row.at < start), None)
        return markers, None if before is None else ChangeRef(
            id=before.id, at=before.at, parameter=before.parameter
        )

    def evaluation(self, change_id: str) -> ChangeEvaluation:
        row = self.session.scalar(select(Change).where(Change.human_id == change_id))
        if row is None:
            raise not_found("Wijziging", change_id)
        from cvidee.changes.evaluation import evaluate_stored_change, render_evaluation

        return render_evaluation(evaluate_stored_change(self.session, row, self.clock()))
