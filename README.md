# CV-idee

[![CI](https://github.com/roordaj/cv-idee/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/roordaj/cv-idee/actions/workflows/ci.yml)

Alleen-lezen analyse- en adviesapp voor een cv-installatie (Remeha Calenta Ace + eTwist) op basis van Home Assistant-gegevens.

- Functionele requirements: [docs/cv-idee-functionele-requirements.md](docs/cv-idee-functionele-requirements.md)
- Technisch plan en architectuur: [docs/technisch-plan.md](docs/technisch-plan.md)
- Ontwerp (leidend voor UI): [docs/design/CV-analyse-v3.dc.html](docs/design/CV-analyse-v3.dc.html)

Werk wordt georganiseerd via GitHub-issues per mijlpaal (M0–M5); zie de roadmap in https://github.com/roordaj/cv-idee/issues/63. Pak alleen issues met label `status:ready` op; zie §6 van het technisch plan.

## Ontwikkelen

Vereist `uv` en Node 22+. `make install`, daarna `make dev` (backend op http://localhost:8099, frontend-devserver met proxy naar `/api`). Controles: `make lint typecheck test`. Conventies en werkwijze: [AGENTS.md](AGENTS.md).

## Container en Home Assistant add-on

Eén image (`Dockerfile`, multi-stage: frontend-build → Python 3.12 slim met uv-venv, ~200 MB). FastAPI serveert de frontend-build; onder HA-ingress injecteert de backend het `X-Ingress-Path` in `index.html` (`<base href>` + `window.__INGRESS_PATH__`, zie `frontend/src/lib/basePath.ts`).

- **Standalone:** `make docker-build` en `docker run -p 8099:8099 -e HA_URL=… -e HA_TOKEN=… -v cvidee-data:/data cvidee:dev`. Draait als non-root gebruiker `cvidee`. Optioneel `CVIDEE_API_TOKEN` voor bearer-auth op `/api` (behalve `/api/health`).
- **Add-on:** `addon/` bevat `config.yaml` (ingress, `mqtt:want`, opties), `run.sh` (bashio → env) en vertalingen. `make addon-local` maakt een zelfstandige add-on-map voor `/addons/` op de HA-host; zie [addon/DOCS.md](addon/DOCS.md). Modus wordt gedetecteerd via `SUPERVISOR_TOKEN` (`cvidee.config`).

### Ontwikkelstack (Mosquitto + Home Assistant + app)

```bash
make dev-up        # docker compose -f docker-compose.dev.yml up --build -d
```

1. Open http://localhost:8123 en doorloop de onboarding (maak een gebruiker aan).
2. Profiel (linksonder) → *Beveiliging* → *Langlevende toegangstokens* → *Token aanmaken*.
3. Zet het token in `.env` in de repo-root als `HA_TOKEN=…` en herstart de app: `docker compose -f docker-compose.dev.yml up -d app`.
4. App: http://localhost:8099. MQTT-broker: `localhost:1883`, gebruiker `dev` / wachtwoord `dev` (de MQTT-integratie in HA is al geconfigureerd).

`dev/homeassistant/` bevat de dev-configuratie met gesimuleerde ketelsignalen (`binary_sensor.dev_ketel_vlam`, `sensor.dev_ketel_status`, `…_gewenste_aanvoer`, `…_aanvoertemperatuur`, `…_retourtemperatuur`, `…_modulatie`, kamer- en buitentemperatuur) die elke minuut veranderen. Deze bestanden worden bij de eerste start naar een volume gekopieerd; `make dev-down` stopt de stack (`docker compose -f docker-compose.dev.yml down -v` wist ook de HA-staat).
