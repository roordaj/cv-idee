# AGENTS.md — conventions for (AI) developers

CV-idee is a **read-only** analysis and advice app for a Remeha Calenta Ace with eTwist, based on Home Assistant (HA) data. Read these first:

- Functional requirements: [`docs/cv-idee-functionele-requirements.md`](docs/cv-idee-functionele-requirements.md) (FR-01 … FR-42)
- Technical plan: [`docs/technisch-plan.md`](docs/technisch-plan.md) — architecture, components, repo structure, working agreement
- Design v3: [`docs/design/CV-analyse-v3.dc.html`](docs/design/CV-analyse-v3.dc.html) — **leading** for screens, texts, colours and interaction
- Roadmap: https://github.com/roordaj/cv-idee/issues/63

## Non-negotiable: read-only

- **Never** write to the boiler or thermostat. No code path may call HA services that control devices (`climate.*`, `water_heater.*`, `number.set_value`, `switch.*`, …).
- The HA token is used only for reading (WebSocket/REST history, states) and for `notify.*` / firing the `cv_analyse_finding` event.
- MQTT: publish and subscribe **only** on own topics `cv_analyse/#` and `homeassistant/+/cv_analyse/#` (plus listening on `homeassistant/status`). Never use `set`/command topics of other devices.
- Never invent numbers: certainty is a documented category, not a percentage; modulation % is never converted to kW without a validated conversion; euros only with a configured price.

## Language convention

- **Code, identifiers, comments, docstrings, commit messages, branch names: English.**
- **UI texts: Dutch** (nl-NL number format with decimal comma, 24h clock, `Europe/Amsterdam`). Texts come from design v3.
- Issues, PR descriptions and docs in `docs/` may be Dutch.
- Use the glossary below when translating domain terms; do not invent synonyms.

## Domain glossary (NL ↔ EN)

| Nederlands | English identifier |
|---|---|
| cyclus / branderperiode | `cycle` / `burner_cycle` |
| brander, vlam | `burner`, `flame` |
| bevinding | `finding` |
| aanbeveling / advies | `recommendation` |
| advieshistorie | `recommendation_history` / `recommendation_snapshot` |
| warmtevraag | `heat_demand` |
| aanvoer(temperatuur) | `flow` (`flow_temperature`) |
| gewenste aanvoer | `flow_setpoint` |
| retour(temperatuur) | `return` (`return_temperature`) |
| naloop | `afterrun` |
| tapwater | `dhw` (domestic hot water) |
| bedrijfsmodus | `operating_mode` |
| stand-by | `standby` |
| storing | `fault` |
| onbekend | `unknown` |
| modulatie | `modulation` |
| buitentemperatuur | `outdoor_temperature` |
| kamertemperatuur / kamersetpoint | `room_temperature` / `room_setpoint` |
| ruimte | `room` |
| zone | `zone` |
| circuit / groep | `circuit` / `loop` |
| mengverdeler | `mixing_manifold` |
| verdeler | `manifold` |
| ketel | `boiler` |
| gegevenskwaliteit | `data_quality` |
| dekking | `coverage` |
| datagat | `data_gap` |
| verouderd | `stale` |
| waarneming | `observation` |
| signaal / signaalrol | `signal` / `signal_role` |
| signaalkoppeling | `signal_mapping` |
| installatieprofiel | `installation_profile` |
| bijzondere periode | `special_period` |
| wijziging / wijzigingslogboek | `change` / `change_log` |
| voor/na-evaluatie | `before_after_evaluation` / `change_evaluation` |
| referentieperiode / observatieperiode | `reference_period` / `observation_period` |
| vergelijkbaarheid | `comparability` |
| zekerheid | `certainty` |
| ernst | `severity` |
| relevantie | `relevance` |
| onderbouwing | `evidence` |
| observatie / interpretatie | `observation` / `interpretation` |
| hypothese | `hypothesis` |
| regel (detectieregel) | `rule` |
| beschikbaarheid (analyse) | `availability` |
| kengetal | `metric` |
| starts per uur | `starts_per_hour` |
| brandduur / pauzeduur | `burn_duration` / `pause_duration` |
| kort branden | `short_cycling` |
| stop tijdens vraag | `stop_during_demand` |
| doorschieten | `overshoot` |
| eindreden | `end_reason` |
| melding / meldingsbeleid | `notification` / `notification_policy` |
| herstelcriterium | `recovery_criterion` |
| succescriterium / terugdraaicriterium | `success_criterion` / `rollback_criterion` |
| status: open / geaccepteerd / uitgesteld / uitgevoerd / afgewezen | `open` / `accepted` / `postponed` / `done` / `rejected` |
| oordeel: verbeterd / verslechterd / afweging / niet toe te schrijven / onvoldoende bewijs | `improved` / `worsened` / `trade_off` / `not_attributable` / `insufficient_evidence` |

