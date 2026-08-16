#!/usr/bin/env bash

set -euo pipefail

IP="${1:-}"

if [[ -z "$IP" ]]; then
    echo "Usage: sudo $0 <IP>"
    exit 1
fi

if ! python3 -c "import ipaddress; ipaddress.ip_address('$IP')" 2>/dev/null; then
    echo "Invalid IP address: $IP"
    exit 1
fi

echo "Unblocking: $IP"

ufw delete deny from "$IP" to any || true
ufw delete deny out to "$IP" || true

echo "Unblocked $IP"
ufw status numbered
