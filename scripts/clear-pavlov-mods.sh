#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# JTWP Pavlov Mod Cleanup
#
# Usage:
#   sudo clear-pavlov-mods <server_id>
#
# Example:
#   sudo clear-pavlov-mods pavlovserver1
#
# This script:
#   1. Resolves a configured server ID to its server path.
#   2. Finds the exact systemd service for that path.
#   3. Saves service metadata + useful commands.
#   4. Stops the Pavlov service.
#   5. Confirms the service stopped.
#   6. Clears ONLY Pavlov/Saved/Mods contents.
#   7. Starts the service again.
#   8. Confirms it returned to active.
#   9. Logs the maintenance action.
# ============================================================


# ============================================================
# SETTINGS
# ============================================================

DATA_ROOT="/home/steam/jtwp-collector-data"

declare -A SERVER_PATHS=(
    ["pavlovserver"]="/home/steam/pavlovserver"
    ["pavlovserver0"]="/home/steam/pavlovserver0"
    ["pavlovserver1"]="/home/steam/pavlovserver1"
    ["pavlovserver2"]="/home/steam/pavlovserver2"
)

STOP_TIMEOUT=30
START_TIMEOUT=60


# ============================================================
# COLORS
# ============================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'


# ============================================================
# HELPERS
# ============================================================

fail() {
    echo -e "${RED}❌ $*${NC}" >&2
    exit 1
}


list_servers() {
    echo "Available servers:"
    echo

    for id in "${!SERVER_PATHS[@]}"; do
        printf "  %-20s %s\n" \
            "$id" \
            "${SERVER_PATHS[$id]}"
    done
}


