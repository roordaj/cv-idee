# CV-analyse

Read-only analyse en advies voor een cv-installatie op basis van Home Assistant-data. De app
schrijft nooit naar de ketel of thermostaat. Zie de gebruikershandleidingen voor de
[eerste analyse](https://github.com/roordaj/cv-idee/blob/main/docs/gebruik/eerste-analyse.md) en
[Home Assistant-terugkoppeling](https://github.com/roordaj/cv-idee/blob/main/docs/gebruik/home-assistant.md).

## Installeren

De bronrepository is momenteel privé. De Home Assistant Supervisor kan een privérepository niet
via de gewone URL ophalen. De winkelinstallatie werkt zodra de bronrepository publiek toegankelijk
is. De GHCR-images openbaar maken geeft alleen toegang tot de containers; daarmee kan Supervisor de
Git-repository niet lezen. Een PAT in de repository-URL bewaart een geheim in de HA-configuratie en
is geen aanbevolen alternatief.

### Lokale installatie

1. Maak in een checkout van deze repository de lokale add-onmap: `make addon-local`.
2. Kopieer `build/addon-local/cv_analyse` naar `/addons/cv_analyse` op de Home Assistant-host,
   bijvoorbeeld met de Samba- of SSH-add-on.
3. Open *Instellingen → Add-ons → Add-on-winkel → ⋮ → Controleren op updates*.
4. Installeer *CV-analyse*, start de add-on en zet *Toon in zijbalk* aan.

De lokale map bouwt de image op de HA-host. De gegenereerde manifestkopie bevat daarom geen
GHCR-imageverwijzing.

### Installatie via de add-onwinkel

Zodra de bronrepository voor Home Assistant toegankelijk is:

1. Open *Instellingen → Add-ons → Add-on-winkel → ⋮ → Repositories*.
2. Voeg `https://github.com/roordaj/cv-idee` toe.
3. Zoek *CV-analyse*, installeer en start de add-on.

Deze route downloadt een vooraf gebouwde image; de HA-host bouwt niets. De versie in
`addon/config.yaml` moet overeenkomen met de releasetag zonder `v`. Een releasebeheerder maakt een
versie met `make addon-version VERSION=v0.1.0`, commit die en pusht daarna de tag. De GHCR-packages
voor amd64 en aarch64 moeten publiek leesbaar zijn voor Supervisor.

## Eerste analyse

Configureer voor MQTT-export eerst de Mosquitto Broker-add-on en de MQTT-integratie in Home
Assistant. Supervisor geeft de brokergegevens automatisch door aan CV-analyse. Zonder broker
blijft de analyse werken; de app probeert dan beperkte REST-state-export.

Na de start open je *CV-analyse* via de zijbalk. Doorloop de eerste setup en koppel bij
*Signaalkoppeling* je HA-entiteiten aan hun betekenis. De brander-/vlamstatus is minimaal nodig;
modus en warmtevraag zijn sterk aanbevolen voor korte-cycli-analyse. Een ontbrekend optioneel
signaal beperkt alleen de analyses die het nodig hebben. Zie [Eerste analyse en historie
importeren](../docs/gebruik/eerste-analyse.md) voor de koppeling, installatiegegevens en import.

## Opties

| Optie | Standaard | Betekenis |
|---|---|---|
| `log_level` | `info` | Detailniveau van het add-onlog. |
| `retentie_dagen` | `180` | Bewaartermijn voor ruwe waarnemingen (7–3650 dagen). Bevindingen en advieshistorie blijven langer bewaard. |
| `notify_doel` | leeg | Doel van een HA-notify-service, zonder `notify.`. Leeg laten om alleen het event `cv_analyse_finding` te versturen. |

Meldingskanalen en bundeling stel je verder in via *Meldingen* in de app. Een `notify`-bericht is
optioneel; het HA-event blijft beschikbaar voor eigen automations.

## Toegang, opslag en back-up

De add-on gebruikt de Home Assistant Supervisor-API voor het lezen van HA-states en Recorder-
historie, en voor meldingen. De enige HA-serviceaanroep is een door de gebruiker gekozen
`notify.*`-service. De app vuurt daarnaast het eigen event `cv_analyse_finding` af. De REST-fallback
schrijft uitsluitend samenvattingsstates met de prefix `sensor.cv_analyse_` of
`binary_sensor.cv_analyse_`. Er zijn geen schrijfopdrachten naar apparaten of MQTT-commandotopics.

De database staat in `/data/cvidee.sqlite` en zit in de add-onback-up. Schema-updates gebeuren bij
het starten. Na herstel van een oudere back-up wordt het schema opnieuw bijgewerkt.
