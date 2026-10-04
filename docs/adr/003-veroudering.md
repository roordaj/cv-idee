# ADR-003 — Veroudering en verbindingsverlies bij alleen-bij-wijziging-events

- Status: voorgesteld
- Datum: 4 oktober 2026
- Issue: #9 · Requirements: FR-06, FR-07, FR-08, FR-11 · Acceptatiescenario 5 (requirements §9)
- Technisch plan: §3.1 (risico verouderingsdetectie), §8 · Bouwt voort op [ADR-002](002-pipeline.md) (§3.1, §3.4, §6, §7, §8)
- Ontwerp: [`docs/design/aanvullingen.md`](../design/aanvullingen.md) §1.5 sectie "Gegevens" (max. leeftijd en "Verwacht regelmatige updates" per signaal, opgeslagen in `signal_mappings`)
- Code: `backend/src/cvidee/analysis/types.py` (kleine contractwijzigingen, §12), docstrings van `timeline.py` en `quality.py`; tests in `backend/tests/analysis/test_types.py`
- Afnemers: #16/#17/#19 (ingest live, import, ontdubbelen), #23 (tijdlijn/kwaliteit), #26 (cycli), #27 (runner), #22 (instellingen)

## 1. Context

Home Assistant (HA) stuurt `state_changed` alleen als een toestand verandert. Een vlam die twee uur uit staat, levert twee uur lang geen enkel event. "Leeftijd van de laatste waarde" is daarom geen bruikbare maat voor veroudering: dan zou elke rustige standby-periode onbekend worden. Tegelijk geldt:

- een datagat mag nooit als uit-tijd tellen (FR-11);
- een reconnect mag geen kunstmatige branderstart geven (FR-08, scenario 5);
- een oude retourmeting wordt niet zonder kwaliteitsmelding met een nieuwe aanvoermeting gecombineerd (FR-07);
- live verwerking en import van dezelfde historie geven dezelfde cycli (FR-06, ADR-002 §6).

