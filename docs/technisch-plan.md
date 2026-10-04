# Technisch plan — CV-idee (CV-analyse en optimalisatieadvies)

Versie 1.0 · 4 oktober 2026

Bronnen:
- Functionele requirements: [`docs/cv-idee-functionele-requirements.md`](cv-idee-functionele-requirements.md) (FR-01 … FR-42)
- Ontwerp: [`docs/design/CV-analyse-v3.dc.html`](design/CV-analyse-v3.dc.html) (Claude Design-project `dd7f260d-…`, bestand *CV-analyse v3*). Het ontwerp is leidend voor schermen, teksten, kleuren en interactie.

## 1. Samenvatting

CV-idee is een **alleen-lezen** analyse-app voor een Remeha Calenta Ace met eTwist. De app leest ketel-, kamer- en buitensignalen uit Home Assistant (HA), reconstrueert bedrijfsmodi en branderperiodes, beoordeelt gegevenskwaliteit, past versiebeheerde detectieregels toe en levert verklaarbare bevindingen en aanbevelingen. Wijzigingen die de gebruiker doorvoert worden gelogd en voor/na geëvalueerd. Samenvattingen gaan terug naar HA als sensoren.

Gekozen basis (besluit 4 okt 2026):

| Onderwerp | Keuze |
|---|---|
| Uitrol | Eén container. Primair als **Home Assistant add-on** met ingress (UI in HA-zijbalk); ook standalone via `docker compose` (ontwikkeling en niet-Supervisor-installaties). |
| Backend | **Python 3.12**, FastAPI, SQLAlchemy 2 + Alembic, pydantic v2, `uv` als packagemanager. |
| Analyse | Pure Python-functies zonder I/O in `cvidee.analysis`; polars voor aggregaties waar nuttig. |
| Opslag | **SQLite** (WAL-modus) in de add-on `/data`-map, achter een repository-laag zodat TimescaleDB later mogelijk is. |
| Frontend | **React 18 + TypeScript + Vite**, React Router, TanStack Query, gegenereerde API-client uit OpenAPI, CSS Modules + design tokens, eigen SVG-grafieken (d3-scale), lucide-react iconen. |
| Terugkoppeling HA (FR-38) | **HA REST `POST /api/states/<entity_id>`**, met herpublicatie bij HA-herstart en periodiek. |
| Meldingen (FR-39) | HA `notify.*`-service via WebSocket `call_service` + HA-event `cv_analyse_finding` voor eigen automations. |

## 2. Architectuur

```
┌────────────────────────── Home Assistant ──────────────────────────┐
│  CAN-bus integratie (Remeha)   eTwist   Zigbee-sensoren   Recorder  │
│        │  state_changed (WebSocket)            │ history (REST)     │
└────────┼───────────────────────────────────────┼────────────────────┘
         ▼                                       ▼
┌──────────────────────────── cv-idee container ─────────────────────┐
│ ingest/                                                            │
│   ha_client (WS live, reconnect, entiteitlijst)                    │
│   history_import (REST history, idempotent, in blokken)            │
│        │ ruwe waarnemingen + verbindingsgebeurtenissen              │
│        ▼                                                           │
│ store/  SQLite: observations, connection_events, config, …         │
│        │                                                           │
│        ▼                                                           │
│ runner/  analyse-runner (venster + watermark, live == import)      │
│        │  roept pure pipeline aan:                                 │
│        ▼                                                           │
│ analysis/                                                          │
│   1 timeline    waarneming → geldigheidsintervallen (+ onbekend)   │
│   2 quality     verouderd / ongeldig / onwaarschijnlijk / resets   │
│   3 modes       CV / tapwater / standby / naloop / storing / onb.  │
│   4 cycles      branderperiodes + eindreden                        │
│   5 metrics     starts/uur, brandduur, pauzes, ΔT, overshoot …     │
│   6 rules       versiebeheerde detectieregels → kandidaat-bevind.  │
│        │                                                           │
│        ▼                                                           │
│ findings/  bevindingen-engine (dedupe, bundelen, prioriteren,      │
│            levenscyclus, aanbevelingen, snapshot advieshistorie)   │
│ changes/   wijzigingslogboek + voor/na-evaluatie                   │
│ notify/    meldingsbeleid (ernst→kanaal, bundel, herstelcriterium) │
│ ha_export/ samenvattende sensoren → HA REST /api/states            │
│ api/       FastAPI (REST, OpenAPI) ── serveert ook frontend-build  │
└────────────────────────────────────────────────────────────────────┘
         ▲
         │ ingress (add-on) of poort 8099 (standalone)
   React-frontend (schermen uit ontwerp v3)
```

