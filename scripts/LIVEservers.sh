#!/usr/bin/env bash

set -euo pipefail

WEBHOOK_URL="${1:-}"
INPUT_FILE="${2:-stringArray.txt}"

MAX_LENGTH=3900
SEPARATOR="********************"

if [[ -z "$WEBHOOK_URL" ]]; then
    echo "Usage: $0 <webhook_url> [input_file]"
    exit 1
fi

if [[ ! -f "$INPUT_FILE" ]]; then
    echo "❌ ERROR: File not found: $INPUT_FILE"
    exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
    echo "❌ ERROR: jq is not installed."
    exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
    echo "❌ ERROR: curl is not installed."
    exit 1
fi


send_embed() {

    local text="$1"
    local part="$2"

    echo "📤 Sending embed part $part..."

    RESPONSE="$(
        jq -n \
            --arg title "🌐 Pavlov Live Servers - Part $part" \
            --arg description "$text" \
            '{
                username: "JTWP Server Browser",
                embeds: [
                    {
                        title: $title,
                        description: $description,
                        color: 3447003,
                        footer: {
                            text: "JTWP.org • Pavlov Server Browser"
                        }
                    }
                ]
            }' |
        curl -sS \
            -w "\n%{http_code}" \
            -H "Content-Type: application/json" \
            -X POST \
            -d @- \
            "$WEBHOOK_URL"
    )"

    HTTP_CODE="$(printf '%s\n' "$RESPONSE" | tail -n 1)"
    BODY="$(printf '%s\n' "$RESPONSE" | sed '$d')"

    if [[ "$HTTP_CODE" != "204" && "$HTTP_CODE" != "200" ]]; then
        echo "❌ Discord webhook failed"
        echo "HTTP: $HTTP_CODE"
        echo "$BODY"
        return 1
    fi

    echo "✅ Part $part sent"

    # Be friendly to Discord rate limits.
    sleep 1
}


buffer=""
part=1
server_count=0


# Read one COMPLETE server block at a time.
while IFS= read -r server_block; do

    # Remove leading/trailing blank lines.
    server_block="$(
        printf '%s\n' "$server_block" |
        sed '/./,$!d' |
        sed -e :a -e '/^\n*$/{$d;N;ba' -e '}'
    )"

    [[ -z "$server_block" ]] && continue

    # Add the separator back for Discord formatting.
    entry="${server_block}"$'\n\n'"${SEPARATOR}"

    new_length=$((
        ${#buffer}
        + ${#entry}
        + 2
    ))

    # If adding this entire server would exceed the embed limit,
    # send the existing buffer first.
    if (( new_length > MAX_LENGTH )) && [[ -n "$buffer" ]]; then

        send_embed \
            "$buffer" \
            "$part"

        ((part++))
        buffer=""
    fi

    if [[ -z "$buffer" ]]; then
        buffer="$entry"
    else
        buffer+=$'\n\n'"$entry"
    fi

    ((server_count++)) || true

done < <(
    awk '
        BEGIN {
            RS="\\*\\*\\*\\*\\*\\*\\*\\*\\*\\*\\*\\*\\*\\*\\*\\*\\*\\*\\*\\*"
            ORS="\0"
        }

        {
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", $0)

            if (length($0) > 0)
                printf "%s%c", $0, 0
        }
    ' "$INPUT_FILE"
)


# Send final remaining servers.
if [[ -n "$buffer" ]]; then
    send_embed \
        "$buffer" \
        "$part"
fi


echo
echo "=========================================="
echo "✅ Pavlov Server List Sent"
echo "=========================================="
echo "🖥️ Servers: $server_count"
echo "📨 Embeds:  $part"
