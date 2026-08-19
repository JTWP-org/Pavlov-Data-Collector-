#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/home/steam/jtwp-collector/Pavlov-Data-Collector-"
ENV_FILE="$PROJECT_ROOT/.env"
PYTHON="/home/steam/jtwp-collector/venv/bin/python3"
COLLECTOR="$PROJECT_ROOT/collector.py"
CONFIG="$PROJECT_ROOT/config.json"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: .env not found: $ENV_FILE"
    exit 1
fi

set -a
source "$ENV_FILE"
set +a

if [[ -z "${JTWP_IP_HASH_SECRET:-}" ]]; then
    echo "ERROR: JTWP_IP_HASH_SECRET is not loaded."
    exit 1
fi

exec "$PYTHON" "$COLLECTOR" -c "$CONFIG"
