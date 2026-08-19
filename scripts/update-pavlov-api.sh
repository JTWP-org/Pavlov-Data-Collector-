#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${JTWP_COLLECTOR_DIR:-/home/steam/jtwp-collector/Pavlov-Data-Collector-}"
VENV_ROOT="${JTWP_VENV_DIR:-/home/steam/jtwp-collector/venv}"
PYTHON="${VENV_ROOT}/bin/python3"
CONFIG="${JTWP_COLLECTOR_CONFIG:-${PROJECT_ROOT}/config.json}"
ENV_FILE="${JTWP_COLLECTOR_ENV:-${PROJECT_ROOT}/.env}"

if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

exec "$PYTHON" "${PROJECT_ROOT}/update_pavlov_api.py" -c "$CONFIG"