### 2.1 Kernprincipes

1. **Alleen-lezen.** Geen enkele code-pad schrijft naar ketel of thermostaat. De HA-token wordt alleen gebruikt voor lezen, `/api/states` van eigen `sensor.cv_analyse_*`-entiteiten en `notify`. (Afbakening §8.)
2. **Live == import (FR-06).** De pipeline is een pure functie `analyse(waarnemingen[t0,t1), config-snapshot, regelversies) → resultaten`. Live verwerking is niets anders dan herhaald draaien van dezelfde functie over een schuivend venster. Een property-test bewaakt dat in blokken verwerken hetzelfde oplevert als in één keer.
3. **Onbekend ≠ uit (FR-11).** Elk tijdstip per signaal is óf een geldige waarde, óf expliciet *onbekend* met reden (geen data, verouderd, ongeldig, verbinding weg). Statistieken rekenen alleen met waargenomen tijd en tonen hun tijdsbasis.
4. **Herkomst van waarden.** Elke waarde draagt `kind ∈ {gemeten, gerapporteerd, afgeleid, geschat}` en bron (entiteit of afleiding). Afgeleide waarden erven de zwakste herkomst.
5. **Observatie ≠ interpretatie ≠ advies (FR-21).** Drie aparte velden in het datamodel; de UI toont ze in drie kolommen.
6. **Versiebeheerde regels (FR-41).** Iedere regel heeft `id` + semver. Bevindingen en adviezen bewaren regelversie, parameters, meetperiode en instellingen-snapshot.
7. **Geen verzonnen getallen.** Zekerheid is een gedocumenteerde categorie, geen percentage (FR-22). Modulatie % wordt nooit naar kW omgerekend zonder gevalideerde omrekening (FR-03). Euro's alleen met ingestelde prijs.

## 3. Componenten

### 3.1 Ingest (`cvidee.ingest`)

- **HA-verbinding.** Add-on: `SUPERVISOR_TOKEN`, `ws://supervisor/core/websocket`, `http://supervisor/core/api`. Standalone: `HA_URL` + long-lived access token (env). Eén `HAClient`-interface met fake-implementatie voor tests.
- **Live.** `subscribe_events(state_changed)` gefilterd op gekoppelde entiteiten. Bij (her)verbinden: `get_states` als peilmoment. Verbindingsstart/-einde worden als `connection_events` opgeslagen; de tijd tussen verlies en herstel is *onbekend* voor alle signalen (FR-08, scenario 5). Reconnect veroorzaakt geen kunstmatige overgang: een `get_states`-waarde na reconnect is een *peiling*, geen *overgang*, en de pipeline maakt geen branderstart op basis van een peiling direct na een datagat.
- **Historie (FR-06).** `GET /api/history/period/<start>?filter_entity_id=…&end_time=…&minimal_response&no_attributes` in blokken van 24 u, idempotent (unieke sleutel `(signal_id, ts, value)`), met voortgang en hervatten.
- **Ontdubbelen (FR-08).** Identieke `(entity, ts, state)` worden genegeerd; opeenvolgende gelijke waarden worden als *bevestiging* (heartbeat) bewaard, niet als overgang.
- **Entiteitlijst** voor de koppel-UI via `get_states` (id, friendly_name, unit, device_class).

