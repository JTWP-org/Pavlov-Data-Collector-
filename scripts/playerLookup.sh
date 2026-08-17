#!/bin/bash

PLAYER="$1"

INDEX="/home/steam/jtwp-collector-data/players/index/by_name.json"
RECORDS="/home/steam/jtwp-collector-data/players/records"

if [[ -z "$PLAYER" ]]; then
    echo "Usage: player-info <playername>"
    exit 1
fi

PRODUCT_ID=$(jq -r --arg player "${PLAYER,,}" '.[$player][0] // empty' "$INDEX")

if [[ -z "$PRODUCT_ID" ]]; then
    echo "Player not found: $PLAYER"
    exit 1
fi

PLAYER_DIR="$RECORDS/$PRODUCT_ID"

if [[ ! -d "$PLAYER_DIR" ]]; then
    echo "Player record directory not found:"
    echo "$PLAYER_DIR"
    exit 1
fi

echo "========================================"
echo " Player:    $PLAYER"
echo " ProductID: $PRODUCT_ID"
echo "========================================"
echo

jq . "$PLAYER_DIR"/*.json