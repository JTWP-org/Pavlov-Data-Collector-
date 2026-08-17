#!/usr/bin/env bash

set -euo pipefail

DATA="/home/steam/jtwp-collector-data"

PLAYER_INDEX="$DATA/players/index/by_ip_hash.json"
SSH_FAILED="$DATA/global/ssh/failed_hosts.json"
SERVERS="$DATA/servers"

if ! command -v jq >/dev/null 2>&1; then
    echo "ERROR: jq is required."
    exit 1
fi

if [[ ! -f "$PLAYER_INDEX" ]]; then
    echo "ERROR: Player IP index not found:"
    echo "$PLAYER_INDEX"
    exit 1
fi

echo "============================================================"
echo " JTWP Player / SSH / RCON IP Correlation"
echo "============================================================"
echo

show_players() {
    local HASH="$1"

    jq -r --arg hash "$HASH" '
        .[$hash][]?
    ' "$PLAYER_INDEX" 2>/dev/null
}

show_player_info() {
    local PID="$1"
    local PLAYER_FILE="$DATA/players/records/$PID/player.json"

    if [[ -f "$PLAYER_FILE" ]]; then
        jq -r '
            "    Player: " + (.current_name // "Unknown") +
            "\n    ProductID: " + (.product_id // "Unknown") +
            "\n    UniqueID: " + (.unique_id // "Unknown") +
            "\n    Admin: " + ((.admin // false)|tostring) +
            "\n    Banned: " + ((.banned // false)|tostring)
        ' "$PLAYER_FILE"
    else
        echo "    ProductID: $PID"
    fi
}

check_hash() {
    local TYPE="$1"
    local SERVER="$2"
    local HASH="$3"
    local ATTEMPTS="$4"

    mapfile -t PLAYERS < <(show_players "$HASH")

    if [[ ${#PLAYERS[@]} -eq 0 ]]; then
        return
    fi

    echo "------------------------------------------------------------"
    echo "MATCH FOUND"
    echo "Type:      $TYPE"

    if [[ -n "$SERVER" ]]; then
        echo "Server:    $SERVER"
    fi

    echo "IP Hash:   $HASH"

    if [[ -n "$ATTEMPTS" ]]; then
        echo "Attempts:  $ATTEMPTS"
    fi

    echo

    for PID in "${PLAYERS[@]}"; do
        show_player_info "$PID"
        echo
    done
}

#
# SSH FAILED CONNECTIONS
#

echo "Checking SSH failed connections..."

if [[ -f "$SSH_FAILED" ]]; then
    while IFS=$'\t' read -r HASH ATTEMPTS; do
        check_hash \
            "SSH Failed Authentication" \
            "" \
            "$HASH" \
            "$ATTEMPTS"
    done < <(
        jq -r '
            to_entries[] |
            [
                .key,
                (.value.failed_attempts // 0)
            ] |
            @tsv
        ' "$SSH_FAILED"
    )
fi

#
# RCON CONNECTIONS
#

echo "Checking RCON connections..."

for SERVER_DIR in "$SERVERS"/*; do

    [[ -d "$SERVER_DIR" ]] || continue

    SERVER_ID="$(basename "$SERVER_DIR")"

    RCON_KNOWN="$SERVER_DIR/rcon/known_hosts.json"
    RCON_FAILED="$SERVER_DIR/rcon/failed_hosts.json"

    #
    # Successful RCON authentication
    #
    if [[ -f "$RCON_KNOWN" ]]; then
        while IFS=$'\t' read -r HASH COUNT; do
            check_hash \
                "RCON Successful Authentication" \
                "$SERVER_ID" \
                "$HASH" \
                "$COUNT"
        done < <(
            jq -r '
                to_entries[] |
                [
                    .key,
                    (.value.successful_connections // 0)
                ] |
                @tsv
            ' "$RCON_KNOWN"
        )
    fi

    #
    # Failed RCON authentication
    #
    if [[ -f "$RCON_FAILED" ]]; then
        while IFS=$'\t' read -r HASH COUNT; do
            check_hash \
                "RCON Failed Authentication" \
                "$SERVER_ID" \
                "$HASH" \
                "$COUNT"
        done < <(
            jq -r '
                to_entries[] |
                [
                    .key,
                    (.value.failed_attempts // 0)
                ] |
                @tsv
            ' "$RCON_FAILED"
        )
    fi

done

echo
echo "============================================================"
echo " Scan Complete"
echo "============================================================"