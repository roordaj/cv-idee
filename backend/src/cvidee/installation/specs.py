"""Catalogue of installation specifications (FR-03): key, label, unit."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SpecInfo:
    key: str
    label: str
    unit: str | None


MAX_FLOW = "max_ch_flow_temperature"
MAX_POWER = "max_ch_power"
MIN_POWER = "min_power"
PUMP_SETTING = "pump_setting"
MODULATION_TO_KW = "modulation_to_kw"
GAS_PRICE = "gas_price"
GAS_METER_SCOPE = "gas_meter_scope"

SPEC_CATALOGUE: tuple[SpecInfo, ...] = (
    SpecInfo(MAX_FLOW, "Maximale CV-aanvoer", "°C"),
    SpecInfo(MAX_POWER, "Maximaal CV-vermogen", "kW"),
    SpecInfo(MIN_POWER, "Minimumvermogen", "kW"),
    SpecInfo(PUMP_SETTING, "Pompstand", None),
    SpecInfo(MODULATION_TO_KW, "Modulatie → kW", None),
    SpecInfo(GAS_PRICE, "Gasprijs", "€/m³"),
    SpecInfo(GAS_METER_SCOPE, "Meterscope gas", None),
)
SPEC_BY_KEY = {s.key: s for s in SPEC_CATALOGUE}
