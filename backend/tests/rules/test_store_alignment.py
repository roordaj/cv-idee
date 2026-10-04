"""Rule enums stored by ``cvidee.store`` must keep the same values (ADR-001 B7, ADR-004)."""

from __future__ import annotations

from enum import StrEnum

import pytest

from cvidee.rules import base
from cvidee.store import enums


@pytest.mark.parametrize(
    ("rules_enum", "store_enum"),
    [
        (base.Certainty, enums.Certainty),
        (base.Severity, enums.Severity),
        (base.SpecialPeriodKind, enums.SpecialPeriodKind),
        (base.CircuitKind, enums.CircuitKind),
    ],
    ids=lambda e: e.__name__,
)
def test_same_values_in_same_order(rules_enum: type[StrEnum], store_enum: type[StrEnum]) -> None:
    assert [m.value for m in rules_enum] == [m.value for m in store_enum]