**Risico — verouderingsdetectie.** HA stuurt `state_changed` alleen bij wijziging. Een vlamstatus die twee uur "uit" blijft geeft geen nieuwe events. Veroudering kan dus niet alleen op leeftijd van de laatste waarde. Strategie (uit te werken in refinement-ticket):
1. HA-states `unavailable`/`unknown` zijn expliciet *onbekend*.
2. Gebruik `last_reported` (HA ≥ 2024.3) waar de integratie periodiek rapporteert.
3. Verbindingsstatus van de eigen WebSocket en (indien beschikbaar) een CAN-gateway-connectiviteitsentiteit.
4. Max. leeftijd per signaal geldt alleen voor signalen die periodiek horen te rapporteren (configureerbaar: `heartbeat_expected`).

### 3.2 Opslag (`cvidee.store`)

SQLite (WAL), SQLAlchemy 2, Alembic-migraties. Tijden altijd UTC (`INTEGER` ms epoch), weergave in `Europe/Amsterdam` (zomertijd!).

Hoofdtabellen (detail in refinement-ticket datamodel):

| Tabel | Inhoud |
|---|---|
| `signal_definitions` | Canonieke signaalrollen (catalogus uit requirements §2), vast in code, met eenheid en benodigd-voor. |
| `signal_mappings` | Koppeling rol → HA-entiteit, eenheid, locatie, bron, kind, betekenis, max. leeftijd, verwachte resolutie, heartbeat. Versiebeheer via `valid_from`. |
| `observations` | `(signal_id, ts, value_num, value_text, kind: change|confirm|poll, received_at)` — ruwe data. Index `(signal_id, ts)`. |
| `connection_events` | Verbinding op/neer, bron (`ws`, `can_gateway`). |
| `quality_events` | Gedetecteerde gebeurtenissen (uitval, te oud, ontdubbeld, onwaarschijnlijk, tellerreset). |
| `installation_profile` | Ketel, circuits (direct / mengverdeler), ruimtes, zones, thermostaat→warmtevraag, specificaties met expliciet `unknown`. Versiebeheerd. |
| `special_periods` | Opstookprotocol, onderhoud, ontluchten, test, vakantie, bijzonder gebruik (FR-10). |
| `mode_segments` | Afgeleide bedrijfsmodusperiodes. |
| `burner_cycles` | Afgeleide branderperiodes met deterministische sleutel `(start_ts)`. |
| `metric_values` | Afgeleide kengetallen per venster (uur/dag) + dekking. |
| `analysis_runs` | Venster, watermark, regelversies, config-hash, duur, fouten. |
| `findings` | Bevindingen (zie §3.6). |
| `finding_evidence` | Onderbouwing: cycli-id's, signalen, tijdvakken, kengetallen. |
| `recommendations` | Advies met actie, reden, effect, voorwaarden, evaluatie, succes-/terugdraaicriterium, status, notities. |
| `recommendation_snapshots` | Advieshistorie (FR-41): meetperiode, instellingen, regelversie + parameters, config-JSON. |
| `changes` | Wijzigingslogboek (FR-29). |
| `change_evaluations` | Voor/na-resultaat, vergelijkbaarheid, oordeel (FR-30/32). |
| `notification_policy`, `notifications` | Meldingsbeleid en verzonden meldingen (FR-39). |
| `settings` | Drempels per regel, max. sensorleeftijd, gasprijs, enz. |

Volume-inschatting: ~15 signalen, ketelsignalen ~0,25 Hz bij wijziging ⇒ max. ~200k rijen/dag. Retentie ruwe data standaard 180 dagen (instelbaar); afgeleide tabellen blijven bewaard. Bij groei: TimescaleDB achter dezelfde repository-interface.

### 3.3 Analyse-pipeline (`cvidee.analysis`)

Alle stappen zijn pure functies op immutable dataclasses. Volgorde:

