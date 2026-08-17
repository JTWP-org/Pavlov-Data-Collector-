#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/steam/jtwp-collector/Pavlov-Data-Collector-"
PYTHON="/home/steam/jtwp-collector/venv/bin/python3"
CONFIG="$PROJECT_DIR/config.json"
ENV_FILE="$PROJECT_DIR/.env"

cd "$PROJECT_DIR"

if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

exec "$PYTHON" "$PROJECT_DIR/update_pavlov_api.py" -c "$CONFIG"
