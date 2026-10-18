# CAN-signalen Remeha Calenta Ace in Home Assistant

Inventarisatie op 18 oktober 2026, uitsluitend via read-only HA MCP: entity search, entity registry, actuele states en recorderhistorie. Geen services, MQTT-publicaties, configuratiewijzigingen of geforceerde storingen uitgevoerd. Requirements FR-01, FR-03, FR-07, FR-09 en FR-12.

## Resultaat en bewijsgrens

De CAN-signalen zijn toegankelijk. Er zijn 33 entiteiten met Calenta-naam: 18 via MQTT en 15 via ESPHome, inclusief twee statuslampen die geen analysesignaal zijn. De ESPHome-device meldt Espressif esp32-c6 met firmware 2026.7.3. Registrymetadata bevestigt twee integratieroutes; het is geen bewijs van twee onafhankelijke metingen.

Een volledige, gepagineerde opname van 48 uur staat in [fixtures/recordings/calenta-can-48h](../fixtures/recordings/calenta-can-48h/README.md). Daarin staan CV-statusperioden van circa 22, 116 en 61 seconden en warmwaterbedrijf. **Een echt vlamsignaal ontbreekt.** Deze perioden mogen dus niet als gevalideerde korte branderperiodes worden gelabeld. Het opnamecriterium van #5 (korte cycli én tapwater met voldoende betekenisbewijs) blijft gedeeltelijk open; vervolgonderzoek staat in [#122](https://github.com/roordaj/cv-idee/issues/122).

## Entiteiten

Actuele voorbeeldwaarden tijdens inventarisatie; geen tijdgesynchroniseerde meetset. Alle hieronder genoemde entiteiten zijn ingeschakeld. Een streep betekent dat HA geen device_class of eenheid meegaf. De exacte entity_id is nodig voor lokale koppeling; unieke apparaat-id's, MAC-adressen, hostnamen en aanvullende locatiegegevens zijn niet opgeslagen.

| entity_id | Integratie | device_class | Eenheid | Voorbeeld |
|---|---|---|---|---|
| `binary_sensor.remeha_calenta_ace_can_verbinding_actief` | mqtt | connectivity | — | on |
| `binary_sensor.remeha_calenta_ace_cv_bedrijf_actief` | mqtt | running | — | off |
| `binary_sensor.remeha_calenta_ace_ventilator_actief` | mqtt | running | — | off |
| `binary_sensor.voorzolder_remeha_calenta_ace_can_verbinding_actief` | esphome | connectivity | — | on |
| `binary_sensor.voorzolder_remeha_calenta_ace_cv_bedrijf_actief` | esphome | running | — | off |
| `binary_sensor.voorzolder_remeha_calenta_ace_ventilator_actief` | esphome | running | — | off |
| `light.remeha_calenta_ace_status_led` | esphome | — | — | off |
| `light.remeha_calenta_ace_status_led_2` | mqtt | — | — | off |
| `sensor.remeha_calenta_ace_aanvoertemperatuur` | mqtt | temperature | °C | 28.6 |
| `sensor.remeha_calenta_ace_actuele_pompsnelheid_am010` | mqtt | — | % | 55.0 |
| `sensor.remeha_calenta_ace_brandermodulatie` | mqtt | — | % | 0 |
| `sensor.remeha_calenta_ace_cv_waterdruk` | mqtt | pressure | bar | 1.8 |
| `sensor.remeha_calenta_ace_delta_t` | mqtt | — | °C | 7.92 |
| `sensor.remeha_calenta_ace_delta_t_experimenteel` | mqtt | — | °C | 0.59 |
| `sensor.remeha_calenta_ace_ketel_substatus_am014` | mqtt | — | — | 0 |
| `sensor.remeha_calenta_ace_ketel_substatus_omschrijving` | mqtt | — | — | Stand-by |
| `sensor.remeha_calenta_ace_ketelstatus_am012` | mqtt | — | — | 0 |
| `sensor.remeha_calenta_ace_ketelstatus_omschrijving` | mqtt | — | — | Stand-by |
| `sensor.remeha_calenta_ace_retourtemperatuur_am018` | mqtt | temperature | °C | 28.18 |
| `sensor.remeha_calenta_ace_retourtemperatuur_experimenteel` | mqtt | temperature | °C | 52.31 |
| `sensor.remeha_calenta_ace_temperatuur_setpoint` | mqtt | temperature | °C | 0.0 |
| `sensor.remeha_calenta_ace_vermogenscommando_can` | mqtt | — | % | 100 |
| `sensor.voorzolder_remeha_calenta_ace_aanvoertemperatuur` | esphome | temperature | °C | 28.6000003814697 |
| `sensor.voorzolder_remeha_calenta_ace_actuele_pompsnelheid_am010` | esphome | — | % | unknown |
| `sensor.voorzolder_remeha_calenta_ace_brandermodulatie` | esphome | — | % | 0.0 |
| `sensor.voorzolder_remeha_calenta_ace_cv_waterdruk` | esphome | pressure | bar | 1.79999995231628 |
| `sensor.voorzolder_remeha_calenta_ace_delta_t` | esphome | — | °C | unknown |
| `sensor.voorzolder_remeha_calenta_ace_ketel_substatus_am014` | esphome | — | — | 0.0 |
| `sensor.voorzolder_remeha_calenta_ace_ketel_substatus_omschrijving` | esphome | — | — | Stand-by |
| `sensor.voorzolder_remeha_calenta_ace_ketelstatus_am012` | esphome | — | — | 0.0 |
| `sensor.voorzolder_remeha_calenta_ace_ketelstatus_omschrijving` | esphome | — | — | Stand-by |
| `sensor.voorzolder_remeha_calenta_ace_retourtemperatuur_am018` | esphome | temperature | °C | unknown |
| `sensor.voorzolder_remeha_calenta_ace_temperatuur_setpoint` | esphome | temperature | °C | 0.0 |

