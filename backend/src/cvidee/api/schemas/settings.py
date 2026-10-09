"""Analysis settings (design additions §1.5, §1.6).

The UI renders the form generically from the JSON schema of :class:`AnalysisSettings`:
``title``, ``description``, ``default``, ``minimum``, ``maximum`` plus the extensions
``x-unit``, ``x-step``, ``x-group`` (:class:`~cvidee.rules.base.ParamGroup`) and ``x-rule``.
Per-signal maximum age and "expects regular updates" live on the signal mapping
(``PUT /api/signals/{signal_id}``), not here.
"""

from __future__ import annotations

from typing import Any, Self

from pydantic import Field, model_validator

from cvidee.api.schemas.common import ApiModel, UtcDateTime
from cvidee.rules.base import ParamGroup


def setting(
    default: Any,
    *,
    title: str,
    description: str,
    group: ParamGroup,
    unit: str | None = None,
    step: float | None = None,
    ge: float | None = None,
    le: float | None = None,
    rules: tuple[str, ...] = (),
) -> Any:
    """A settings field with the ``x-*`` extensions the settings screen renders."""
    extra: dict[str, Any] = {"x-group": str(group)}
    if unit is not None:
        extra["x-unit"] = unit
    if step is not None:
        extra["x-step"] = step
    if rules:
        extra["x-rule"] = list(rules)
    return Field(
        default=default,
        title=title,
        description=description,
        ge=ge,
        le=le,
        json_schema_extra=extra,
    )


_SC, _CF, _EF = ParamGroup.SHORT_CYCLES, ParamGroup.COMFORT, ParamGroup.EFFECT_MEASUREMENT
_DA, _RC, _CO, _DI = (
    ParamGroup.DATA,
    ParamGroup.RECOVERY,
    ParamGroup.COSTS,
    ParamGroup.DISPLAY,
)


