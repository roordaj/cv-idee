#!/usr/bin/env bash
# Container entry point.
#
# Add-on mode (SUPERVISOR_TOKEN set by the Supervisor): read the add-on options with
# bashio and export them as CVIDEE_* environment variables. Standalone mode: use the
# environment as given (HA_URL, HA_TOKEN, MQTT_*, CVIDEE_*).
set -euo pipefail

if [[ -n "${SUPERVISOR_TOKEN:-}" ]]; then
    # shellcheck source=/dev/null
    source /usr/lib/bashio/bashio.sh

    CVIDEE_LOG_LEVEL="$(bashio::config 'log_level' 'info')"
    CVIDEE_RETENTION_DAYS="$(bashio::config 'retentie_dagen' '180')"
    export CVIDEE_LOG_LEVEL CVIDEE_RETENTION_DAYS
    if bashio::config.has_value 'notify_doel'; then
        CVIDEE_NOTIFY_TARGET="$(bashio::config 'notify_doel')"
        export CVIDEE_NOTIFY_TARGET
    fi
    export CVIDEE_DB_PATH=/data/cvidee.sqlite
    bashio::log.info "Starting CV-analyse (add-on mode, log level ${CVIDEE_LOG_LEVEL})"
else
    echo "Starting CV-analyse (standalone mode)"
fi

# Map Home Assistant log levels onto uvicorn's.
case "${CVIDEE_LOG_LEVEL:-info}" in
    trace) uvicorn_level=trace ;;
    debug) uvicorn_level=debug ;;
    notice | info) uvicorn_level=info ;;
    warning) uvicorn_level=warning ;;
    error) uvicorn_level=error ;;
    fatal | critical) uvicorn_level=critical ;;
    *) uvicorn_level=info ;;
esac

mkdir -p "$(dirname "${CVIDEE_DB_PATH:-/data/cvidee.sqlite}")"

exec uvicorn cvidee.main:create_app --factory \
    --host 0.0.0.0 --port "${CVIDEE_PORT:-8099}" \
    --log-level "${uvicorn_level}" --no-server-header