1. **Timeline.** Per signaal: geldigheidsintervallen `[t_i, t_{i+1})`, afgekapt op max. leeftijd (indien heartbeat verwacht), connectiviteitsgaten, `unavailable`. Resultaat: `SignalTimeline` met waarden én onbekend-intervallen met reden.
2. **Quality (FR-07, FR-08, FR-11).** Plausibiliteitsgrenzen per rol (bv. aanvoer 0–100 °C), ongeldige waarden ⇒ onbekend; tellerresets bij cumulatieve tellers (gas) ⇒ nieuw segment, nooit negatief verbruik; tijdafstemming: combinaties van signalen (bv. ΔT) alleen als beide waarden binnen tolerantie vers zijn, anders kwaliteitsvlag. Dekking per signaal en per venster.
3. **Modes (FR-09).** Classificatie uit status-/moduscode (mapping configureerbaar, standaard voor Calenta Ace na CAN-inventarisatie), vlam, pomp. Naloop = pomp/status na vlam-uit zonder vraag. Zonder modussignaal: `onbekend` met beperkte zekerheid.
4. **Cycles (FR-12).** Branderperiodes uit vlamovergangen. Per cyclus: start, einde, duur, modus, gewenste/werkelijke aanvoer, retour, modulatie, warmtevraag tijdens en ná stop, eindreden ∈ {`stop_tijdens_vraag`, `einde_vraag`, `einde_tapvraag`, `datagat`}. Cyclus met gat ⇒ `onvolledig`, duur als ondergrens ("≥ 4:00"). Fases per cyclus: opstart, stabiel, naloop (FR-15).
5. **Metrics (FR-13, FR-15).** Starts per *waargenomen* uur (tijdsbasis zichtbaar), totale brandtijd, gemiddelde/mediaan brandduur, aandeel kort, pauzeduur alleen tussen CV-cycli tijdens warmtevraag (standby telt niet mee), overshoot t.o.v. gewenste aanvoer, opwarmsnelheid, ketel-ΔT alleen in stabiele fase.
6. **Rules.** Zie §3.4.

**Runner (`cvidee.runner`).** Elke minuut: venster `[watermark − lookback, nu − settle)` met `lookback` ≥ max. cyclusduur + marge (standaard 6 u) en `settle` 2 min. Resultaten worden ge-upsert op deterministische sleutels; afgeleide data binnen het venster wordt vervangen. Historische import draait dezelfde runner in blokken over het importbereik. Elke run legt regelversies en config-hash vast.

### 3.4 Regelengine (`cvidee.rules`)

```python
class Rule(Protocol):
    id: str                       # "kort-branden"
    version: str                  # "1.3.0"
    category: Category            # Cycli, Temperatuur, Gegevenskwaliteit, …
    required_signals: set[Role]   # voor beschikbaarheid (FR-04)
    optional_signals: set[Role]   # beperkt als ontbrekend
    applies_to: InstallationPredicate   # bv. niet voor mengverdeler-circuit
    applies_in_modes: set[Mode]
    params_schema: type[BaseModel]      # configureerbare drempels, zichtbaar in UI
    def evaluate(self, ctx: RuleContext, params) -> list[FindingCandidate]: ...
```

- **Beschikbaarheid (FR-04)** per analyse = functie van gekoppelde signalen, dekking en resolutie: `beschikbaar | beperkt | niet_beschikbaar` + lijst ontbrekende/beperkende signalen. Korte-cycli-analyse alleen als werkelijke resolutie van vlamstatus fijn genoeg is voor de ingestelde cyclusgrens.
- **Zekerheidsmodel (FR-22, FR-28).** Categorieën: `onvoldoende_bewijs`, `voorlopig`, `matig`, `redelijk`, `hoog`, `hoog_gemeten`. Elke regel documenteert criteria (min. aantal relevante cycli, min. dekking, herhaling over dagen, ontbrekende signalen verlagen één stap). Criteria worden in de UI getoond als onderbouwing (dekking, relevante cycli, herhaling, ontbrekende signalen).
- **Hypotheses (FR-23).** Regels mogen meerdere hypotheses leveren, elk met aanwijzing vóór, wat ontbreekt en onderscheidende meting.
- **Uitsluitingen.** Bijzondere perioden (FR-10) en tapwatercycli worden standaard uitgesloten van normaalgedrag en CV-conclusies; blijven zichtbaar.

