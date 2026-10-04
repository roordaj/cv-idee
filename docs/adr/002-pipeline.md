# ADR-002 — Analyse-pipeline: contract en determinisme

- Status: voorgesteld
- Datum: 4 oktober 2026
- Issue: #8 · Requirements: FR-06, FR-07, FR-08, FR-09, FR-11, FR-12, FR-13, FR-15, FR-16
- Technisch plan: §2.1, §3.1, §3.3, §3.4, §5
- Code: `backend/src/cvidee/analysis/` (`types.py`, stappen als stubs, `pipeline.py`), test-skelet `backend/tests/analysis/test_determinism.py`

## 1. Context

FR-06 eist dat live verwerking en een import van dezelfde historie **dezelfde cycli** opleveren. Het technisch plan kiest daarom voor één pure pipeline-functie die de runner herhaald aanroept over een schuivend venster. Dit ADR legt vast:

- de stappen, met invoer en uitvoer per stap;
- de types (`cvidee.analysis.types`) waarop de stappen werken;
- het venster/watermark-algoritme van de runner, inclusief wat er gebeurt met een cyclus die over een venstergrens loopt;
- waarom "in blokken verwerken == in één keer verwerken" geldt en onder welke voorwaarden;
- tijdzone/DST, samplingtolerantie bij het combineren van signalen, en hoe onbekende tijd doorwerkt.

Hiermee kunnen #23 (tijdlijn/kwaliteit), #24 (modi), #26 (cycli), #27 (runner), #28 (cyclusstatistieken) en #29 (temperatuur) parallel worden gebouwd. Het databaseschema (#7, ADR-001) slaat de hier gedefinieerde types op; de analyse-types zijn bewust onafhankelijk van SQLAlchemy. Veroudering bij alleen-bij-wijziging-events wordt in detail uitgewerkt in #9 (ADR-003); dit ADR legt alleen vast hoe de pipeline die uitkomst gebruikt.

## 2. Besluit in het kort

1. **Puur.** Elke stap is een pure functie op immutable dataclasses (`frozen=True, slots=True`, collecties als `tuple`). Geen I/O, geen klok: `now` is een parameter van `run_pipeline`. Uitvoer hangt niet af van invoervolgorde (stappen sorteren zelf op `Observation.sort_key`); sommen van floats in tijdsvolgorde met `math.fsum`.
2. **Tijd = UTC-milliseconden (`int`).** Geen `datetime` in de pipeline. `Europe/Amsterdam` alleen voor presentatie en voor lokale dagbuckets.
3. **Venster.** De runner draait elke minuut `run_pipeline` over `[emit_from − lookback, now − settle)` met `emit_from = floor_uur(watermark)`, `lookback` standaard 6 u, `settle` standaard 2 min.
4. **Replace-from upsert.** Alle afgeleide data heeft een deterministische sleutel. De runner verwijdert per run alle afgeleide rijen met sleutel `≥ emit_from` en voegt de uitvoer van de run in, in één transactie.
5. **Watermark** = `min(horizon − lookahead, start van de vroegste nog niet definitieve cyclus)`. Een open cyclus houdt het watermark dus vast; zij wordt elke run volledig opnieuw berekend tot ze definitief is.
6. **Canoniek raster.** Interval-uitvoer (modussegmenten, kwaliteitsgebeurtenissen) wordt gesplitst op hele UTC-uren. Lezers voegen aangrenzende stukken samen. Cycli worden nooit gesplitst.
7. **Onbekend ≠ uit.** Onbekende tijd heeft een reden, telt nergens als uit-tijd en zit nooit in een tijdsbasis.

## 3. Stappen, invoer en uitvoer

