"""Installation profile (FR-02, FR-03): versioned store, default profile and rule predicates."""

from cvidee.installation.defaults import default_profile
from cvidee.installation.facts import profile_facts
from cvidee.installation.predicates import (
    boiler_dt_representative,
    circuit_is_mixed,
    known,
    modulation_to_kw,
)
from cvidee.installation.repository import SqlInstallationProfileRepository

__all__ = [
    "SqlInstallationProfileRepository",
    "boiler_dt_representative",
    "circuit_is_mixed",
    "default_profile",
    "known",
    "modulation_to_kw",
    "profile_facts",
]
