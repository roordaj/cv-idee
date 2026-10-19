# `comfort-per-ruimte` — gemeten comfortafwijking per ruimte

- **Id:** `comfort-per-ruimte` · **Huidige versie:** 1.0.0 · **Categorie:** `comfort` (UI: "Comfort")
- **Code:** `backend/src/cvidee/rules/room_comfort.py` · **Issue:** #161
- **Requirements:** FR-17, FR-21, FR-22, FR-28

## Doel

Meldt gemeten comfortverlies tijdens expliciet ingestelde comforturen wanneer dit de ingestelde weekgrens overschrijdt. De regel stelt geen oorzaak vast en leidt geen comfortdoel af uit de kamersetpoint.

## Toepasbaarheid

| Aspect | Waarde |
|---|---|
| Bedrijfsmodi (`applies_in_modes`) | verwarmingsbedrijf; tapwater (`dhw`) en onbekende modus tellen niet mee |
| Installatie (`applies_to`) | alleen afzonderlijke ruimtes met een verwarmingscircuit en expliciet schema |
| Bijzondere perioden | comfortuitsluitingen en perioden zonder verwachting worden overgeslagen; een expliciet tijdelijk doel wordt toegepast |
| Beoordelingsperiode (`history_ms`) | laatste 7 dagen |
| Scope-sleutel (`scope_key`) | `room:<room_key>` — één bevinding per ruimte |
| Bundelen (`supports`) | geen |

## Signalen

| Rol | Verplicht / optioneel | Gebruik | Effect als het ontbreekt |
|---|---|---|---|
| `room_temperature` | verplicht per ruimte | gemeten temperatuur tegenover het ingestelde comfortdoel | geen bevinding; beschikbaarheid vermeldt ontbrekende mapping |
| `room_setpoint` | optioneel | afzonderlijke vergelijking tegenover werkelijk kamersetpoint | doelanalyse blijft mogelijk; setpointmetrics ontbreken |
| `operating_mode` | verplicht voor geldige verwarmingsuren | sluit tapwater en onbekende modus uit | onbekende intervallen tellen niet mee |

**Resolutie (`resolution_limits`):** onbekende en ontbrekende intervallen blijven onbekend; ze worden nooit als nul of comfortverlies geteld.

## Parameters

De regel heeft geen eigen parameters. De bestaande analyse-instellingen leveren de comfortmarge, toegestane comfortverliesuren per week, minimale dekking en minimale waarnemingsduur.

## Zekerheid

De regel rapporteert een directe temperatuurmeting zonder oorzaakinterpretatie. Een bevinding vereist een expliciet doel, geldige dekking en voldoende waargenomen uren. De gemeten afwijking tegenover doel en setpoint blijft per ruimte gescheiden.

## Hypotheses

De regel toont geen oorzaakhypotheses. Een temperatuurafwijking kan samenhangen met sensor, regeling, afgifte of gebouw; deze gegevens stellen dat niet vast.

## Advies

| Situatie | Soort | Actie | Omvang | Terugdraaicriterium |
|---|---|---|---|---|
| Gemeten verlies boven de ingestelde grens | `check` | Controleer het comfortdoel en de metingen van deze ruimte. | niet te onderbouwen | n.v.t. |

De app wijzigt geen instellingen. De waarneming en het advies gelden uitsluitend voor de ruimte waarop de bevinding is gescopeerd.

## Herstel

De bevinding herstelt wanneer voldoende gemeten comforturen beschikbaar zijn en het comfortverlies niet langer boven de ingestelde weekgrens ligt. Onvoldoende dekking of een datagat geldt niet als herstel.

## Wijzigingen

### 1.0.0 — 2026-10-19

- Eerste versie met comfortverlies tegenover expliciete per-ruimte doelen.
