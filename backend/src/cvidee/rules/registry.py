"""Rule registry, parameter loading/schema and snapshots (ADR-004 §7-§9).

The registry is the single list of rules the runner evaluates. It validates rule identity
(kebab-case id, semver), produces the JSON schema the settings UI renders, validates stored
parameters and builds the snapshot (rule id, version, parameters, hash) that runs, findings
and advice history store (FR-41).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from cvidee.rules.availability import AvailabilityPolicy, assess, rule_requirement
from cvidee.rules.base import (
    Availability,
    AvailabilityStatus,
    FindingCandidate,
    Rule,
    RuleContext,
    RuleParams,
    validate_rule_identity,
)


def canonical_json(value: Any) -> str:
    """Deterministic JSON (sorted keys, no whitespace) for hashing and storage."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class RuleSnapshot:
    """What a run, finding and advice snapshot record about a rule (FR-41)."""

    rule_id: str
    version: str
    params_json: str
    """Canonical JSON of the effective parameters (defaults included)."""
    params_hash: str

    @property
    def params(self) -> dict[str, Any]:
        loaded: dict[str, Any] = json.loads(self.params_json)
        return loaded


@dataclass(frozen=True, slots=True)
class LoadedParams:
    """Stored parameters after lenient loading (see :meth:`RuleRegistry.load_stored`)."""

    params: RuleParams
    dropped: tuple[str, ...] = ()
    """Stored keys that were unknown or no longer valid and fell back to the default."""


@dataclass(frozen=True, slots=True)
class RuleOutcome:
    """Result of evaluating one rule for one context."""

    snapshot: RuleSnapshot
    applicable: bool
    """``False`` if the installation predicate excluded the rule."""
    availability: Availability
    candidates: tuple[FindingCandidate, ...] = ()

    @property
    def evaluated(self) -> bool:
        return self.applicable and self.availability.status is not AvailabilityStatus.UNAVAILABLE


