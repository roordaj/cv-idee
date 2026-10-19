"""Pattern certainty stays separate from missing cause measurements (#132)."""

from pathlib import Path

from sqlalchemy import select

from cvidee.analysis.types import Role
from cvidee.rules.base import Certainty
from cvidee.store.models import Finding
from tests.scenarios.runner import run_scenario


def test_scenario_two_reports_high_cycle_certainty_with_unknown_cause(tmp_path: Path) -> None:
    scenario_dir = tmp_path / "scenario02"
    scenario_dir.mkdir()
    factory, runner, _data = run_scenario(scenario_dir, "02-kort-branden")

    outcome = runner.registry.outcomes["kort-branden"]
    (candidate,) = outcome.candidates
    assert candidate.severity.value == "high"
    assert candidate.certainty is Certainty.HIGH
    assert candidate.evidence.pattern_cycles == 475
    assert candidate.evidence.missing_signals
    assert any(ref.role is Role.FLOW_RATE for ref in candidate.evidence.missing_signals)

    with factory() as session:
        findings = list(session.scalars(select(Finding).where(Finding.rule_id == "kort-branden")))
    assert len(findings) == 1
    assert findings[0].certainty.value == "high"