class AnalysisSettings(ApiModel):
    """All user-adjustable analysis settings with their defaults (proposals, §7 q4)."""

    # Korte cycli
    short_cycle_min: float = setting(
        3.0,
        title="Kortecyclusgrens",
        group=_SC,
        unit="min",
        step=0.5,
        ge=1,
        le=15,
        rules=("kort-branden",),
        description="Een cv-cyclus die korter duurt dan deze grens én stopt terwijl de "
        "thermostaat nog warmte vraagt, telt als korte cyclus.",
    )
    demand_after_stop_s: int = setting(
        60,
        title="Warmtevraag na stop",
        group=_SC,
        unit="s",
        step=10,
        ge=0,
        le=600,
        rules=("stop-tijdens-vraag",),
        description="Hoe lang de warmtevraag na het stoppen van de brander nog moet aanhouden "
        'om te spreken van "stop tijdens vraag".',
    )
    min_short_cycles: int = setting(
        4,
        title="Minimum aantal korte cycli",
        group=_SC,
        unit="cycli",
        step=1,
        ge=2,
        le=30,
        rules=("kort-branden",),
        description="Zoveel korte cycli moeten er binnen één beoordeling zijn voordat de app "
        "een patroon meldt. Eén korte cyclus is nooit een waarschuwing.",
    )
    min_observation_hours: int = setting(
        6,
        title="Minimale observatieduur",
        group=_SC,
        unit="uur",
        step=1,
        ge=1,
        le=72,
        rules=("kort-branden", "overzicht"),
        description="Zoveel uur met gegevens tijdens cv-bedrijf of warmtevraag is nodig voordat "
        "de app iets over cycli concludeert. Uren zonder gegevens tellen niet mee.",
    )
    repetition_days: int = setting(
        2,
        title="Herhaling over dagen",
        group=_SC,
        unit="dagen",
        step=1,
        ge=1,
        le=14,
        rules=("kort-branden",),
        description="Een patroon heet structureel als het op minstens zoveel dagen binnen de "
        "periode voorkomt.",
    )
    repetition_window_days: int = setting(
        7,
        title="Herhaling: van de laatste",
        group=_SC,
        unit="dagen",
        step=1,
        ge=3,
        le=28,
        rules=("kort-branden",),
        description="Lengte van de periode waarbinnen de herhaling wordt geteld.",
    )
    # Comfort
    comfort_margin_c: float = setting(
        0.5,
        title="Comfortgrens",
        group=_CF,
        unit="°C",
        step=0.1,
        ge=0.1,
        le=3.0,
        rules=("voor-na",),
        description="Een ruimte telt als te koud als de gemeten temperatuur meer dan zoveel "
        "graden onder het setpoint ligt.",
    )
    allowed_comfort_loss_h_per_week: float = setting(
        4.0,
        title="Toegestaan comfortverlies",
        group=_CF,
        unit="u/week",
        step=0.5,
        ge=0,
        le=40,
        rules=("voor-na",),
        description="Standaard terugdraaicriterium per ruimte: zoveel uur per week mag een "
        "ruimte te koud zijn na een wijziging.",
    )
    # Effectmeting
    comparison_days: int = setting(
        7,
        title="Lengte vergelijkingsperiode",
        group=_EF,
        unit="dagen",
        step=1,
        ge=3,
        le=28,
        rules=("voor-na",),
        description="Even lange periode vóór en ná de wijziging. Gemarkeerde perioden worden "
        "eruit gelaten.",
    )
    comparable_weather_c: float = setting(
        2.0,
        title="Vergelijkbaar weer",
        group=_EF,
        unit="°C",
        step=0.5,
        ge=0.5,
        le=6.0,
        rules=("voor-na",),
        description="Verschil in gemiddelde buitentemperatuur waarbinnen de perioden "
        "vergelijkbaar zijn.",
    )
    limited_weather_c: float = setting(
        4.0,
        title="Beperkt vergelijkbaar weer",
        group=_EF,
        unit="°C",
        step=0.5,
        ge=1.0,
        le=10.0,
        rules=("voor-na",),
        description="Tot dit verschil is de vergelijking beperkt (lagere zekerheid); daarboven "
        "rapporteert de app geen effect.",
    )
    min_period_coverage_pct: int = setting(
        90,
        title="Minimale dekking per periode",
        group=_EF,
        unit="%",
        step=1,
        ge=50,
        le=100,
        rules=("voor-na",),
        description="Zoveel procent van de tijd moeten de benodigde signalen gegevens hebben "
        "in beide perioden.",
    )
    # Gegevens
    min_assessment_coverage_pct: int = setting(
        80,
        title="Minimale dekking voor een beoordeling",
        group=_DA,
        unit="%",
        step=1,
        ge=50,
        le=100,
        rules=("overzicht",),
        description='Onder deze dekking van de kernsignalen toont het Overzicht "Onvoldoende '
        'gegevens" en geeft de app geen beoordeling.',
    )
    flame_resolution_s: int = setting(
        10,
        title="Gewenste meetresolutie vlamstatus",
        group=_DA,
        unit="s",
        step=1,
        ge=1,
        le=60,
        rules=("beschikbaarheid",),
        description="Hoe vaak de vlamstatus minimaal ververst moet worden.",
    )
    retention_days: int = setting(
        180,
        title="Bewaartermijn ruwe gegevens",
        group=_DA,
        unit="dagen",
        step=30,
        ge=30,
        le=730,
        description="Ruwe meetwaarden ouder dan dit worden opgeruimd. Afgeleide cycli, "
        "bevindingen en advieshistorie blijven bewaard.",
    )
    # Herstel
    recovery_days: int = setting(
        3,
        title="Dagen zonder patroon",
        group=_RC,
        unit="dagen",
        step=1,
        ge=1,
        le=14,
        description="Zoveel aaneengesloten dagen moet het patroon weg zijn.",
    )
    recovery_comparable_weather_only: bool = setting(
        True,
        title="Alleen bij vergelijkbaar weer",
        group=_RC,
        description="Herstel telt alleen als het weer vergelijkbaar is met de periode waarin "
        "het patroon optrad.",
    )
    recovery_min_coverage_pct: int = setting(
        90,
        title="Minimale dekking in herstelperiode",
        group=_RC,
        unit="%",
        step=1,
        ge=50,
        le=100,
        description="Zoveel procent gegevens is nodig in de herstelperiode.",
    )
    postpone_days: int = setting(
        7,
        title="Uitstellen standaard",
        group=_RC,
        unit="dagen",
        step=1,
        ge=1,
        le=60,
        description='Termijn achter de knop "Uitstellen" bij een advies.',
    )
    # Kosten
    gas_price_eur_per_m3: float | None = setting(
        None,
        title="Gasprijs",
        group=_CO,
        unit="€ per m³",
        step=0.01,
        ge=0.01,
        le=10.0,
        description="All-in prijs per m³. Leeg laten = geen euro's.",
    )
    # Weergave
    show_explanations: bool = setting(
        True,
        title="Uitleg tonen",
        group=_DI,
        description="Toont uitleg bij kengetallen, begrippen bij bevindingen en de uitlegbanners.",
    )
    show_requirement_ids: bool = setting(
        False,
        title="Requirement-ID's tonen",
        group=_DI,
        description="Alleen zichtbaar in dev-modus.",
    )

    @model_validator(mode="after")
    def _cross_validate(self) -> Self:
        if self.repetition_days > self.repetition_window_days:
            raise ValueError("Herhaling: het eerste getal mag niet groter zijn dan het tweede.")
        if self.limited_weather_c < self.comparable_weather_c:
            raise ValueError("'Beperkt vergelijkbaar weer' moet ≥ 'Vergelijkbaar weer' zijn.")
        return self


class SettingsIn(ApiModel):
    """``PUT /api/settings``: ``revision`` must match the stored one (else 409)."""

    revision: str
    values: AnalysisSettings
    onboarding_completed_at: UtcDateTime | None = None
    changed_by: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=1000)


class SettingsResponse(ApiModel):
    revision: str = Field(description="Version token, including the configuration hash.")
    updated_at: UtcDateTime | None
    values: AnalysisSettings
    onboarding_completed_at: UtcDateTime | None
    recompute_started: bool = Field(description="True when saving started a recomputation.")
    json_schema: dict[str, Any] = Field(
        description="JSON schema of 'values' with x-unit/x-step/x-group/x-rule for rendering."
    )


class SettingsRevisionOut(ApiModel):
    revision: str
    config_hash: str
    saved_at: UtcDateTime
    changed_by: str | None
    note: str | None
    values: AnalysisSettings


class SettingsHistory(ApiModel):
    items: list[SettingsRevisionOut]
