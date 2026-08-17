#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# SETTINGS
# Add/remove Pavlov server IDs here.
# ============================================================

DATA_ROOT="/home/steam/jtwp-collector-data"

declare -A SERVER_PATHS=(
    ["pavlovserver"]="/home/steam/pavlovserver"
    ["pavlovserver0"]="/home/steam/pavlovserver0"
    ["pavlovserver1"]="/home/steam/pavlovserver1"
)

STOP_TIMEOUT=30
START_TIMEOUT=60

# ============================================================
# HELPERS
# ============================================================

fail() {
    echo "❌ $*" >&2
    exit 1
}

list_servers() {
    echo "Available servers:"
    for id in "${!SERVER_PATHS[@]}"; do
        printf '  %-20s %s\n' "$id" "${SERVER_PATHS[$id]}"
    done
}

find_service_for_path() {
    local server_path="$1"
    local service info
    local -a matches=()

    while read -r service _; do
        [[ -z "$service" ]] && continue

        info="$(
            systemctl show "$service" \
                -p WorkingDirectory \
                -p ExecStart \
                -p FragmentPath \
                2>/dev/null || true
        )"

        if grep -Fq "$server_path" <<<"$info"; then
            matches+=("$service")
        fi
    done < <(
        systemctl list-unit-files \
            --type=service \
            --no-legend \
            --no-pager
    )

    if (( ${#matches[@]} == 0 )); then
        return 1
    fi

    if (( ${#matches[@]} > 1 )); then
        echo "Multiple services reference $server_path:" >&2
        printf '  %s\n' "${matches[@]}" >&2
        return 2
    fi

    printf '%s\n' "${matches[0]}"
}

wait_for_inactive() {
    local service="$1"
    local waited=0

    while systemctl is-active --quiet "$service"; do
        (( waited >= STOP_TIMEOUT )) && return 1
        sleep 1
        ((waited+=1))
    done
}

wait_for_active() {
    local service="$1"
    local waited=0

    while ! systemctl is-active --quiet "$service"; do
        (( waited >= START_TIMEOUT )) && return 1
        sleep 1
        ((waited+=1))
    done
}

save_service_metadata() {
    local output="$1"
    local server_id="$2"
    local server_path="$3"
    local service="$4"

    local working_directory exec_start fragment_path active_state enabled_state detected_at

    working_directory="$(systemctl show "$service" -p WorkingDirectory --value 2>/dev/null || true)"
    exec_start="$(systemctl show "$service" -p ExecStart --value 2>/dev/null || true)"
    fragment_path="$(systemctl show "$service" -p FragmentPath --value 2>/dev/null || true)"
    active_state="$(systemctl show "$service" -p ActiveState --value 2>/dev/null || true)"
    enabled_state="$(systemctl show "$service" -p UnitFileState --value 2>/dev/null || true)"
    detected_at="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"

    python3 - \
        "$output" "$server_id" "$server_path" "$service" \
        "$working_directory" "$exec_start" "$fragment_path" \
        "$active_state" "$enabled_state" "$detected_at" <<'PY'
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

data = {
    "server_id": server_id,
    "server_path": server_path,
    "service": service,
    "detected_at": detected_at,
    "matches": [{
        "service": service,
        "working_directory": working_directory or None,
        "exec_start": exec_start or None,
        "fragment_path": fragment_path or None,
        "active_state": active_state or None,
        "unit_file_state": enabled_state or None,
    }],
    "match_count": 1,
    "commands": {
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
    },
}

path = Path(output)
path.parent.mkdir(parents=True, exist_ok=True)
tmp = path.with_name(path.name + ".tmp")
tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
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
        "$output" "$server_id" "$service" "$mods_path" \
        "$removed" "$success" "$message" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

output, server_id, service, mods_path, removed, success, message = sys.argv[1:]

record = {
    "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
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
    f.write(json.dumps(record, separators=(",", ":")) + "\n")
PY
}

# ============================================================
# ARGUMENTS / VALIDATION
# ============================================================

if [[ $EUID -ne 0 ]]; then
    fail "Run this script with sudo."
fi

SERVER_ID="${1:-}"

if [[ -z "$SERVER_ID" ]]; then
    echo "Usage: sudo $0 <server_id>"
    echo
    list_servers
    exit 1
fi

if [[ -z "${SERVER_PATHS[$SERVER_ID]+x}" ]]; then
    echo "❌ Unknown server ID: $SERVER_ID"
    echo
    list_servers
    exit 1
fi

SERVER_PATH="$(realpath -m "${SERVER_PATHS[$SERVER_ID]}")"
MODS_PATH="$SERVER_PATH/Pavlov/Saved/Mods"
SERVICE_JSON="$DATA_ROOT/servers/$SERVER_ID/server/service.json"
MAINT_LOG="$DATA_ROOT/servers/$SERVER_ID/server/maintenance.jsonl"

[[ -d "$SERVER_PATH" ]] || fail "Server path does not exist: $SERVER_PATH"
[[ -d "$MODS_PATH" ]] || fail "Mods path does not exist: $MODS_PATH"

EXPECTED="$(realpath -m "$SERVER_PATH/Pavlov/Saved/Mods")"
ACTUAL="$(realpath -m "$MODS_PATH")"
[[ "$ACTUAL" == "$EXPECTED" ]] || fail "Mods path safety check failed."

# ============================================================
# FIND SERVICE
# ============================================================

echo "🔎 Finding systemd service for $SERVER_ID..."

set +e
SERVICE="$(find_service_for_path "$SERVER_PATH")"
RC=$?
set -e

(( RC == 0 )) || {
    if (( RC == 1 )); then
        fail "No systemd service references $SERVER_PATH"
    fi
    fail "Multiple matching services found; refusing to guess."
}

save_service_metadata "$SERVICE_JSON" "$SERVER_ID" "$SERVER_PATH" "$SERVICE"

MOD_COUNT="$(
    find "$MODS_PATH" -mindepth 1 -maxdepth 1 -print 2>/dev/null | wc -l
)"

echo
echo "=============================================="
echo "🧹 Pavlov Mod Cleanup"
echo "=============================================="
echo "🎮 Server ID:      $SERVER_ID"
echo "📁 Server Path:    $SERVER_PATH"
echo "⚙️ Service:        $SERVICE"
echo "📦 Mods Directory: $MODS_PATH"
echo "📊 Entries:        $MOD_COUNT"
echo "📝 Service Data:   $SERVICE_JSON"
echo

SERVER_STOPPED=false
CLEANUP_COMPLETE=false

restart_on_exit() {
    local rc=$?

    if [[ "$SERVER_STOPPED" == true ]] && [[ "$CLEANUP_COMPLETE" != true ]]; then
        echo "⚠️ Attempting to restart $SERVICE because the cleanup exited early..." >&2
        systemctl start "$SERVICE" >/dev/null 2>&1 || true
    fi

    exit "$rc"
}
trap restart_on_exit EXIT

# ============================================================
# STOP -> CLEAR -> START
# ============================================================

echo "🛑 Stopping $SERVICE..."
systemctl stop "$SERVICE"

if ! wait_for_inactive "$SERVICE"; then
    append_maintenance_log \
        "$MAINT_LOG" "$SERVER_ID" "$SERVICE" "$MODS_PATH" 0 false \
        "Service did not stop within ${STOP_TIMEOUT}s"
    fail "Server did not stop within ${STOP_TIMEOUT}s."
fi

SERVER_STOPPED=true
echo "✅ Server stopped."

echo "🧹 Clearing installed mods..."
find "$MODS_PATH" \
    -mindepth 1 \
    -maxdepth 1 \
    -exec rm -rf -- {} +

echo "✅ Removed $MOD_COUNT entries."

echo "▶️ Starting $SERVICE..."
systemctl start "$SERVICE"

if ! wait_for_active "$SERVICE"; then
    append_maintenance_log \
        "$MAINT_LOG" "$SERVER_ID" "$SERVICE" "$MODS_PATH" "$MOD_COUNT" false \
        "Mods cleared, but service failed to return to active state"
    fail "Mods were cleared, but $SERVICE failed to return to active state."
fi

SERVER_STOPPED=false
CLEANUP_COMPLETE=true

# Refresh metadata now that service is running again.
save_service_metadata "$SERVICE_JSON" "$SERVER_ID" "$SERVER_PATH" "$SERVICE"

append_maintenance_log \
    "$MAINT_LOG" "$SERVER_ID" "$SERVICE" "$MODS_PATH" "$MOD_COUNT" true \
    "Server stopped, installed mods cleared, and service restarted successfully"

echo
echo "=============================================="
echo "✅ Mod cleanup complete"
echo "=============================================="
echo "🎮 Server:  $SERVER_ID"
echo "⚙️ Service: $SERVICE"
echo "🗑️ Removed: $MOD_COUNT entries"
echo "📝 Log:      $MAINT_LOG"
