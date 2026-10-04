"""Registry, parameter schema/loading, snapshots and the example rule (ADR-004 §7-§9)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from cvidee.analysis.types import HOUR_MS, Mode, Role, TimeRange
from cvidee.rules.base import (
    AvailabilityStatus,
    Certainty,
    InstallationFacts,
    RecommendationKind,
    Rule,
    RuleContext,
    RuleParams,
    SpecialPeriod,
    SpecialPeriodKind,
)
from cvidee.rules.example import ExampleCycleParams, ExampleCycleRule
from cvidee.rules.registry import RuleRegistry, default_registry, rule_set_hash

from .helpers import DAY_MS, PROFILE, T0, boiler_signals, cycle

REPO_ROOT = Path(__file__).resolve().parents[3]
RULE_DOCS = REPO_ROOT / "docs" / "regels"
RULE_DOC_SECTIONS = (
    "## Doel",
    "## Toepasbaarheid",
    "## Signalen",
    "## Parameters",
    "## Zekerheid",
    "## Hypotheses",
    "## Advies",
    "## Wijzigingen",
)

RULE: Rule = ExampleCycleRule()  # structural check against the protocol (mypy)
REGISTRY = RuleRegistry([RULE])
NOW = T0 + 7 * DAY_MS
PERIOD = TimeRange(NOW - 7 * DAY_MS, NOW)


def context(cycles_per_day: dict[int, int], **kwargs: object) -> RuleContext:
    cycles = tuple(
        cycle(T0 + day * DAY_MS + 6 * HOUR_MS + i * HOUR_MS)
        for day, n in sorted(cycles_per_day.items())
        for i in range(n)
    )
    fields: dict[str, object] = {
        "now": NOW,
        "period": PERIOD,
        "profile": PROFILE,
        "signals": boiler_signals(),
        "cycles": cycles,
    }
    fields.update(kwargs)
    return RuleContext(**fields)  # type: ignore[arg-type]


# -- identity --------------------------------------------------------------------------


class _Renamed(ExampleCycleRule):
    def __init__(self, rule_id: str, version: str = "1.0.0") -> None:
        self.id = rule_id  # type: ignore[misc]
        self.version = version  # type: ignore[misc]


@pytest.mark.parametrize(
    ("rule_id", "version", "match"),
    [
        ("Kort_Branden", "1.0.0", "kebab-case"),
        ("kort-branden", "1.3", "MAJOR.MINOR.PATCH"),
        ("kort-branden", "01.3.0", "MAJOR.MINOR.PATCH"),
    ],
)
def test_identity_validation(rule_id: str, version: str, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        RuleRegistry([_Renamed(rule_id, version)])


def test_registry_basics() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        RuleRegistry([ExampleCycleRule(), ExampleCycleRule()])
    registry = RuleRegistry([_Renamed("b-regel"), _Renamed("a-regel")])
    assert [r.id for r in registry] == ["a-regel", "b-regel"]
    assert registry.versions() == {"a-regel": "1.0.0", "b-regel": "1.0.0"}
    assert "a-regel" in registry
    assert len(registry) == 2
    with pytest.raises(KeyError):
        registry.get("onbekend")


# -- parameters ------------------------------------------------------------------------


def test_params_json_schema_has_ui_extensions() -> None:
    schema = REGISTRY.params_json_schema("voorbeeld-cycli")
    assert schema["x-rule"] == "voorbeeld-cycli"
    assert schema["x-rule-version"] == "0.1.0"
    prop = schema["properties"]["min_cycles"]
    assert prop["title"] == "Minimum aantal cycli"
    assert prop["default"] == 4
    assert (prop["minimum"], prop["maximum"]) == (1, 50)
    assert prop["x-unit"] == "cycli"
    assert prop["x-step"] == 1
    assert prop["x-group"] == "short_cycles"
    assert prop["x-rule"] == "voorbeeld-cycli"
    combined = REGISTRY.settings_schema()
    assert combined["properties"]["rules"]["properties"]["voorbeeld-cycli"] == schema


def test_validate_params_is_strict() -> None:
    assert REGISTRY.validate_params("voorbeeld-cycli", {}) == ExampleCycleParams()
    with pytest.raises(ValidationError):
        REGISTRY.validate_params("voorbeeld-cycli", {"onbekend": 1})
    with pytest.raises(ValidationError):
        REGISTRY.validate_params("voorbeeld-cycli", {"min_cycles": 0})
    with pytest.raises(ValidationError, match="structural_days"):
        REGISTRY.validate_params("voorbeeld-cycli", {"structural_days": 10, "window_days": 7})
    with pytest.raises(ValidationError):
        ExampleCycleParams().min_cycles = 3  # frozen model


def test_load_stored_is_lenient() -> None:
    loaded = REGISTRY.load_stored(
        "voorbeeld-cycli", {"min_cycles": 6, "oude_drempel": 3, "window_days": 99}
    )
    assert loaded.params == ExampleCycleParams(min_cycles=6)
    assert loaded.dropped == ("oude_drempel", "window_days")
    cross = REGISTRY.load_stored("voorbeeld-cycli", {"structural_days": 10, "window_days": 7})
    assert cross.params == ExampleCycleParams()
    assert cross.dropped == ("structural_days", "window_days")
    assert REGISTRY.load_stored("voorbeeld-cycli", None).params == ExampleCycleParams()


def test_snapshot_is_canonical_and_tracks_params() -> None:
    a = REGISTRY.snapshot("voorbeeld-cycli", ExampleCycleParams())
    b = REGISTRY.snapshot("voorbeeld-cycli", ExampleCycleParams.model_validate({}))
    c = REGISTRY.snapshot("voorbeeld-cycli", ExampleCycleParams(min_cycles=5))
    assert a == b
    assert a.params_hash != c.params_hash
    assert a.params == {"min_cycles": 4, "structural_days": 2, "window_days": 7}
    assert a.params_json == '{"min_cycles":4,"structural_days":2,"window_days":7}'
    assert rule_set_hash([a]) != rule_set_hash([c])
    with pytest.raises(TypeError):
        REGISTRY.snapshot("voorbeeld-cycli", RuleParams())


# -- evaluation ------------------------------------------------------------------------


def test_unavailable_rule_is_not_evaluated() -> None:
    outcome = REGISTRY.evaluate(
        "voorbeeld-cycli",
        context({0: 3}, signals=boiler_signals(without=(Role.FLAME,))),
        ExampleCycleParams(),
    )
    assert outcome.availability.status is AvailabilityStatus.UNAVAILABLE
    assert not outcome.evaluated
    assert outcome.candidates == ()


def test_not_applicable_rule_is_not_evaluated() -> None:
    class DirectOnly(ExampleCycleRule):
        def applies_to(self, profile: InstallationFacts) -> bool:
            return not profile.has_mixing_manifold

    registry = RuleRegistry([DirectOnly()])
    outcome = registry.evaluate("voorbeeld-cycli", context({0: 3}), ExampleCycleParams())
    assert not outcome.applicable
    assert outcome.candidates == ()


def test_too_few_cycles_gives_insufficient_evidence_and_a_measurement() -> None:
    outcome = REGISTRY.evaluate("voorbeeld-cycli", context({0: 3}), ExampleCycleParams())
    (c,) = outcome.candidates
    assert c.certainty is Certainty.INSUFFICIENT_EVIDENCE
    assert c.recommendation is not None
    assert c.recommendation.kind is RecommendationKind.MEASUREMENT
    assert outcome.snapshot.version == "0.1.0"


def test_one_day_is_preliminary_repeated_is_stronger() -> None:
    one_day = REGISTRY.evaluate("voorbeeld-cycli", context({0: 9}), ExampleCycleParams())
    assert one_day.candidates[0].certainty is Certainty.PRELIMINARY
    repeated = REGISTRY.evaluate(
        "voorbeeld-cycli", context({0: 3, 2: 3, 4: 3}), ExampleCycleParams()
    )
    c = repeated.candidates[0]
    assert c.certainty is Certainty.REASONABLE
    assert c.evidence.repetition_days == 3
    assert c.evidence.repetition_window_days == 7
    assert c.evidence.missing_signals == ()
    assert c.recommendation is None
    assert c.no_advice_reason


def test_missing_optional_signal_lowers_and_is_listed() -> None:
    ctx = context({0: 3, 2: 3, 4: 3}, signals=boiler_signals(without=(Role.HEAT_DEMAND,)))
    outcome = REGISTRY.evaluate("voorbeeld-cycli", ctx, ExampleCycleParams())
    assert outcome.availability.status is AvailabilityStatus.LIMITED
    c = outcome.candidates[0]
    assert c.certainty is Certainty.MODERATE
    assert [str(s) for s in c.evidence.missing_signals] == ["heat_demand@boiler"]


def test_excluded_cycles_do_not_count() -> None:
    ctx = context(
        {0: 3, 2: 3, 4: 3},
        special_periods=(
            SpecialPeriod(TimeRange(T0 + 2 * DAY_MS, T0 + 3 * DAY_MS), SpecialPeriodKind.TEST),
        ),
    )
    dhw = (*ctx.cycles, cycle(T0 + 5 * DAY_MS, minutes=10, mode=Mode.DHW))
    ctx = context({0: 3, 2: 3, 4: 3}, special_periods=ctx.special_periods, cycles=dhw)
    c = REGISTRY.evaluate("voorbeeld-cycli", ctx, ExampleCycleParams()).candidates[0]
    assert c.evidence.relevant_cycles == 6
    assert c.evidence.excluded_cycles == 4
    assert c.evidence.excluded_ms == DAY_MS


def test_evaluation_is_deterministic() -> None:
    ctx = context({0: 3, 2: 3, 4: 3})
    first = REGISTRY.evaluate("voorbeeld-cycli", ctx, ExampleCycleParams())
    again = REGISTRY.evaluate("voorbeeld-cycli", ctx, ExampleCycleParams())
    assert first == again


# -- documentation ---------------------------------------------------------------------


def check_rule_doc(text: str, version: str) -> list[str]:
    problems = [f"missing section {s!r}" for s in RULE_DOC_SECTIONS if s not in text]
    if not re.search(rf"^### {re.escape(version)}\b", text, re.MULTILINE):
        problems.append(f"no changelog entry '### {version}'")
    return problems


def test_template_has_every_section() -> None:
    template = (RULE_DOCS / "_template.md").read_text(encoding="utf-8")
    assert check_rule_doc(template, "1.0.0") == []


def test_every_registered_rule_is_documented() -> None:
    """Each production rule has ``docs/regels/<id>.md`` with its current version."""
    problems: list[str] = []
    for rule in default_registry():
        doc = RULE_DOCS / f"{rule.id}.md"
        if not doc.exists():
            problems.append(f"{doc} is missing")
            continue
        text = doc.read_text(encoding="utf-8")
        problems.extend(f"{rule.id}: {p}" for p in check_rule_doc(text, rule.version))
    assert problems == []
