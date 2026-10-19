"""Production runner acceptance for ordinary and explicit DHW scenarios (#128)."""

from pathlib import Path

from sqlalchemy import select

from cvidee.store.models import Finding
from tests.scenarios.runner import run_scenario


def test_normal_scenarios_are_silent_and_repeated_dhw_stays_visible(tmp_path: Path) -> None:
    expected = {
        "01-normaal-cv": set(),
        "03-stop-na-einde-vraag": set(),
        "04-tapwater": {"tapwater-uitgesloten"},
    }
    for name, rule_ids in expected.items():
        scenario_dir = tmp_path / name
        scenario_dir.mkdir()
        factory, _runner, _data = run_scenario(scenario_dir, name)
        with factory() as session:
            findings = list(session.scalars(select(Finding)))
        assert {finding.rule_id for finding in findings} == rule_ids
        if name == "04-tapwater":
            (finding,) = findings
            assert finding.support["excluded_cycles"] == 17
