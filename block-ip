#!/usr/bin/env bash

set -euo pipefail

IP="${1:-}"

if [[ -z "$IP" ]]; then
    echo "Usage: sudo $0 <IP>"
    exit 1
fi

# Basic IPv4 validation
if ! python3 -c "import ipaddress; ipaddress.ip_address('$IP')" 2>/dev/null; then
    echo "Invalid IP address: $IP"
    exit 1
fi

# Safety: don't accidentally block the IP of your current SSH session
SSH_IP="${SSH_CONNECTION%% *}"

if [[ -n "${SSH_CONNECTION:-}" && "$IP" == "$SSH_IP" ]]; then
    echo "ERROR: $IP is the IP of your current SSH connection."
    echo "Blocking it would disconnect you."
    exit 1
fi

echo "Blocking all traffic for: $IP"

# Block incoming connections FROM this IP
ufw deny from "$IP" to any

# Block outgoing connections TO this IP
ufw deny out to "$IP"

echo
echo "Blocked:"
echo "  IN  <- $IP"
echo "  OUT -> $IP"

ufw status numbered
