# CV-analyse

Alleen-lezen analyse en advies voor een cv-installatie (Remeha Calenta Ace met eTwist) op basis
van Home Assistant-gegevens. De add-on schrijft **nooit** naar ketel of thermostaat.

> Deze documentatie is een placeholder; ze wordt aangevuld zodra de functionaliteit er is.

## Installatie

### Lokale add-on (ontwikkeling)

1. Bouw in deze repository een zelfstandige add-on-map: `make addon-local`.
2. Kopieer `build/addon-local/cv_analyse` naar `/addons/cv_analyse` op de Home Assistant-host
   (bijv. via de Samba- of SSH-add-on).
3. *Instellingen → Add-ons → Add-on-winkel → ⋮ → Controleren op updates*; de add-on verschijnt
   onder *Lokale add-ons*. Installeren bouwt de image lokaal.
4. Starten en *Toon in zijbalk* aanzetten; de UI opent via ingress.

### Via de add-on-repository

Deze installatie werkt met de huidige private bronrepository pas nadat de Git-repository publiek
is gemaakt; Home Assistant toont geen aanmeldscherm voor een privérepository. De lokale route
hierboven blijft bruikbaar zolang de bron privé is.

1. Open in Home Assistant *Instellingen → Add-ons → Add-on-winkel → ⋮ → Repositories*.
2. Voeg `https://github.com/roordaj/cv-idee` toe en selecteer *Toevoegen*.
3. Zoek *CV-analyse* onder de beschikbare add-ons, installeer en start deze.

De repository bevat `addon/config.yaml`; het veld `image` verwijst naar een vooraf gebouwde
GHCR-image per architectuur. Installeren via deze route bouwt dus niets op de Home Assistant-host.
Een release wordt gepubliceerd wanneer een `vMAJOR.MINOR.PATCH`-tag naar GitHub wordt gepusht.
De configuratieversie moet dan exact overeenkomen met de tag zonder `v`. Werk de versie bij met
`make addon-version VERSION=v0.1.0`, commit die wijziging en push daarna de tag.

De Supervisor heeft toegang tot de Git-repository nodig om de add-oncatalogus op te halen; alleen
toegang tot het image-package is daarvoor niet genoeg. Deze release maakt alleen de containerimages
beschikbaar en verandert de zichtbaarheid van de broncode niet. Een PAT in de repository-URL kan
toegang geven tot een privérepository, maar bewaart het geheim bij de HA-configuratie en is daarom
geen aanbevolen installatiemethode.

De Supervisor kan ook geen GHCR-inloggegevens uit de GitHub-sessie gebruiken. Maak daarom de
GHCR-packages `cv-idee-addon-amd64` en `cv-idee-addon-aarch64` openbaar nadat de eerste release ze
heeft aangemaakt. Dit publiceert alleen de containers. Controleer de package-instellingen via
GitHub → *Packages* → package → *Package settings* → *Change visibility* → *Public*.

Zolang de bronrepository privé is, kan de lokale installatie hierboven worden gebruikt door iemand
met een checkout van de repository. Zie [Home Assistant: apps publiceren](https://developers.home-assistant.io/docs/add-ons/publishing/) voor de image- en architectuurconventies.

## Opties

| Optie | Standaard | Betekenis |
|---|---|---|
| `log_level` | `info` | Logniveau. |
| `retentie_dagen` | `180` | Hoe lang ruwe waarnemingen bewaard blijven. |
| `notify_doel` | — | Notify-service voor meldingen (zonder `notify.`). Leeg: alleen het HA-event `cv_analyse_finding`. |

## Verbindingen

- **Home Assistant:** via de Supervisor-proxy met het `SUPERVISOR_TOKEN` (alleen lezen en `notify`).
- **MQTT:** de add-on vraagt de Mosquitto-brokergegevens op bij de Supervisor (`services: mqtt:want`)
  voor de terugkoppeling van samenvattende sensoren naar Home Assistant.
- **Opslag:** SQLite in `/data`.

## Database en back-up

De database (`/data/cvidee.sqlite`) staat in `/data` en wordt daarom meegenomen in Home Assistant-back-ups van de add-on. Het schema wordt bij elke start automatisch bijgewerkt (Alembic-migraties); een herstart op een bestaande database is veilig. Mislukt de migratie, dan start de add-on niet en staat de oorzaak in het log. Herstel van een back-up brengt oudere data terug; het schema wordt bij de volgende start weer op het huidige niveau gebracht.
