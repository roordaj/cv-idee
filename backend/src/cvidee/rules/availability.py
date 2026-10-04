"""Availability per analysis and per rule (FR-04, ADR-004 §6). Pure functions.

``available`` / ``limited`` / ``unavailable`` follow from which signals are mapped, their
coverage and staleness, and their actual resolution. The result is structured
(:class:`~cvidee.rules.base.AvailabilityIssue`); the API/UI renders Dutch notes such as
"Ontbreekt: cumulatief gasverbruik".
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from cvidee.analysis.types import DurationMs, Role, ScopeKind, SignalRef
from cvidee.rules.base import (
    AnalysisAvailability,
    AnalysisId,
    Availability,
    AvailabilityIssue,
    AvailabilityStatus,
    InstallationFacts,
    IssueKind,
    ResolutionLimit,
    Rule,
    RuleParams,
    SignalStatus,
    signal_ref,
)

AVAILABLE = AvailabilityStatus.AVAILABLE
LIMITED = AvailabilityStatus.LIMITED
UNAVAILABLE = AvailabilityStatus.UNAVAILABLE

_SINGLETON_KINDS = frozenset({ScopeKind.BOILER, ScopeKind.OUTDOOR})
SECOND_MS: DurationMs = 1000


@dataclass(frozen=True, slots=True)
class AnyOf:
    """At least one alternative must be satisfied; an alternative is a set of roles that
    are needed together (e.g. manifold flow *and* return)."""

    alternatives: tuple[tuple[Role, ...], ...]

    def __post_init__(self) -> None:
        if not self.alternatives or not all(self.alternatives):
            raise ValueError("AnyOf needs at least one non-empty alternative")


@dataclass(frozen=True, slots=True)
class SignalRequirement:
    """What an analysis or rule needs.

    * ``required`` / ``required_any`` missing → ``unavailable``;
    * ``optional`` / ``optional_any`` missing → ``limited``;
    * low coverage or a stale signal → ``limited``;
    * resolution coarser than a :class:`ResolutionLimit` → its ``on_exceed``.

    Roles scoped to a room, zone or manifold apply to every such entity in the installation
    profile (and every mapped one): some missing → ``limited``, all missing → as above.
    """

    required: tuple[Role, ...] = ()
    required_any: tuple[AnyOf, ...] = ()
    optional: tuple[Role, ...] = ()
    optional_any: tuple[AnyOf, ...] = ()
    resolution: tuple[ResolutionLimit, ...] = ()


@dataclass(frozen=True, slots=True)
class AvailabilityPolicy:
    """Settings that influence availability (design additions §1.5, section "Gegevens")."""

    min_coverage: float = 0.8
    """"Minimale dekking voor een beoordeling" (80 %)."""
    desired_flame_resolution_ms: DurationMs = 10 * SECOND_MS
    """"Gewenste meetresolutie vlamstatus" (10 s)."""

    def __post_init__(self) -> None:
        if not 0.0 < self.min_coverage <= 1.0:
            raise ValueError("AvailabilityPolicy: min_coverage must be within (0, 1]")
        if self.desired_flame_resolution_ms <= 0:
            raise ValueError("AvailabilityPolicy: desired_flame_resolution_ms must be positive")


def analysis_requirements(policy: AvailabilityPolicy) -> Mapping[AnalysisId, SignalRequirement]:
    """The requirement table of ADR-004 §6.2 (signal table of requirements §2)."""
    return {
        AnalysisId.CYCLES: SignalRequirement(
            required=(Role.FLAME,),
            optional=(Role.OPERATING_MODE,),
            optional_any=(AnyOf(((Role.HEAT_DEMAND,), (Role.FLOW_SETPOINT,))),),
            resolution=(ResolutionLimit(Role.FLAME, policy.desired_flame_resolution_ms),),
        ),
        AnalysisId.TEMPERATURE: SignalRequirement(
            required=(Role.FLAME, Role.FLOW_TEMPERATURE, Role.FLOW_SETPOINT),
            optional=(Role.RETURN_TEMPERATURE, Role.OPERATING_MODE),
        ),
        AnalysisId.OPERATING_MODE: SignalRequirement(
            required_any=(AnyOf(((Role.OPERATING_MODE,), (Role.FLAME,))),),
            optional=(Role.OPERATING_MODE,),
        ),
        AnalysisId.COMFORT: SignalRequirement(
            required=(Role.ROOM_TEMPERATURE, Role.ROOM_SETPOINT),
            optional=(Role.OUTDOOR_TEMPERATURE,),
        ),
        AnalysisId.ZONES: SignalRequirement(
            required=(Role.FLAME,),
            required_any=(AnyOf(((Role.ZONE_DEMAND,), (Role.VALVE_STATE,))),),
        ),
        AnalysisId.HYDRAULIC: SignalRequirement(
            required=(Role.FLOW_TEMPERATURE, Role.RETURN_TEMPERATURE),
            required_any=(
                AnyOf(
                    (
                        (Role.MANIFOLD_FLOW_TEMPERATURE, Role.MANIFOLD_RETURN_TEMPERATURE),
                        (Role.FLOW_RATE,),
                    )
                ),
            ),
            optional=(Role.PUMP_STATE,),
        ),
        AnalysisId.CONSUMPTION: SignalRequirement(
            required=(Role.GAS_CUMULATIVE,),
            optional=(Role.OUTDOOR_TEMPERATURE,),
        ),
        AnalysisId.EFFICIENCY: SignalRequirement(
            required=(Role.GAS_CUMULATIVE, Role.HEAT_METER),
        ),
    }


def rule_requirement(rule: Rule, params: RuleParams) -> SignalRequirement:
    """Requirement of a rule: its required/optional roles plus its resolution limits."""
    return SignalRequirement(
        required=tuple(sorted(rule.required_signals)),
        optional=tuple(sorted(rule.optional_signals)),
        resolution=rule.resolution_limits(params),
    )


# --------------------------------------------------------------------------------------
# Assessment
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Env:
    signals: Mapping[SignalRef, SignalStatus]
    profile: InstallationFacts
    policy: AvailabilityPolicy


@dataclass(frozen=True, slots=True)
class _Verdict:
    status: AvailabilityStatus
    issues: tuple[AvailabilityIssue, ...] = ()


def _refs_for(role: Role, env: _Env) -> tuple[SignalRef, ...]:
    kind = role.scope_kind
    if kind in _SINGLETON_KINDS:
        return (signal_ref(role),)
    keys = set(env.profile.scope_keys(kind))
    keys.update(
        ref.scope.key
        for ref in env.signals
        if ref.role is role and ref.scope.kind is kind and ref.scope.key is not None
    )
    return tuple(signal_ref(role, key) for key in sorted(keys))


def _assess_role(role: Role, *, required: bool, env: _Env) -> _Verdict:
    """Verdict for one role. ``required=False`` caps the status at ``limited``."""
    missing_status = UNAVAILABLE if required else LIMITED
    refs = _refs_for(role, env)
    if not refs:
        return _Verdict(missing_status, (AvailabilityIssue(IssueKind.NO_SCOPE_IN_PROFILE, role),))
    issues: list[AvailabilityIssue] = []
    absent = 0
    for ref in refs:
        key = ref.scope.key
        status = env.signals.get(ref)
        if status is None:
            issues.append(AvailabilityIssue(IssueKind.NOT_MAPPED, role, key, required))
            absent += 1
        elif status.coverage == 0.0:
            issues.append(AvailabilityIssue(IssueKind.NO_DATA, role, key, required))
            absent += 1
        else:
            if status.coverage < env.policy.min_coverage:
                issues.append(AvailabilityIssue(IssueKind.LOW_COVERAGE, role, key, required))
            if status.stale:
                issues.append(AvailabilityIssue(IssueKind.STALE, role, key, required))
    if absent == len(refs):
        verdict = missing_status
    elif issues:
        verdict = LIMITED
    else:
        verdict = AVAILABLE
    return _Verdict(verdict, tuple(issues))


def _assess_roles(roles: Iterable[Role], *, required: bool, env: _Env) -> _Verdict:
    status = AVAILABLE
    issues: list[AvailabilityIssue] = []
    for role in roles:
        verdict = _assess_role(role, required=required, env=env)
        status = status.worst(verdict.status)
        issues.extend(verdict.issues)
    return _Verdict(status, tuple(issues))


def _assess_any(group: AnyOf, *, required: bool, env: _Env) -> _Verdict:
    verdicts = [_assess_roles(alt, required=required, env=env) for alt in group.alternatives]
    best = min(verdicts, key=lambda v: v.status.rank)
    if best.status is AVAILABLE:
        return best
    # Not fully satisfied: report every alternative so the UI can list all options
    # ("Ontbreekt: verdeleraanvoer, -retour, debiet").
    return _Verdict(best.status, tuple(i for v in verdicts for i in v.issues))


def _assess_resolution(limit: ResolutionLimit, env: _Env) -> _Verdict:
    status = AVAILABLE
    issues: list[AvailabilityIssue] = []
    for ref in _refs_for(limit.role, env):
        sig = env.signals.get(ref)
        if sig is None or sig.coverage == 0.0:
            continue  # reported as missing by the role check
        if sig.resolution_ms is None:
            status = status.worst(LIMITED)
            issues.append(
                AvailabilityIssue(IssueKind.RESOLUTION_UNKNOWN, limit.role, ref.scope.key)
            )
        elif sig.resolution_ms > limit.max_interval_ms:
            status = status.worst(limit.on_exceed)
            issues.append(AvailabilityIssue(IssueKind.RESOLUTION, limit.role, ref.scope.key))
    return _Verdict(status, tuple(issues))


def assess(
    requirement: SignalRequirement,
    signals: Iterable[SignalStatus],
    profile: InstallationFacts,
    policy: AvailabilityPolicy | None = None,
) -> Availability:
    """Availability of one analysis or rule. ``signals`` holds the *mapped* signals."""
    policy = policy or AvailabilityPolicy()
    env = _Env({s.signal: s for s in signals}, profile, policy)
    verdicts = [
        _assess_roles(requirement.required, required=True, env=env),
        _assess_roles(requirement.optional, required=False, env=env),
        *(_assess_any(g, required=True, env=env) for g in requirement.required_any),
        *(_assess_any(g, required=False, env=env) for g in requirement.optional_any),
        *(_assess_resolution(limit, env) for limit in requirement.resolution),
    ]
    status = AVAILABLE
    issues: set[AvailabilityIssue] = set()
    for verdict in verdicts:
        status = status.worst(verdict.status)
        issues.update(verdict.issues)
    return Availability(status, tuple(sorted(issues)))


def assess_analyses(
    signals: Iterable[SignalStatus],
    profile: InstallationFacts,
    policy: AvailabilityPolicy | None = None,
) -> tuple[AnalysisAvailability, ...]:
    """Availability of every analysis, in :class:`AnalysisId` order (design v3 table)."""
    policy = policy or AvailabilityPolicy()
    statuses = tuple(signals)
    table = analysis_requirements(policy)
    return tuple(
        AnalysisAvailability(analysis, assess(table[analysis], statuses, profile, policy))
        for analysis in AnalysisId
    )