MVP-regels: `kort-branden` (FR-14), `stop-tijdens-vraag` (FR-16), `temperatuurverloop` (FR-15), `dataverlies` / `sensor-verouderd` (FR-07/11), `tapwater-uitgesloten` (FR-09, info), `hydraulisch-onvoldoende` (FR-24, scenario 6), `voor-na` (FR-30, via change-evaluatie).

### 3.5 Installatieprofiel en signaalregister

- **Signaalcatalogus** (code): rollen uit requirements §2 (vlam, modus, warmtevraag, gewenste aanvoer, ketelaanvoer, ketelretour, modulatie, kamertemp per ruimte, kamersetpoint per ruimte, buitentemp, gas cumulatief, zonevraag/klep per zone, verdeleraanvoer/-retour per verdeler, debiet/pompstatus, warmtemeter). Rollen kunnen per ruimte/zone/circuit geparametriseerd zijn.
- **Profiel (FR-02/03).** Ketel (model, max. aanvoer, max. CV-vermogen, minimumvermogen, pompstand — elk met `unknown`), circuits (`direct` of `mengverdeler` met groepen), ruimtes (circuit, sensor, thermostaat), welke thermostaat warmtevraag bepaalt. Regels vragen het profiel via predicaten op (bv. "ketel-ΔT is niet representatief voor dit circuit").

### 3.6 Bevindingen en aanbevelingen (`cvidee.findings`)

- **Bevinding** = `{human_id "B-014", rule_id, rule_version, categorie, titel, ernst (hoog|middel|laag|info), zekerheid, relevantie (energie|comfort|bedrijfsstabiliteit), observatie, periode, signalen, interpretatie, hypotheses[], onderbouwing{dekking, relevante_cycli, herhaling, ontbrekende_signalen}, evidence[], status, first_seen, last_seen}`.
- **Dedupe/levenscyclus.** Sleutel `(rule_id, scope)`; nieuwe kandidaten met dezelfde sleutel werken de bestaande bevinding bij (geen nieuwe per cyclus — FR-39). Een bevinding sluit pas na het herstelcriterium (bv. 3 dagen zonder patroon bij vergelijkbaar weer en ≥ 90 % data). Een datagat telt nooit als herstel (scenario 5).
- **Bundelen (FR-26).** Bundelregels koppelen kandidaten die bij hetzelfde patroon horen (zelfde tijdvak + bekende relatie, bv. stop-tijdens-vraag + overshoot + korte pauze ⇒ onderzoekspunt "kort branden"). Oorspronkelijke kandidaten blijven als onderbouwing zichtbaar ("Samengevoegd tot één punt").
- **Prioriteren.** Ernst × zekerheid × relevantie × recentheid; deterministisch, uitleg zichtbaar.
- **Aanbeveling (FR-25).** Actie, reden, verwacht effect, comfortinvloed, omvang (of expliciet "niet te onderbouwen"), voorwaarden, evaluatie, succescriterium, terugdraaicriterium. Adviezen worden gefilterd op profiel en beschikbare data (FR-24: zonder verdelerdata geen lusadvies). Bij onvoldoende bewijs: aanvullende meting i.p.v. diagnose (FR-28).
- **Opvolging (FR-27).** Status `open | geaccepteerd | uitgesteld(tot) | uitgevoerd | afgewezen | terugdraaien_geactiveerd`, notities. Uitgesteld komt terug op datum of eerder bij verslechtering (meer korte cycli / comfortverlies).
- **Snapshot (FR-41).** Bij aanmaken en bij elke statuswijziging: meetperiode, instellingen, profielversie, regelversie + parameters. UI toont "Sindsdien:" als de regel daarna is gewijzigd.

### 3.7 Wijzigingen en effectmeting (`cvidee.changes`)

- **Logboek (FR-29).** Tijdstip, parameter (uit lijst + vrij), oud/nieuw, reden, uitgevoerd door, gekoppelde aanbeveling. Grafieken tonen wijzigingen als markers.
- **Voor/na (FR-30).** Referentie- en observatieperiode (standaard 7 d, ingestelde perioden uitgesloten), kengetallen starts/uur, mediaan brandduur, aandeel kort, gem. aanvoer stabiel bedrijf, comfort per ruimte (uren > 0,5 °C onder setpoint).
- **Vergelijkbaarheid (FR-32).** Checks: buitentemperatuurverschil, setpoints, andere wijzigingen in een van beide perioden (overlap ⇒ "niet toe te schrijven"), gemarkeerde perioden, dekking. Oordelen: `verbeterd | verslechterd | afweging | niet_toe_te_schrijven | onvoldoende_bewijs`. Afweging (minder starts, slechter comfort) wordt nooit als verbetering gelabeld en activeert het terugdraaicriterium (scenario 7).

