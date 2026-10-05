"""MVP acceptance scenarios (requirements §9, issue #15).

Assertions on what exists today (generator invariants, pipeline stages 1-4) must pass.
Assertions that need the rule runner, rules, findings engine or change evaluation are
``xfail(strict=False)`` with the ticket that will turn them on.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from cvidee.analysis.types import Mode
from tests.scenarios.harness import (
    StageRun,
    load_build,
    load_expected,
    run_stages,
    scenario_dirs,
)

DIRS = scenario_dirs()
IDS = [d.name for d in DIRS]
Loaded = tuple[Any, StageRun, dict[str, Any]]
_CACHE: dict[str, Loaded] = {}


def _load(directory: Path) -> Loaded:
    if directory.name not in _CACHE:
        data = load_build(directory)
        _CACHE[directory.name] = (data, run_stages(data), load_expected(directory))
    return _CACHE[directory.name]


@pytest.fixture(params=DIRS, ids=IDS)
def scenario(request: pytest.FixtureRequest) -> Loaded:
    return _load(request.param)


def _by_name(name: str) -> Loaded:
    return _load(next(d for d in DIRS if d.name == name))


def test_ten_scenarios_with_expectations() -> None:
    assert len(DIRS) == 10
    for d in DIRS:
        expected = load_expected(d)
        assert expected["scenario"] == d.name
        assert "must_not" in expected
        assert "findings" in expected


def test_generator_is_deterministic(scenario: Loaded) -> None:
    data, _, expected = scenario
    again = load_build(next(d for d in DIRS if d.name == expected["scenario"]))
    assert again.observations == data.observations
    assert again.truth_cycles == data.truth_cycles


def test_truth_cycles_match_expected_counts(scenario: Loaded) -> None:
    data, _, expected = scenario
    truth = Counter((c.mode.value, c.end_reason.value) for c in data.truth_cycles)
    for mode in ("ch", "dhw"):
        for reason, n in expected["cycles"].get(mode, {}).items():
            assert truth[(mode, reason)] == n, (mode, reason)


def test_observed_cycles_by_end_reason(scenario: Loaded) -> None:
    _, run, expected = scenario
    cycles = expected["cycles"]
    observed = Counter(
        (c.mode.value, c.end_reason.value if c.end_reason else None) for c in run.cycles
    )
    for mode in ("ch", "dhw", "unknown"):
        for reason, n in cycles.get(mode, {}).items():
            assert abs(observed[(mode, reason)] - n) <= cycles["tolerance"], (mode, observed)


def test_mode_shares(scenario: Loaded) -> None:
    _, run, expected = scenario
    total = sum(m.end - m.start for m in run.modes)
    share: Counter[str] = Counter()
    for m in run.modes:
        share[m.mode.value] += m.end - m.start
    for mode, (lo, hi) in expected["mode_share"].items():
        assert lo <= share[mode] / total <= hi, (mode, share[mode] / total)


def test_no_cycle_starts_inside_a_gap(scenario: Loaded) -> None:
    data, run, _ = scenario
    for c in run.cycles:
        if c.start_observed:
            for g_start, g_end, _kind in data.gaps:
                assert not (g_start < c.start < g_end), (c.start, g_start, g_end)


def test_can_outage_gives_no_fictitious_start_and_marks_gap() -> None:
    data, run, expected = _by_name("05-can-uitval")
    assert len(data.gaps) == expected["gaps"]
    for g_start, g_end, _kind in data.gaps:
        for c in run.cycles:
            if g_start < c.start <= g_end + 60_000:
                assert not c.start_observed
    assert any(m.mode is Mode.UNKNOWN for m in run.modes)


def test_stop_after_demand_is_not_stop_during_demand() -> None:
    _, run, _ = _by_name("03-stop-na-einde-vraag")
    ch = [c for c in run.cycles if c.mode is Mode.CH and c.end_reason is not None]
    assert ch
    assert all(c.end_reason is not None and c.end_reason.value == "demand_ended" for c in ch)


def test_dhw_cycles_are_separate_from_ch() -> None:
    _, run, expected = _by_name("04-tapwater")
    dhw = [c for c in run.cycles if c.mode is Mode.DHW]
    assert len(dhw) == expected["cycles"]["dhw"]["dhw_ended"]
    assert all(c.end_reason is not None and c.end_reason.value == "dhw_ended" for c in dhw)


def test_insufficient_data_cycles_are_unclassified() -> None:
    _, run, _ = _by_name("10-onvoldoende-gegevens")
    assert run.cycles
    assert all(c.mode is Mode.UNKNOWN for c in run.cycles)
    assert all(
        c.end_reason is not None and c.end_reason.value == "undetermined" for c in run.cycles
    )


def test_special_period_and_changes_are_reported() -> None:
    data, _, expected = _by_name("09-opstookprotocol")
    assert [p[2] for p in data.special_periods] == [s["kind"] for s in expected["special_periods"]]
    assert len(_by_name("08-gelijktijdige-wijzigingen")[0].changes) == 2
    assert len(_by_name("07-aanvoerwijziging-comfort")[0].changes) == 1


# --------------------------------------------------------------------------------------
# Not implemented yet: runner, rules, findings engine, change evaluation.
# --------------------------------------------------------------------------------------

_PENDING = {
    "findings": "rules #30-#33, findings engine #34",
    "must_not": "rules #30-#33, findings engine #34",
    "availability": "availability #25 and the rule runner",
    "before_after": "change evaluation #39 (voor-na)",
}


@pytest.mark.parametrize("section", sorted(_PENDING))
@pytest.mark.parametrize("name", IDS)
@pytest.mark.xfail(strict=False, reason="needs rule runner, rules and change evaluation (#30-#39)")
def test_pipeline_outcomes(name: str, section: str) -> None:
    from cvidee.analysis import pipeline

    _, _, expected = _by_name(name)
    if section not in expected:
        pytest.skip(f"{name} has no {section} expectations")
    assert hasattr(pipeline, "run_pipeline"), f"{section}: not implemented ({_PENDING[section]})"
    pytest.fail(f"{section}: not implemented ({_PENDING[section]})")
