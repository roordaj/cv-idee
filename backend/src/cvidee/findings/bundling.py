"""Declarative, deterministic bundling of overlapping rule candidates (FR-26).

Bundling changes presentation, never the parent's certainty, priority or advice. Quality
and operating-context findings remain separate. A child must explicitly support the
parent rule and satisfy the policy's scope and period relation.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from cvidee.rules.base import CycleRef, FindingCandidate, InstallationFacts
from cvidee.rules.registry import RuleOutcome, RuleSnapshot

Key = tuple[str, str]


@dataclass(frozen=True)
class BundlePolicy:
    parent_rule: str
    child_rules: tuple[str, ...]
    allow_circuit_scope: bool = False


POLICIES = (
    BundlePolicy("kort-branden", ("stop-tijdens-vraag", "temperatuurverloop", "hydraulisch"), True),
    BundlePolicy("stop-tijdens-vraag", ("temperatuurverloop",)),
)


@dataclass(frozen=True)
class BundleMember:
    snapshot: RuleSnapshot
    candidate: FindingCandidate

    @property
    def key(self) -> Key:
        return self.snapshot.rule_id, self.candidate.scope_key


@dataclass(frozen=True)
class BundlePlan:
    outcomes: tuple[RuleOutcome, ...]
    members: dict[Key, tuple[BundleMember, ...]]
    parents: dict[Key, Key]


def _same_scope(parent: str, child: str, policy: BundlePolicy, profile: InstallationFacts) -> bool:
    if parent == child:
        return True
    return (
        policy.allow_circuit_scope
        and parent == "boiler:ch"
        and child in {f"circuit:{c.key}:ch" for c in profile.circuits}
    )


def bundle_candidates(
    outcomes: Sequence[RuleOutcome],
    profile: InstallationFacts,
    protected: frozenset[Key] = frozenset(),
    policies: tuple[BundlePolicy, ...] = POLICIES,
) -> BundlePlan:
    """Assign each child at most once, prioritising the declared parent policy order.

    Touching half-open periods do not overlap. A protected child has advice already in
    follow-up and remains separately visible. Rule/scope ordering makes results independent
    of registry iteration order. Suppressed descendants move with a bundled parent.
    """
    records = sorted(
        (BundleMember(o.snapshot, c) for o in outcomes for c in o.candidates),
        key=lambda item: item.key,
    )
    by_key = {record.key: record for record in records}
    parents: dict[Key, Key] = {}
    for policy in policies:
        roots = [
            r for r in records if r.snapshot.rule_id == policy.parent_rule and r.key not in parents
        ]
        for child in records:
            if (
                child.snapshot.rule_id not in policy.child_rules
                or child.key in protected
                or child.key in parents
            ):
                continue
            choices = [
                root
                for root in roots
                if policy.parent_rule in child.candidate.supports
                and _same_scope(
                    root.candidate.scope_key, child.candidate.scope_key, policy, profile
                )
                and root.candidate.period.overlaps(child.candidate.period)
                and _shared_cycles(root.candidate, child.candidate)
            ]
            if choices:
                parents[child.key] = choices[0].key
    # Resolve a support chain to its root; policies must never create a cycle.
    for key in parents:
        visited = {key}
        root = parents[key]
        while root in parents:
            if root in visited:
                raise ValueError("Cyclic bundle policies")
            visited.add(root)
            root = parents[root]
        parents[key] = root
    members = {
        key: tuple(by_key[child] for child in sorted(parents) if parents[child] == key)
        for key in sorted(set(parents.values()))
    }
    filtered = tuple(
        replace(
            outcome,
            candidates=tuple(
                c
                for c in outcome.candidates
                if (outcome.snapshot.rule_id, c.scope_key) not in parents
            ),
        )
        for outcome in sorted(outcomes, key=lambda o: o.snapshot.rule_id)
    )
    return BundlePlan(filtered, members, parents)


def _shared_cycles(parent: FindingCandidate, child: FindingCandidate) -> bool:
    parent_keys = {ref.cycle_start for ref in parent.refs if isinstance(ref, CycleRef)}
    child_keys = {ref.cycle_start for ref in child.refs if isinstance(ref, CycleRef)}
    return not parent_keys or not child_keys or bool(parent_keys & child_keys)


def bundle_signature(
    content: Mapping[str, Any],
) -> tuple[tuple[object, object, object, object], ...]:
    """Snapshot identity changes on source/version/parameters, not on every live count."""
    return tuple(
        (
            source.get("rule"),
            source.get("scope_key"),
            source.get("parameters", {}),
            source.get("source_finding_id"),
        )
        for source in content.get("bundle", [])
    )
