# CV-idee

[![CI](https://github.com/roordaj/cv-idee/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/roordaj/cv-idee/actions/workflows/ci.yml)

Alleen-lezen analyse- en adviesapp voor een cv-installatie (Remeha Calenta Ace + eTwist) op basis van Home Assistant-gegevens.

- Functionele requirements: [docs/cv-idee-functionele-requirements.md](docs/cv-idee-functionele-requirements.md)
- Technisch plan en architectuur: [docs/technisch-plan.md](docs/technisch-plan.md)
- Ontwerp (leidend voor UI): [docs/design/CV-analyse-v3.dc.html](docs/design/CV-analyse-v3.dc.html)

Werk wordt georganiseerd via GitHub-issues per mijlpaal (M0–M5); zie de roadmap in https://github.com/roordaj/cv-idee/issues/63. Pak alleen issues met label `status:ready` op; zie §6 van het technisch plan.

## Ontwikkelen

Vereist `uv` en Node 22+. `make install`, daarna `make dev` (backend op http://localhost:8099, frontend-devserver met proxy naar `/api`). Controles: `make lint typecheck test`. Conventies en werkwijze: [AGENTS.md](AGENTS.md).