### 3.8 Meldingen en HA-export

- **HA-export (FR-38).** `POST /api/states/sensor.cv_analyse_*` met attributen (`friendly_name`, `unit_of_measurement`, `icon`, `attribution`). Entiteiten uit ontwerp: `sensor.cv_analyse_starts_per_uur`, `…_korte_cycli_6u`, `…_gegevensdekking`, `…_open_bevindingen`, `…_hoogste_ernst`, `…_volgende_actie`, `binary_sensor.cv_analyse_onvoldoende_gegevens` (+ `…_bedrijfsmodus`). Beperking REST-states: geen `unique_id`, niet bewerkbaar in UI, verdwijnen bij HA-herstart ⇒ herpubliceren bij `homeassistant_started`-event, na eigen reconnect en elke 5 min.
- **Meldingen (FR-39).** Beleid per ernst: `direct | dagbundel | weekrapport | geen`. Eén melding per bevinding; opnieuw alleen bij verslechtering (ernst omhoog of patroon substantieel erger) als dat aan staat. Verzending via `notify.<doel>` (instelbaar) en altijd een HA-event `cv_analyse_finding` (voor eigen automations).

### 3.9 API (`cvidee.api`)

FastAPI met OpenAPI-schema als contract (gecommit in `api/openapi.json`; CI controleert dat het actueel is). Frontend genereert types met `openapi-typescript` + `openapi-fetch`. Hoofdroutes:

```
GET  /api/status                       bedrijfsmodus, live-status, dekking vandaag
GET  /api/overview                     alles voor Overzicht (FR-36)
GET  /api/signals | PUT /api/signals/{role}     (FR-01)
GET  /api/ha/entities                  entiteitlijst voor koppelen
GET  /api/analyses                     beschikbaarheid (FR-04)
GET|PUT /api/installation              (FR-02/03/05)
GET|POST|DELETE /api/periods           (FR-10)
GET  /api/quality?from&to              dekking, events, modusverdeling (FR-06–11)
GET  /api/timeline?from&to             gesampelde reeksen + modi + cycli voor grafiek
GET  /api/cycles?from&to               (FR-12/13)
GET  /api/findings | /api/findings/{id}     (FR-21–28, FR-37)
POST /api/findings/{id}/status | /notes     (FR-27)
GET  /api/history                      advieshistorie (FR-41)
GET|POST /api/changes | GET /api/changes/{id}/evaluation   (FR-29/30/32)
GET|PUT /api/notifications/policy, GET /api/notifications    (FR-39)
GET  /api/ha/export                    huidige exportwaarden (FR-38)
POST /api/import                       historische import starten, GET voortgang (FR-06)
GET|PUT /api/settings                  drempels, gasprijs, …
```

Ingress: alle URL's relatief (Vite `base: './'`, router-basename uit `X-Ingress-Path`). Standalone: optionele eenvoudige token-auth (env `CVIDEE_API_TOKEN`).

### 3.10 Frontend (`frontend/`)

Leidend: ontwerp v3. Belangrijk: het Claude Design-project bevat ook een "Modernist"-design system, maar **v3 gebruikt dat niet**; volg de visuele taal van v3.

