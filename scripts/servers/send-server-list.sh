#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(
    cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1
    pwd -P
)"

WEBHOOK_URL="${1:-}"
INPUT_FILE="${2:-$SCRIPT_DIR/stringArray.txt}"
TITLE="${3:-PAVLOV LIVE SERVERS}"

if [[ -z "$WEBHOOK_URL" ]]; then
    echo "Usage: $0 <webhook_url> [input_file] [title]"
    exit 1
fi

exec bash "$SCRIPT_DIR/send-discord.sh" \
    "$WEBHOOK_URL" \
    "text" \
    "$INPUT_FILE" \
    "$TITLE"
