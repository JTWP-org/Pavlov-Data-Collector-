#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${JTWP_PROJECT_ROOT:-/home/steam/jtwp-collector/Pavlov-Data-Collector-}"
SCRIPT_DIR="$PROJECT_ROOT/scripts/servers"
ENV_FILE="${JTWP_ENV_FILE:-$PROJECT_ROOT/.env}"

TSV_FILE="$SCRIPT_DIR/servers.tsv"
IMAGE_GENERATOR="$SCRIPT_DIR/generate-server-image.py"
SEND_DISCORD="$SCRIPT_DIR/send-discord.sh"
IMAGE_OUTPUT_DIR="${JTWP_PAVLOV_IMAGE_DIR:-/home/steam/jtwp-collector-data/global/pavlov_api}"
PYTHON="${JTWP_PYTHON:-/home/steam/jtwp-collector/venv/bin/python3}"

MODE="image"
TITLE="${JTWP_SERVER_IMAGE_TITLE:-PAVLOV LIVE SERVERS}"

echo
echo "=========================================="
echo "🖼️ JTWP LIVE SERVERS IMAGE"
echo "=========================================="
echo

if [[ ! -f "$ENV_FILE" ]]; then
    echo "❌ .env file not found:"
    echo "   $ENV_FILE"
    exit 1
fi

if [[ ! -s "$TSV_FILE" ]]; then
    echo "❌ servers.tsv is missing or empty:"
    echo "   $TSV_FILE"
    echo
    echo "Run build-string-array.sh first."
    exit 1
fi

if [[ ! -f "$IMAGE_GENERATOR" ]]; then
    echo "❌ generate-server-image.py not found:"
    echo "   $IMAGE_GENERATOR"
    exit 1
fi

if [[ ! -f "$SEND_DISCORD" ]]; then
    echo "❌ send-discord.sh not found:"
    echo "   $SEND_DISCORD"
    exit 1
fi

if [[ ! -x "$PYTHON" ]]; then
    echo "❌ Python not found:"
    echo "   $PYTHON"
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

mkdir -p "$IMAGE_OUTPUT_DIR"

echo "🧹 Removing old generated images..."
rm -f "$IMAGE_OUTPUT_DIR"/live-servers-*.png

echo "🖼️ Generating server images..."
"$PYTHON" "$IMAGE_GENERATOR" \
    --tsv "$TSV_FILE" \
    --output-dir "$IMAGE_OUTPUT_DIR"

mapfile -t IMAGES < <(
    find "$IMAGE_OUTPUT_DIR" \
        -maxdepth 1 \
        -type f \
        -name 'live-servers-*.png' \
        -print |
    sort -V
)

IMAGE_COUNT="${#IMAGES[@]}"

if [[ "$IMAGE_COUNT" -eq 0 ]]; then
    echo "❌ No live-server images were generated."
    exit 1
fi

echo "✅ Generated $IMAGE_COUNT image(s)."
echo

part=1
for image in "${IMAGES[@]}"; do
    echo "📤 Sending image $part/$IMAGE_COUNT:"
    echo "   $image"

    bash "$SEND_DISCORD" \
        "$WEBHOOK_URL" \
        "$MODE" \
        "$image" \
        "$TITLE - Part $part/$IMAGE_COUNT"

    ((part++))
    sleep 1
done

echo
echo "=========================================="
echo "✅ LIVE SERVER IMAGE COMPLETE"
echo "=========================================="
echo "📊 TSV: $TSV_FILE"
echo "🖼️ Images sent: $IMAGE_COUNT"