Er is daarnaast een update-entiteit voor firmware; die hoort niet bij de analyse. Alleen lezen.

De Remeha/eTwist-cloudroute bevat daarnaast `climate.huis` (actuele kamer 20 °C, doel 20 °C), `binary_sensor.huis_status` (device_class heat, off), `sensor.huis_current_schedule_setpoint` (20 °C), volgende setpoint/tijd, waterdruk 1,8 bar en zes energie-entiteiten voor verwarmen/koelen/tapwater. `sensor.dhw_water_temperature` is unknown; `sensor.home_outdoor_temperature` is unavailable. Energiebetekenis en tijdsbasis zijn niet gevalideerd. De cloudroute is geen direct CAN-vlambewijs. Er is geen gevalideerde buitenmeting in deze inventarisatie.

Aanvullende Remeha-entiteiten (apart leesmoment; cloudbron, niet opgenomen in de fixture):

| entity_id | device_class | Eenheid | Voorbeeld |
|---|---|---|---|
| `binary_sensor.huis_status` | heat | — | off |
| `climate.huis` | — | — | auto |
| `sensor.dhw_water_temperature` | temperature | °C | unknown |
| `sensor.home_cooling_energy_consumed` | energy | kWh | 0 |
| `sensor.home_cooling_energy_delivered` | energy | kWh | 0 |
| `sensor.home_heating_energy_consumed` | energy | kWh | 24.0 |
| `sensor.home_heating_energy_delivered` | energy | kWh | 0 |
| `sensor.home_hot_water_energy_consumed` | energy | kWh | 0 |
| `sensor.home_hot_water_energy_delivered` | energy | kWh | 0 |
| `sensor.home_outdoor_temperature` | temperature | °C | unavailable |
| `sensor.home_water_pressure` | pressure | bar | 1.8 |
| `sensor.huis_current_schedule_setpoint` | temperature | °C | 20.0 |
| `sensor.huis_next_setpoint` | temperature | °C | 17.0 |
| `sensor.huis_next_setpoint_time` | timestamp | — | volgend tijdstip aanwezig (ISO8601) |

## Updategedrag en resolutie

De tabel geeft **afstanden tussen recorderrecords**, niet de gegarandeerde CAN-/rapportcadans. Mediaan/minimum/maximum in seconden over het 48-uursvenster; het eerste record kan een door HA ingevoegde grenswaarde zijn. Ook met `significant_changes_only=false` en `minimal_response=true` is dit geen opname van alle ongewijzigde rapporten. Een korte minimumafstand kan een statusflits zijn. Een lange afstand kan zowel een constante waarde als ontbrekende bevestiging betekenen.

