# syntax=docker/dockerfile:1
#
# Single container image for CV-idee: frontend build served by the FastAPI backend.
# Used for the standalone container (docker-compose) and for the Home Assistant add-on
# (see addon/README section in DOCS.md; `make addon-local` assembles a local add-on folder
# that contains this Dockerfile together with the sources, keeping the same layout).
#
# Build context: repository root.   docker build -t cvidee .

ARG PYTHON_IMAGE=python:3.12-slim-bookworm

# --- 1. Frontend build -------------------------------------------------------------------
FROM node:22-alpine AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- 2. Backend virtualenv (uv) ----------------------------------------------------------
FROM ${PYTHON_IMAGE} AS backend
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /src/backend
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./
RUN uv sync --frozen --no-dev --no-editable

# --- 3. Runtime --------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime

# bashio (add-on option handling in run.sh) needs bash, curl and jq.
ARG BASHIO_VERSION=0.19.0
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl jq ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /usr/lib/bashio \
    && curl -fsSL "https://github.com/hassio-addons/bashio/archive/refs/tags/v${BASHIO_VERSION}.tar.gz" \
       | tar -xz --strip-components=2 -C /usr/lib/bashio "bashio-${BASHIO_VERSION}/lib" \
    && ln -s /usr/lib/bashio/bashio /usr/bin/bashio

# Non-root user for standalone mode. The add-on build passes APP_USER=root (addon/build.yaml)
# because the Supervisor mounts /data owned by root.
ARG APP_USER=cvidee
RUN groupadd --system --gid 1000 cvidee \
    && useradd --system --uid 1000 --gid cvidee --home-dir /app --no-create-home cvidee \
    && mkdir -p /data && chown cvidee:cvidee /data

COPY --from=backend /app/.venv /app/.venv
# The package is installed non-editable, so ship alembic.ini + migrations/ separately; the app
# migrates the database at startup (cvidee.store.schema, CVIDEE_MIGRATIONS_DIR).
COPY --from=backend /src/backend/alembic.ini /app/migrations-root/alembic.ini
COPY --from=backend /src/backend/migrations /app/migrations-root/migrations
COPY --from=frontend /src/frontend/dist /app/static
COPY --chmod=0755 addon/run.sh /app/run.sh

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    CVIDEE_STATIC_DIR=/app/static \
    CVIDEE_DB_PATH=/data/cvidee.sqlite \
    CVIDEE_MIGRATIONS_DIR=/app/migrations-root \
    CVIDEE_PORT=8099

WORKDIR /app
USER ${APP_USER}
EXPOSE 8099
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD curl -fsS "http://127.0.0.1:${CVIDEE_PORT}/api/health" || exit 1
CMD ["/app/run.sh"]
