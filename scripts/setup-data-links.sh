#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# SETTINGS
# ============================================================

# Main collector data directory
SOURCE_ROOT="/home/steam/jtwp-collector-data"

# Where the symlinks should be created
DEST_ROOT="/home/steam/pavlovserver1/Pavlov/Saved/Config/ModSave/JTWP/Data"

# Folders to expose through symlinks
LINKS=(
    "servers"
    "players"
    "global"
)

# If true, existing symlinks will be replaced
REPLACE_EXISTING=true

# ============================================================
# SCRIPT
# ============================================================

echo "========================================"
echo " JTWP Data Link Setup"
echo "========================================"
echo

echo "Source:"
echo "  $SOURCE_ROOT"
echo

echo "Destination:"
echo "  $DEST_ROOT"
echo

# Create destination path if needed
mkdir -p "$DEST_ROOT"

for NAME in "${LINKS[@]}"; do

    SOURCE="$SOURCE_ROOT/$NAME"
    DEST="$DEST_ROOT/$NAME"

    echo "Processing: $NAME"

    # Make sure source exists
    if [[ ! -e "$SOURCE" ]]; then
        echo "  ERROR: Source does not exist:"
        echo "  $SOURCE"
        echo
        continue
    fi

    # Existing destination
    if [[ -L "$DEST" ]]; then

        if [[ "$REPLACE_EXISTING" == "true" ]]; then
            echo "  Replacing existing symlink..."
            rm "$DEST"
        else
            echo "  Symlink already exists. Skipping."
            echo
            continue
        fi

    elif [[ -e "$DEST" ]]; then
        echo "  ERROR: Destination exists and is not a symlink:"
        echo "  $DEST"
        echo "  Not touching it."
        echo
        continue
    fi

    ln -s "$SOURCE" "$DEST"

    echo "  Created:"
    echo "  $DEST -> $SOURCE"
    echo

done

echo "========================================"
echo " Current Links"
echo "========================================"

ls -lah "$DEST_ROOT"
