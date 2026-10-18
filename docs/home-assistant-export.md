# Terugkoppeling naar Home Assistant

Issue #40, FR-38. De app publiceert uitsluitend eigen samenvattende entiteiten;
ketel en thermostaat worden niet aangestuurd.

## MQTT (voorkeur)

Standalone: stel `MQTT_HOST`, `MQTT_PORT` (standaard 1883), `MQTT_USER` en
`MQTT_PASSWORD` in. De add-on haalt de optionele MQTT-service op via Supervisor
`GET /services/mqtt`. Een verbindingsfout probeert opnieuw met een oplopende
wachttijd van 1 tot maximaal 60 seconden; analyse blijft onafhankelijk draaien.
`CVIDEE_EXPORT_URL` kan het adres van de app bevatten voor de apparaatpagina.

Er verschijnt één apparaat **CV-analyse** met vaste `unique_id`-waarden en de
entiteiten uit ontwerp v3: starts per uur, korte cycli in zes uur, gegevensdekking,
open bevindingen, hoogste ernst, volgende actie, bedrijfsmodus en onvoldoende
gegevens. `default_entity_id` geeft de Nederlandse voorgestelde entity-id; een
door de gebruiker in HA gewijzigde naam wordt gerespecteerd.

Discovery staat retained op `homeassistant/<component>/cv_analyse/<sleutel>/config`;
waarden en attributen op `cv_analyse/<sleutel>/state` en `/attributes`. Publicatie
gebeurt bij verandering. Bij `homeassistant/status = online` wordt discovery
opnieuw aangeboden; de app luistert alleen op dit HA-topic.

`cv_analyse/status` wordt online nadat configuratie en waarden zijn gepubliceerd.
Een retained Last Will zet dit bij onverwachte uitval offline; ook normaal stoppen
publiceert offline. Daardoor worden oude retained waarden niet als actuele waarden
van een werkende app gepresenteerd. Vervallen eigen discovery-entiteiten kunnen
met een leeg retained configbericht worden verwijderd.

## Meetbasis en ontbrekende gegevens

Kengetallen gebruiken de bestaande pure cyclusanalyse over zes uur, tot de
gebruikelijke afwikkeltijd van twee minuten vóór nu. Attributen vermelden begin,
einde, geobserveerde seconden en dekking. De actuele beschikbaarheid en modus
worden apart tot nu beoordeeld: een recente uitval wordt direct zichtbaar.
Tapwater en onvolledige cycli tellen niet mee bij korte cv-cycli. Dit zijn
monitoringgetallen, geen automatische conclusie dat de installatie goed werkt.

Bij onvoldoende dekking, ontbrekende actuele kernsignalen of onvoldoende bewezen
vlamresolutie worden de cyclusgetallen `unknown` en onvoldoende gegevens `on`.
MQTT gebruikt voor numerieke sensoren de voorgeschreven payload `None` om een
oude waarde daadwerkelijk te wissen. Er worden geen resoluties verzonnen.
Open bevindingen bevatten ook adviesstatussen in hun attributen; de eerstvolgende
open of geaccepteerde actie bevat het bevinding-ID, de titel en de adviesstatus.

## Zonder broker

Als geen broker is geconfigureerd of Supervisor geen MQTT-service aanbiedt,
publiceert de app via `POST /api/states/<eigen entity-id>`. Een geconfigureerde maar
onbereikbare broker blijft MQTT proberen; de transportkeuze wisselt niet stilzwijgend.
REST-entiteiten hebben geen MQTT-device registry of vaste MQTT `unique_id`.
Ze worden bij wijziging, iedere vijf minuten en na `homeassistant_started` of
herverbinding opnieuw gepubliceerd. REST heeft geen Last Will; bij abrupt
appverlies kan HA de uitval niet via deze terugvalmethode vaststellen.

`GET /api/ha/export` toont de actieve modus (`mqtt`, `fallback`, `none`), verbinding,
laatste publicatie en de eigen waarden. Zonder HA en broker is export uitgeschakeld.

## Verificatie

`docker compose -f docker-compose.dev.yml up -d mosquitto` start de testbroker.
Voer daarna uit: `CVIDEE_TEST_MQTT_HOST=127.0.0.1 uv run --project backend pytest
backend/tests/ha_export -q`. CI start dezelfde compose-service. Tests controleren
retained discovery/state, normale stop en Last Will bij het abrupt beëindigen van
een eigen tijdelijk exportproces. HA-herstartontvangst wordt nagebootst zonder op
`homeassistant/status` te publiceren. REST, Supervisor en WebSocket-herstartdetectie
worden tegen lokale fake-HA-eindpunten getest. De apparaatweergave in een echte
HA-installatie vraagt een geconfigureerde HA-verbinding.

Bronnen: [MQTT discovery](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery),
[MQTT-sensorwaarden en default_entity_id](https://www.home-assistant.io/integrations/sensor.mqtt/),
[aiomqtt reconnect](https://aiomqtt.bo3hm.com/reconnection).
