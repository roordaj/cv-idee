# `<regel-id>` — <korte titel>

<!--
Sjabloon voor de documentatie van een detectieregel (ADR-004 §7).
Kopieer naar docs/regels/<regel-id>.md. De test `test_every_registered_rule_is_documented`
controleert dat elke geregistreerde regel een bestand heeft met alle secties hieronder en
een wijzigingsregel `### <huidige versie>`.
-->

- **Id:** `<regel-id>` · **Huidige versie:** 1.0.0 · **Categorie:** `<Category>` (UI: "<Dutch label>")
- **Code:** `backend/src/cvidee/rules/<module>.py` · **Issue:** #<n>
- **Requirements:** FR-..

## Doel

Welk patroon detecteert de regel, in één of twee zinnen, en waarom is het relevant (energie, comfort, bedrijfsstabiliteit)? Wat detecteert de regel uitdrukkelijk **niet**?

## Toepasbaarheid

| Aspect | Waarde |
|---|---|
| Bedrijfsmodi (`applies_in_modes`) | bv. alleen `ch`; tapwater (`dhw`) en naloop uitgesloten |
| Installatie (`applies_to`) | bv. altijd / niet bij alleen mengverdeler / alleen met directe radiatorkring |
| Bijzondere perioden | standaard uitgesloten (FR-10); afwijkingen hier motiveren |
| Beoordelingsperiode (`history_ms`) | bv. laatste 7 dagen (parameter `window_days`) |
| Scope-sleutel (`scope_key`) | bv. `boiler:ch` — één bevinding per … |
| Bundelen (`supports`) | bv. ondersteunt `kort-branden` |

## Signalen

| Rol | Verplicht / optioneel | Gebruik | Effect als het ontbreekt |
|---|---|---|---|
| `flame` | verplicht | starts, brandduur | regel niet beschikbaar |
| `heat_demand` | optioneel | stop tijdens vraag | beperkt; zekerheid één stap lager; hypothese X niet te onderscheiden |

**Resolutie (`resolution_limits`):** bv. vlamstatus ≤ kortecyclusgrens ÷ 4 → anders beperkt; > ÷ 2 → niet beschikbaar.

## Parameters

| Veld (`params_schema`) | Label (UI) | Standaard | Eenheid · stap | Bereik | `x-group` |
|---|---|---|---|---|---|
| `short_cycle_min` | Kortecyclusgrens | 3 | min · 0,5 | 1 – 15 | `short_cycles` |

Kruisvalidaties: …

## Zekerheid

Criteria-sjabloon (ADR-004 §5). Lege cel = niet van toepassing. Ontbrekende optionele signalen verlagen de zekerheid één stap (niet onder *matig*).

| Niveau | Dekking kernsignalen | Relevante cycli | Waargenomen uren | Herhaling (dagen) | Overig |
|---|---|---|---|---|---|
| minimum (anders *onvoldoende bewijs*) | ≥ 80 % | ≥ 6 | ≥ 6 u | | |
| structureel (anders *voorlopig*) | | | | ≥ 2 van 7 | |
| *redelijk* | ≥ 90 % | ≥ 12 | | ≥ 3 | |
| *hoog* | ≥ 95 % | ≥ 30 | | ≥ 5 | |
| *hoog (gemeten)* | alleen als `allow_measured` en de kandidaat een directe meting is | | | | |
| plafond (`max_certainty`) | bv. *redelijk* voor correlaties | | | | |

Wat telt als "relevante cyclus" en wat als "dekking" voor deze regel: …

## Hypotheses

| Hypothese | Aanwijzing (vóór) | Ontbreekt / tegen | Onderscheidende meting | Signalen die helpen |
|---|---|---|---|---|
| … | … | … | … | `valve_state` |

Wanneer wordt een hypothese weggelaten of anders geformuleerd (afhankelijk van beschikbare signalen en het installatieprofiel)?

## Advies

Per situatie het advies in het formaat van requirements §5 (`RecommendationDraft`):

| Situatie | Soort | Actie | Omvang | Terugdraaicriterium |
|---|---|---|---|---|
| onvoldoende bewijs | `measurement` | Aanvullende meting: … | — | n.v.t. |
| patroon, oorzaak onbekend | `check` | Controleer eerst … | niet te onderbouwen | n.v.t. |
| patroon, oorzaak onderbouwd | `setting_change` | … (alleen bij zekerheid ≥ *matig*) | alleen met onderbouwing | verplicht |

Voorbeeldteksten (observatie / interpretatie / advies) zoals ze in de UI verschijnen: …

## Herstel

Wanneer is het patroon voorbij (input voor het herstelcriterium van de bevindingen-engine, #34)? Een datagat telt nooit als herstel.

## Wijzigingen

Nieuwste bovenaan. Versiebeleid: ADR-004 §7 (patch = geen uitkomstwijziging, minor = uitkomst kan veranderen met compatibele parameters, major = parameters of scope-sleutel incompatibel).

### 1.0.0 — JJJJ-MM-DD

- Eerste versie.