find_service_for_path() {
    local server_path="$1"
    local service
    local working_directory
    local exec_start
    local -a exact_matches=()
    local -a exec_matches=()

    while read -r service _; do
        [[ -z "$service" ]] && continue

        working_directory="$(
            systemctl show "$service" \
                -p WorkingDirectory \
                --value \
                2>/dev/null || true
        )"

        exec_start="$(
            systemctl show "$service" \
                -p ExecStart \
                --value \
                2>/dev/null || true
        )"

        # ----------------------------------------------------
        # BEST MATCH:
        # WorkingDirectory exactly equals the configured path.
        #
        # This prevents:
        #
        # /home/steam/pavlovserver
        #
        # from incorrectly matching:
        #
        # /home/steam/pavlovserver0
        # /home/steam/pavlovserver1
        # /home/steam/pavlovserver2
        # ----------------------------------------------------

        if [[ "$working_directory" == "$server_path" ]]; then
            exact_matches+=("$service")
            continue
        fi

        # ----------------------------------------------------
        # FALLBACK MATCH:
        # ExecStart references a file INSIDE the exact path.
        #
        # The trailing "/" provides a path boundary.
        # ----------------------------------------------------

        if [[ "$exec_start" == *"$server_path/"* ]]; then
            exec_matches+=("$service")
        fi

    done < <(
        systemctl list-unit-files \
            --type=service \
            --no-legend \
            --no-pager
    )

    # Prefer exact WorkingDirectory matches.
    if (( ${#exact_matches[@]} == 1 )); then
        printf '%s\n' "${exact_matches[0]}"
        return 0
    fi

    if (( ${#exact_matches[@]} > 1 )); then
        echo "Multiple services have WorkingDirectory exactly equal to:" >&2
        echo "  $server_path" >&2
        printf '  %s\n' "${exact_matches[@]}" >&2
        return 2
    fi

    # Only use ExecStart fallback when there was no exact match.
    if (( ${#exec_matches[@]} == 1 )); then
        printf '%s\n' "${exec_matches[0]}"
        return 0
    fi

    if (( ${#exec_matches[@]} > 1 )); then
        echo "Multiple services reference files inside:" >&2
        echo "  $server_path" >&2
        printf '  %s\n' "${exec_matches[@]}" >&2
        return 2
    fi

    return 1
}


wait_for_inactive() {
    local service="$1"
    local waited=0

    while systemctl is-active --quiet "$service"; do
        if (( waited >= STOP_TIMEOUT )); then
            return 1
        fi

        sleep 1
        ((waited+=1))
    done

    return 0
}


wait_for_active() {
    local service="$1"
    local waited=0

    while ! systemctl is-active --quiet "$service"; do
        if (( waited >= START_TIMEOUT )); then
            return 1
        fi

        sleep 1
        ((waited+=1))
    done

    return 0
}


save_service_metadata() {
    local output="$1"
    local server_id="$2"
    local server_path="$3"
    local service="$4"

    local working_directory
    local exec_start
    local fragment_path
    local active_state
    local enabled_state
    local detected_at

    working_directory="$(
        systemctl show "$service" \
            -p WorkingDirectory \
            --value \
            2>/dev/null || true
    )"

    exec_start="$(
        systemctl show "$service" \
            -p ExecStart \
            --value \
            2>/dev/null || true
    )"

    fragment_path="$(
        systemctl show "$service" \
            -p FragmentPath \
            --value \
            2>/dev/null || true
    )"

    active_state="$(
        systemctl show "$service" \
            -p ActiveState \
            --value \
            2>/dev/null || true
    )"

    enabled_state="$(
        systemctl show "$service" \
            -p UnitFileState \
            --value \
            2>/dev/null || true
    )"

    detected_at="$(
        date -u +"%Y-%m-%dT%H:%M:%SZ"
    )"

    python3 - \
        "$output" \
        "$server_id" \
        "$server_path" \
        "$service" \
        "$working_directory" \
        "$exec_start" \
        "$fragment_path" \
        "$active_state" \
        "$enabled_state" \
        "$detected_at" <<'PY'
import json
import os
import sys
from pathlib import Path

(
    output,
    server_id,
    server_path,
    service,
    working_directory,
    exec_start,
    fragment_path,
    active_state,
    enabled_state,
    detected_at,
) = sys.argv[1:]

commands = {
    "status": f"sudo systemctl status {service} --no-pager",
    "start": f"sudo systemctl start {service}",
    "stop": f"sudo systemctl stop {service}",
    "restart": f"sudo systemctl restart {service}",
    "enable": f"sudo systemctl enable {service}",
    "disable": f"sudo systemctl disable {service}",
    "enable_now": f"sudo systemctl enable --now {service}",
    "disable_now": f"sudo systemctl disable --now {service}",
    "logs": f"sudo journalctl -u {service} -n 100 --no-pager",
    "logs_live": f"sudo journalctl -u {service} -f",
    "is_active": f"systemctl is-active {service}",
    "is_enabled": f"systemctl is-enabled {service}",
}

data = {
    "server_id": server_id,
    "server_path": server_path,
    "service": service,
    "detected_at": detected_at,
    "working_directory": working_directory or None,
    "exec_start": exec_start or None,
    "fragment_path": fragment_path or None,
    "active_state": active_state or None,
    "unit_file_state": enabled_state or None,
    "commands": commands,
}

path = Path(output)
path.parent.mkdir(parents=True, exist_ok=True)

tmp = path.with_name(path.name + ".tmp")

with tmp.open("w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")

os.replace(tmp, path)
PY
}


append_maintenance_log() {
    local output="$1"
    local server_id="$2"
    local service="$3"
    local mods_path="$4"
    local removed="$5"
    local success="$6"
    local message="$7"

    python3 - \
        "$output" \
        "$server_id" \
        "$service" \
        "$mods_path" \
        "$removed" \
        "$success" \
        "$message" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

(
    output,
    server_id,
    service,
    mods_path,
    removed,
    success,
    message,
) = sys.argv[1:]

record = {
    "timestamp": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
    "type": "clear_installed_mods",
    "server_id": server_id,
    "service": service,
    "mods_path": mods_path,
    "removed_entries": int(removed),
    "success": success.lower() == "true",
    "message": message,
}

path = Path(output)
path.parent.mkdir(parents=True, exist_ok=True)

with path.open("a", encoding="utf-8") as f:
    f.write(
        json.dumps(
            record,
            separators=(",", ":")
        )
        + "\n"
    )
PY
}


# ============================================================
# ROOT CHECK
# ============================================================

if [[ $EUID -ne 0 ]]; then
    fail "Run this script with sudo."
fi


# ============================================================
# ARGUMENT
# ============================================================

SERVER_ID="${1:-}"

if [[ -z "$SERVER_ID" ]]; then
    echo
    echo "Usage:"
    echo
    echo "  sudo clear-pavlov-mods <server_id>"
    echo
    list_servers
    echo
    exit 1
fi


# ============================================================
# VALIDATE SERVER ID
# ============================================================

if [[ -z "${SERVER_PATHS[$SERVER_ID]+x}" ]]; then
    echo -e "${RED}❌ Unknown server ID: $SERVER_ID${NC}"
    echo
    list_servers
    exit 1
fi


SERVER_PATH="$(
    realpath -m "${SERVER_PATHS[$SERVER_ID]}"
)"

MODS_PATH="$SERVER_PATH/Pavlov/Saved/Mods"

SERVICE_JSON="$DATA_ROOT/servers/$SERVER_ID/server/service.json"

MAINT_LOG="$DATA_ROOT/servers/$SERVER_ID/server/maintenance.jsonl"


# ============================================================
# SAFETY CHECKS
# ============================================================

[[ -d "$SERVER_PATH" ]] || \
    fail "Server path does not exist: $SERVER_PATH"

[[ -d "$MODS_PATH" ]] || \
    fail "Mods directory does not exist: $MODS_PATH"

EXPECTED="$(
    realpath -m "$SERVER_PATH/Pavlov/Saved/Mods"
)"

ACTUAL="$(
    realpath -m "$MODS_PATH"
)"

if [[ "$ACTUAL" != "$EXPECTED" ]]; then
    fail "Mods path safety check failed."
fi

# Extra hard guard against an empty or root-like path.
if [[ "$MODS_PATH" == "/" || "$MODS_PATH" == "/home" || "$MODS_PATH" == "/home/steam" ]]; then
    fail "Unsafe Mods path detected: $MODS_PATH"
fi


# ============================================================
# FIND SYSTEMD SERVICE
# ============================================================

echo
echo "🔎 Finding systemd service for:"
echo "   $SERVER_ID"
echo
echo "📁 Server path:"
echo "   $SERVER_PATH"
echo

set +e
SERVICE="$(
    find_service_for_path "$SERVER_PATH"
)"
RC=$?
set -e

if (( RC == 1 )); then
    fail "No systemd service references $SERVER_PATH"
fi

if (( RC == 2 )); then
    fail "Multiple matching services found; refusing to guess."
fi


# ============================================================
# SAVE SERVICE INFORMATION
# ============================================================

save_service_metadata \
    "$SERVICE_JSON" \
    "$SERVER_ID" \
    "$SERVER_PATH" \
    "$SERVICE"


# ============================================================
# COUNT MOD ENTRIES
# ============================================================

MOD_COUNT="$(
    find "$MODS_PATH" \
        -mindepth 1 \
        -maxdepth 1 \
        -print \
        2>/dev/null |
    wc -l
)"