| MQTT-entiteit (achtervoegsel) | Records | Mediaan s | Minimum s | Maximum s |
|---|---:|---:|---:|---:|
| `can_verbinding_actief` | 1 | — | — | — |
| `cv_bedrijf_actief` | 51 | 1241,544 | 21,538 | 36428,175 |
| `ventilator_actief` | 49 | 1348,071 | 40,153 | 36409,409 |
| `aanvoertemperatuur` | 4958 | 1,978 | 0,025 | 10826,573 |
| `actuele_pompsnelheid_am010` | 2 | 135292,569 | 135292,569 | 135292,569 |
| `brandermodulatie` | 3771 | 1,022 | 0,090 | 36428,607 |
| `cv_waterdruk` | 137 | 84,012 | 3,921 | 36008,840 |
| `delta_t` | 85 | 2,009 | 0,982 | 135303,551 |
| `delta_t_experimenteel` | 1 | — | — | — |
| `ketel_substatus_am014` | 606 | 1,099 | 0,007 | 36003,528 |
| `ketel_substatus_omschrijving` | 606 | 1,099 | 0,008 | 36003,527 |
| `ketelstatus_am012` | 289 | 8,402 | 0,015 | 36004,610 |
| `ketelstatus_omschrijving` | 289 | 8,402 | 0,008 | 36004,618 |
| `retourtemperatuur_am018` | 63 | 3,889 | 2,068 | 135303,436 |
| `retourtemperatuur_experimenteel` | 1 | — | — | — |
| `temperatuur_setpoint` | 1712 | 10,003 | 1,241 | 36064,610 |
| `vermogenscommando_can` | 1 | — | — | — |

Actuele states bevatten `last_changed`, `last_updated` en `last_reported`. Bij de CAN-entiteiten waren deze gelijk; bij `climate.huis` was `last_reported` recent terwijl `last_changed` ouder was. De aanwezigheid van het veld bewijst dus geen periodieke bevestiging per CAN-entiteit. Voor de opname zijn alle pagina's opgehaald en aantallen gecontroleerd.

Opvallend: MQTT retour rapporteert één korte meetserie en blijft daarna 28,18 °C tonen; ESPHome retour wordt circa 58 s na de laatste waarde unknown. De pompserie wordt native circa 60 s na 55% unknown, terwijl MQTT 55% blijft tonen. MQTT Delta T blijft 7,92 °C; native is unknown. Experimentele retour/Delta T en vermogenscommando blijven constant. Gebruik die niet als verse bevestiging of als reden om een timeout uit te schakelen.

## Statuscodes

Onderstaande betekenis komt **uit de omschrijvingsentiteiten van de gateway**, gekoppeld aan de numerieke records (zelfde volgorde en alle AM012-paren binnen 1 s). Dit is geen onafhankelijke validatie tegen Remeha-documentatie of firmwarebron. Vluchtovergangen tussen codes bestaan tot op millisecondenniveau.

| AM012 | Gatewayomschrijving | Voorstel bij expliciet gevalideerde installatiemapping |
|---:|---|---|
| 0 | Stand-by | standby |
| 1 | Warmtevraag | overgang; geen bewijs van CV-branden |
| 2 | Ketel starten | overgang; geen bewijs van tapwater |
| 3 | CV-bedrijf | ch |
| 4 | Warmwaterbedrijf | dhw |
| 5 | Ketel stoppen | overgang; nog geen bevestigde naloop |
| 6 | Pomp nadraaien | afterrun |
| 8 | Gecontroleerde stop | overgang; geen storing aannemen |

Geen storing/blokkering in het venster gezien. Andere codes zijn onbekend; geen betekenis invullen op basis van een generieke tabel. AM014 werd met deze labels gezien:

| AM014 | Gatewayomschrijving |
|---:|---|
| 0 | Stand-by |
| 1 | Antipendelcyclus |
| 3,21 | Niet gedocumenteerd |
| 4 | Wachten op startvoorwaarden |
| 10 | Externe gasklep sluiten |
| 13 | Voorventilatie |
| 15 | Branderstartcommando |
| 17 | Voorontsteking |
| 18 | Ontsteking |
| 19 | Vlamcontrole |
| 30 | Normale temperatuurregeling |
| 31 | Beperkte temperatuurregeling |
| 32 | Normale vermogensregeling |
| 33 | Vermogensregeling gradient 1 |
| 36 | Vlamvermogensregeling |
| 37 | Stabilisatietijd |
| 38 | Koude start |
| 39 | CV hervatten |
| 41 | Naventilatie |
| 44 | Ventilator stoppen |
| 60 | Pomp nadraaien |
| 61 | Pomp stoppen |
| 63 | Antipendeltimer |

Ook AM014 19 'Vlamcontrole' is geen zelfstandig, voortdurend vlamsignaal. Hetzelfde geldt voor 15 'Branderstartcommando'. Niet omzetten naar vlamstarts zonder decoderbewijs.

