#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <rcon-password>"
    echo "Prints Pavlov RCON's lowercase MD5 password hash."
    exit 1
fi

printf '%s' "$1" | md5sum | awk '{print $1}'