# ============================================================
# SUMMARY
# ============================================================

echo "=============================================="
echo "🧹 Pavlov Mod Cleanup"
echo "=============================================="
echo
echo -e "🎮 Server ID:      ${CYAN}$SERVER_ID${NC}"
echo -e "📁 Server Path:    ${CYAN}$SERVER_PATH${NC}"
echo -e "⚙️ Service:        ${CYAN}$SERVICE${NC}"
echo -e "📦 Mods Directory: ${CYAN}$MODS_PATH${NC}"
echo -e "📊 Entries:        ${CYAN}$MOD_COUNT${NC}"
echo
echo "📝 Service metadata:"
echo "   $SERVICE_JSON"
echo
echo "📝 Maintenance log:"
echo "   $MAINT_LOG"
echo


# ============================================================
# FAILSAFE RESTART
# ============================================================

SERVER_STOPPED=false
CLEANUP_COMPLETE=false

restart_on_exit() {
    local rc=$?

    if [[ "$SERVER_STOPPED" == true && "$CLEANUP_COMPLETE" != true ]]; then
        echo
        echo -e "${YELLOW}⚠️ Cleanup exited early.${NC}"
        echo "Attempting to restart:"
        echo "  $SERVICE"

        systemctl start "$SERVICE" >/dev/null 2>&1 || true
    fi

    exit "$rc"
}

trap restart_on_exit EXIT


# ============================================================
# STOP SERVER
# ============================================================

echo -e "${YELLOW}🛑 Stopping $SERVICE...${NC}"

systemctl stop "$SERVICE"

if ! wait_for_inactive "$SERVICE"; then
    append_maintenance_log \
        "$MAINT_LOG" \
        "$SERVER_ID" \
        "$SERVICE" \
        "$MODS_PATH" \
        0 \
        false \
        "Service did not stop within ${STOP_TIMEOUT}s"

    fail "Server did not stop within ${STOP_TIMEOUT}s."
fi

SERVER_STOPPED=true

echo -e "${GREEN}✅ Server stopped.${NC}"
echo


# ============================================================
# CLEAR MODS
# ============================================================

echo "🧹 Clearing installed mods..."

# Delete everything INSIDE Mods, including hidden entries,
# but keep the Mods directory itself.
find "$MODS_PATH" \
    -mindepth 1 \
    -maxdepth 1 \
    -exec rm -rf -- {} +

echo -e "${GREEN}✅ Removed $MOD_COUNT entries.${NC}"
echo


# ============================================================
# START SERVER
# ============================================================

echo -e "${YELLOW}▶️ Starting $SERVICE...${NC}"

systemctl start "$SERVICE"

if ! wait_for_active "$SERVICE"; then
    append_maintenance_log \
        "$MAINT_LOG" \
        "$SERVER_ID" \
        "$SERVICE" \
        "$MODS_PATH" \
        "$MOD_COUNT" \
        false \
        "Mods cleared, but service failed to return to active state"

    fail "Mods were cleared, but $SERVICE failed to return to active state."
fi

SERVER_STOPPED=false
CLEANUP_COMPLETE=true

echo -e "${GREEN}✅ Server is running.${NC}"
echo


# ============================================================
# REFRESH SERVICE METADATA
# ============================================================

save_service_metadata \
    "$SERVICE_JSON" \
    "$SERVER_ID" \
    "$SERVER_PATH" \
    "$SERVICE"


# ============================================================
# LOG SUCCESS
# ============================================================

append_maintenance_log \
    "$MAINT_LOG" \
    "$SERVER_ID" \
    "$SERVICE" \
    "$MODS_PATH" \
    "$MOD_COUNT" \
    true \
    "Server stopped, installed mods cleared, and service restarted successfully"


# ============================================================
# FINISHED
# ============================================================

echo "=============================================="
echo -e "${GREEN}✅ Mod cleanup complete${NC}"
echo "=============================================="
echo
echo "🎮 Server:   $SERVER_ID"
echo "⚙️ Service:  $SERVICE"
echo "🗑️ Removed:  $MOD_COUNT entries"
echo "📝 Metadata: $SERVICE_JSON"
echo "📝 Log:      $MAINT_LOG"
echo

