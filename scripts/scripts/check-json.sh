#!/usr/bin/env bash

set -uo pipefail

# ============================================
# SETTINGS
# ============================================

# Directory to scan.
# Default: project root (parent of this scripts folder)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_ROOT="$(dirname "$SCRIPT_DIR")"

SCAN_PATH="${1:-$DEFAULT_ROOT}"

# ============================================
# COLORS
# ============================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# ============================================
# CHECK REQUIREMENTS
# ============================================

if ! command -v jq >/dev/null 2>&1; then
    echo -e "${RED}❌ jq is not installed.${NC}"
    echo
    echo "Install it with:"
    echo "sudo apt install jq"
    exit 1
fi

if [[ ! -d "$SCAN_PATH" ]]; then
    echo -e "${RED}❌ Directory does not exist:${NC}"
    echo "$SCAN_PATH"
    exit 1
fi

# ============================================
# START
# ============================================

echo
echo "=============================================="
echo "🔍 JTWP JSON Validator"
echo "=============================================="
echo
echo "📁 Scanning:"
echo "$SCAN_PATH"
echo

TOTAL=0
VALID=0
INVALID=0

# ============================================
# SCAN JSON FILES
# ============================================

while IFS= read -r -d '' FILE; do

    ((TOTAL++))

    # Capture jq's actual parse error.
    ERROR="$(jq empty "$FILE" 2>&1)"
    STATUS=$?

    if [[ $STATUS -eq 0 ]]; then

        ((VALID++))

        echo -e "${GREEN}✅ VALID${NC}   $FILE"

    else

        ((INVALID++))

        echo
        echo -e "${RED}❌ INVALID${NC} $FILE"
        echo -e "${YELLOW}   $ERROR${NC}"
        echo

    fi

done < <(
    find "$SCAN_PATH" \
        -type f \
        -iname '*.json' \
        -print0
)

# ============================================
# SUMMARY
# ============================================

echo
echo "=============================================="
echo "📊 JSON Validation Summary"
echo "=============================================="
echo
echo -e "📄 Total:   ${CYAN}$TOTAL${NC}"
echo -e "✅ Valid:   ${GREEN}$VALID${NC}"
echo -e "❌ Invalid: ${RED}$INVALID${NC}"
echo

if [[ $INVALID -gt 0 ]]; then
    echo -e "${RED}❌ JSON validation FAILED.${NC}"
    exit 1
else
    echo -e "${GREEN}✅ All JSON files are valid!${NC}"
    exit 0
fi
