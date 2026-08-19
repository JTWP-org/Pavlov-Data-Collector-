#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${JTWP_PROJECT_ROOT:-/home/steam/jtwp-collector/Pavlov-Data-Collector-}"
SCRIPT_DIR="$PROJECT_ROOT/scripts/servers"
ENV_FILE="${JTWP_ENV_FILE:-$PROJECT_ROOT/.env}"
INPUT_FILE="${JTWP_PAVLOV_SERVERS_JSON:-/home/steam/jtwp-collector-data/global/pavlov_api/servers.json}"
OUTPUT_DIR="$SCRIPT_DIR"

RAW_JSON="$OUTPUT_DIR/serversRAW.json"
TSV_FILE="$OUTPUT_DIR/servers.tsv"
STRING_ARRAY="$OUTPUT_DIR/stringArray.txt"
SEND_DISCORD="$SCRIPT_DIR/send-discord.sh"

DISCORD_TITLE="${JTWP_SERVER_TEXT_TITLE:-PAVLOV LIVE SERVERS}"

echo
echo "=========================================="
echo "🌐 JTWP Pavlov Server Builder"
echo "=========================================="
echo
echo "Input:  $INPUT_FILE"
echo "Output: $OUTPUT_DIR"
echo

if [[ ! -f "$INPUT_FILE" ]]; then
    echo "❌ servers.json not found:"
    echo "   $INPUT_FILE"
    exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
    echo "❌ jq is not installed."
    exit 1
fi

if ! jq -e '.servers | type == "array"' "$INPUT_FILE" >/dev/null 2>&1; then
    echo "❌ Invalid Pavlov server JSON: expected a top-level .servers array."
    exit 1
fi

mkdir -p "$OUTPUT_DIR"

echo "🔨 Building serversRAW.json..."
jq '
  .servers |= sort_by(-(.slots // 0))
' "$INPUT_FILE" > "$RAW_JSON"

[[ -s "$RAW_JSON" ]] || {
    echo "❌ Failed to create serversRAW.json"
    exit 1
}

echo "📊 Building servers.tsv..."
jq -r '
  [
    "Players",
    "Build",
    "Name",
    "Map",
    "Region",
    "Company"
  ],
  (
    .servers
    | sort_by(-(.slots // 0))
    | .[]
    | [
        "\(.slots // 0)/\(.max_slots // 0)",
        (.server_type // "Unknown"),
        (
          .name // "Unknown"
          | gsub("[^A-Za-z0-9 _.,#()\\[\\]-]"; "")
          | .[0:32]
        ),
        (.map_label // "Unknown"),
        (.host.region_name // "Unknown"),
        (.host.provider // "Unknown")
      ]
  )
  | @tsv
' "$INPUT_FILE" > "$TSV_FILE"

[[ -s "$TSV_FILE" ]] || {
    echo "❌ Failed to create servers.tsv"
    exit 1
}

echo "📝 Building stringArray.txt..."
jq -r '
  .servers
  | sort_by(-(.slots // 0))
  | .[]
  |
    "\\* :flag_\((.host.country_code // "unknown") | ascii_downcase): | **Build**: `\(.server_type // "Unknown")` \\* `\(.slots // 0)/\(.max_slots // 0)` \\* **Name**: `\((.name // "Unknown" | gsub("[^A-Za-z0-9 _.,#()\\[\\]-]"; "") | .[0:32]))` \\* **Map**: `\(.map_label // "Unknown")` \\* **Region**: `\(.host.region_name // "Unknown")` \\* **Company**: `\(.host.provider // "Unknown")` |\n\n********************"
' "$INPUT_FILE" > "$STRING_ARRAY"

[[ -s "$STRING_ARRAY" ]] || {
    echo "❌ Failed to create stringArray.txt"
    exit 1
}

SERVER_COUNT="$(jq '.servers | length' "$INPUT_FILE")"

echo
echo "=========================================="
echo "✅ Build Complete"
echo "=========================================="
echo "🖥️ Servers: $SERVER_COUNT"
echo "JSON:   $RAW_JSON"
echo "TSV:    $TSV_FILE"
echo "Array:  $STRING_ARRAY"

# By default this script keeps the existing behavior and sends the text list.
# Set JTWP_SKIP_DISCORD_SEND=1 to build files only.
if [[ "${JTWP_SKIP_DISCORD_SEND:-0}" == "1" ]]; then
    echo
    echo "ℹ️ Discord send skipped (JTWP_SKIP_DISCORD_SEND=1)."
    exit 0
fi

if [[ ! -f "$ENV_FILE" ]]; then
    echo "❌ .env not found:"
    echo "   $ENV_FILE"
    exit 1
fi

if [[ ! -f "$SEND_DISCORD" ]]; then
    echo "❌ send-discord.sh not found:"
    echo "   $SEND_DISCORD"
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

echo
echo "📤 Sending server list to Discord..."

bash "$SEND_DISCORD" \
    "$WEBHOOK_URL" \
    "text" \
    "$STRING_ARRAY" \
    "$DISCORD_TITLE"

echo
echo "✅ JTWP Server Build + Discord Complete"
