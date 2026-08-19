#!/usr/bin/env bash

set -euo pipefail

echo "=========================================="
echo "🛡️ JTWP UFW Block Order Repair"
echo "=========================================="
echo

if [[ $EUID -ne 0 ]]; then
    echo "❌ Run this script with sudo."
    exit 1
fi

# Collect IPv4 addresses that currently have DENY IN rules.
mapfile -t BLOCKED_IPS < <(
    ufw status |
    awk '
        $2 == "DENY" &&
        $3 ~ /^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/ {
            print $3
        }
    ' |
    sort -u
)

COUNT="${#BLOCKED_IPS[@]}"

if [[ "$COUNT" -eq 0 ]]; then
    echo "✅ No IPv4 DENY IN rules found."
    exit 0
fi

echo "🔎 Found $COUNT blocked IPs:"
echo

printf '  %s\n' "${BLOCKED_IPS[@]}"

echo
echo "🔄 Moving blocked IPs above ALLOW rules..."
echo

for IP in "${BLOCKED_IPS[@]}"; do

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🚫 $IP"

    # Remove the existing inbound rule by rule definition.
    # This is safer than deleting by rule number.
    ufw --force delete deny from "$IP" to any || true

    # Put the inbound block at the very top.
    ufw insert 1 deny from "$IP" to any

    # Make sure outbound block exists too.
    # UFW will skip it if it already exists.
    ufw deny out to "$IP"

done

echo
echo "=========================================="
echo "✅ Repair complete"
echo "=========================================="
echo

ufw status numbered
