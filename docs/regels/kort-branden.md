# `kort-branden` — herhaald kort branden tijdens warmtevraag

- **Id:** `kort-branden` · **Huidige versie:** 1.0.0 · **Categorie:** `cycles` (UI: "Cycli")
- **Code:** `backend/src/cvidee/rules/short_cycling.py` · **Issue:** #30
- **Requirements:** FR-14, FR-23, FR-24, FR-28

## Doel

Detecteert dat de brander herhaaldelijk binnen de kortecyclusgrens stopt terwijl de warmtevraag blijft bestaan ("pendelen"). Relevant voor bedrijfsstabiliteit (slijtage) en energie. De regel stelt de oorzaak niet vast: zij noemt drie hypotheses en een onderscheidende controle. Eén korte cyclus, tapwatercycli en cycli in gemarkeerde perioden tellen nooit mee.

## Toepasbaarheid

| Aspect | Waarde |
|---|---|
| Bedrijfsmodi (`applies_in_modes`) | alleen `ch`; tapwater (`dhw`) en naloop uitgesloten |
| Installatie (`applies_to`) | altijd |
| Bijzondere perioden | uitgesloten (FR-10), geen afwijking |
| Beoordelingsperiode (`history_ms`) | laatste 7 dagen (parameter `window_days`) |
| Scope-sleutel (`scope_key`) | `boiler:ch` — één bevinding voor het patroon |
| Bundelen (`supports`) | geen; `stop-tijdens-vraag` (#31) ondersteunt deze regel |

Een korte cyclus is een volledige cv-cyclus met eindreden `stop_during_demand` (de pipeline bepaalt of de warmtevraag na de stop aanhield) en een duur korter dan `short_cycle_min`. Onvolledige cycli (open, datagat) tellen niet mee.

## Signalen

| Rol | Verplicht / optioneel | Gebruik | Effect als het ontbreekt |
|---|---|---|---|
| `flame` | verplicht | starts, brandduur | regel niet beschikbaar |
| `operating_mode` | verplicht | tapwater uitsluiten | regel niet beschikbaar |
| `heat_demand` | verplicht | stop tijdens vraag | regel niet beschikbaar |
| `flow_setpoint`, `flow_temperature`, `return_temperature`, `modulation` | optioneel | aanwijzingen bij hypotheses | beperkt; zekerheid één stap lager |
| `outdoor_temperature` | optioneel | hypothese 3 | beperkt; hypothese 3 niet te onderscheiden |
| `valve_state`, `pump_state`, `flow_rate`, `manifold_*_temperature` | optioneel | onderscheidende metingen hypothese 1 en 2 | beperkt; "Ontbreekt" noemt het signaal |

**Resolutie (`resolution_limits`):** vlamstatus ≤ kortecyclusgrens ÷ 4 → anders beperkt; > ÷ 2 → niet beschikbaar.

## Parameters

| Veld (`params_schema`) | Label (UI) | Standaard | Eenheid · stap | Bereik | `x-group` |
|---|---|---|---|---|---|
| `short_cycle_min` | Kortecyclusgrens | 3 | min · 0,5 | 1 – 15 | `short_cycles` |
| `min_short_cycles` | Minimum aantal korte cycli | 4 | cycli · 1 | 2 – 30 | `short_cycles` |
| `min_observation_h` | Minimale observatieduur | 6 | uur · 1 | 1 – 72 | `short_cycles` |
| `structural_days` | Herhaling over dagen (eerste veld) | 2 | dagen · 1 | 1 – 14 | `short_cycles` |
| `window_days` | Beoordelingsperiode (tweede veld) | 7 | dagen · 1 | 3 – 28 | `short_cycles` |

Kruisvalidatie: `structural_days` ≤ `window_days`. "Warmtevraag na stop" (60 s) is een parameter van de pipeline/`stop-tijdens-vraag` (#31), niet van deze regel.

## Zekerheid

Criteria-sjabloon (ADR-004 §5). Lege cel = niet van toepassing. Ontbrekende optionele signalen verlagen de zekerheid één stap (niet onder *matig*).

| Niveau | Dekking kernsignalen | Relevante cycli | Waargenomen uren | Herhaling (dagen) | Overig |
|---|---|---|---|---|---|
| geen kandidaat | | korte cycli < `min_short_cycles` | | | |
| minimum (anders *onvoldoende bewijs*) | ≥ 80 % | | ≥ `min_observation_h` (6 u) | | |
| structureel (anders *voorlopig*) | | | | ≥ `structural_days` van `window_days` (2 van 7) | |
| *redelijk* | ≥ 90 % | ≥ 12 | | ≥ 3 | |
| *hoog* | ≥ 95 % | ≥ 30 | | ≥ 5 | |
| *hoog (gemeten)* | niet bereikbaar (interpretatie nodig) | | | | |
| plafond (`max_certainty`) | *hoog* | | | | |

Dekking: laagste dekking van `flame`, `operating_mode` en `heat_demand`. Relevante cycli: volledige cv-cycli buiten gemarkeerde perioden. Waargenomen uren: brandduur plus pauzes van die cycli (uren zonder gegevens tellen niet). Een dag telt voor de herhaling bij ≥ 2 korte cycli op die dag.

## Hypotheses

| Hypothese | Aanwijzing (vóór) | Ontbreekt / tegen | Onderscheidende meting | Signalen die helpen |
|---|---|---|---|---|
| Te weinig open afgifte | aanvoer boven gewenst tijdens korte cycli; modulatie laag | zone- en klepstatus niet gekoppeld | aantal open vloerverwarmingsgroepen en radiatorkranen tijdens de cycli | `valve_state`, `zone_demand` |
| Beperkte doorstroming ketelcircuit | ketel-ΔT tijdens branden | pompstatus en debiet onbekend; verdeleraanvoer/-retour niet gekoppeld | pompstatus of debiet; verdeleraanvoer en -retour | `pump_state`, `flow_rate`, `manifold_*_temperature` |
| Minimumvermogen boven actuele warmtevraag | modulatie laag tijdens korte cycli | minimumvermogen in kW niet vastgelegd; buitentemperatuur | vergelijk cycli bij lagere buitentemperatuur; leg minimumvermogen vast | `outdoor_temperature` |

Aanwijzingen bevatten alleen getallen uit de data; ontbreekt een signaal, dan staat er "geen aanwijzing in de beschikbare gegevens". Bij *onvoldoende bewijs* worden geen hypotheses getoond.

## Advies

| Situatie | Soort | Actie | Omvang | Terugdraaicriterium |
|---|---|---|---|---|
| onvoldoende bewijs | `measurement` | Verzamel meer gegevens met cv-bedrijf voordat er iets wordt geconcludeerd. | — | n.v.t. |
| patroon (voorlopig of structureel) | `check` | Controleer welke circuits werkelijk open staan en of doorstroming beschikbaar is. | niet te onderbouwen | n.v.t. |

De regel adviseert nooit een instellingswijziging: eerst de onderscheidende controle of meting. Vervolgstap ("Daarna"): aanvoerverlaging alleen overwegen met een comfortgrens per ruimte (advieshistorie v1.3).

Voorbeeld (UI): *Waarneming:* "In 24 van 30 cv-cycli stopt de brander binnen 3 minuten terwijl de warmtevraag blijft bestaan …". *Interpretatie:* "Dit past bij onvoldoende warmteafgifte ten opzichte van het geleverde vermogen, maar bewijst de oorzaak niet." *Advies:* "Controleer welke circuits werkelijk open staan en of doorstroming beschikbaar is."

## Herstel

Het patroon is voorbij als in de beoordelingsperiode minder dan `min_short_cycles` korte cycli voorkomen bij voldoende observatieduur. Een datagat of te weinig observatie telt nooit als herstel.

## Wijzigingen

### 1.0.0 — 2026-10-05

- Eerste versie.
