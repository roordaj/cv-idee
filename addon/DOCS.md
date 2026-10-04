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

### Als add-on-repository

`repository.yaml` staat in de root van de repository. De Supervisor bouwt een add-on uit een
repository met de add-on-map (`addon/`) als build-context, waarin de broncode niet zit. Installatie
via de repository-URL werkt daarom pas zodra er een gepubliceerde image is (`image:` in
`config.yaml`, gebouwd door CI uit de root-`Dockerfile`). Tot die tijd: lokale add-on gebruiken.

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
