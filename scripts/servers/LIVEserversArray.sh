#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${JTWP_PROJECT_ROOT:-/home/steam/jtwp-collector/Pavlov-Data-Collector-}"
SCRIPT_DIR="$PROJECT_ROOT/scripts/servers"
ENV_FILE="${JTWP_ENV_FILE:-$PROJECT_ROOT/.env}"
SEND_DISCORD="$SCRIPT_DIR/send-discord.sh"
STRING_ARRAY="$SCRIPT_DIR/stringArray.txt"

MODE="text"
TITLE="${JTWP_SERVER_TEXT_TITLE:-PAVLOV LIVE SERVERS}"

echo
echo "=========================================="
echo "🌐 JTWP LIVE SERVERS ARRAY"
echo "=========================================="
echo

if [[ ! -f "$ENV_FILE" ]]; then
    echo "❌ .env file not found:"
    echo "   $ENV_FILE"
    exit 1
fi

if [[ ! -f "$SEND_DISCORD" ]]; then
    echo "❌ send-discord.sh not found:"
    echo "   $SEND_DISCORD"
    exit 1
fi

if [[ ! -s "$STRING_ARRAY" ]]; then
    echo "❌ stringArray.txt is missing or empty:"
    echo "   $STRING_ARRAY"
    echo
    echo "Run build-string-array.sh first."
    exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

WEBHOOK_URL="${JTWP_CMD_OUTPUT_WEBHOOK_URL:-}"

if [[ -z "$WEBHOOK_URL" ]]; then
    echo "❌ JTWP_CMD_OUTPUT_WEBHOOK_URL is not set in:"
    echo "   $ENV_FILE"
    exit 1
fi

SERVER_COUNT="$(
    grep -c '^\\\* :flag_' "$STRING_ARRAY" 2>/dev/null || true
)"

echo "📄 Input: $STRING_ARRAY"
echo "🖥️ Server entries: $SERVER_COUNT"
echo "📨 Mode: $MODE"
echo "🏷️ Title: $TITLE"
echo

bash "$SEND_DISCORD" \
    "$WEBHOOK_URL" \
    "$MODE" \
    "$STRING_ARRAY" \
    "$TITLE"

echo
echo "✅ LIVE SERVER ARRAY COMPLETE"
