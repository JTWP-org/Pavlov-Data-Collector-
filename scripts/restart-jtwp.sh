#!/usr/bin/env bash

set -e

echo "🔄 Restarting JTWP services..."

SERVICES=(
    jtwp-admin-monitor
    jtwp-discord-bot
    jtwp-rcon-loop
    jtwp-ssh-watcher
    jtwp-ddos-watcher
)

for SERVICE in "${SERVICES[@]}"; do
    if systemctl list-unit-files "${SERVICE}.service" --no-legend 2>/dev/null | grep -q "${SERVICE}.service"; then
        echo "  ↻ $SERVICE"
        systemctl restart "$SERVICE"
    else
        echo "  ⚠ $SERVICE not installed"
    fi
done

echo
echo "✅ JTWP services restarted."
echo

for SERVICE in "${SERVICES[@]}"; do
    if systemctl list-unit-files "${SERVICE}.service" --no-legend 2>/dev/null | grep -q "${SERVICE}.service"; then
        printf "%-25s " "$SERVICE"
        systemctl is-active "$SERVICE"
    fi
done