ADR-002 legde het contract al vast (`ObservationKind` change/confirm/poll, `UnknownReason`, `ConnectionEvent`, `Alignment`/`align_pair`, veroudering alleen vooruit). Dit ADR beslist **hoe** de ingest HA-gegevens omzet naar dat contract en **welke** regels de tijdlijn (#23) toepast, met testgevallen die #23 direct kan overnemen.

De CAN-inventarisatie (#5) is nog niet klaar. De beslissingen hieronder zijn daarom zo gekozen dat ze voor elke integratie werken (ESPHome, MQTT, eigen integratie). Alleen standaardwaarden hangen van #5 af; zie §11.

## 2. Wat Home Assistant werkelijk doet

Onderzocht in de HA-documentatie en de broncode (`home-assistant/core`, dev-branch, geraadpleegd 4 oktober 2026). Bronnen staan in §14.

| # | Feit | Bron |
|---|---|---|
| H1 | Een state heeft drie tijdstempels: `last_changed` (alleen bij toestandswijziging), `last_updated` (toestand of attributen gewijzigd), `last_reported` (elke keer dat de integratie de state schrijft, ook zonder wijziging). `last_reported` bestaat sinds HA 2024.3. | [S1], [S2] |
| H2 | Schrijft een integratie dezelfde toestand en dezelfde attributen, dan maakt HA **geen** nieuwe state: het bestaande object krijgt een nieuwe `last_reported`, en HA vuurt `state_reported` (niet `state_changed`). | [S1], [S6] `StateMachine.async_set` |
| H3 | `state_reported` kan niet zonder `event_filter` worden beluisterd (`EventBus.async_listen` gooit "Event filter is required"). Het WebSocket-commando `subscribe_events` geeft geen filter mee, dus een externe WebSocket-client kan `state_reported` **niet** abonneren. `subscribe_entities` luistert ook alleen naar `state_changed`. | [S6] `core.py`, [S7] `websocket_api/commands.py`, [S5] |
| H4 | In een `state_changed`-event bevat `old_state` de **bijgewerkte** `last_reported`: het laatste moment waarop de oude waarde nog werd gerapporteerd. | [S5], [S6] (docstring `State.last_reported`) |
| H5 | `state_changed` vuurt ook als alleen attributen wijzigen (dan `new_state.state == old_state.state`), en bij integraties met `force_update` ook bij gelijke toestand (dan zelfs nieuwe `last_changed`). | [S6] `async_set` (`same_state = … and not force_update`), [S8] |
| H6 | `get_states` (WebSocket) en `GET /api/states/<entity_id>` (REST) geven per state `last_changed`, `last_updated` én `last_reported` (`State.as_dict`). | [S6] `State.as_dict`, [S3] |
| H7 | De recorder luistert alleen naar `state_changed`. `last_reported_ts` van de **vorige** rij wordt bijgewerkt zodra de volgende `state_changed` binnenkomt; de laatste rij heeft dus nog een oude `last_reported_ts`. Er komen geen rijen bij voor alleen-gerapporteerde waarden. | [S5], [S9] `recorder/core.py` |
| H8 | De history-API (`GET /api/history/period/<start>`) geeft **nooit** `last_reported` terug (`get_significant_states_with_session` vraagt het niet op). Velden: `state`, `last_changed`, `last_updated` (+ `attributes`, `entity_id`). | [S3], [S10] `recorder/history/__init__.py` |
| H9 | `minimal_response`: tussenliggende items alleen `state` + `last_changed`, en items met **dezelfde toestand als het vorige item worden weggelaten** (attribuut-only en `force_update`-rijen verdwijnen). De tijd is `last_updated` van de rij, gelijk aan `last_changed` bij een echte toestandswijziging. | [S3], [S10] `_sorted_states_to_dict` |
| H10 | Het eerste item van een history-antwoord is de toestand **op** `start_time` (tenzij `skip_initial_state`), met als tijdstempel `start_time` zelf — een synthetisch peilmoment, geen wijziging. Rijen worden gefilterd op `start_time < last_updated < end_time` (beide grenzen exclusief). | [S10], [S11] `history/__init__.py` |
| H11 | `significant_changes_only` (standaard aan) laat voor de meeste domeinen alleen rijen met `last_changed == last_updated` door; voor toestandsignalen met `minimal_response` maakt dat geen verschil. | [S10] `_significant_states_stmt` |
| H12 | `unavailable` = de integratie kan de toestand niet leveren (apparaat onbereikbaar); `unknown` = er is (nog) geen waarde. Beide zijn gewone toestandswaarden, dus ze staan in `state_changed` én in de history. | [S2], [S8] |
| H13 | Integraties melden een verbroken gateway niet uniform: ESPHome zet alle entiteiten van een apparaat op `unavailable` als de API-verbinding wegvalt, en biedt optioneel een `status`-binary_sensor (device_class connectivity); MQTT-entiteiten worden `unavailable` via een availability-topic of na `expire_after`. Een gateway die wel met HA verbonden blijft maar de CAN-bus kwijt is, kan zijn laatste waarden gewoon blijven tonen. | [S12], [S13], [S14] |

**Gevolgen voor het ontwerp**

1. Live kan de app bevestigingen niet als eventstroom ontvangen (H3). Ze zijn wel op te vragen: `last_reported` bij een state-opvraging (H6) en in `old_state` bij elke wijziging (H4).
2. Historische import kent geen bevestigingen (H8, H9). Live en import verschillen dus onvermijdelijk in bewijs voor "nog steeds dezelfde waarde". Het ontwerp moet ervoor zorgen dat **cycli** daar niet van afhangen (§6.4).
3. Het eerste history-item en elke `get_states`-waarde zijn peilingen, geen overgangen (H10).

## 3. Signaalsoorten en geldigheid van een waarde

Elk signaal heeft in `signal_mappings` twee instellingen (ontwerp §1.5 "Gegevens per signaal"): `heartbeat_expected` ("Verwacht regelmatige updates") en `max_age` ("Max. leeftijd", alleen actief als de toggle aan staat). In de pipeline: `SignalConfig.heartbeat_expected` en `SignalConfig.max_age_ms`; `heartbeat_expected=True` vereist nu een positieve `max_age_ms` (§12).

### 3.1 Beslisregels

| | Alleen bij wijziging (`heartbeat_expected = False`) | Periodiek rapporterend (`heartbeat_expected = True`) |
|---|---|---|
| Bewijs dat de waarde geldt | De laatste waarneming; HA heeft geen nieuwere toestand gemeld. | `evidence_ts` van de laatste waarneming (wijziging, bevestiging of `last_reported` van een peiling). |
| Geldig tot | De volgende waarneming van het signaal, `unavailable`/`unknown`, een verbindingsgat (§5) of de horizon. | Als links, maar uiterlijk tot `evidence_ts + max_age`. |
| Verouderd (`STALE`) | **Nooit** op leeftijd. Uitval wordt alleen gezien via `unavailable`/`unknown`, de eigen WebSocket, de gateway-entiteit of afgeleide gateway-uitval (§5). | Vanaf `evidence_ts + max_age` tot de volgende waarneming. |
| Herkomst bij combineren (§7) | `ASSUMED_UNCHANGED` | `ALIGNED` of `MISALIGNED` op basis van bewijstijden |
| In historiebereik (§6) | Ongewijzigd. | Behandeld als alleen-bij-wijziging: geen veroudering, want history bevat geen bevestigingen. |

### 3.2 Toelichting

- **Veroudering is prospectief** (ADR-002 §3.1). `STALE` is een functie van de verzameling waarnemingen, niet van `now`. Een run met horizon vóór `evidence_ts + max_age` toont de waarde tot de horizon; een latere run toont vanaf dat punt `STALE`. Komt er later (late data) een bevestiging binnen met een tijdstempel in dat stuk, dan zet de runner het watermark terug (ADR-002 §4.6) en verdwijnt het `STALE`-stuk. Zo blijft "in blokken == in één keer" gelden.
- **Een bevestiging is geen overgang.** Een `CONFIRM` begint een nieuw `ValueInterval` met dezelfde waarde (intervallen worden niet samengevoegd, ADR-002 §3.1), maar cyclusdetectie ziet aaneengesloten intervallen met gelijke waarde als één toestand.
- **Na `STALE` komt de waarde terug** met de eerstvolgende waarneming. Een `CONFIRM` of `POLL` herstelt de waarde zonder overgang; een `CHANGE` na `STALE` is een waargenomen wijziging, maar omdat de voorafgaande toestand onbekend is, telt een vlam-aan daarna niet als start (§7).
- **Standaardwaarden** volgen het ontwerp: `heartbeat_expected` aan voor kamer- en buitentemperatuur, uit voor alle ketelsignalen tot #5 aantoont dat de integratie per signaal periodiek rapporteert (`last_reported` loopt op zonder wijziging). Standaard `max_age`: ketelsignalen 30 s; kamertemperaturen 10 min; buitentemperatuur 15 min; verdeler, zone/klep, pomp/debiet 1 min; gas en warmtemeter 1 u; bereik 5 s – 24 u.
- **Hulp bij instellen.** De kolom "Werkelijk" (ontwerp §1.5) toont het mediane interval tussen opeenvolgende `CHANGE`- en `CONFIRM`-waarnemingen van de laatste 24 u. Zijn er bevestigingen bij een signaal waarvoor de toggle uit staat, dan kan de UI een hint tonen ("Dit signaal lijkt regelmatig te rapporteren"). Dat is een suggestie, geen automatische omschakeling: de instelling hoort bij de configuratie-snapshot (`config_hash`).
- **Verschil met de StatusPill "Vertraagd".** De pil in de header ("laatste waarneming > 2 min", ontwerp §0.3) gaat over de hele app (komen er nog berichten binnen?), niet over één signaal. Die blijft bestaan naast de veroudering per signaal.

## 4. Van HA-bericht naar waarneming (ingest)

### 4.1 Tijdbasis

Waarnemingstijden komen uit HA-tijdstempels (`last_changed`, `last_reported`), niet uit de ontvangsttijd. Tijden die de app zelf bepaalt (peilmoment, verbinding op/neer) worden naar de HA-tijdbasis omgerekend met een geschatte klokafwijking: de mediaan van `received_at − time_fired` over de laatste 100 events (0 zolang die er niet is). In add-onmodus is die afwijking vrijwel nul (zelfde host). Een afwijking van meer dan 2 s wordt gelogd en getoond op Gegevenskwaliteit. Tijden worden afgerond naar beneden op hele milliseconden.

### 4.2 Toewijzing

| HA-bericht | Waarneming | `ts` | Opmerking |
|---|---|---|---|
| `state_changed`, `new_state.state ≠ old_state.state` | `CHANGE` (nieuwe waarde) | `new_state.last_changed` | Echte overgang (H1). |
| idem, en `old_state.last_reported > old_state.last_updated` | **eerst** `CONFIRM` (oude waarde) | `old_state.last_reported` | Laatste bewijs voor de oude waarde (H4); dezelfde informatie die de recorder als `last_reported_ts` bewaart (H7). |
| `state_changed`, `new_state.state == old_state.state` (attribuutwijziging of `force_update`) | `CONFIRM` | `new_state.last_updated` | Geen overgang (H5). |
| `state_changed`, `old_state` ontbreekt (nieuwe entiteit, HA-start) | `CHANGE` | `new_state.last_changed` | Voorafgaand is `NO_DATA`/onbekend, dus geen start (§7). |
| `state_changed`, `new_state` ontbreekt (entiteit verwijderd) | `CHANGE` met `value = None` | `time_fired` | Daarna `UNAVAILABLE`. |
| toestand `unavailable` of `unknown` | waarneming met `value = None` | zoals hierboven | → `UnknownReason.UNAVAILABLE` (H12). |
| `get_states` bij (her)verbinden | `POLL` per gekoppelde entiteit, `last_reported` = HA-`last_reported` | peilmoment = `ts` van het `ConnectionEvent(WS, up)` | Mag `last_reported < ts` hebben (§4.3). |
| Bevestigingspeiling (§4.4) | `CONFIRM` als waarde gelijk is en `last_reported` is opgeschoven | HA-`last_reported` | Anders niets opslaan. |
| Herstelpeiling (§5.4) | `POLL` per gateway-signaal | peilmoment | |

Aanvullende ingestregels:

- **Een `CONFIRM` heeft altijd de waarde van de voorgaande waarneming van dat signaal.** Wijkt de waarde toch af (race, bug), dan behandelt de tijdlijn de waarneming als `POLL`: nooit als overgang (test T14).
- **Botsende milliseconden.** Twee `CHANGE`s van één entiteit die na afronding dezelfde ms krijgen, worden in HA-volgorde opgeschoven naar de eerstvolgende vrije ms. Live en import zien dezelfde µs-volgorde, dus de uitkomst is gelijk (test I9).
- **Ontdubbelen** (FR-08): een waarneming met dezelfde `(signal, ts, value)` als een bestaande wordt niet opgeslagen; de sterkste soort blijft staan (`CHANGE` > `CONFIRM` > `POLL`). De pipeline doet hetzelfde defensief en meldt het aantal als `QualityEvent(DUPLICATE)`.
- **Waarden** worden genormaliseerd zoals in ADR-002 (`float`/`bool`/`str`); een niet-parseerbare waarde wordt als tekst bewaard en in stap 2 `INVALID`.

### 4.3 Peiling met oude bewijstijd

Een `get_states` na herverbinden geeft de toestand die HA *nu* heeft, met de `last_reported` waarop HA die waarde voor het laatst van de integratie hoorde. Voor een periodiek rapporterend signaal kan dat lang geleden zijn (de integratie is stil gevallen terwijl HA de oude waarde laat staan). Daarom mag een `POLL`-waarneming `last_reported < ts` hebben; `evidence_ts` is dan ouder dan het peilmoment. Is `evidence_ts + max_age ≤ ts`, dan is het signaal direct vanaf het peilmoment `STALE` (test T11). Voor `CHANGE` en `CONFIRM` blijft `last_reported ≥ ts` verplicht. Dit is de enige wijziging aan `Observation` (§12).

### 4.4 Bevestigingspeiling voor periodieke signalen

Omdat `state_reported` niet via de WebSocket te volgen is (H3), haalt de ingest voor elk signaal met `heartbeat_expected` periodiek `GET /api/states/<entity_id>` op (alleen lezen, toegestaan volgens AGENTS.md):

- interval = kleinste `max_age` van de periodieke signalen ÷ 3, begrensd op [5 s, 60 s] (standaard dus 10 s);
- `CONFIRM` opslaan als de toestand gelijk is aan de laatst opgeslagen waarde **en** `last_reported` minstens `max_age ÷ 3` later is dan het laatst opgeslagen bewijs; anders niets;
- wijkt de toestand af, dan niets opslaan: de `state_changed`-stroom is leidend voor overgangen;
- een mislukte peiling levert geen waarneming en geen verbindingsgebeurtenis op; het signaal veroudert dan vanzelf, wat eerlijk is.

Volume: zes ketelsignalen elke 10 s ≈ 52k rijen per dag, binnen de raming van plan §3.2. Voorwaarde: peilinterval + vertraging in HA < `settle` (2 min), anders komen bevestigingen als late data binnen en zet elke peiling het watermark terug.

## 5. Verbindingen

### 5.1 Eigen WebSocket (`ConnectionSource.WS`)

- **Neer** (`up = False`): `ts` = tijdstip van het laatste bericht dat van HA is ontvangen (ping/pong elke 20 s). Dat is het laatste moment waarvoor de app kan instaan; de tijd daarna is onbekend.
- **Op** (`up = True`): volgorde bij herverbinden is authenticeren → `subscribe_events(state_changed)` → `get_states`. `ts` van het op-event = peilmoment van `get_states`, en tegelijk de `ts` van alle `POLL`s. Een `state_changed` die tussen abonneren en peilen binnenkomt met een HA-tijd vóór het peilmoment, valt in het gat en wordt dus gemaskeerd (test T9): liever een gemiste start dan een kunstmatige.
- **App-herstart of crash**: de ingest bewaart elke minuut `ingest_alive_at`. Bij het opstarten schrijft hij, als het laatste WS-event "op" was, eerst `ConnectionEvent(WS, up=False, ts=ingest_alive_at)`.
- Zonder enig WS-event (ook geen carry-in) beschouwt de tijdlijn de WebSocket als **op**. Dat geldt alleen voor periodes vóór de eerste live verbinding, die door een import worden afgedekt (§6).

### 5.2 Gateway-connectiviteitsentiteit (optioneel, `ConnectionSource.CAN_GATEWAY`)

- Configureerbaar in de signaalkoppeling: één HA-entiteit die de verbinding van de CAN-gateway weergeeft (bijv. een binary_sensor met device_class connectivity, H13).
- De ingest slaat de toestanden ervan op als gewone waarnemingen van die entiteit, live én bij import (ADR-001 B2: ruwe data per HA-entiteit). Bij het lezen voor een run zet de store ze om in `ConnectionEvent(CAN_GATEWAY, up=…)` met `ts` van de waarneming: `on` → op; `off`, `unavailable` en `unknown` → neer (behoudend). Een gelijke waarde na een gelijke waarde is idempotent.
- Effect: alleen signalen met `via_can_gateway` worden `DISCONNECTED`.
- Wordt een andere gateway-entiteit gekozen, dan is dat een gewone configuratiewijziging: nieuwe `config_hash`, en de runner herberekent vanaf `valid_from` (ADR-002 §4.6). Er hoeft niets opnieuw geïmporteerd te worden, zolang de ingest de entiteit al volgde. Een nieuw gekozen entiteit wordt vanaf dat moment gevolgd, en waar mogelijk uit de HA-historie aangevuld.

### 5.3 Afgeleide gateway-uitval

Een gateway die met HA verbonden blijft maar de CAN-bus kwijt is, laat zijn laatste waarden staan (H13). Een vlam die op "aan" blijft staan, zou dan een cyclus van uren geven. Als er periodieke signalen via dezelfde gateway zijn, ziet de app dat toch:

- **Regel**: met `PipelineConfig.derive_gateway_outage` (standaard aan) en minstens één signaal met `heartbeat_expected` en `via_can_gateway`: de gateway geldt als **neer** op elk moment buiten historiebereik waarop **al** die signalen onbekend zijn met reden `STALE` of `UNAVAILABLE`, en minstens één daarvan `STALE` is.
- **Effect**: zoals een expliciete gateway-uitval: signalen met `via_can_gateway` worden `DISCONNECTED`; `QualityEvent(CONNECTION_LOST, source=CAN_GATEWAY, detail="derived")`.
- **Einde**: zodra één van die periodieke signalen weer een waarde heeft.
- De regel is deterministisch: hij wordt berekend uit de stap-1-tijdlijnen van de periodieke signalen (twee passen binnen `build_timelines`).
- Zonder periodieke gateway-signalen (de standaard tot #5) doet de regel niets. Er blijft dan een restrisico: een stilgevallen gateway zonder `unavailable` en zonder connectiviteitsentiteit is niet te zien. Dit restrisico staat op Gegevenskwaliteit vermeld zolang geen enkel gatewaysignaal periodiek rapporteert.

### 5.4 Na een gat: geen overdracht, wel een herstelpeiling

- **Een waarde van vóór een gat geldt er niet na.** Na een uitval (WS, gateway expliciet of afgeleid) blijft een getroffen signaal `DISCONNECTED` tot zijn eerstvolgende waarneming.
- **WS**: de `POLL`s van §5.1 vallen samen met het op-event, dus er is geen staart.
- **Gateway** (expliciet of afgeleid): de ingest doet een **herstelpeiling** (`POLL` via `GET /api/states/<entity_id>` voor alle `via_can_gateway`-signalen):
  - 30 s na een `CAN_GATEWAY`-op-event, zodat de integratie zijn waarden heeft kunnen verversen;
  - direct, zodra een periodiek gatewaysignaal weer rapporteert na een stilte langer dan zijn `max_age` (dit spiegelt §5.3; de ingest kan het zelf zien).
- Bij **import** is de equivalente herstelpeiling de recorder-toestand op `up + 30 s` (history-opvraging met beginstand); afgeleide uitval bestaat in historiebereik niet (§6).

### 5.5 Voorrang per signaal

Voor elk tijdstip, per signaal, de eerste die van toepassing is:

1. WS neer en niet afgedekt door historie → `DISCONNECTED`
2. `via_can_gateway` en gateway neer (expliciet of afgeleid) → `DISCONNECTED`
3. Na een gat uit 1–2 en nog geen nieuwe waarneming → `DISCONNECTED`
4. Laatste waarneming heeft `value = None` → `UNAVAILABLE`
5. Periodiek signaal, buiten historiebereik, en `t ≥ evidence_ts + max_age` → `STALE`
6. Geen waarneming vóór `t` → `NO_DATA`
7. Anders: `ValueInterval` van de laatste waarneming

Stap 2 (`apply_quality`) kan daarna nog `INVALID`/`IMPLAUSIBLE` maken. Voor gecombineerde signalen geldt de vaste voorrang van `unknown_union` (ADR-002 §8).

## 6. Historische import: dezelfde waarnemingenstroom

### 6.1 Opvraging

`GET /api/history/period/<start>?filter_entity_id=…&end_time=…&minimal_response&no_attributes` in blokken van 24 u (plan §3.1). `significant_changes_only` blijft standaard (H11). Opeenvolgende blokken overlappen 1 ms (`start = vorig einde − 1 ms`) omdat beide grenzen exclusief zijn (H10); de dubbele rij valt weg bij het ontdubbelen.

### 6.2 Toewijzing

| History-item | Waarneming |
|---|---|
| tussenliggend item (toestand ≠ vorige, H9) | `CHANGE`, `ts = last_changed` — gelijk aan de live `CHANGE` (H1, H9) |
| `unavailable`/`unknown` | `value = None`, net als live |
| eerste item van het **eerste** blok van een initiële import | `POLL` op `start` (H10: synthetisch peilmoment) |
| eerste item van volgende blokken | niet opslaan (de waarde is bekend uit het vorige blok); wel controleren dat de entiteit aanwezig is |
| herstelpeiling na `CAN_GATEWAY` op (§5.4) | `POLL` op `up + 30 s` met de recorder-toestand op dat moment |

Er ontstaan bij import **geen** `CONFIRM`s: de history-API levert geen `last_reported` (H8) en laat herhaalde toestanden weg (H9).

### 6.3 Historiebereik (`ConnectionSource.HISTORY`)

Een import markeert het bereik dat hij afdekt met `ConnectionEvent(HISTORY, up=True)` aan het begin en `up=False` aan het eind. Pas als **alle** gekoppelde entiteiten voor het hele bereik zijn opgehaald, worden de waarnemingen en de twee events in één transactie geschreven. Ontbreekt een entiteit in de recorder (uitgesloten of al opgeruimd), dan wordt het bereik niet gemarkeerd en blijft een eventueel gat `DISCONNECTED`.

Binnen historiebereik:

- maskeert een WS-uitval niet: de recorder heeft de wijzigingen in die periode vastgelegd;
- is er geen veroudering op leeftijd en geen afgeleide gateway-uitval: er zijn geen bevestigingen om op te steunen;
- geeft `align_pair` periodieke signalen `heartbeat=False` mee (§7).

Twee toepassingen:

1. **Initiële import** (eerste installatie): bereik `[import_start, eerste WS-op)`.
2. **Gat aanvullen**: na herverbinden haalt de ingest het gat `[WS neer, WS op)` uit de historie, zodra `now − WS op > settle`. Hij gebruikt de beginstand alleen als controle; wijkt die af van de laatst bekende waarde, dan wordt het een `POLL` op het begin van het gat, nooit een `CHANGE`. Wat binnen het gat in de recorder staat, zijn echte, door HA vastgelegde overgangen. Die tellen dus mee (test T19).

Import overschrijft **nooit** een bereik waarin de app live verbonden was. De eigen database is de bron voor herberekening (ADR-002 §4.6–4.7).

### 6.4 Pariteit live ↔ import (FR-06)

- **Overgangen zijn gelijk.** Een live `CHANGE` en een history-item hebben dezelfde HA-`last_changed` en dezelfde waarde. `unavailable`/`unknown` staan in beide.
- **Bevestigingen zijn er alleen live.** Ze beïnvloeden alleen veroudering (§3) en tijdafstemming (§7), en veroudering staat in historiebereik uit. Voor een signaal **zonder** `heartbeat_expected` zijn tijdlijn en cycli daarom identiek. Een vlamsignaal is in de praktijk alleen-bij-wijziging (te bevestigen door #5).
- **Gedocumenteerde uitzondering.** Bij een periodiek vlamsignaal kan live een `STALE`-stuk of een afgeleide gateway-uitval zien die in de historie onzichtbaar is: de gateway was stil, maar HA liet de oude waarde staan. Live is dan behoudender (`DATA_GAP` in plaats van een doorlopende cyclus). Omdat import nooit over live bereik schrijft, leidt dit niet tot tegenstrijdige opgeslagen cycli. De pariteitstest van #19 gebruikt alleen-bij-wijziging-signalen of een historie zonder stiltes langer dan `max_age`.
- **Gepaarde kengetallen** (ΔT, overshoot) kunnen op geïmporteerde data een lagere dekking hebben, omdat periodieke signalen daar als alleen-bij-wijziging gelden (§7). Ze kunnen nooit een *andere* waarde krijgen.

## 7. Peiling versus overgang en cyclusdetectie

**Begrippen**

- **Overgang**: een `CHANGE` waarvan de waarde verschilt van een **bekende** voorgaande waarde van hetzelfde signaal. Alleen overgangen kunnen een cyclusgrens zijn.
- **Peiling**: een `POLL` (reconnect, herstelpeiling, beginstand van een import). Een peiling stelt een waarde vast zonder te zeggen wanneer die ontstond.
- **Bevestiging**: een `CONFIRM` (dezelfde waarde, extra bewijs).

**Regels voor `detect_cycles`** (#26; ADR-002 §3.4 blijft geldig)

1. Aaneengesloten `ValueInterval`s met dezelfde vlamwaarde vormen één toestand, ongeacht `origin` (`CONFIRM`/`POLL` splitsen geen cyclus).
2. **Start** (`start_observed = True`): een vlam-aan-interval met `origin = CHANGE`, direct voorafgegaan door een `ValueInterval` met vlam uit. Dat interval mag zelf `CHANGE`, `CONFIRM` of `POLL` zijn: een peiling "uit" gevolgd door een wijziging naar "aan" is een waargenomen start (T7, T21).
3. **Geen start** (`start_observed = False`, telt nooit als start) als vlam-aan begint met een `POLL` of `CONFIRM`, of direct volgt op een `UnknownInterval` (welke reden ook), of op `context_start` ligt. Dit is de kern van scenario 5: na een reconnect geeft een peiling "aan" een cyclus met onbekend begin, geen start (T8, T9, T10).
4. **Einde** is de eerste bekende vlam-uit. Wordt de vlam onbekend tijdens branden, dan eindigt de cyclus aan het begin van het onbekende stuk met `DATA_GAP`, en de duur is een ondergrens.
5. **Pauze** (`pause_before_ms`) alleen als de vlam ertussen de hele tijd bekend uit was; tijd met onbekende vlam is nooit pauze en nooit uit-tijd (FR-11).
6. **Een datagat telt nooit als herstel** (scenario 5): het hoort niet bij de tijdsbasis van kengetallen en dus ook niet bij herstelcriteria (ADR-002 §8).

## 8. Tijdafstemming bij combineren (FR-07)

Combinaties gaan via `quality.align_pair(a, b, ts, tolerance, a_heartbeat=…, b_heartbeat=…)` (ADR-002 §7). Formalisering:

- `E_x` = `observed_at` van het interval van signaal x op `ts` (bewijstijd).
- `C_x` = `observed_at` van het laatste interval van x op of vóór `ts` met `origin ∈ {CHANGE, POLL}` (laatste verse aflezing van een waarde).
- `hb_x` = `heartbeat_expected` van x, maar `False` als `ts` in historiebereik valt. De aanroeper bepaalt dit uit de `HISTORY`-dekking; `align_pair` zelf blijft ongewijzigd.
- Tolerantie `tol` = `pair_tolerance(config, a, b)`, standaard 30 s (`default_pair_tolerance_ms`), per paar instelbaar.

| Situatie | `alignment` | Gevolg |
|---|---|---|
| a of b onbekend op `ts` | `None` | paar onbekend; telt niet in de tijdsbasis; geen `MISALIGNED`-event (het onbekende signaal heeft al een eigen event) |
| `hb_a` en `hb_b`, `|E_a − E_b| ≤ tol` | `ALIGNED` | combineren |
| `hb_a` en `hb_b`, `|E_a − E_b| > tol` | `MISALIGNED` | niet combineren; event |
| a alleen-bij-wijziging en `C_b − E_a > tol`, of b alleen-bij-wijziging en `C_a − E_b > tol` | `MISALIGNED` | niet combineren; event. De andere kant is ná het laatste bewijs van het stille signaal duidelijk veranderd. |
| anders, met minstens één alleen-bij-wijziging | `ASSUMED_UNCHANGED` | combineren met zwakkere herkomst; onderbouwing vermeldt "aangenomen ongewijzigd" |

**Bemonstering.** Consumenten (#29) bemonsteren op elke intervalgrens van a of b binnen het bereik dat ze nodig hebben. Opeenvolgende `MISALIGNED`-monsters vormen één `QualityEvent(MISALIGNED, signal=a, other_signal=b)` van eerste tot laatste afgekeurd monster, gesplitst op het raster. `a`/`b` volgen de volgorde van `SignalRef` (a < b), zodat de sleutel deterministisch is.

## 9. Kwaliteitsgebeurtenissen

Alle gebeurtenissen zijn `QualityEvent`s met sleutel `key = (kind, signal, other_signal, source, start)` (§12), gesplitst op het canonieke raster (ADR-002 §4.5), `end = None` zolang ze lopen op de horizon. `final` zet de pipeline op basis van het watermark.

| `QualityEventKind` | Wanneer | `signal` | `source` | `other_signal` | `count` | `detail` | Plan §3.2 |
|---|---|---|---|---|---|---|---|
| `DATA_GAP` | `UnknownReason.NO_DATA` (geen waarneming) | signaal | – | – | – | – | uitval |
| `STALE` | `UnknownReason.STALE` | signaal | – | – | – | `max_age_s=<n>` | te oud |
| `UNAVAILABLE` | `UnknownReason.UNAVAILABLE` | signaal | – | – | – | – | uitval |
| `CONNECTION_LOST` | een bron is neer: effectieve WS-gaten (na aftrek van historiebereik) en `CAN_GATEWAY` (expliciet of afgeleid). **Eén per bron, niet per signaal**; de `DISCONNECTED`-intervallen van signalen geven geen eigen event. | `None` | `WS` / `CAN_GATEWAY` | – | – | `derived` bij afgeleide uitval | uitval |
| `INVALID` | waarde van verkeerd type | signaal | – | – | – | ruwe waarde (afgekapt op 40 tekens) | – |
| `IMPLAUSIBLE` | buiten `[plausible_min, plausible_max]` | signaal | – | – | – | `min..max` | onwaarschijnlijk |
| `COUNTER_RESET` | daling van een cumulatieve teller; puntgebeurtenis `start == end` | signaal | – | – | – | `<oud>-><nieuw>` | tellerreset |
| `DUPLICATE` | exacte dubbele waarnemingen weggelaten; één per signaal per rastervak `[uur, uur+1)` | signaal | – | – | aantal ≥ 1 | – | ontdubbeld |
| `MISALIGNED` | combinatie buiten tolerantie (§8) | a | – | b | – | `max_skew_ms=<n>` | – |

`detail` is kort en machineleesbaar; de UI maakt er Nederlandse tekst van ("CAN-data 30 minuten onderbroken", "Retour te oud om met aanvoer te combineren"). `HISTORY` levert geen kwaliteitsgebeurtenis op: een aangevuld gat is geen gat.

Er komt **geen** nieuw soort voor klokafwijking. Die wordt in de ingest gemeten en op Gegevenskwaliteit getoond (§4.1); ze is geen eigenschap van een signaalinterval.

## 10. Testgevallen

### 10.1 Notatie

- Tijden in seconden vanaf T0 (T0 op een heel UTC-uur), context `[0, end)`, WS op tenzij anders vermeld.
- Waarnemingen: `C(t,v)` = `CHANGE`, `F(t,v)` = `CONFIRM`, `P(t,v[,lr])` = `POLL` met optionele `last_reported`. `v = –` betekent `None` (`unavailable`/`unknown`).
- Verbindingen: `WS↓t`/`WS↑t`, `GW↓t`/`GW↑t` (`CAN_GATEWAY`), `H↑t`/`H↓t` (`HISTORY`).
- Uitvoer: `V(start,end,waarde,observed_at,origin)` en `U(start,end,reden)`.

Signalen: `FLAME` alleen-bij-wijziging; `FLOW` periodiek met `max_age = 30 s`; `via_can_gateway` alleen waar vermeld. Bij cycli: warmtevraag niet gekoppeld, dus eindreden `UNDETERMINED` waar niet anders vermeld.

### 10.2 Tijdlijn (`build_timeline` / `build_timelines`, #23)

| # | Geval | Invoer | Verwachte intervallen | Verwachte cycli / events |
|---|---|---|---|---|
| T1 | Lange stilte, alleen-bij-wijziging | FLAME `C(0,off)`; end 7200 | `V(0,7200,off,0,change)` | geen events |
| T2 | Periodiek met bevestigingen | FLOW `C(0,50) F(20,50) F(40,50)`; end 60 | `V(0,20,50,0,change) V(20,40,50,20,confirm) V(40,60,50,40,confirm)` | geen |
| T3 | Periodiek verouderd | FLOW `C(0,50)`; end 100 | `V(0,30,50,0,change) U(30,100,stale)` | `STALE(flow,30,None)` |
| T4 | Herstel na veroudering | FLOW `C(0,50) F(50,50)`; end 70 | `V(0,30,…) U(30,50,stale) V(50,70,50,50,confirm)` | `STALE(flow,30,50)` |
| T5 | Prospectief, late bevestiging | FLOW `C(0,50)`; run 1 end 20; run 2 end 100; run 3 end 100 plus late `F(25,50)` | run 1 `V(0,20,…)`; run 2 = T3; run 3 `V(0,25,…) V(25,55,50,25,confirm) U(55,100,stale)` | run 3 `STALE(flow,55,None)`; geen `STALE` op 30 |
| T6 | `unavailable` | FLAME `C(0,off) C(600,–) C(900,on) C(1200,off)`; end 1800 | `V(0,600,off) U(600,900,unavailable) V(900,1200,on,900,change) V(1200,1800,off)` | cyclus 900–1200 `start_observed=False`, `complete=False`; starts 0; `UNAVAILABLE(flame,600,900)` |
| T7 | Scenario 5: gat, peiling uit, dan start | FLAME `C(0,off)`, `WS↓600 WS↑2400`, `P(2400,off) C(2700,on) C(3000,off)`; end 3600 | `V(0,600,off) U(600,2400,disconnected) V(2400,2700,off,2400,poll) V(2700,3000,on,2700,change) V(3000,3600,off)` | cyclus 2700–3000 compleet, telt als start; starts 1; `CONNECTION_LOST(ws,600,2400)`; waargenomen tijd 1800 s |
| T8 | Scenario 5: reconnect tijdens branden | FLAME `C(0,off) C(300,on)`, `WS↓600 WS↑2400`, `P(2400,on) C(2880,off)`; end 3600 | `V(0,300,off) V(300,600,on,300,change) U(600,2400,disconnected) V(2400,2880,on,2400,poll) V(2880,3600,off)` | A: 300→600 `DATA_GAP`, duur ≥ 300, `start_observed=True`; B: 2400→2880 `start_observed=False`, `complete=False`; starts 1 (geen kunstmatige start op 2400) |
| T9 | Wijziging net vóór het op-event | FLAME `C(0,off)`, `WS↓600 WS↑2400`, `C(2399,on) P(2400,on)`; end 3000 | `V(0,600,off) U(600,2400,disconnected) V(2400,3000,on,2400,poll)` | cyclus vanaf 2400 `start_observed=False`; starts 0 |
| T10 | HA-herstart | FLAME `C(0,off)`, `WS↓600 WS↑660`, `P(660,–) C(690,off) C(1200,on) C(1500,off)`; end 1800 | `V(0,600,off) U(600,660,disconnected) U(660,690,unavailable) V(690,1200,off,690,change) V(1200,1500,on) V(1500,1800,off)` | cyclus 1200–1500 compleet, telt als start |
| T11 | Peiling met oude `last_reported` | FLOW `C(0,50) F(20,50)`, `WS↓30 WS↑600`, `P(600,50,lr=300)`; end 700 | `V(0,20,…) V(20,30,50,20,confirm) U(30,600,disconnected) U(600,700,stale)` | `CONNECTION_LOST(ws,30,600)`, `STALE(flow,600,None)` |
| T12 | Peiling met verse `last_reported` | als T11 met `P(600,50,lr=590)` | `… U(30,600,disconnected) V(600,620,50,590,poll) U(620,700,stale)` | `STALE(flow,620,None)` |
| T13 | Duplicaten | FLAME `C(0,off) C(0,off) P(0,off)`; end 3600 | `V(0,3600,off,0,change)` | `DUPLICATE(flame,0,3600,count=2)` |
| T14 | Afwijkende bevestiging | FLAME `C(0,off) F(100,on)`; end 200 | `V(0,100,off) V(100,200,on,100,poll)` | cyclus vanaf 100 `start_observed=False` |
| T15 | Gateway-entiteit | FLAME `via_can_gateway`: `C(0,off)`, `GW↓600 GW↑1200`, `P(1230,off) C(1500,on)`; end 1800 | `V(0,600,off) U(600,1230,disconnected) V(1230,1500,off,1230,poll) V(1500,1800,on,1500,change)` | cyclus vanaf 1500 telt als start; `CONNECTION_LOST(can_gateway,600,1200)` |
| T16 | Gateway raakt niet-gatewaysignaal niet | als T15 plus ROOM_TEMPERATURE (niet `via_can_gateway`) `C(0,20.5)` | ROOM `V(0,1800,20.5,0,change)` | – |
| T17 | Afgeleide gateway-uitval | FLOW (`via_can_gateway`) `C(0,50) F(10,50) F(20,50) F(30,50) F(200,50)`; FLAME (`via_can_gateway`) `C(0,off) P(201,off)`; end 300 | FLOW `V(0,10) V(10,20) V(20,30) V(30,60,50,30,confirm) U(60,200,stale) V(200,300,50,200,confirm)`; FLAME `V(0,60,off) U(60,201,disconnected) V(201,300,off,201,poll)` | `STALE(flow,60,200)`, `CONNECTION_LOST(can_gateway,60,200,detail=derived)` |
| T18 | Gedeeltelijk verouderd, geen afleiding | als T17 plus RETURN (periodiek, `via_can_gateway`) met `F` elke 10 s tot 300 | FLOW als T17; FLAME `V(0,300,off,0,change)` | alleen `STALE(flow,60,200)` |
| T19 | Gat aangevuld uit historie | FLAME live `C(0,off)`, `WS↓600`; import `H↑600 C(1200,on) C(1500,off) H↓2400`; `WS↑2400 P(2400,off)`; end 3000 | `V(0,1200,off,0,change) V(1200,1500,on,1200,change) V(1500,2400,off,1500,change) V(2400,3000,off,2400,poll)` | cyclus 1200–1500 compleet, telt als start; geen `CONNECTION_LOST` |
| T20 | Geen veroudering in historiebereik | FLOW `H↑0 C(0,50) C(600,52) H↓1200`, `WS↑1200 P(1200,52,lr=1195)`; end 1300 | `V(0,600,50,0,change) V(600,1200,52,600,change) V(1200,1225,52,1195,poll) U(1225,1300,stale)` | `STALE(flow,1225,None)` |
| T21 | Initiële import, beginstand is peiling | FLAME `H↑0 P(0,off) C(300,on) C(600,off)`; end 900 | `V(0,300,off,0,poll) V(300,600,on,300,change) V(600,900,off)` | cyclus 300–600 compleet, telt als start |
| T22 | Carry-in na gat | FLAME carry-in `C(-100,on)` vóór `context_start=0`, carry-in WS-event `WS↓-50`; `WS↑120 P(120,on)`; end 300 | `U(0,120,disconnected) V(120,300,on,120,poll)` | geen start |

### 10.3 Ingest (#17, #19)

| # | HA-invoer | Verwachte waarneming(en) |
|---|---|---|
| I1 | `state_changed` off→on, `new.last_changed = t` | `C(t,on)` |
| I2 | `state_changed` met `new.state == old.state` (attribuut of `force_update`), `new.last_updated = u` | `F(u,v)` |
| I3 | `state_changed` off→on op t, `old.last_reported = r > old.last_updated` | `F(r,off)`, `C(t,on)` |
| I4a | Bevestigingspeiling: zelfde waarde, `last_reported` opgeschoven ≥ `max_age/3` | `F(last_reported,v)` |
| I4b | Bevestigingspeiling: `last_reported` niet opgeschoven, of minder dan `max_age/3` | niets |
| I4c | Bevestigingspeiling: andere waarde dan opgeslagen | niets (wachten op `state_changed`) |
| I5 | `state_changed` met `new_state = None` op `time_fired = t` | `C(t,–)` |
| I6 | Toestand `unavailable` of `unknown` | waarneming met `value = None` |
| I7 | Herverbinden: `get_states` op peilmoment p | `WS↑p` en per gekoppelde entiteit `P(p,v,lr=last_reported)` |
| I8 | Initiële import, eerste blok: items `[start: off, 300: on, 600: off]` | `H↑start`, `P(start,off)`, `C(300,on)`, `C(600,off)`, `H↓` op importeinde |
| I9 | Twee wijzigingen op 1000,2 ms (50,0) en 1000,7 ms (50,1) | `C(1000,50.0)`, `C(1001,50.1)` — live en import gelijk |
| I10 | Blokgrens: rij exact op het einde van blok n | precies één waarneming (overlap 1 ms + ontdubbelen) |
| I11 | Gat aanvullen: beginstand wijkt af van de laatst bekende waarde | `P(gat_begin,v)` — nooit `C` |
| I12 | Gat aanvullen: één gekoppelde entiteit ontbreekt in de recorder | niets opgeslagen, geen `HISTORY`-events |
| I13 | Gateway-entiteit `on→off→unavailable→on` op t1..t4 | vier gewone waarnemingen; bij lezen `GW↓t2`, (t3 idempotent neer), `GW↑t4`; herstelpeiling `P(t4+30 s)` voor alle `via_can_gateway`-signalen |
| I14 | App-crash, herstart; `ingest_alive_at = a`, laatste WS-event was op | eerst `WS↓a`, daarna normaal herverbinden (I7) |

### 10.4 Tijdafstemming (`align_pair`, #23/#29), tolerantie 30 s

| # | a (aanvoer) | b (retour) | ts | Verwacht |
|---|---|---|---|---|
| A1 | periodiek, E=100 | periodiek, E=110 | 115 | `ALIGNED` |
| A2 | periodiek, E=100 | periodiek, E=140 | 145 | `MISALIGNED` |
| A3 | periodiek, C=10, E=20 | alleen-bij-wijziging, C=E=0 | 25 | `ASSUMED_UNCHANGED` (C_a − E_b = 10 ≤ 30) |
| A4 | periodiek, C=50 | alleen-bij-wijziging, E=0 | 55 | `MISALIGNED` (50 > 30) |
| A5 | periodiek, C=0, bevestigd tot E=300 | alleen-bij-wijziging, E=0 | 305 | `ASSUMED_UNCHANGED` (a niet veranderd) |
| A6 | beide alleen-bij-wijziging, C=E=0 en C=E=40 | | 45 | `MISALIGNED` (C_b − E_a = 40 > 30) |
| A7 | periodiek | onbekend (`STALE`) | – | `None`, geen `MISALIGNED`-event |
| A8 | periodiek, E=100, maar ts in historiebereik (hb=False) | periodiek, E=140, C=140 | 145 | `MISALIGNED` via de alleen-bij-wijzigingregel (C_b − E_a = 40 > 30) |

### 10.5 Kwaliteitsgebeurtenissen (`apply_quality`, #23)

| # | Situatie | Verwachte events |
|---|---|---|
| Q1 | WS neer 600–2400 (T7), 15 signalen | precies één `CONNECTION_LOST(None,source=ws,600,2400)`; geen events per signaal |
| Q2 | WS neer 3000–4200 (over een uurgrens) | `CONNECTION_LOST(ws,3000,3600)`, `CONNECTION_LOST(ws,3600,4200)` |
| Q3 | WS- en gateway-uitval beginnen beide op 600 | twee events met verschillende `key` (`source` ws / can_gateway) |
| Q4 | Gasteller 1234,5 → 0,4 op t | `COUNTER_RESET(gas,t,t,detail="1234.5->0.4")` |
| Q5 | 3 exacte dubbelen in uur 0, 1 in uur 1 | `DUPLICATE(…,0,3600,count=3)`, `DUPLICATE(…,3600,7200,count=1)` |
| Q6 | Aanvoer tegelijk misaligned met retour en met gewenste aanvoer | twee `MISALIGNED` met verschillende `other_signal` |
| Q7 | `STALE` nog actief op de horizon | `end = None`, `final = False` |
| Q8 | Gat volledig aangevuld uit historie (T19) | geen `CONNECTION_LOST` |

## 11. Te bevestigen door #5

De beslisregels hangen niet van de CAN-inventarisatie af; deze punten bepalen alleen standaardwaarden en welke optionele mechanismen actief zijn.

1. **Welke integratie** levert de CAN-gegevens (ESPHome, MQTT, eigen), en hoe ziet een verbroken gateway eruit in HA: worden entiteiten `unavailable`, is er een connectiviteitsentiteit (→ §5.2), of blijven de laatste waarden staan (→ §5.3)?
2. **Per signaal: loopt `last_reported` op zonder wijziging, en met welk interval?** Meten met `GET /api/states/<entity_id>` over minstens een uur standby en een uur branden. Dit bepaalt `heartbeat_expected` en `max_age` per ketelsignaal. Verwachting: binary-signalen (vlam) alleen bij wijziging, temperaturen mogelijk periodiek.
3. **`force_update`** in gebruik? (Zichtbaar als `state_changed` met gelijke toestand en nieuwe `last_changed`.)
4. **Resolutie en latentie**: vlamstatus (koppeling met "Gewenste meetresolutie vlamstatus"), temperaturen (0,1 of 0,5 K) en de typische tijd tussen wijzigingen van aanvoer en retour. Dit bepaalt de paartolerantie (standaard 30 s) en of `MISALIGNED` vaak voorkomt.
5. **Recorder**: zijn alle gekoppelde entiteiten opgenomen (geen `exclude`), en wat is `purge_keep_days`? Dit bepaalt of gat-aanvulling (§6.3) en initiële import mogelijk zijn.
6. **Gedrag bij herstart** van HA en van de gateway: `unavailable`/`unknown` en dan echte waarden, of herstelde (mogelijk oude) waarden via RestoreEntity? Oude herstelde waarden zijn een reden om `heartbeat_expected` aan te zetten.
7. **Klok**: draait de app als add-on (zelfde host) of standalone? Zet de integratie zelf tijdstempels, of gebruikt HA de ontvangsttijd?
8. **Status-/foutcode-entiteit** van de ketel of gateway die communicatiefouten meldt (eventueel bruikbaar als gateway-connectiviteit).
9. **Duur van vlam-uitperiodes** in de praktijk (zomer: uren). Dit bepaalt of een alleen-bij-wijziging-vlam zonder gateway-entiteit een acceptabel restrisico is (§5.3).

## 12. Wijzigingen in het contract (`types.py`)

Minimaal en achterwaarts compatibel (alle nieuwe velden hebben een standaardwaarde):

| Wijziging | Waarom |
|---|---|
| `Observation`: `last_reported < ts` toegestaan voor `POLL`; `evidence_ts` mag dan vóór `ts` liggen. | Een peiling kan oud bewijs hebben (§4.3, T11). |
| `ObservationKind`: docstrings bepalen nu welke HA-tijdstempel `ts` is. | Pariteit live ↔ import (§4.2, §6.2). |
| `ConnectionSource.HISTORY` | Historiebereik: gat aangevuld, geen veroudering (§6.3). |
| `QualityEvent`: velden `source`, `other_signal`, `count`, plus property `key` = `(kind, signal, other_signal, source, start)` met validatie per soort. | De oude sleutel `(kind, signal, start)` botste bij gelijktijdige WS- en gateway-uitval en bij één signaal dat met twee partners misaligned was (Q3, Q6). |
| `SignalConfig`: `heartbeat_expected` vereist een positieve `max_age_ms`. | Anders is veroudering niet gedefinieerd. |
| `PipelineConfig.derive_gateway_outage` (standaard `True`) | Afgeleide gateway-uitval uit te zetten (§5.3). |
| Docstrings `timeline.connection_outages`, `timeline.build_timeline`, `quality.align_pair` | Verwijzen naar deze regels. |

Het schema van ADR-001 volgt in een vervolgticket, **#77**: een nieuwe migratie voor `connection_events.source = 'history'`, de kolommen `source`, `other_signal` en `count` in `quality_events`, en `QualityEvent.key` als unieke sleutel. Daar hoort ook de ontdubbelregel "sterkste soort blijft staan" bij de unieke sleutel `(source_entity_id, ts, state)` van `observations`. Tot #77 klaar is, schrijft nog niets deze waarden weg (ingest en runner bestaan nog niet). `test_determinism.py` gebruikt de nieuwe sleutel al.

## 13. Open vragen

1. **Bevestigingspeiling via REST** (§4.4) is extra verkeer en een tweede codepad naast de WebSocket. Alternatief: alleen `old_state.last_reported` uit `state_changed` gebruiken. Dat geeft bewijs pas *bij* de volgende wijziging, dus veroudering zou altijd achteraf zijn. Voorstel: peilen, maar alleen als minstens één signaal `heartbeat_expected` heeft (standaard: alleen kamer- en buitentemperatuur, interval dan 60 s).
2. **Afgeleide gateway-uitval** (§5.3) kan vals-positief zijn als alle periodieke gatewaysignalen tegelijk een te krappe `max_age` hebben. Voorstel: standaard aan; de UI toont bij de melding welke signalen verouderd waren, en de schakelaar komt in de sectie "Gegevens" (#22).
3. **Gepaarde kengetallen op geïmporteerde data** hebben een lagere dekking (§6.4). Acceptabel, of `align_pair` in historiebereik versoepelen (bijv. `ASSUMED_UNCHANGED` zolang geen van beide verandert)? Voorstel: eerst meten na #5.
4. **Staart na een gateway-uitval** (30 s tot de herstelpeiling) telt als `DISCONNECTED` maar zit niet in de `CONNECTION_LOST`-gebeurtenis. Voorstel: zo laten; de dekking per signaal laat het wel zien.

## 14. Bronnen

- [S1] HA developer blog, "New state timestamp State.last_reported" (20 maart 2024) — https://developers.home-assistant.io/blog/2024/03/20/state_reported_timestamp/
- [S2] HA docs, "State and state object" (`last_changed`, `last_updated`, `last_reported`, `unavailable`/`unknown`) — https://www.home-assistant.io/docs/configuration/state_object/
- [S3] HA developer docs, REST API (`/api/states/<entity_id>`, `/api/history/period/<timestamp>`: `minimal_response`, `no_attributes`, `significant_changes_only`, `end_time`) — https://developers.home-assistant.io/docs/api/rest/
- [S4] HA developer docs, WebSocket API (`subscribe_events`, `get_states`) — https://developers.home-assistant.io/docs/api/websocket/
- [S5] HA architecture discussion #1062, "Always keep track of when entity state is written" (recorder werkt `last_reported` van de vorige rij bij; `state_reported` niet in wildcard-abonnementen) — https://github.com/home-assistant/architecture/discussions/1062
- [S6] `homeassistant/core.py` — `StateMachine.async_set` (gelijke toestand → `state_reported`, `force_update`), `EventBus.async_listen` ("Event filter is required" voor `state_reported`), `State.as_dict` / docstring `last_reported` — https://github.com/home-assistant/core/blob/dev/homeassistant/core.py
- [S7] `homeassistant/components/websocket_api/commands.py` — `handle_subscribe_events` (geen `event_filter`), `handle_subscribe_entities` (alleen `state_changed`) — https://github.com/home-assistant/core/blob/dev/homeassistant/components/websocket_api/commands.py
- [S8] HA developer docs, Entity (`available`, `force_update`, `should_poll`) — https://developers.home-assistant.io/docs/core/entity/
- [S9] `homeassistant/components/recorder/core.py` — bijwerken van `last_reported_ts` van de vorige rij bij een nieuwe `state_changed` — https://github.com/home-assistant/core/blob/dev/homeassistant/components/recorder/core.py
- [S10] `homeassistant/components/recorder/history/__init__.py` — `get_significant_states_with_session` (`include_last_reported=False`), `_significant_states_stmt`, `_sorted_states_to_dict` (minimal response laat gelijke toestanden weg; tijd = `last_updated`) — https://github.com/home-assistant/core/blob/dev/homeassistant/components/recorder/history/__init__.py
- [S11] `homeassistant/components/history/__init__.py` — queryparameters (`skip_initial_state`, `significant_changes_only`, `minimal_response`, `no_attributes`, standaard `end_time` = start + 1 dag) — https://github.com/home-assistant/core/blob/dev/homeassistant/components/history/__init__.py
- [S12] HA community, "ESPHome Device Status Sensor" (entiteiten `unavailable` bij verbroken API-verbinding; `status`-binary_sensor) — https://community.home-assistant.io/t/esphome-device-status-sensor/386354
- [S13] ESPHome issue #5414, gedrag van de `status`-binary_sensor — https://github.com/esphome/issues/issues/5414
- [S14] HA docs, MQTT sensor (`availability`, `expire_after`) — https://www.home-assistant.io/integrations/sensor.mqtt/
