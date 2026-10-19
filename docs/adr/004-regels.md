# ADR-004 — Regelengine, zekerheidsmodel en beschikbaarheid

- Status: voorgesteld
- Datum: 4 oktober 2026
- Issue: #10 · Requirements: FR-04, FR-14, FR-21–FR-24, FR-25, FR-28, FR-41 (+ §3 sensorleeftijd/resolutie, §4 "geen universele norm", §5 informatieformaat)
- Technisch plan: §2.1, §3.4–§3.7
- Code: `backend/src/cvidee/rules/` — `base.py` (protocol en types), `certainty.py`, `availability.py`, `registry.py`, `example.py` (voorbeeldregel `voorbeeld-cycli`); tests in `backend/tests/rules/`; regeldocumentatie `docs/regels/<id>.md` (sjabloon `docs/regels/_template.md`)

## 1. Context

Alle bevindingen en adviezen komen uit detectieregels. Zonder één contract zouden de MVP-regels (#30 `kort-branden`, #31 `stop-tijdens-vraag`, #32 `dataverlies`/`sensor-verouderd`/`tapwater-uitgesloten`, #33 `hydraulisch`, #39 `voor-na`), de bevindingen-engine (#34–#37), de beschikbaarheid (#25) en de instellingen (#22, #51) elk een eigen vorm kiezen. Dit ADR legt vast:

- wat een regel is (protocol) en wat zij mag lezen (`RuleContext`);
- wat zij oplevert (`FindingCandidate` met observatie / interpretatie / advies gescheiden, hypotheses, onderbouwing, bewijsverwijzingen, scope-sleutel, bundelrelatie, `RecommendationDraft`);
- het zekerheidsmodel: zes categorieën, een criteria-sjabloon dat iedere regel invult en een deterministische afleiding — **geen percentages** (FR-22);
- de beschikbaarheidsfunctie per analyse en per regel (FR-04), inclusief resolutiecheck;
- regelregister, semver, changelog-formaat `docs/regels/<id>.md`;
- parameters: pydantic-model → JSON-schema met `x-*`-extensies voor de instellingen-UI, opslag/validatie in `settings`, en de snapshot voor advieshistorie (FR-41).

Uitgangspunten uit het plan (§2.1): observatie ≠ interpretatie ≠ advies; versiebeheerde regels; geen verzonnen getallen. Uit ADR-002: regels draaien ná de pipeline op opgeslagen afgeleide data, zijn puur en kennen geen klok.

## 2. Besluit in het kort

1. **Puur en los van opslag.** Een regel is een object met `evaluate(ctx, params) -> Sequence[FindingCandidate]`. `RuleContext` is een immutable dataclass die de runner vult uit de store; `cvidee.rules` importeert geen SQLAlchemy en doet geen I/O. `now` is een veld van de context.
2. **Kandidaat, geen bevinding.** Regels leveren `FindingCandidate`s. Menselijke id's (B-014), status, `first_seen`/`last_seen`, dedupe, bundelen, prioriteren en herstel horen bij de bevindingen-engine (#34/#35).
3. **Zekerheid = categorie uit een criteria-sjabloon.** `derive_certainty(evidence, criteria, measured=…)` geeft een `Certainty` plus reden-codes. Iedere regel vult `CertaintyCriteria` in en documenteert die tabel in `docs/regels/<id>.md`.
4. **FR-28 in het type afgedwongen.** Een kandidaat met `insufficient_evidence` moet een advies van soort `measurement` hebben; een `setting_change` kan niet bij `insufficient_evidence` of `preliminary` en vereist altijd een terugdraaicriterium.
5. **Beschikbaarheid is één pure functie** op een `SignalRequirement` (verplicht, één-van, optioneel, resolutielimieten), de status van de gekoppelde signalen en het installatieprofiel. Dezelfde functie bepaalt de analyse-tabel (Cycli … Rendement) en of een regel wordt geëvalueerd.
6. **Registry + semver.** Regel-id's zijn de kebab-case id's uit ontwerp v3 (`kort-branden`); versies zijn `MAJOR.MINOR.PATCH`, in de UI als `v1.3`. Elke productieregel heeft `docs/regels/<id>.md` met een wijzigingsregel voor de huidige versie (test).
7. **Parameters zijn een pydantic-model per regel**; het JSON-schema (met `x-unit`, `x-step`, `x-group`, `x-rule`) is de enige bron voor de instellingen-UI. Opslag als JSON-object per regel in `settings`; strikt valideren bij opslaan, mild laden bij lezen.
8. **Snapshot** = `(rule_id, version, params_json canoniek, params_hash)`; runs, bevindingen en advies-snapshots slaan dit op (FR-41).

### Taal van identifiers

Conform AGENTS.md zijn identifiers en enum-waarden Engels. Het plan noemt de zekerheidscategorieën in het Nederlands (`onvoldoende_bewijs` … `hoog_gemeten`); in code en API heten ze zoals in §5.1. Uitzondering: **regel-id's** zijn UI-tekst uit het ontwerp (`kort-branden v1.3`) en blijven Nederlands kebab-case, net als de HA-entiteit-id's. Teksten die een regel in een kandidaat zet (titel, observatie, interpretatie, hypotheses, advies) zijn Nederlandse UI-tekst (nl-NL getalnotatie). Beschikbaarheid en zekerheidsredenen zijn gestructureerde codes; de API/UI maakt er Nederlandse zinnen van.

## 3. `RuleContext` — wat een regel mag lezen

De runner (#27) bouwt per evaluatie één context over de beoordelingsperiode van de regel (`history_ms(params)` vóór `now`). Alle collecties zijn tuples, gesorteerd op start (determinisme: regels mogen niet van invoervolgorde afhangen).

| Veld / methode | Inhoud | Bron |
|---|---|---|
| `now` | tijdstip van de evaluatie (UTC-ms); nooit de systeemklok | runner |
| `period` | `TimeRange` van de beoordeling, eindigt op de horizon | runner |
| `profile: InstallationFacts` | ketel­specificaties (elk `None` = onbekend, FR-03), circuits (`direct` / `mixing_manifold` met verdeler), ruimtes, zones, profielversie | #20 |
| `signals: tuple[SignalStatus]` | per **gekoppeld** signaal: dekking over de periode, `stale`, werkelijke resolutie | #18, #23, #25 |
| `availability` / `availability_of(analysis)` | uitkomst van §6 per analyse | §6 |
| `cycles` | `BurnerCycle`s (ADR-002) in de periode | #26 |
| `mode_segments` | `ModeSegment`s | #24 |
| `metrics` / `metrics_named(name, mode)` | opgeslagen `MetricValue`s (uur, dag, periode) met tijdsbasis en dekking | #28, #29 |
| `quality_events` / `quality_events_of(*kinds)` | kwaliteitsgebeurtenissen | #23 |
| `special_periods` | `SpecialPeriod(range, kind, excluded)` (FR-10) | #21 |
| `timelines` / `timeline(signal, rng)` | lui geladen `SignalTimeline` (een week ruwe tijdlijn past niet in een dataclass); `TimelineSource`-protocol, in tests `StaticTimelines` | runner/store |
| `config_hash` | config-snapshot van de run (ADR-002) | runner |
| `tz` / `local_days(rng)` | `Europe/Amsterdam`-kalenderdagen als UTC-bereiken (23/25 u op DST-dagen) voor "herhaling over dagen" | — |

Hulpmethoden:

- `relevant_cycles(modes={CH}, rng)` — cycli waarvan de start in `rng` ligt, in de gevraagde modi, en die **geen uitgesloten bijzondere periode overlappen**. Tapwater valt zo standaard af (FR-14, scenario 4); opstookprotocol e.d. ook (FR-10, scenario 9).
- `excluded_cycles(...)` — wat daardoor is weggelaten, voor "· 1 tapwatercyclus uitgesloten".
- `excluded_ranges(rng)`, `is_excluded(rng)` — uitgesloten tijd (onderdeel van de onderbouwing, FR-11).
- `signal_status(ref)`, `is_mapped(ref)`, `unmapped(refs)` — voor `missing_signals`.

Niet in de context (bewust): wijzigingslogboek en voor/na-evaluaties (komen erbij met #38/#39 als extra veld), andere bevindingen (regels zijn onafhankelijk; samenhang loopt via `supports`, §4.4), meldingsbeleid.

### 3.1 Uitsluitingen

Standaard gelden: tapwatercycli en naloop tellen niet in CV-conclusies; uitgesloten bijzondere perioden tellen niet in normaalgedrag. Een regel die hiervan afwijkt (bv. `tapwater-uitgesloten` kijkt juist naar tapwater; `dataverlies` kijkt ook in gemarkeerde perioden) zegt dat in de sectie *Toepasbaarheid* van zijn regeldocument. Uitgesloten tijd en cycli staan in `EvidenceSummary.excluded_ms` / `excluded_cycles`.

## 4. Regelprotocol en uitvoer

### 4.1 `Rule`

```python
class Rule(Protocol):
    id: str                                # "kort-branden" (kebab-case, nooit wijzigen)
    version: str                           # "1.3.0" (semver, §7)
    category: Category                     # cycles, temperature, data_quality, effect_measurement, …
    required_signals: frozenset[Role]      # ontbreekt → regel niet beschikbaar
    optional_signals: frozenset[Role]      # ontbreekt → beperkt, zekerheid lager
    applies_in_modes: frozenset[Mode]      # bv. {CH}
    params_schema: type[RuleParams]        # pydantic, §8
    def applies_to(self, profile: InstallationFacts) -> bool          # installatiepredicaat
    def resolution_limits(self, params) -> tuple[ResolutionLimit, ...] # §6.3
    def history_ms(self, params) -> DurationMs                        # benodigde periode
    def certainty_criteria(self, params) -> CertaintyCriteria         # §5.2
    def evaluate(self, ctx: RuleContext, params) -> Sequence[FindingCandidate]
```

(In code als read-only properties in een `Protocol`; `BaseRule[P]` is een basisklasse met getypeerde parameters.) `applies_to` is een methode in plaats van een los predicaat-object: zo blijft het protocol structureel en testbaar, en kan een regel ook op specificaties beslissen ("minimumvermogen onbekend → hypothese 3 zonder getal").

`RuleRegistry.evaluate(rule_id, ctx, params)` voert per regel uit: (1) `applies_to(profile)` onwaar → niet van toepassing, geen kandidaten; (2) beschikbaarheid van de regel (§6) `unavailable` → niet geëvalueerd; (3) `evaluate`; (4) kandidaten gesorteerd op `(scope_key, period.start)`, maximaal één per `scope_key`, en een kandidaat mag niet zijn eigen regel `supports`en. Uitkomst: `RuleOutcome(snapshot, applicable, availability, candidates)`.

### 4.2 `FindingCandidate`

| Veld | Betekenis | Ontwerp v3 (B-014) |
|---|---|---|
| `scope_key` | dedupesleutel binnen de regel; nooit een tijdstip. Dedupe = `(rule_id, scope_key)` (FR-39) | `boiler:ch` |
| `category`, `title` | categorie en titel | Cycli · "Herhaald kort branden …" |
| `severity` | `high` / `medium` / `low` / `info` (ernst) | Hoog |
| `certainty` | §5 | Matig |
| `relevance` | `energy` / `comfort` / `operational_stability` / `data_reliability`; verplicht behalve bij `info` | bedrijfsstabiliteit, energie |
| `observation` | **alleen** meetwaarden en tijdvak (FR-21) | "In 18 van 24 cv-cycli stopt …" |
| `period`, `signals` | tijdvak en gebruikte signalen | Zo 4 okt 06:00–10:10; vlamstatus, … |
| `interpretation` | wat het kan betekenen; claimt geen oorzaak als bewezen (FR-16) | "Dit past bij …, maar bewijst de oorzaak niet." |
| `hypotheses` | `Hypothesis`-lijst (§4.3) | 3 verklaringen |
| `recommendation` | `RecommendationDraft` of `None` | "Controleer welke circuits …" |
| `no_advice_reason` | verplicht als er geen advies is | B-015/B-016 |
| `evidence: EvidenceSummary` | onderbouwing (§4.5) | dekking, relevante cycli, herhaling, ontbreekt |
| `refs: tuple[EvidenceRef]` | verwijzingen naar data (FR-37) | cycli in de tijdlijn |
| `supports: tuple[str]` | regel-id's waaronder deze kandidaat gebundeld kan worden (FR-26) | stop-tijdens-vraag → kort-branden |

Rule-id en -versie zitten niet in de kandidaat; die voegt de registry toe via de snapshot (geen dubbele bron).

### 4.3 `Hypothesis`

`name`, `evidence_for` (aanwijzing), `missing` (wat ontbreekt of ertegen pleit — ontwerp: "Ontbreekt"), `distinguishing_measurement` (onderscheidende meting), en `signals_needed: tuple[Role]` zodat de UI naar "signaal koppelen" kan linken. Een regel mag hypotheses weglaten of anders formuleren afhankelijk van beschikbare signalen en profiel (FR-23/24); dat staat in zijn regeldocument.

### 4.4 Bundelrelatie

Een kandidaat noemt in `supports` de regels waaronder hij als onderbouwing past. De bundelregel van de engine (#35) koppelt kandidaten met overlappend `period` en compatibele scope aan een kandidaat van de genoemde regel; de oorspronkelijke kandidaten blijven als onderbouwing zichtbaar ("Samengevoegd tot één punt"). Zo kent de regel alleen de *relatie*, niet de andere kandidaat, en blijft evaluatie per regel onafhankelijk.

### 4.5 Onderbouwing en bewijsverwijzingen

`EvidenceSummary` (onderbouwing, FR-22) bevat precies de feiten waaruit de zekerheid volgt: `coverage` (bekend deel van de relevante tijd voor de kernsignalen), `unknown_ms`, `excluded_ms`, `excluded_cycles`, `relevant_cycles` (noemer, "van 24 cv-cycli"), `pattern_cycles` (teller), `observed_hours`, `repetition_days` / `repetition_window_days` ("3 van laatste 7 dagen"), `missing_signals` (gesorteerd; optionele signalen die zouden onderscheiden of versterken). De UI toont deze vier blokken uit ontwerp v3 direct hieruit.

`EvidenceRef` is een unie van `CycleRef(cycle_start)`, `PeriodRef(range, label)`, `SignalEvidence(signal, range, assumed_unchanged)`, `MetricRef(name, window_start, mode)` en `QualityEventRef(kind, start, signal)` — telkens de deterministische sleutels uit ADR-002, zodat `finding_evidence` (#7) ze kan opslaan en de UI het tijdvak/de cycli kan openen (FR-37). `assumed_unchanged` markeert combinaties met `Alignment.ASSUMED_UNCHANGED` (ADR-002 §7).

### 4.6 `RecommendationDraft` (requirements §5, FR-25)

| §5-element | Bron |
|---|---|
| Titel, relevantie | `FindingCandidate.title`, `.relevance` |
| Waargenomen patroon, periode, signalen | `.observation`, `.period`, `.signals` |
| Verklaringen, aanwijzingen vóór/tegen, zekerheid | `.interpretation`, `.hypotheses`, `.certainty` |
| Concrete eerste actie of aanvullende meting | `kind` (`setting_change` / `check` / `measurement` / `revert`) + `action` |
| Verwacht effect, invloed op comfort | `expected_effect`, `comfort_impact` |
| Wijzigingsomvang | `magnitude`; `None` ⇒ UI-tekst "Niet te onderbouwen met huidige gegevens — geen getal genoemd." |
| Evaluatieperiode, voorwaarden vergelijkbaarheid | `evaluation`, `evaluation_days`, `conditions` |
| Succes-, terugdraaicriterium | `success_criterion`, `rollback_criterion` (`None` ⇒ "N.v.t."; verplicht bij `setting_change`) |
| Opvolgstatus | niet in het concept: de engine (#36) start op `open` |
| (extra) | `reason`; `parameter` (koppeling met wijzigingslogboek, FR-29); `follow_up` ("Daarna", B-011) |

Opslag (ADR-001, `recommendations`): `kind == measurement` ⇒ `is_additional_measurement`; `magnitude is None` ⇒ `magnitude_substantiated = false`; de overige velden 1-op-1.

Validaties in het type: `setting_change` zonder terugdraaicriterium is ongeldig; `setting_change` bij `insufficient_evidence` of `preliminary` is ongeldig; `insufficient_evidence` vereist een advies van soort `measurement` (FR-28, scenario 10).

## 5. Zekerheidsmodel (FR-22, FR-28)

### 5.1 Categorieën

Geordend van zwak naar sterk. Geen percentage, nergens.

| Code | Plan / UI | Betekenis | Gevolg |
|---|---|---|---|
| `insufficient_evidence` | onvoldoende_bewijs · "Onvoldoende bewijs" | het minimum (dekking, relevante cycli, waargenomen uren) is niet gehaald, of een onmisbaar gegeven ontbreekt | geen diagnose; advies is altijd een aanvullende meting |
| `preliminary` | voorlopig · "Voorlopig" | minimum gehaald, maar het patroon is (nog) niet op genoeg dagen gezien | getoond als voorlopig; geen instellingsadvies |
| `moderate` | matig · "Matig" | structureel patroon, net boven het minimum, of lager door ontbrekende signalen | controle/meting of voorzichtig advies |
| `reasonable` | redelijk · "Redelijk" | ruime dekking en voldoende cycli/herhaling | advies mogelijk met voorwaarden |
| `high` | hoog · "Hoog" | alle *hoog*-drempels gehaald, geen relevante signalen ontbreken | — |
| `high_measured` | hoog_gemeten · "Hoog (gemeten)" | als *hoog*, en de bevinding is een directe meting zonder interpretatiestap (bv. de app zag de verbinding zelf wegvallen) | alleen voor regels met `allow_measured` |

### 5.2 Criteria-sjabloon

Iedere regel vult `CertaintyCriteria` in (en dezelfde tabel in zijn regeldocument):

| Rij | Velden (`Thresholds`) | Niet gehaald ⇒ |
|---|---|---|
| `minimum` | `coverage`, `relevant_cycles`, `observed_hours`, `repetition_days` | `insufficient_evidence` |
| `structural_repetition_days` van `repetition_window_days` | aantal dagen met het patroon binnen het venster | `preliminary` |
| `reasonable` | idem | blijft `moderate` |
| `high` | idem | blijft `reasonable` |
| `allow_measured` | regel mag `high_measured` geven voor kandidaten met `measured=True` | blijft `high` |
| `max_certainty` | plafond, bv. `reasonable` voor regels die alleen correleren (FR-18) | — |

Een veld `None` doet niet mee. Een rij `None` (`reasonable`/`high`) betekent "niveau niet bereikbaar"; een rij `Thresholds()` betekent "bereikt zodra de rij erboven gehaald is". **Een onbekende waarde in de onderbouwing (`None`) haalt een drempel nooit** — onbekend is geen "genoeg".

### 5.3 Afleiding (`derive_certainty`)

1. Een `minimum`-drempel niet gehaald → `insufficient_evidence` (reden-codes per drempel).
2. `repetition_days < structural_repetition_days` → `preliminary` (`not_structural`).
3. Start op `moderate`; `reasonable` gehaald → `reasonable`; daarbovenop `high` gehaald → `high`; `measured` én `allow_measured` → `high_measured`.
4. **Ontbrekende signalen verlagen één stap**: `missing_signals` niet leeg → één stap lager, één keer (ongeacht het aantal), en nooit onder `moderate` — *voorlopig* en *onvoldoende bewijs* gaan over de hoeveelheid data, niet over welke signalen er zijn.
5. Plafond `max_certainty`.

De uitkomst bevat reden-codes (`below_min_coverage`, `not_structural`, `reasonable_met`, `lowered_for_missing_signals`, `capped`, …) zodat de UI kan uitleggen waarom ("Matig: redelijk, één stap lager omdat zoneklep, verdeler en pomp ontbreken"). De afleiding is monotoon: meer dekking, cycli of herhaling geeft nooit een zwakkere categorie (property-test).

### 5.4 Ijkpunten uit ontwerp v3

| Bevinding | Onderbouwing | Uitkomst |
|---|---|---|
| B-014 `kort-branden` | 93 % dekking, 24 relevante cycli, 3 van 7 dagen; zoneklep/verdeler/pomp ontbreken | criteria van #30 geven *redelijk*, −1 voor ontbrekende signalen → **Matig** (test `test_design_b014_is_moderate`) |
| B-015 `dataverlies` | de app mat de onderbreking zelf; `allow_measured`, `measured=True` | **Hoog (gemeten)** |
| B-012 `hydraulisch` | verdelersignalen ontbreken; minimum niet haalbaar | **Onvoldoende bewijs** + advies `measurement` "plaats temperatuursensoren op verdeleraanvoer en -retour" |
| B-016 `tapwater-uitgesloten` | modus direct gerapporteerd, 100 % dekking, interpretatie "uitgesloten" | **Hoog** (`info`, geen advies) |
| B-011 `voor-na` | 97 % dekking beide perioden, vergelijkbaar weer; plafond *redelijk* tot weerscorrectie (#59) | **Redelijk** |

## 6. Beschikbaarheid (FR-04)

### 6.1 Functie

```python
assess(requirement: SignalRequirement, signals: Iterable[SignalStatus],
       profile: InstallationFacts, policy: AvailabilityPolicy) -> Availability
assess_analyses(signals, profile, policy) -> tuple[AnalysisAvailability, ...]
```

`Availability = (status ∈ {available, limited, unavailable}, issues)`; een `AvailabilityIssue` is `(kind, role, scope_key, required)` met `kind ∈ {not_mapped, no_data, low_coverage, stale, resolution, resolution_unknown, no_scope_in_profile}`. `missing_required` en `missing_signals` geven de `SignalRef`s voor "Ontbreekt: …". Teksten maakt de API (#25).

Per rol:

| Situatie | Verplicht | Optioneel |
|---|---|---|
| niet gekoppeld (`not_mapped`) of gekoppeld zonder enige data (`no_data`) | `unavailable` | `limited` |
| dekking < `policy.min_coverage` (standaard 80 %, instelling "Minimale dekking voor een beoordeling") | `limited` | `limited` |
| nu verouderd (`stale`) | `limited` | `limited` |

Rollen per ruimte/zone/verdeler gelden voor **elke** entiteit uit het profiel (plus elke gekoppelde): een deel ontbreekt → `limited`; alle ontbreken → zoals in de tabel; profiel heeft er geen → `no_scope_in_profile`. `AnyOf`-groepen (bv. "warmtevraag óf gewenste aanvoer") zijn gehaald zodra één alternatief (een set rollen die samen nodig zijn) beschikbaar is; anders telt het beste alternatief en worden de problemen van **alle** alternatieven gemeld ("Ontbreekt: verdeleraanvoer, -retour, debiet"). Eindstatus = slechtste van alle onderdelen. De functie hangt niet af van invoervolgorde.

### 6.2 Tabel per analyse

| Analyse (`AnalysisId`) | Verplicht | Eén van (verplicht) | Optioneel | Resolutie |
|---|---|---|---|---|
| Cycli (`cycles`) | `flame` | — | `operating_mode`; één van `heat_demand` / `flow_setpoint` | `flame` ≤ gewenste meetresolutie (10 s) → anders `limited` |
| Temperatuur (`temperature`) | `flame`, `flow_temperature`, `flow_setpoint` | — | `return_temperature`, `operating_mode` | — |
| Bedrijfsmodus (`operating_mode`) | — | `operating_mode` / `flame` | `operating_mode` (zonder: afgeleid, beperkte zekerheid, FR-09) | — |
| Comfort (`comfort`) | `room_temperature`, `room_setpoint` per ruimte | — | `outdoor_temperature` | — |
| Zones (`zones`) | `flame` | `zone_demand` / `valve_state` per zone | — | — |
| Hydraulisch (`hydraulic`) | `flow_temperature`, `return_temperature` | — | (`manifold_flow_temperature` + `manifold_return_temperature` per verdeler) / lokaal circuit-`flow_rate`; `pump_state` | — |
| Verbruik (`consumption`) | `gas_cumulative` | — | `outdoor_temperature` (weerscorrectie) | — |
| Rendement (`efficiency`) | `gas_cumulative`, `heat_meter` | — | — | — |

Gevolgen, getest: zonder gasmeter blijft Cycli `available` en is Verbruik `unavailable` met ontbrekend `gas_cumulative@boiler` (FR-04-acceptatie); Rendement alleen met gas **én** warmtemeter; zonder modussignaal zijn Cycli en Bedrijfsmodus `limited`; een verouderde slaapkamersensor maakt Comfort `limited` (ontwerp v3). Correctie #130: met keteltemperaturen maar zonder bruikbare lokale verdelerdata is Hydraulisch `limited` (scenario 6), met expliciete ontbrekende signalen. Zonder benodigde keteltemperaturen blijft die analyse `unavailable`. De afzonderlijke informatiewaarschuwing over ontbrekende lokale data kan wel draaien en geeft uitsluitend meetadvies; beperkte beschikbaarheid heft de diagnosegrens niet op.

### 6.3 Resolutiecheck

`ResolutionLimit(role, max_interval_ms, on_exceed)` vergelijkt de **werkelijke** resolutie (`SignalStatus.resolution_ms`, bepaald door #25 — bv. mediane rapportage-interval van de CAN-gateway) met een grens. Overschreden → `on_exceed` (`limited` of `unavailable`); resolutie nog niet bepaald → `limited` met `resolution_unknown` (geen aanname dat het wel goed zit). De analyse-tabel gebruikt de instelling "Gewenste meetresolutie vlamstatus"; een regel legt eigen grenzen op via `resolution_limits(params)`, bv. `kort-branden`: vlamresolutie > kortecyclusgrens ÷ 4 → `limited`, > ÷ 2 → `unavailable` (FR-11 §3: korte-cycli-analyse alleen als de resolutie de ingestelde grens kan onderscheiden).

### 6.4 Per regel

`rule_requirement(rule, params)` = verplichte en optionele rollen van de regel + `resolution_limits(params)`. De registry evalueert een regel niet als die `unavailable` is; bij `limited` wel, en de regel zet de ontbrekende optionele signalen in `missing_signals` (wat de zekerheid één stap verlaagt, §5.3).

## 7. Regelregister, versies en documentatie

- **Register.** `RuleRegistry(rules)` valideert id (kebab-case), versie (semver), geen rol tegelijk verplicht en optioneel, en unieke id's; iteratie in id-volgorde. `default_registry()` is de productielijst (leeg tot #30–#33/#39); de voorbeeldregel `voorbeeld-cycli` staat er bewust niet in. `versions()` gaat naar `analysis_runs`.
- **Semver.**
  - *patch*: geen verandering in uitkomst (tekstcorrectie, refactor, documentatie);
  - *minor*: uitkomst kan veranderen bij compatibele parameters (drempel-standaardwaarde, zekerheidscriteria, nieuwe hypothese, aangepaste adviestekst, nieuwe optionele parameter);
  - *major*: parameters incompatibel (veld hernoemd/verwijderd/eenheid gewijzigd) of de betekenis van `scope_key` verandert (dedupe breekt: bestaande bevindingen worden gesloten met reden "regel gewijzigd", nieuwe beginnen).
  De UI toont `v{major}.{minor}` (`display_version`). Elke versie-ophoging die de uitkomst kan veranderen, triggert herberekening zoals een configuratiewijziging (ADR-002 §4.6).
- **Documentatie.** Elke regel heeft `docs/regels/<id>.md` volgens `docs/regels/_template.md`: Doel, Toepasbaarheid, Signalen, Parameters, Zekerheid (de criteria-tabel van §5.2), Hypotheses, Advies, Herstel, Wijzigingen. De changelog staat onderaan, nieuwste eerst, als `### 1.3.0 — 2026-09-24` met opsomming. De test `test_every_registered_rule_is_documented` faalt als een geregistreerde regel geen document of geen regel voor zijn huidige versie heeft. De Advieshistorie ("Sindsdien: …", ontwerp v3) toont de changelog-items tussen de vastgelegde en de huidige versie.

## 8. Parameters

### 8.1 Schema

Per regel één `RuleParams`-subklasse (pydantic, `frozen`, `extra="forbid"`). Velden via `param(default, title=, description=, unit=, step=, ge=, le=, group=)`:

- `title`, `description` — Nederlandse UI-tekst (label en uitleg uit aanvullingen §1.5);
- `ge`/`le` → `minimum`/`maximum`, `default` → standaardwaarde;
- `json_schema_extra`: `x-unit` (bv. `min`, `s`, `cycli`, `dagen`, `%`), `x-step`, `x-group` (`short_cycles`, `comfort`, `effect_measurement`, `data`, `recovery`, `costs`, `display` = de secties van het instellingenscherm);
- de registry voegt `x-rule` (op elke property en op de wortel) en `x-rule-version` toe ("Standaard 3 min · gebruikt door kort-branden v1.3");
- kruisvalidaties als pydantic `model_validator` (bv. herhaling *x ≤ y*).

**Eenheden.** Waarden worden opgeslagen in de eenheid die de UI toont; de veldnaam draagt de eenheid als achtervoegsel (`short_cycle_min`, `heat_demand_after_stop_s`, `min_coverage_pct`) en de regel rekent zelf om naar ms. Zo is wat de gebruiker ziet exact wat in de snapshot staat.

`RuleRegistry.settings_schema()` geeft `{"rules": {rule_id: schema}}`; #22 voegt daar de algemene instellingen (sensorleeftijd per rol, gewenste resolutie, gasprijs, herstel) aan toe in hetzelfde `x-*`-formaat. Parameters die door meerdere regels of door de pipeline worden gebruikt (bv. "Warmtevraag na stop" = `end_reason_lookahead_ms` van ADR-002) zijn algemene instellingen, geen regelparameter.

### 8.2 Opslag en validatie

- Opslag in `settings` als één JSON-object per regel, sleutel `rules.<rule_id>`; alleen afwijkingen van de standaard hoeven bewaard (ontbrekend = standaard).
- **Opslaan** (`PUT /api/settings`, #22): `validate_params` — strikt: onbekende sleutel, waarde buiten bereik of mislukte kruisvalidatie → `ValidationError` → 422 met veldfouten.
- **Laden** (runner): `load_stored` — mild: onbekende sleutels (bv. na een major-versie) en niet meer geldige waarden vallen terug op de standaard en worden gemeld in `dropped` (logregel + kwaliteitsmelding in de UI). De analyse stopt nooit op een verouderde instelling.

### 8.3 Snapshot (FR-41)

`RuleRegistry.snapshot(rule_id, params)` → `RuleSnapshot(rule_id, version, params_json, params_hash)`, met `params_json` canoniek (gesorteerde sleutels, geen witruimte, standaardwaarden inbegrepen) en `params_hash = sha256(params_json)`. `rule_set_hash(snapshots)` is het regel-deel van de config-hash (#22, #27).

| Waar | Wat wordt vastgelegd |
|---|---|
| `analysis_runs` (#27) | `versions()` + `rule_set_hash` als onderdeel van `config_hash` |
| bevinding (#34) | `rule_id`, `version`, `params_hash` van de laatste kandidaat |
| `recommendation_snapshots` (#37) | volledige `RuleSnapshot` (incl. `params_json`), meetperiode (`period`), profielversie (`InstallationFacts.version`), `config_hash` — bij aanmaken en bij elke statuswijziging |

Daarmee kan de gebruiker later zien "Kortecyclusgrens 3 min · min. 4 korte cycli" en, via de changelog, wat er sindsdien aan de regel veranderde — ook als de regel intussen een nieuwe major-versie heeft.

## 9. Gevolgen voor andere tickets

- **#25** implementeert de API-notities op `assess_analyses`, en bepaalt `SignalStatus.resolution_ms`/`coverage`/`stale` uit de opgeslagen data (ADR-003 voor `stale`).
- **#30–#33, #39** implementeren regels als `BaseRule[P]`-subklassen, met `docs/regels/<id>.md` en een registratie in `default_registry()`.
- **#34/#35** gebruiken `(rule_id, scope_key)` als dedupesleutel, `supports` voor bundelen, `EvidenceSummary` voor de onderbouwing en `EvidenceRef` voor `finding_evidence`.
- **Store (ADR-001, #7)**: `cvidee.rules` hangt niet van de store af; de store mapt. Concreet:
  - `findings.support` krijgt de vorm van `EvidenceSummary` (dit ADR maakt die definitief): `coverage`, `unknown_ms`, `excluded_ms`, `excluded_cycles`, `relevant_cycles` (noemer, "van 24"), `pattern_cycles` (teller, "18"), `observed_hours`, `repetition_days`, `repetition_window_days`, `missing_signals` (als `str(SignalRef)`). Het voorlopige `total_cycles` uit ADR-001 heet hier `relevant_cycles`, en het daar genoemde `relevant_cycles` heet `pattern_cycles`.
  - `finding_evidence.kind`: `CycleRef` → `cycle`, `PeriodRef` → `time_range`, `SignalEvidence` → `signal`, `MetricRef` → `metric`, `QualityEventRef` → `quality_event`; `change` en `bundled_candidate` vult de engine (#35/#39).
  - `findings.rule_params` / `recommendation_snapshots.rule_params` = `RuleSnapshot.params_json`.
  - `Certainty`, `Severity`, `SpecialPeriodKind` en `CircuitKind` hebben dezelfde waarden als in `cvidee.store.enums`; `test_store_alignment.py` bewaakt dat.
- **#20/#21** leveren `InstallationFacts` en `SpecialPeriod` aan de runner.
- **#22/#51** renderen het instellingenscherm generiek uit `settings_schema()`.

## 10. Open vragen

1. **Plafond voor correlatieregels.** Voorstel: regels die alleen samenhang tonen (zones, FR-18; voor/na zonder weerscorrectie) krijgen `max_certainty = reasonable`. Bevestigen bij #39/#56.
2. **Ondergrens bij ontbrekende signalen.** Gekozen: niet onder *matig*. Alternatief: tot *voorlopig* laten zakken. Huidige keuze voorkomt dat "voorlopig" twee betekenissen krijgt.
3. **Onbekende resolutie = beperkt.** Conservatief: tot #25 de resolutie meet, is Cycli `limited`. Als dat in de praktijk te vaak "beperkt" geeft, kan #25 een standaardresolutie per integratie aannemen — maar dan zichtbaar.
4. **Zones met gemengde signalen** (de ene zone vraag, de andere alleen klepstatus) gelden nu als `limited`, omdat geen enkel alternatief alle zones dekt. Herzien in #56.
5. **Dubbele enums met de store.** `Certainty`, `Severity`, `SpecialPeriodKind`, `CircuitKind` bestaan nu in `cvidee.rules.base` én `cvidee.store.enums` (waarden gelijk, test bewaakt). Voorstel: de store re-exporteert ze uit `cvidee.rules.base`, zoals hij dat al doet voor `cvidee.analysis.types` (ADR-001 B7). Niet in deze PR om de store niet te raken.
6. **Regel-id-taal.** Gekozen voor Nederlandse kebab-case id's omdat ze in de UI staan; alternatief is Engelse id's met een apart label. Wijzigen kan alleen vóór de eerste release (id's zijn dedupesleutels).
7. **pydantic als directe afhankelijkheid.** `pydantic` komt nu transitief mee via FastAPI/pydantic-settings (zoals al in `cvidee.config`); bij de volgende wijziging van `pyproject.toml` expliciet opnemen.
