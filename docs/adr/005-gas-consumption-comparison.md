# ADR-005: Select observed periods before weather-normalizing gas use

- **Status:** accepted for the first FR-31 implementation
- **Date:** 2026-10-19
- **Issue:** #189

## Context

FR-31 asks for measured gas use to be compared using outdoor temperature, room
setpoint, heating duration and use. The available data can include a cumulative
gas meter, outdoor temperature, room temperature and setpoint, boiler mode and
burner cycles, heat demand, zones, installation/profile revisions and marked
special periods. It does not guarantee a separate meter for space heating, a
measure of cooking or hot-water gas use, or a reliable record of household
occupancy and appliance use. A `boiler_only` meter can still include domestic hot
water; a `whole_house` meter can also include cooking and other gas uses.

## Options considered

| Method | Advantages | Limitations for CV-idee |
|---|---|---|
| Heating-degree-day ratio | Simple and explainable. | It scales total gas as if all consumption were weather-sensitive. It cannot isolate cooking or hot-water baseload, and it does not control for setpoint or operating context. |
| Degree-day or change-point regression | Can estimate a weather-independent intercept and a weather-sensitive slope. | A fitted intercept does not prove which end use consumed that gas. It needs representative weather and energy data, measured influential variables, and model-fit checks. A daily or weekly result from sparse, mixed-use readings would imply precision the data cannot establish. |
| Multivariable regression or machine learning | Could represent weather and measured use context together. | The app does not have complete independent measures for household use or hot-water draws. Heating runtime is correlated with the gas outcome and cannot be used as if it were an independent fuel measure. More coefficients do not resolve a missing meter boundary. |
| Select a previously observed period | Keeps the result on measured values; assumptions and both raw totals stay visible; no extrapolation or fitted coefficient. | It describes two observed periods. It is not a normalized heating quantity and cannot establish why their gas totals differ. It may return no eligible period. |

## Decision

The first implementation uses **selection of an explicitly chosen, previously
observed period of the same duration**. It does not calculate a weather-adjusted
gas volume. The UI and API call this a *periodevergelijking* or *geselecteerde
periode* and show both measured totals, periods and context. They must not label
the result *weersgecorrigeerd*, *genormaliseerd*, *ruimteverwarmingsverbruik*,
*rendement* or *besparing*.

A period can be offered as a context-matched candidate only when its gas source,
unit, meter identity and confirmed scope match the selected period; counter
coverage in both meets the existing `min_period_coverage_pct` setting (default
90%); the windows have equal elapsed duration; and there is no reset, unresolved
gap, overlapping window, excluded special period or profile/mapping change that
invalidates the pair. Outdoor temperature and required room-setpoint profiles
must meet the same configured coverage requirement. One such historical window
is the minimum for a descriptive pair; it does not support a population-level or
causal conclusion. Weather, setpoint, heat-demand,
burner-runtime and available zone context are shown side by side. Use the existing
before/after weather and coverage criteria as conservative comparison checks,
not as evidence that a gas model is valid. Room setpoint profiles must match the
existing before/after comparison rule. Missing use context remains `unknown`;
the app does not infer that cooking, hot-water draw or occupancy stayed constant.

The user chooses from eligible historical candidates; the app does not choose a
"best" match using undisclosed weights. If use context is unknown, the raw pair
may still be inspected but its comparison status is **limited** and no heating
effect is attributed. If scope, counter continuity, coverage or weather context
prevents a meaningful pair, comparison is **unavailable** with the reason shown.
Unknown is never represented by zero. The raw counter values remain available
independently of comparison status.

For a whole-house meter, the result always refers to whole-house gas. For a
boiler-only meter, it refers to total boiler gas, which can include domestic hot
water. Burner mode or DHW cycle counts are context only: they do not provide a
validated gas split. No application-level allocation of gas to cooking, DHW or
space heating is permitted from elapsed time, modulation, cycle count or a
generic conversion factor.

Degree-day ratios, change-point regression and multivariable models remain
deferred. Reconsider them only after an implementation can establish the meter
boundary and relevant end uses, has continuous representative data across the
observed weather range (at minimum, one continuous representative year spanning
heating and non-heating use), measures its independent variables over matching
periods, and reserves observations to test out-of-sample fit and residuals. The
applicable fit thresholds must be selected and justified before model code is
written; there is no universal sample count independent of the model and meter.
It must report the model, training interval, assumptions, uncertainty and
observed-range limits. A model that fails those checks returns `unknown` /
unavailable rather than a corrected value.

## Consequences

- FR-31 can ship a conservative measured-period comparison without promising a
  correction that current inputs cannot support.
- The `comparison` availability is independent from raw consumption, costs and
  efficiency. Missing comparison context does not hide valid raw meter data.
- The comparison presents weather, room setpoint, burner/heat-demand duration,
  available zone context, meter scope, coverage, resets, special periods and
  profile/mapping versions. It shows which of those are unknown.
- Existing weather thresholds are reused only as comparison gates. They do not
  become a fitted heating balance point or a gas-specific validation threshold.
- Follow-up #192 implements the selected-period comparison. #190 must design the
  limited/unknown states and avoid a normalized-volume or savings claim.

## Evidence

- Makhmalbaf, Srivastava and Wang, *Simulation-Based Weather Normalization
  Approach to Study the Impact of Weather on Energy Use of Buildings in the
  U.S.*, Proceedings of BS2013. The review explains that ratio methods do not
  separate non-weather-sensitive baseload, while regression needs a meaningful
  relationship and can be confounded by other variables. [Paper (PNNL / Building
  Energy Score)](https://buildingenergyscore.energy.gov/resources/download?key=publications/weather_normalization.pdf)
- ASHRAE Handbook, Chapter 19, *Energy Estimating and Modeling Methods*. It
  describes change-point models, their baseline intercept and heating slope,
  data requirements, and limitations from schedules and factors other than
  outdoor temperature. [ASHRAE Handbook chapter](https://handbook.ashrae.org/Handbooks/F21/IP/f21_ch19/f21_ch19_ip.aspx)
- Efficiency Valuation Organization, *IPMVP Core Concepts*. It requires
  influential independent variables to be measured for the same periods and
  describes representative baseline data and statistical validation for
  regression models. [IPMVP document](https://evo-world.org/en/general/1897-x-ipmvp-core-concepts-statutory-review-copy-1/file)