- **Tokens** (`src/styles/tokens.css`): font *Plus Jakarta Sans* (self-hosted via `@fontsource`, add-on kan offline draaien), achtergrond `#f4f5f8`, tekst `#1d2433`, kaarten wit met rand `#e7e9ee`, afgeronde hoeken. Palet (basis / tint / donker): oranje `#ea6a2f/#fdeee6/#a2421a` (accent, primaire knop, hover `#d65a20`), teal `#1a9e8f/#e1f4f1/#0f6b61`, violet `#7c5cd6/#efeafb/#563ba8`, blauw `#3b7ddd/#e7effb/#2659a8`, amber `#d99a12/#fcf3dc/#8a6206`, rose `#e0475b/#fce8eb/#a92536`, groen `#2f9e5b/#e4f4ea/#1d6b3c`, slate `#5b6475/#eef0f3/#3d4452`; muted tekst `#8a92a3`; focus `2px solid #ea6a2f`. `font-variant-numeric: tabular-nums`.
- **Semantiek kleur.** Ernst: hoog=rose, middel=amber, laag=blauw, info=slate. Status: open=blauw, geaccepteerd=teal, uitgevoerd=groen, uitgesteld/afgewezen=slate, terugdraaien=rose. Analyse: beschikbaar=groen, beperkt=amber, niet=slate. Grafiek: CV-branden oranje, kort-tijdens-vraag rose, tapwater blauw, geen data = grijze arcering, aanvoer oranje, gewenst grijs gestippeld, retour blauw, modulatie violet.
- **Layout.** Zijbalk 240 px met secties *Analyse* (Overzicht, Bevindingen [teller], Cycli, Wijzigingen, Advieshistorie) en *Instellingen* (Signalen [9/15], Installatie, Gegevenskwaliteit, Meldingen) + alleen-lezen-melding; onder 960 px viewport een icon-rail van 72 px. Header: live-status, bron, datum. Bevindingen: lijst links ≥ 1060 px main-breedte, anders chips bovenaan; detail 2 kolommen ≥ 700 px.
- **Schermen.** Overzicht, Bevindingen, Cycli, Wijzigingen, Advieshistorie, Signalen, Installatie, Gegevenskwaliteit, Meldingen.
- **Uitleglaag.** Instelling "uitleg tonen" (standaard aan): KPI-uitleg, begrippenlijst per bevinding (glossary uit ontwerp), uitlegbanner op Cycli. Instelling "requirement-ID's tonen" alleen in dev-modus.
- **Grafieken.** Eigen SVG-componenten: mini-tijdlijn (overzicht), meerbaans-tijdlijn (modus, warmtevraag, brander, temperatuur, modulatie) met datagat-arcering, cyclusselectie gekoppeld aan tabel, voor/na-balken, dekkingsbalken, donut, modusverdeling.
- **Taal.** UI volledig Nederlands; getallen met komma (`nl-NL`), tijden 24 u, `Europe/Amsterdam`.

## 4. Repository-structuur

```
backend/
  pyproject.toml            uv, ruff, mypy --strict, pytest
  src/cvidee/
    ingest/  store/  analysis/  rules/  runner/  findings/
    changes/  notify/  ha_export/  api/  config.py  main.py
  migrations/               alembic
  tests/                    unit, property (hypothesis), scenario
frontend/
  src/ app/ components/ screens/ charts/ api/ styles/ lib/
fixtures/
  scenarios/                10 MVP-acceptatiescenario's (input + verwachte uitkomst)
  recordings/               geanonimiseerde HA-opnames (na CAN-inventarisatie)
addon/
  config.yaml  Dockerfile  run.sh  translations/  DOCS.md
docker-compose.dev.yml      app + HA dev-instance + fake data feeder
docs/
  technisch-plan.md  adr/  signalen-calenta.md  werkwijze.md  design/
AGENTS.md / CLAUDE.md        conventies voor (AI-)ontwikkelaars
```

## 5. Teststrategie

- **Unit** per pipeline-stap op kleine, handgemaakte reeksen.
- **Property-based** (hypothesis): blokverwerking == geheelverwerking (FR-06); geen negatief verbruik bij resets; reconnect levert geen extra start op; onbekende tijd telt nooit als uit-tijd.
- **Scenario/golden tests**: de 10 MVP-acceptatiescenario's uit requirements §9 als fixtures (synthetische generator, zelfde vorm als de simulatie in het ontwerp) met verwachte bevindingen, beschikbaarheid en oordelen. Deze vormen samen de MVP-acceptatie.
- **API**: contracttests tegen OpenAPI.
- **Frontend**: vitest + Testing Library voor componenten, Playwright smoke per scherm tegen een seed-database.
- **E2E**: docker-compose met HA dev-instance en replay van fixtures.

