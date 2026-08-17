#!/usr/bin/env bash
set -euo pipefail

PROJECT="/home/steam/jtwp-collector/Pavlov-Data-Collector-"
VENV="/home/steam/jtwp-collector/venv"

echo "Installing async-pavlov..."
"$VENV/bin/pip" install async-pavlov

echo "Installing systemd service..."
sudo install -m 644 "$PROJECT/jtwp-rcon-trigger-watcher.service" /etc/systemd/system/jtwp-rcon-trigger-watcher.service

echo "Reloading systemd..."
sudo systemctl daemon-reload

echo "Enabling and starting RCON trigger watcher..."
sudo systemctl enable --now jtwp-rcon-trigger-watcher

echo
sudo systemctl status jtwp-rcon-trigger-watcher --no-pager
