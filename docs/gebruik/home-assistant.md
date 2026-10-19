# CV-analyse in Home Assistant

Met de MQTT-integratie publiceert CV-analyse een apparaat en entiteiten via MQTT Discovery. De
eventuele REST-fallback heeft beperkingen en is geen volledige vervanging.

## MQTT en apparaat

Installeer en start Mosquitto Broker en configureer de MQTT-integratie in Home Assistant. De
add-on vraagt de brokergegevens via Supervisor op. Na verbinding verschijnt één apparaat:
**CV-analyse** (fabrikant *CV-idee*). Discovery wordt opnieuw aangeboden na een HA-herstart.

De add-on publiceert alleen eigen samenvattingen en discoveryconfiguratie:

- Status en waarden: `cv_analyse/#`
- Discoveryconfiguratie: `homeassistant/sensor/cv_analyse/#` en
  `homeassistant/binary_sensor/cv_analyse/#`
- HA-startsignaal: alleen luisteren naar `homeassistant/status`

De app abonneert niet op apparaatcommando's en gebruikt geen `set`-topics.

## Entiteiten en Lovelace

De entity-id's worden door MQTT Discovery aangemaakt. Voeg ze aan een standaard Entities-kaart toe:

```yaml
type: entities
title: CV-analyse
show_header_toggle: false
entities:
  - entity: sensor.cv_analyse_starts_per_uur
    name: Starts per uur
  - entity: sensor.cv_analyse_korte_cycli_6u
    name: Korte cycli (6 uur)
  - entity: sensor.cv_analyse_gegevensdekking
    name: Gegevensdekking
  - entity: sensor.cv_analyse_open_bevindingen
    name: Open bevindingen
  - entity: sensor.cv_analyse_hoogste_ernst
    name: Hoogste ernst
  - entity: sensor.cv_analyse_volgende_actie
    name: Volgende actie
  - entity: sensor.cv_analyse_bedrijfsmodus
    name: Bedrijfsmodus
  - entity: binary_sensor.cv_analyse_onvoldoende_gegevens
    name: Onvoldoende gegevens
```

Bij `sensor.cv_analyse_open_bevindingen` staan de bevindingen in het `findings`-attribuut. De
entiteiten bevatten samenvattingen; open de app voor observatie, bewijs, onzekerheid en
aanbevelingen. `binary_sensor.cv_analyse_onvoldoende_gegevens` is aan wanneer de samenvatting
onvoldoende betrouwbare actuele gegevens heeft.

## Automations

Elke verzonden melding vuurt ook `cv_analyse_finding` af, zelfs als het notify-kanaal op *Geen*
staat. De payload bevat onder andere `kind`, `finding_ids`, `severity`, `certainty`, `title`,
`detail` en `notification_id`. `kind` is bijvoorbeeld `finding_new`, `finding_worsened` of
`finding_resolved`. Gebruik bijvoorbeeld een persistent Home Assistant-bericht voor nieuwe hoge
bevindingen:

```yaml
alias: CV-analyse - hoge bevinding
triggers:
  - trigger: event
    event_type: cv_analyse_finding
conditions:
  - condition: template
    value_template: >-
      {{ trigger.event.data.kind == 'finding_new'
         and trigger.event.data.severity == 'high' }}
actions:
  - action: persistent_notification.create
    data:
      title: "{{ trigger.event.data.title }}"
      message: "{{ trigger.event.data.detail }}"
mode: queued
```

De volgende automation reageert alleen wanneer de huidige gegevenskwaliteit onvoldoende wordt:

```yaml
alias: CV-analyse - gegevens controleren
triggers:
  - trigger: state
    entity_id: binary_sensor.cv_analyse_onvoldoende_gegevens
    to: "on"
actions:
  - action: persistent_notification.create
    data:
      title: CV-analyse kan niet volledig beoordelen
      message: Controleer de gegevensdekking en signaalkoppelingen in CV-analyse.
mode: single
```

Vervang een persistent notification door je eigen notify-service als je een pushbericht wilt.
Vul in de add-onoptie `notify_doel` de servicenaam in zonder `notify.`. Zonder die optie worden
geen pushmeldingen verzonden; het event en de MQTT-samenvattingen blijven werken.

## REST-state-fallback

Als MQTT niet is geconfigureerd maar Home Assistant wel bereikbaar is, publiceert de app dezelfde
eigen samenvattingswaarden via de HA REST states-API. Alleen `sensor.cv_analyse_*` en
`binary_sensor.cv_analyse_*` worden beschreven. Deze states:

- maken geen apparaat- of entity-registryvermelding via MQTT Discovery;
- kunnen na een Home Assistant-herstart ontbreken tot de app opnieuw publiceert;
- bieden niet dezelfde beschikbaarheids- en retained-stateafhandeling als MQTT Discovery.

Configureer MQTT voor blijvende discovery, het apparaat in HA en betrouwbare beschikbaarheid.
REST-export bestuurt geen apparaten; hij publiceert alleen de eigen samenvattingsstates.