## 6. Werkwijze voor parallelle agents

- **Contract eerst.** Mijlpaal M0 levert schema, pipeline-types, regel-interface, API-contract en frontend-fundament. Daarna kunnen vier lanes parallel: *ingest/kwaliteit*, *analyse/regels*, *bevindingen/wijzigingen*, *UI*.
- **Tickets** bevatten: context, scope, buiten scope, acceptatiecriteria, requirement-ID's, afhankelijkheden (`Depends on #n`), en welke modules ze raken (conflictvermijding).
- **Labels.** `type:*` (feature, refinement, spike, chore, test, docs), `area:*` (backend, analysis, ingest, frontend, ha, infra), `prio:M|S|L`, `status:ready|blocked|needs-refinement|in-progress|needs-human`.
- **Oppakken.** Alleen tickets met `status:ready`. Claim = jezelf toewijzen + `status:in-progress` + comment. Branch `<type>/<issue>-<slug>`, PR met `Closes #n`, CI groen, kleine PR's. Een GitHub Action zet `status:blocked → status:ready` zodra alle `Depends on`-issues gesloten zijn.
- **Refinement-tickets** leveren een ADR/document en waar nodig vervolgtickets; ze blokkeren de implementatietickets die ervan afhangen.
- **Definition of Done.** Tests (incl. relevante scenario's) groen, lint/typecheck groen, OpenAPI bijgewerkt, UI volgt ontwerp v3, documentatie bij wijziging gedrag, geen schrijfacties naar ketel/thermostaat.

## 7. Mijlpalen

| Mijlpaal | Inhoud |
|---|---|
| **M0 Fundament** | Scaffold, CI, add-on/compose, refinement datamodel/pipeline/regels/API/veroudering, CAN-inventarisatie, frontend-fundament, scenario-generator. |
| **M1 Data** | HA-client, opslag, historische import, signaalregister, installatieprofiel, bijzondere perioden, kwaliteit, bedrijfsmodi, beschikbaarheid, runner. |
| **M2 Analyse** | Cycli, statistieken, temperatuur, regels kort-branden / stop-tijdens-vraag / dataverlies / tapwater / hydraulisch. |
| **M3 Advies, terugkoppeling & UI (MVP)** | Bevindingen-engine, bundelen, aanbevelingen + opvolging, advieshistorie, wijzigingen + voor/na, HA-export, meldingen, alle schermen, MVP-acceptatie. |
| **M4 Uitbreiding (S)** | Comfort per ruimte, zones, mengverdeler, normaalgedrag-afwijking, verbruik + weerscorrectie, begeleide experimenten, aanvoerproef, rapporten, normaalgedragmodel. |
| **M5 Later (L)** | Natuurlijke-taaltoelichting door taalmodel (alleen op aangeleverde bevindingen). |

## 8. Open punten en risico's

| Punt | Aanpak |
|---|---|
| Welke CAN-signalen de Calenta Ace werkelijk levert, met welke resolutie en statuscodes. | Spike-ticket (vereist toegang tot de HA-instantie van de gebruiker); modus-mapping configureerbaar zodat implementatie niet blokkeert. |
| Veroudering bij alleen-bij-wijziging-events. | Refinement-ticket (zie §3.1). |
| REST-states zonder `unique_id`. | Herpublicatie; later eventueel MQTT discovery of eigen integratie. |
| Klokverschillen tussen bronnen. | Gebruik HA `last_changed`/`last_reported`, tolerantie per signaalcombinatie, kwaliteitsvlag. |
| SQLite-groei. | Retentie ruwe data + aggregaten; TimescaleDB-optie. |
| Zomertijd. | Alles UTC intern; tests rond 25 okt 2026 (DST-overgang). |
| Drempels zonder universele norm. | Alle drempels instelbaar, zichtbaar in UI en in snapshot vastgelegd. |