HA entity ids exported to HA follow the design (Dutch, e.g. `sensor.cv_analyse_starts_per_uur`); that is UI-facing text, not an identifier convention.

## Repository layout

```
backend/            Python 3.12, uv, FastAPI (src layout: backend/src/cvidee)
  src/cvidee/       ingest, store, analysis, rules, runner, findings, changes, notify, ha_export, api
  tests/            pytest (+ hypothesis, pytest-asyncio, httpx)
frontend/           Vite + React 18 + TypeScript (strict), React Router, TanStack Query
docs/               requirements, technical plan, design
```

Each backend package's `__init__.py` docstring describes its responsibility; respect those boundaries. `cvidee.analysis` stays pure (no I/O).

## Commands

| Command | What it does |
|---|---|
| `make install` | `uv sync` (backend) + `npm ci` (frontend) |
| `make dev` | Backend on http://localhost:8099 (uvicorn, reload) + Vite dev server proxying `/api` to it |
| `make test` | `pytest` + `vitest run` |
| `make lint` | `ruff check` + `ruff format --check` + `eslint` + `prettier --check` |
| `make typecheck` | `mypy --strict` + `tsc --noEmit` |
| `make fmt` | Auto-format (ruff, eslint --fix, prettier) |
| `make build` | Production build of the frontend |

Run `make lint typecheck test` before opening a PR. Copy `.env.example` to `.env` for local configuration (never commit `.env`).

## Working agreement (technical plan §6)

1. **Pick up** only issues labelled `status:ready`. Prefer `prio:M` over `prio:S` (and `prio:S` over `prio:L`); within a priority, follow the milestone order (M0 → M5).
2. **Claim** the issue: assign yourself (if possible), swap label `status:ready` → `status:in-progress` and add a comment that you picked it up.
3. **Branch** from `main`: `<type>/<issue>-<slug>`, e.g. `feat/12-burner-cycles`, `chore/1-monorepo-scaffold`. `<type>` matches the `type:*` label (feature → `feat`, chore, refinement, spike, test, docs).
4. **Stay in scope.** Respect the issue's scope / out-of-scope and the modules it says it touches (conflict avoidance with parallel agents). Need more? Create a follow-up issue.
5. **PR**: small and focused, body contains a summary, how it was verified and `Closes #<n>`. CI must be green.
6. **Blocked** issues (`status:blocked`) become `status:ready` automatically when all `Depends on #n` issues are closed. Use `status:needs-human` when you need a decision or access you don't have.
7. **Refinement** issues deliver an ADR/document and, where needed, follow-up issues.

## CI and required checks

`.github/workflows/ci.yml` runs on every pull request and on pushes to `main`:

- `backend` — `uv sync`, ruff check, ruff format --check, mypy --strict, pytest (via the Makefile targets).
- `frontend` — `npm ci`, eslint, prettier --check, tsc, vitest, production build.
- `openapi` — placeholder (no-op) until #11 adds `api/openapi.json`; it will then fail when the committed spec differs from the generated one.

Branch protection advice for `main`: require a pull request, require the status checks **`backend`** and **`frontend`** to pass (add `openapi` once #11 makes it real), and require branches to be up to date before merging. Never merge with a red check.

## Definition of Done

- Tests (including relevant scenarios) pass; lint and typecheck pass (`make lint typecheck test`, CI green).
- OpenAPI contract / documentation updated when behaviour changes.
- UI follows design v3 (texts in Dutch).
- No write actions to boiler or thermostat; MQTT only on own topics.
- PR references the issue with `Closes #<n>`.
