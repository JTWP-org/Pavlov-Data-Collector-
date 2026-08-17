#!/usr/bin/env bash
set -euo pipefail

DATA_ROOT="${JTWP_DATA_ROOT:-/home/steam/jtwp-collector-data}"

if [[ "${1:-}" != "--yes" ]]; then
    echo "⚠️ This permanently deletes everything INSIDE:"
    echo "   $DATA_ROOT"
    echo
    echo "Run:"
    echo "   sudo $0 --yes"
    exit 2
fi

[[ -d "$DATA_ROOT" ]] || {
    echo "Data folder does not exist: $DATA_ROOT"
    exit 1
}

REAL="$(realpath -m "$DATA_ROOT")"

if [[ "$REAL" != "/home/steam/jtwp-collector-data" ]]; then
    echo "Refusing unexpected data path: $REAL"
    exit 1
fi

echo "🧹 Clearing collector data..."
find "$REAL" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +

echo "✅ Collector data cleared."
echo "📁 Root folder preserved: $REAL"