De bestaande voorlopige appmapping `1→CH,2→DHW` past **niet** bij deze AM012-bron. Koppel deze status niet met die defaults. [#123](https://github.com/roordaj/cv-idee/issues/123) levert een installatiegebonden mapping voor live én import, inclusief vastgelegde herkomst. De synthetische fixtures hebben een eigen expliciete codetabel; die is geen ketelprotocol.

## Voorgestelde signaalkoppeling

Voorstellen, geen automatisch toegepaste configuratie. De oorspronkelijke waarden zijn gerapporteerd; fysieke sensorlocatie/decoderdefinitie moet waar nodig worden bevestigd.

| Signaalrol | Kandidaat | Voorwaarde |
|---|---|---|
| operating_mode | MQTT ketelstatus_am012 | expliciete AM012-mapping via #123; geen generieke defaults |
| flow_temperature | native aanvoertemperatuur | ketellocatie bevestigen; kwaliteit/actualiteit blijven controleren |
| return_temperature | native retourtemperatuur_am018 | ontbreekt meestal; unknown behouden, geen oude MQTT-waarde invullen |
| flow_setpoint | native temperatuur_setpoint | naam suggereert waterdoel; decoderbetekenis en 0 verifiëren |
| modulation | native brandermodulatie | gerapporteerd%; referentie onbekend; geen kW-berekening |
| heat_demand | binary_sensor.huis_status | cloud heat-status kandidaat; daadwerkelijke vraagbetekenis/vertraging valideren |
| room_temperature | climate.huis/current_temperature | attribuutbron; hoofdruimte/zone expliciet vastleggen |
| room_setpoint | climate.huis/temperature | actief doelattribuut, niet blind volgend/planningssetpoint |
| flame | geen | CV-actief, ventilator, status en modulatie niet als flame aannemen |
| pump | geen gevalideerde boolean | AM010% onvoldoende betrouwbaar; ventilator is geen pomp |
| outdoor_temperature | geen beschikbare gevalideerde bron | cloudbron unavailable |
| gateway_connectivity | CAN Verbinding Actief (diagnostiek) | alleen busindicator; geen broker-/HA-bereikbaarheidsgarantie |

De tabel vereist attribuutextractie waar genoemd. Een ontbrekende rol blokkeert alleen de analyses die die rol nodig hebben. Geen installatiesettings zijn aangepast.

## CAN-verlies en verbinding

CAN Verbinding Actief bleef het hele venster on (slechts grensrecord), ook terwijl AM010/AM018 native unknown werden. Dit bewijst dat de busindicator geen versheid per signaal garandeert. Er is geen natuurlijke CAN-uitval of brokerdisconnect in dit venster waargenomen. Niet vastgesteld: of de indicator bij echte busuitval off of unavailable wordt, MQTT availability/retainedbeleid, herstelgedrag en periodieke heartbeat. HA-state uitlezen kan niet aantonen dat de broker nu bereikbaar is. Er zijn geen externe MQTT-topics beluisterd of gepubliceerd.

[#122](https://github.com/roordaj/cv-idee/issues/122) bundelt het ontbrekende decoder-/vlam-/timeoutbewijs. Tot die tijd: geen gevalideerde startfrequentie of cyclusduur van deze installatie, geen opgewaardeerde zekerheid en geen onveilige terugval op oude waarden.


## Onafhankelijke documentatie en decoderonderzoek

De officiële [installatie- en servicehandleiding Calenta Ace, 7685807 v.11, 8 november 2023](https://documentation.remeha.nl/wp-content/uploads/sites/68/2025/12/Installatie-en-servicehandleiding-Calenta-Ace-V11.pdf), tabellen 72, 74 en 75, bevestigt de hierboven waargenomen AM012-betekenissen. Zij noemt ook codes 9 (blokkering) en 10 (vergrendeling); die zijn hier niet waargenomen. Dit ondersteunt statussemantiek, maar valideert nog niet de gebruikte CAN-decoder.

Tabel 74 beschrijft **GM003 als vlamdetectie (0 uit, 1 aan)** en GM007 afzonderlijk als ontsteken. GM003 is niet als HA-entiteit aangetroffen. GM011 is het vermogenssetpoint ten opzichte van het maximum; AM024 is relatief toestelvermogen (tabel 72). Het is niet bewezen welk van die velden de gateway als brandermodulatie of vermogenscommando exposeert. Geen kW-omrekening of flame-afleiding.

Read-only device-/integratiemetadata bevat geen firmwareproject-URL of decoderbron, alleen het generieke bordmodel en de ESPHome-versie. Het publieke [aequitas/remeha-canbus](https://github.com/aequitas/remeha-canbus) is een relevante ESPHome/CAN-implementatie, maar niet aantoonbaar de lokaal gebruikte firmware. Die bron is daarom geen bewijs van de betekenis van deze installatie-entiteiten. Voor #122 is de lokale decoderconfiguratie nodig, of een verifieerbare koppeling aan een specifieke bronversie; toegang tot HA-states/history alleen dekt dit niet.