class RuleRegistry:
    """Immutable set of rules, iterated in id order (determinism)."""

    def __init__(self, rules: Iterable[Rule]) -> None:
        by_id: dict[str, Rule] = {}
        for rule in rules:
            validate_rule_identity(rule)
            if rule.id in by_id:
                raise ValueError(f"duplicate rule id {rule.id!r}")
            by_id[rule.id] = rule
        self._rules = dict(sorted(by_id.items()))

    def __iter__(self) -> Iterator[Rule]:
        return iter(self._rules.values())

    def __len__(self) -> int:
        return len(self._rules)

    def __contains__(self, rule_id: object) -> bool:
        return rule_id in self._rules

    def get(self, rule_id: str) -> Rule:
        try:
            return self._rules[rule_id]
        except KeyError:
            raise KeyError(f"unknown rule {rule_id!r}") from None

    def versions(self) -> dict[str, str]:
        """``{rule_id: version}`` as stored in ``analysis_runs``."""
        return {rule.id: rule.version for rule in self}

    # -- parameters ----------------------------------------------------------------------

    def default_params(self, rule_id: str) -> RuleParams:
        return self.get(rule_id).params_schema()

    def validate_params(self, rule_id: str, raw: Mapping[str, Any]) -> RuleParams:
        """Strict validation for ``PUT /api/settings``: unknown keys or invalid values raise
        :class:`pydantic.ValidationError` (→ 422). Missing keys take their defaults."""
        return self.get(rule_id).params_schema.model_validate(dict(raw))

    def load_stored(self, rule_id: str, raw: Mapping[str, Any] | None) -> LoadedParams:
        """Lenient loading of stored values (e.g. written by an older rule version):
        unknown keys and values that are no longer valid fall back to the default and are
        reported in ``dropped``, so the runner never stops on an outdated setting."""
        schema = self.get(rule_id).params_schema
        values = dict(raw or {})
        dropped = sorted(k for k in values if k not in schema.model_fields)
        for key in dropped:
            del values[key]
        try:
            return LoadedParams(schema.model_validate(values), tuple(dropped))
        except ValidationError as exc:
            bad = {str(err["loc"][0]) for err in exc.errors() if err["loc"]}
            bad_fields = bad & set(values)
            if not bad_fields:
                # A cross-field validator failed: fall back to defaults for all stored keys.
                bad_fields = set(values)
            for key in bad_fields:
                del values[key]
            params = schema.model_validate(values)
            return LoadedParams(params, tuple(sorted({*dropped, *bad_fields})))

    def params_json_schema(self, rule_id: str) -> dict[str, Any]:
        """JSON schema of one rule's parameters with ``x-rule``/``x-rule-version`` at the
        root and ``x-rule`` on every property (design additions §1.5)."""
        rule = self.get(rule_id)
        schema = rule.params_schema.model_json_schema()
        schema["x-rule"] = rule.id
        schema["x-rule-version"] = rule.version
        for prop in schema.get("properties", {}).values():
            prop["x-rule"] = rule.id
        return schema

    def settings_schema(self) -> dict[str, Any]:
        """Combined schema ``{"rules": {rule_id: schema}}`` for ``GET /api/settings``."""
        return {
            "type": "object",
            "properties": {
                "rules": {
                    "type": "object",
                    "properties": {rule.id: self.params_json_schema(rule.id) for rule in self},
                    "additionalProperties": False,
                }
            },
        }

    # -- snapshots -----------------------------------------------------------------------

    def snapshot(self, rule_id: str, params: RuleParams) -> RuleSnapshot:
        rule = self.get(rule_id)
        if not isinstance(params, rule.params_schema):
            raise TypeError(f"params for {rule_id} must be {rule.params_schema.__name__}")
        params_json = canonical_json(params.model_dump(mode="json"))
        return RuleSnapshot(rule.id, rule.version, params_json, _sha256(params_json))

    # -- evaluation ----------------------------------------------------------------------

    def evaluate(
        self,
        rule_id: str,
        ctx: RuleContext,
        params: RuleParams,
        policy: AvailabilityPolicy | None = None,
    ) -> RuleOutcome:
        """Evaluate one rule: installation predicate → availability gate → ``evaluate``.

        Candidates are returned sorted by ``(scope_key, period.start)``; a rule may emit at
        most one candidate per ``scope_key`` per evaluation (dedupe key, FR-39).
        """
        rule = self.get(rule_id)
        snapshot = self.snapshot(rule_id, params)
        availability = assess(rule_requirement(rule, params), ctx.signals, ctx.profile, policy)
        if not rule.applies_to(ctx.profile):
            return RuleOutcome(snapshot, False, availability)
        if availability.status is AvailabilityStatus.UNAVAILABLE:
            candidates = tuple(
                sorted(
                    rule.unavailable_evidence(ctx, params),
                    key=lambda c: (c.scope_key, c.period.start),
                )
            )
            keys = [c.scope_key for c in candidates]
            if len(keys) != len(set(keys)):
                raise ValueError(f"rule {rule_id} emitted several candidates for one scope_key")
            for candidate in candidates:
                if rule_id in candidate.supports:
                    raise ValueError(f"rule {rule_id}: a candidate cannot support its own rule")
            return RuleOutcome(snapshot, True, availability, candidates)
        candidates = tuple(
            sorted(rule.evaluate(ctx, params), key=lambda c: (c.scope_key, c.period.start))
        )
        keys = [c.scope_key for c in candidates]
        if len(keys) != len(set(keys)):
            raise ValueError(f"rule {rule_id} emitted several candidates for one scope_key")
        for candidate in candidates:
            if rule_id in candidate.supports:
                raise ValueError(f"rule {rule_id}: a candidate cannot support its own rule")
        return RuleOutcome(snapshot, True, availability, candidates)


def rule_set_hash(snapshots: Iterable[RuleSnapshot]) -> str:
    """Hash over rule versions and parameters; part of the config hash (#22, #27)."""
    items = sorted((s.rule_id, s.version, s.params_hash) for s in snapshots)
    return _sha256(canonical_json(items))


def default_registry() -> RuleRegistry:
    """The production rules (the MVP rules land one by one: #30-#33, #39)."""
    from cvidee.rules.before_after import BeforeAfterRule
    from cvidee.rules.data_quality import DataLossRule, StaleSensorRule
    from cvidee.rules.dhw import DhwExcludedRule
    from cvidee.rules.hydraulic import HydraulicRule
    from cvidee.rules.room_comfort import RoomComfortRule
    from cvidee.rules.short_cycling import ShortCyclingRule
    from cvidee.rules.stop_during_demand import StopDuringDemandRule
    from cvidee.rules.temperature import TemperatureRule

    return RuleRegistry(
        (
            BeforeAfterRule(),
            ShortCyclingRule(),
            StopDuringDemandRule(),
            TemperatureRule(),
            DataLossRule(),
            StaleSensorRule(),
            DhwExcludedRule(),
            HydraulicRule(),
            RoomComfortRule(),
        )
    )
