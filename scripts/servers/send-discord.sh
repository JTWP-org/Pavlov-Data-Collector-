#!/usr/bin/env bash
set -euo pipefail

WEBHOOK_URL="${1:-}"
MODE="${2:-}"
INPUT="${3:-}"
TITLE="${4:-JTWP}"

MAX_LENGTH=3900
SEPARATOR='********************'

usage() {
    echo "Usage:"
    echo "  $0 <webhook_url> text <file> <title>"
    echo "  $0 <webhook_url> image <image_file> <title>"
}

if [[ -z "$WEBHOOK_URL" || -z "$MODE" || -z "$INPUT" ]]; then
    echo "❌ Missing required argument."
    usage
    exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
    echo "❌ jq is not installed."
    exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
    echo "❌ curl is not installed."
    exit 1
fi

discord_post_json() {
    local payload="$1"
    local response
    local http_code
    local body

    response="$(
        curl -sS \
            -w $'\n%{http_code}' \
            -H "Content-Type: application/json" \
            -X POST \
            -d "$payload" \
            "$WEBHOOK_URL"
    )"

    http_code="$(printf '%s\n' "$response" | tail -n 1)"
    body="$(printf '%s\n' "$response" | sed '$d')"

    if [[ "$http_code" == "200" || "$http_code" == "204" ]]; then
        return 0
    fi

    echo "❌ Discord request failed."
    echo "HTTP: $http_code"
    [[ -n "$body" ]] && echo "$body"
    return 1
}

send_text_part() {
    local content="$1"
    local part="$2"
    local payload

    payload="$(
        jq -n \
            --arg title "$TITLE - Part $part" \
            --arg description "$content" \
            '{
                username: "JTWP",
                embeds: [
                    {
                        title: $title,
                        description: $description,
                        color: 3447003,
                        footer: {
                            text: "JTWP.org"
                        }
                    }
                ]
            }'
    )"

    discord_post_json "$payload"
    echo "✅ Part $part sent."
    sleep 1
}

send_text() {
    local buffer=""
    local part=1
    local block=""
    local new_length

    if [[ ! -s "$INPUT" ]]; then
        echo "❌ Text input file is missing or empty:"
        echo "   $INPUT"
        exit 1
    fi

    while IFS= read -r -d '' block; do
        [[ -z "$block" ]] && continue

        block="$(
            printf '%s' "$block" |
            sed \
                -e ':a' \
                -e '/^[[:space:]]*$/{$d;N;ba' \
                -e '}' \
                -e '/./,$!d'
        )"

        [[ -z "$block" ]] && continue

        block="${block}"$'\n'"$SEPARATOR"

        if (( ${#block} > MAX_LENGTH )); then
            echo "❌ One server block exceeds $MAX_LENGTH characters."
            exit 1
        fi

        new_length=$(( ${#buffer} + ${#block} + 2 ))

        if (( new_length > MAX_LENGTH )) && [[ -n "$buffer" ]]; then
            send_text_part "$buffer" "$part"
            ((part++))
            buffer=""
        fi

        if [[ -z "$buffer" ]]; then
            buffer="$block"
        else
            buffer+=$'\n\n'"$block"
        fi
    done < <(
        awk -v sep="$SEPARATOR" '
            BEGIN {
                RS=sep
            }
            {
                gsub(/^[[:space:]]+|[[:space:]]+$/, "", $0)
                if (length($0) > 0) {
                    printf "%s%c", $0, 0
                }
            }
        ' "$INPUT"
    )

    if [[ -n "$buffer" ]]; then
        send_text_part "$buffer" "$part"
    fi

    echo "✅ Text send complete. Embeds sent: $part"
}

send_image() {
    local filename
    local payload
    local response
    local http_code
    local body

    if [[ ! -f "$INPUT" ]]; then
        echo "❌ Image not found:"
        echo "   $INPUT"
        exit 1
    fi

    filename="$(basename "$INPUT")"

    payload="$(
        jq -nc \
            --arg title "$TITLE" \
            --arg filename "$filename" \
            '{
                username: "JTWP",
                embeds: [
                    {
                        title: $title,
                        color: 3447003,
                        image: {
                            url: ("attachment://" + $filename)
                        },
                        footer: {
                            text: "JTWP.org"
                        }
                    }
                ]
            }'
    )"

    response="$(
        curl -sS \
            -w $'\n%{http_code}' \
            -X POST \
            -F "payload_json=$payload" \
            -F "files[0]=@$INPUT;filename=$filename" \
            "$WEBHOOK_URL"
    )"

    http_code="$(printf '%s\n' "$response" | tail -n 1)"
    body="$(printf '%s\n' "$response" | sed '$d')"

    if [[ "$http_code" == "200" || "$http_code" == "204" ]]; then
        echo "✅ Image sent successfully: $filename"
        return 0
    fi

    echo "❌ Discord image upload failed."
    echo "HTTP: $http_code"
    [[ -n "$body" ]] && echo "$body"
    return 1
}

case "${MODE,,}" in
    text)
        send_text
        ;;
    image)
        send_image
        ;;
    *)
        echo "❌ Unknown mode: $MODE"
        echo "Valid modes: text, image"
        exit 1
        ;;
esac