```
observations + connection_events (+ carry-in)          config-snapshot, window, now
        │
        ▼
1 timeline   build_timelines          → SignalTimeline per signaal
2 quality    apply_quality            → SignalTimeline (opgeschoond) + QualityEvent
3 modes      classify_modes           → ModeSegment (op raster)
4 cycles     detect_cycles            → BurnerCycle (+ fases, aggregaten, pauze)
5 metrics    hourly_cycle_metrics,    → MetricValue (uur-buckets, per cyclus)
             cycle_/hourly_temperature_metrics
        │  PipelineResult (alleen sleutels ≥ emit_from) + next_watermark
        ▼
runner: upsert → 6 rules (cvidee.rules, ADR-004) → findings
```

| Stap | Module / functie | Invoer | Uitvoer |
|---|---|---|---|
| 1 Timeline | `timeline.build_timelines`, `build_timeline`, `connection_outages`, `unknown_union` | `Observation[]` (+ carry-in per signaal), `ConnectionEvent[]` (+ carry-in per bron), `PipelineConfig.signals`, `AnalysisWindow` | `SignalTimeline` per geconfigureerd signaal: aaneengesloten `ValueInterval`/`UnknownInterval` over `[context_start, end)` |
| 2 Quality | `quality.apply_quality`, `detect_counter_resets`, `align_pair`, `pair_tolerance`, `coverage_by_signal` | tijdlijnen uit 1, plausibiliteitsgrenzen, tellerconfig | tijdlijnen waarin ongeldig/onwaarschijnlijk → onbekend; `QualityEvent[]`; dekking per signaal |
| 3 Modes | `modes.classify_modes`, `map_mode_code`, `split_on_grid` | tijdlijnen (modus/status, vlam, warmtevraag, gewenste aanvoer, pomp), modus-mapping | `ModeSegment[]` met `Mode` en `ModeCertainty`, aaneengesloten, op raster |
| 4 Cycles | `cycles.detect_cycles`, `classify_end_reason`, `cycle_phases`, `cycle_aggregates` | tijdlijnen, modussegmenten, config | `BurnerCycle[]` met eindreden, fases, aggregaten, `pause_before_ms` |
| 5a Cyclus-kengetallen | `metrics_cycles.hourly_cycle_metrics` (in de run), `summarize_cycles` (periodes, buiten de run) | cycli, modi, vlam-/vraagtijdlijn, uur-buckets | `MetricValue[]` per uur: starts, brandtijd, waargenomen tijd, vraagtijd; per periode: starts/uur, mediaan/gemiddelde brandduur, aandeel kort, mediaan pauze |
| 5b Temperatuur | `metrics_temperature.cycle_temperature_metrics`, `hourly_temperature_metrics` | cycli (met fases), tijdlijnen aanvoer/retour/gewenst | overshoot, opwarmsnelheid, ketel-ΔT en gem. aanvoer in stabiele fase |
| 6 Rules | `cvidee.rules` (ADR-004, #10) | opgeslagen afgeleide data + profiel + regelparameters | `FindingCandidate[]` |

### 3.1 Timeline

- Elke geaccepteerde waarneming start een `ValueInterval` dat loopt tot de volgende waarneming van het signaal, een verbindingsgat, veroudering of de horizon. Intervallen worden **niet** samengevoegd: `observed_at` (bewijstijd) en `origin` (`change`/`confirm`/`poll`) blijven beschikbaar voor tijdafstemming en overgangsdetectie.
- De carry-in-waarneming (laatste vóór `context_start`) geeft een interval dat op `context_start` begint maar zijn oorspronkelijke `observed_at` en `origin` houdt.
- HA `unavailable`/`unknown` (`value is None`) → `UnknownReason.UNAVAILABLE`. Eigen WebSocket weg → alle signalen `DISCONNECTED`; CAN-gateway weg → alleen signalen met `via_can_gateway`. Vóór de eerste waarneming → `NO_DATA`.
- Veroudering alleen voor signalen met `heartbeat_expected`: waarde geldig tot `evidence_ts + max_age`, daarna `STALE`. Dit is **prospectief**: wat eenmaal bekend was, wordt niet achteraf onbekend (anders zou het resultaat van een run afhangen van het moment van draaien). Detailregels: ADR-003 (#9).
- Exacte duplicaten `(signal, ts, value)` vallen weg.

### 3.2 Quality

- Plausibiliteit per rol (bv. aanvoer 0–100 °C): erbuiten → `IMPLAUSIBLE`; verkeerd type → `INVALID`.
- Elk onbekend interval levert een `QualityEvent` (sleutel `(kind, signal, start)`, op raster gesplitst; `end=None` zolang het doorloopt).
- Tellerresets (gas): een daling start een nieuw segment; verbruik wordt per segment berekend en is nooit negatief.
- Combinaties van signalen gaan via `align_pair` (§7).

### 3.3 Modes

- Met modus-/statussignaal: mapping (configureerbaar, standaard voor de Calenta Ace na #5) → zekerheid `DIRECT`.
- Zonder modussignaal: afgeleid uit vlam, warmtevraag, gewenste aanvoer, pomp → `INFERRED` ("beperkte zekerheid", FR-09).
- `AFTERRUN`: pomp/naloopstatus na vlam-uit zonder vraag, maximaal `afterrun_max_ms` (standaard 15 min).
- Ontbreken de signalen om te beslissen → `UNKNOWN` met zekerheid `NONE`. Onbekend wordt nooit standby.

**Aanvulling (#24).** Uitwerking in `analysis/modes.py`:

- **Mapping.** `PipelineConfig.mode_mapping` (eerste treffer wint; numerieke codes als geheel getal, `1.0` → `"1"`). Voorlopige standaard uit ontwerp v3: `1` = CV, `2` = tapwater (`PROVISIONAL_MODE_MAPPING`); #5 bevestigt of vervangt dit en levert de storings-/blokkeringscodes. `FAULT_BLOCKING` ontstaat alleen uit een gemapte code (apparaatmelding, bron `operating_mode@boiler`), nooit afgeleid. Een apparaatcode wint altijd, ook een `AFTERRUN`-code (niet afgekapt; de cyclusfase kapt zelf af op `afterrun_max_ms`).
- **Geen, onbekende of niet-gemapte code** → afleiden (`INFERRED`). Warmtevraag = warmtevraagsignaal, of, als dat niet bekend is, gewenste aanvoer ≥ `demand_flow_setpoint_min_c` (voorlopig 20 °C).
  - vlam aan + vraag → `CH`; vlam aan zonder vraag → `DHW` (combiketel; houdt tapwater uit CV-statistiek, scenario 4), behalve binnen `afterrun_max_ms` nadat er tijdens dezelfde brandperiode nog vraag was (uitlopen na einde vraag → `CH`, zodat scenario 3 `DEMAND_ENDED` blijft);
  - vlam uit + vraag → `CH`; vlam uit zonder vraag → `AFTERRUN` zolang de pomp loopt, binnen `afterrun_max_ms` na een bekende vlam-uit-overgang en tot de eerste bekende pomp-uit; anders `STANDBY`. Zonder gekoppelde pomp wordt geen naloop afgeleid (`STANDBY`); een gekoppelde maar onbekende pomp binnen dat venster → `UNKNOWN`.
  - vlam of vraag onbekend → `UNKNOWN`. Na onbekende tijd (ADR-003 §5.4) begint geen naloopvenster: er is geen bekende vlam-uit-overgang.
- **`sources`** = de signalen waarop de beslissing berust (gesorteerd); leeg bij `UNKNOWN`. Segmenten met verschillende bronnen worden niet samengevoegd.
- Alle terugblik is begrensd door `afterrun_max_ms` (≤ lookback, §5), dus in blokken == in één keer geldt; bewaakt door `test_chunked_equals_whole` in `tests/analysis/test_modes.py`. `merge_segments` is de lezerskant van §4.5.

### 3.4 Cycles

Semantiek volgt de simulatie in ontwerp v3 (`buildSim`): eindredenen `stop` / `vraag` / `tapwater` / `onvolledig` ⇒ `STOP_DURING_DEMAND` / `DEMAND_ENDED` / `DHW_ENDED` / `DATA_GAP`.

- **Start** = vlam-aan-interval met `origin = change`, direct voorafgegaan door een bekend vlam-uit-interval → `start_observed = True`. Vlam aan na onbekende tijd, op de vensterstart, of uit een `poll`/`confirm` → cyclus met `start_observed = False`; die telt **nooit** als start (FR-08, scenario 5: geen kunstmatige start na reconnect).
- **Einde** = eerste bekende vlam-uit. Eindreden via `classify_end_reason`:
  - tapwatercyclus → `DHW_ENDED`;
  - warmtevraag bekend en aanwezig gedurende `[stop, stop + end_reason_lookahead)` (standaard 60 s) → `STOP_DURING_DEMAND`;
  - warmtevraag bekend en afwezig → `DEMAND_ENDED`;
  - warmtevraag onbekend of niet gekoppeld → `UNDETERMINED` (toegevoegd t.o.v. het plan: zonder bewijs claimen we geen van beide; FR-04/FR-16).
- **Vlam wordt onbekend tijdens branden** → `end` = begin van het onbekende interval, `end_reason = DATA_GAP`, `complete = False`, `duration_ms` is een ondergrens (UI: "≥ 4:00"). Na het gat begint geen nieuwe start (zie hierboven).
- **Nog aan op de horizon** → `end = None`, `duration_ms = horizon − start` (ondergrens), voorlopig.
- `complete` ⇔ begin én einde zijn waargenomen overgangen en de vlam was de hele tijd bekend.
- **Modus** van de cyclus: `DHW` als er tapwater overlapt, anders `CH` als CV overlapt, anders `UNKNOWN`.
- **Fases** (FR-15): `STARTUP` tot aanvoer ≥ gewenst − 2 K of na `startup_max_ms` (3 min); `STABLE` daarna tot vlam-uit; `AFTERRUN` vanaf vlam-uit zolang modus naloop is (mag na `end` doorlopen).
- **Pauze**: `pause_before_ms` alleen als de vorige cyclus ≤ `max_pause_ms` (60 min) eerder eindigde en de vlam ertussen bekend uit was. Anders `None`. Standby-uren worden zo nooit "pauze".
- Sleutel: `start`.

### 3.5 Metrics

Twee lagen, omdat een dag (of de rollende 6 u van `korte_cycli_6u`) niet in elk venster past:

1. **In de run**: additieve uur-buckets (UTC-uur) — `STARTS` (alleen `start_observed`, in het uur van de start), `BURN_TIME`, `OBSERVED_TIME`, `HEAT_DEMAND_TIME`, per modus — en per-cyclus-temperatuurkengetallen. Sleutel `(name, mode, window.kind, window.range.start, cycle_start)`.
2. **Periodes** (dag, rollend 6 u, voor/na): `summarize_cycles` is een pure functie op **opgeslagen** cycli en uur-tijdsbases. Mediaan en aandelen worden uit de cycli zelf berekend, niet uit uurgemiddelden. Omdat de opgeslagen cycli live en bij import gelijk zijn (§6), zijn deze uitkomsten dat ook.

Regels: starts per **waargenomen** uur (tijdsbasis zichtbaar — in de simulatie 5,5 u bij 30 min gat); brandduurstatistiek alleen over complete CV-cycli; kort = complete CV-cyclus met `STOP_DURING_DEMAND` en duur < drempel; tapwater- en onvolledige cycli uit CV-statistiek; ΔT en gemiddelde aanvoer alleen in `STABLE` en alleen op afgestemde samples (§7).

## 4. Venster, watermark en upsert (runner, #27)

### 4.1 Begrippen

| Begrip | Definitie | Standaard |
|---|---|---|
| `now` | tijdstip van de tick, parameter | — |
| `settle` | wachttijd voor late events | 2 min |
| horizon `end` | `now − settle`; data ≥ horizon wordt genegeerd | — |
| `watermark` W | alles met einde ≤ W is definitief | opgeslagen in `analysis_runs` |
| raster | hele UTC-uren (`grid_ms`) | 1 u |
| `emit_from` | `floor_raster(W)` | — |
| `lookback` L | contextdeel vóór `emit_from` | 6 u |
| `context_start` | `emit_from − L` | — |
| lookahead | `end_reason_lookahead_ms` (≤ settle) | 60 s |

`AnalysisWindow.for_run(watermark, now, lookback_ms, settle_ms, grid_ms)` bouwt dit venster.

### 4.2 Per tick

1. Lees waarnemingen met `ts ∈ [context_start, end)` plus per signaal de laatste waarneming vóór `context_start` (carry-in); idem voor verbindingsgebeurtenissen.
2. `result = run_pipeline(observations, connection_events, config, window, now)`.
3. In één transactie: verwijder afgeleide rijen (cycli, modussegmenten, kwaliteitsgebeurtenissen, uur-kengetallen) met sleutel `≥ emit_from`; voeg `result.*` in; sla `result.next_watermark`, regelversies en `config_hash` op in `analysis_runs`.
4. Draai de regels (stap 6) op de bijgewerkte data.

Dit is een **idempotente upsert**: dezelfde tick twee keer draaien geeft dezelfde database.

### 4.3 Watermark

```
next_watermark = min( end − lookahead,
                      start van de vroegste cyclus die open is of eindigt na end − lookahead )
```

begrensd tot `[emit_from, end]`. Een item is **definitief** (`final = True`) als zijn einde ≤ `next_watermark`; anders voorlopig (open cyclus, het laatste gedeeltelijke uur/segment, een nog lopende kwaliteitsgebeurtenis). Voorlopige items worden in een volgende run vervangen.

**Aanvulling (#26).** Een gesloten cyclus kijkt ook ná haar einde: de naloopfase (`AFTERRUN`) loopt tot `afterrun_max_ms` na vlam-uit. "Eindigt na `end − lookahead`" wordt daarom gelezen als `cycles.cycle_settles_at(cyclus) > end`, met `cycle_settles_at = einde + max(lookahead, afterrun_max_ms)` (`None` = open). Zonder deze aanvulling kan een cyclus met afgekapte naloop definitief worden en geldt in blokken == in één keer niet (aangetoond door de property-test in `tests/analysis/test_cycles.py`).

### 4.4 Een cyclus over een venstergrens

- **Over de horizon (open cyclus).** De cyclus heeft `end = None`, is voorlopig en houdt het watermark op zijn `start`. De volgende run begint dus met `emit_from ≤ start` en berekent de cyclus vanaf het begin opnieuw, met sleutel `start`; de oude rij wordt vervangen. Dit geldt ook voor cycli die langer duren dan de lookback (een modulerende ketel kan uren branden): het watermark wacht, de lookback schuift mee.
- **Over `emit_from` / in het lookbackdeel.** Cycli waarvan de start in het lookbackdeel ligt, worden in elke run opnieuw berekend, maar alleen als context (pauze vóór de volgende cyclus, naloop, modus). Ze worden niet opnieuw geschreven: hun sleutel ligt vóór `emit_from`, en dankzij de watermark-regel waren ze al definitief. Een cyclus kan `emit_from` niet "half" overspannen: was zij bij de vorige run nog niet definitief, dan lag het watermark — en dus `emit_from` — op of vóór haar start.
- **Over `context_start`.** Een cyclus die al brandde op `context_start` krijgt in deze run `start_observed = False` en een afgekapt begin. Haar sleutel ligt vóór `emit_from`, dus zij wordt niet uitgegeven; de opgeslagen, eerder definitief berekende versie blijft staan.
- **Alleen cycli waarvan het einde vóór `end − lookahead` ligt zijn definitief.** Een cyclus die 30 s vóór de horizon stopt, is nog voorlopig: haar eindreden hangt af van de warmtevraag in de lookahead. Hetzelfde geldt voor een cyclus waarvan de naloop nog kan doorlopen (zie aanvulling in §4.3).

### 4.5 Canoniek raster voor intervallen

Modussegmenten en kwaliteitsgebeurtenissen worden op hele UTC-uren gesplitst. Zo hangt hun sleutel (`start`) niet af van waar een venster begon, en kan een langdurig standby- of uitvalinterval het watermark niet dagen vasthouden. De store/API voegt aangrenzende stukken met gelijke inhoud samen voor weergave ("CAN-data 30 minuten onderbroken"). Omdat `emit_from` op het raster ligt, valt een gesplitst stuk altijd volledig binnen of buiten het uitgegeven deel.

### 4.6 Late data, configuratiewijziging en herberekening

- **Late waarneming** (ts vóór het watermark, bv. na een import of een vertraagde gateway): ingest registreert de vroegste late `ts`; de runner zet `watermark = min(watermark, ts)` en de volgende tick herberekent vanaf dat uur. Er is geen apart herstelpad.
- **Configuratiewijziging** (signaalkoppeling, drempels, modus-mapping): nieuwe `config_hash`; de runner zet het watermark terug naar het begin van de periode waarop de wijziging van toepassing is (`valid_from`), of naar het begin van de ruwe data bij een globale wijziging.
- **Retentie**: ruwe data ouder dan de retentie wordt niet meer herberekend; afgeleide data blijft staan.

### 4.7 Historische import

Import gebruikt **dezelfde runner** in blokken (standaard 24 u, plan §3.1): voor elk blok `now := blok_einde + settle`, verder identiek. Het watermark schuift per blok op; de import kan worden hervat vanaf het opgeslagen watermark. Import van een periode vóór reeds verwerkte data is een late-data-geval (§4.6). Live-runner en import delen één lock (één schrijver).

## 5. Eisen aan de lookback

`lookback ≥ maximale stapcontext + raster`, gecontroleerd in `PipelineConfig.__post_init__`. Stapcontext = hoe ver een uitkomst met sleutel k terugkijkt vóór k:

| Afhankelijkheid | Context |
|---|---|
| `pause_before_ms` (vorige cyclus) | `max_pause_ms` (60 min) |
| naloop/modus na vlam-uit | `afterrun_max_ms` (15 min) |
| opstartfase | `startup_max_ms` (3 min) |
| uur-bucket die `emit_from` bevat | 1 raster (1 u) |
| status op `context_start` | carry-in (onbeperkt, geen lookback nodig) |

De standaard van 6 u is ruim groter dan dit minimum en dekt ook de maximale duur van een normale cyclus plus marge, zodat in het gewone geval geen run ver hoeft terug te kijken. Voor cycli die langer branden dan de lookback zorgt de watermark-regel (§4.3) voor correctheid; de lookback is dan alleen nog context.

## 6. Waarom in blokken == in één keer

**Bewering.** Laat *heel* = één run met watermark T0 en horizon T1, en *blokken* = een reeks runs met oplopende horizonnen h₁ < … < hₙ = T1 volgens §4. Dan is de inhoud van de afgeleide tabellen na beide gelijk.

**Schets.**

1. *Lokaliteit.* Elke uitkomst met sleutel k is een functie van (a) de toestand van de signalen op `k − C` (C = stapcontext, §5), die via tijdlijn + carry-in in elke run gelijk is, en (b) de waarnemingen in `[k − C, einde(k) + lookahead]`.
2. *Volledige context.* Elke uitgegeven sleutel is ≥ `emit_from` ≥ `context_start + L` en L ≥ C + raster, dus alle benodigde data ligt in het venster.
3. *Geen afgekapte cycli.* Een cyclus met start ≥ `emit_from` begint binnen het venster en wordt volledig gezien; een cyclus die nog loopt houdt het watermark vast (§4.3), dus geen run schrijft een afgekapte versie definitief.
4. *Last-writer-wins op deterministische sleutels.* Een voorlopig item wordt vervangen zodra een latere run het opnieuw uitgeeft; definitieve items worden nooit gewijzigd (ze liggen voor `emit_from` van alle latere runs, of worden identiek herschreven als ze in het uur van `emit_from` vallen).
5. Na de laatste run (horizon T1) zijn dus alle items gelijk aan die van de hele run, inclusief de voorlopige items aan het eind.

**Voorwaarden** (overtreding = geen garantie; elk punt heeft een eigenaar):

| Voorwaarde | Bewaakt door |
|---|---|
| Dezelfde waarnemingenverzameling: alle waarnemingen met ts < horizon zijn er bij die run (late data → §4.6). | ingest (#16, #17, #19) + runner (#27) |
| Live en import leveren dezelfde `Observation`s (zelfde `kind`, zelfde normalisatie). In het bijzonder: een `get_states`-waarde na reconnect is `poll`, een history-seed is `poll`; `last_reported` alleen gebruiken als het in beide paden gelijk wordt vastgelegd. | ingest (#17, #19), ADR-003 (#9) |
| Dezelfde configuratie-snapshot (`config_hash`) en regelversies. | runner (#27) |
| Stappen zijn puur, deterministisch en volgorde-onafhankelijk; geen klok; geen afhankelijkheid van `set`-volgorde; floats via `math.fsum` in tijdsvolgorde. | alle analyse-tickets |
| Veroudering is prospectief (§3.1). | #23, ADR-003 |
| Lookback ≥ stapcontext + raster (§5). | `PipelineConfig` |
| Interval-uitvoer op het canonieke raster (§4.5). | #23, #24 |
| Carry-in wordt aangeleverd voor elk signaal en elke verbindingsbron. | runner (#27) |

Bewaakt door `test_chunked_equals_whole` (hypothesis): willekeurige vlam/vraag-historie met verbindingsuitval en willekeurige blokgrenzen; de test simuleert de runner exact zoals in §4.2. De test is `xfail(strict=False, raises=NotImplementedError)` tot de stappen bestaan; het ticket dat de laatste stap oplevert verwijdert de marker.

## 7. Samplingtolerantie bij het combineren van signalen (FR-07)

Combinaties (ketel-ΔT uit aanvoer/retour, overshoot uit aanvoer/gewenst, later verdeler-ΔT) gaan altijd via `quality.align_pair(a, b, ts, tolerance, a_heartbeat=…, b_heartbeat=…)`, dat een `PairSample` met `Alignment` teruggeeft:

| Situatie | `alignment` | Gevolg |
|---|---|---|
| Eén van beide onbekend | `None` | Combinatie onbekend; telt niet in de tijdsbasis. |
| Beide periodiek rapporterend en `|observed_at_a − observed_at_b| ≤ tolerantie` | `ALIGNED` | Combineren. |
| Beide periodiek, verschil > tolerantie | `MISALIGNED` | Niet combineren; `QualityEvent(MISALIGNED)`; telt niet in de tijdsbasis. ("Een oude retourmeting wordt niet met een nieuwe aanvoermeting gecombineerd zonder kwaliteitsmelding.") |
| Minstens één signaal alleen-bij-wijziging | `ASSUMED_UNCHANGED` | Combineren met zwakkere herkomst; de onderbouwing van een bevinding vermeldt dit. Als het andere signaal sindsdien meer dan de tolerantie *veranderd* is terwijl dit signaal geen bewijs gaf, alsnog `MISALIGNED`. |

Tolerantie per combinatie via `PairTolerance` in de config; standaard 30 s (`default_pair_tolerance_ms`). Bewijstijd van een waarde = `observed_at` van het interval (wijziging, bevestiging of `last_reported`). Afgeleide waarden krijgen `Provenance.derive(...)`: de zwakste herkomst van de invoer, nooit sterker dan `DERIVED`.

## 8. Hoe onbekende tijd doorwerkt (FR-11)

- **Tijdlijn**: onbekend is een expliciet interval met reden (`no_data`, `stale`, `invalid`, `implausible`, `disconnected`, `unavailable`); de tijdlijn dekt het venster zonder gaten.
- **Combinaties**: onbekend als één van de invoeren onbekend is (`unknown_union`, vaste voorrang van redenen).
- **Modi**: onbekende beslissignalen → `UNKNOWN`, nooit standby.
- **Cycli**: vlam onbekend tijdens branden → `DATA_GAP`, duur als ondergrens; tijd met vlam onbekend is geen pauze; na een gat geen nieuwe start.
- **Kengetallen**: elke `MetricValue` draagt `time_basis_seconds` (alleen bekende tijd) en `coverage` (= tijdsbasis / vensterlengte). Te weinig tijdsbasis → `value = None`, niet 0.
- **Regels/bevindingen**: dekking en uitgesloten tijd zijn onderdeel van de onderbouwing; een datagat telt nooit als herstel (scenario 5).

## 9. Tijdzone en zomertijd

- Intern en in opslag: UTC, `int` milliseconden sinds epoch (`TimestampMs`). Geen `datetime.now()` in `cvidee.analysis`; `now` is altijd een parameter.
- Uur-buckets en het raster zijn **UTC-uren**. Omdat de offset van `Europe/Amsterdam` een heel aantal uren is, vallen UTC-uurgrenzen samen met lokale uurgrenzen; op de DST-dagen heeft de lokale dag 23 of 25 uur-buckets.
- Dagbuckets (`MetricWindowKind.DAY`) zijn lokale kalenderdagen `[00:00, 00:00)` in `Europe/Amsterdam`, door de aanroeper naar UTC omgezet (`zoneinfo`). De tijdsbasis maakt 23/25 u expliciet.
- Presentatie (API → UI) zet om naar `Europe/Amsterdam`, 24-uursklok.
- Testen rond de overgang van 25 oktober 2026 (03:00 → 02:00 lokale tijd) horen bij #28 en #27.

## 10. Gevolgen

- De types in `cvidee.analysis.types` zijn het contract; wijzigingen erin raken meerdere tickets en gaan via een PR met deze ADR erbij.
- `cvidee.store` (#7) moet voor cycli, modussegmenten, kwaliteitsgebeurtenissen en uur-kengetallen de sleutels van §3–§4 als unieke sleutel hebben en "verwijder ≥ emit_from + invoegen" in één transactie ondersteunen; `analysis_runs` bewaart `watermark`, `emit_from`, `end`, `config_hash` en regelversies.
- Dag- en periodekengetallen worden niet door de runner gematerialiseerd maar op aanvraag (of gecachet met dezelfde replace-from-regel) uit opgeslagen cycli berekend.
- Kosten: een cyclus die uren brandt laat elke tick uren herberekenen. Bij ~200k rijen/dag is dat acceptabel; meten in #27.

## 11. Open vragen

1. **`UNDETERMINED` als vijfde eindreden.** Afwijking van het plan (vier redenen). Alternatief: `DEMAND_ENDED` met `heat_demand_after_stop = None`. Voorstel: houden; de UI toont "onbepaald".
2. **`last_reported`** is bij history-import niet altijd beschikbaar. Voorstel (ADR-003, #9): ingest zet bevestigingen om in `confirm`-waarnemingen zodat live en import dezelfde invoer geven.
3. **Drempels** (`max_pause_ms` 60 min, `end_reason_lookahead_ms` 60 s, `startup_max_ms` 3 min, `startup_flow_margin_k` 2 K, `afterrun_max_ms` 15 min, paartolerantie 30 s) zijn redelijke startwaarden zonder meetonderbouwing; bijstellen na de CAN-inventarisatie (#5) en zichtbaar maken in instellingen (#22).
4. **Meerdere ketels** vallen buiten scope; de cyclussleutel `start` gaat uit van één brander.
