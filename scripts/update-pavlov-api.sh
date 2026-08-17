#!/usr/bin/env bash
set -euo pipefail

COLLECTOR_DIR="${JTWP_COLLECTOR_DIR:-/home/steam/jtwp-collector}"
PYTHON="${COLLECTOR_DIR}/venv/bin/python3"
CONFIG="${JTWP_COLLECTOR_CONFIG:-${COLLECTOR_DIR}/config.json}"
ENV_FILE="${JTWP_COLLECTOR_ENV:-${COLLECTOR_DIR}/.env}"

if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

exec "$PYTHON" "${COLLECTOR_DIR}/update_pavlov_api.py" -c "$CONFIG"
