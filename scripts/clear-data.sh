#!/usr/bin/env bash
set -euo pipefail

DATA_ROOT="/home/steam/jtwp-collector-data"
OWNER="steam"
GROUP="steam"

if [[ "${1:-}" != "--yes" ]]; then
    echo "⚠️  This will remove all collector data under:"
    echo "    $DATA_ROOT"
    echo
    read -r -p "ARE YOU SURE YOU WANT TO REMOVE ALL THE DATA? Type YES: " confirm

    if [[ "$confirm" != "YES" ]]; then
        echo "❌ Cancelled."
        exit 1
    fi
fi

echo "🧹 Clearing collector data..."

rm -rf "${DATA_ROOT:?}/"*

mkdir -p \
    "$DATA_ROOT/global" \
    "$DATA_ROOT/private" \
    "$DATA_ROOT/players/records" \
    "$DATA_ROOT/players/index" \
    "$DATA_ROOT/servers"

chown -R "$OWNER:$GROUP" "$DATA_ROOT"

chmod 755 "$DATA_ROOT"
chmod 700 "$DATA_ROOT/private"

echo "✅ Collector data cleared."
echo "📁 Root folder preserved: $DATA_ROOT"
echo "👤 Ownership restored to: $OWNER:$GROUP"
