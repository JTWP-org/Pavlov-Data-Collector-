
```
Pavlov-Data-Collector-/
├── README-UPDATED-SCRIPTS.md
├── active.json
├── active_config.py
├── admin_monitor.py
├── collector.py
├── config.json
├── connection_watcher.py
├── custom_commands.json
├── ddos_watcher.py
├── discord_bot.py
├── rcon_loop.py
├── rcon_trigger_watcher.py
├── requirements-additions.txt
├── requirements.txt
├── ssh_watcher.py
├── update_pavlov_api.py
│
├── resource/
│   ├── BalancingTable.csv
│   ├── README.md
│   ├── WebhookResponseCodes.json
│   ├── default_maps.json
│   ├── game_modes.json
│   ├── gunEmoji.json
│   ├── icon.json
│   ├── items.json
│   ├── limited_ammo_types.json
│   ├── rcon_commands.json
│   ├── resource_audit.json
│   └── resource_manifest.json
│
├── scripts/
│   ├── LIVEservers.sh
│   ├── backup-data.py
│   ├── block-ip.sh
│   ├── check-player-connections.sh
│   ├── clear-data.sh
│   ├── clear-pavlov-mods.sh
│   ├── export-data.py
│   ├── generate-server-image.py
│   ├── install-rcon-bridge.sh
│   ├── playerLookup.sh
│   ├── rcon-md5.sh
│   ├── rebuild-ip-index.py
│   ├── run-collector.sh
│   ├── send-ddos-embed.sh
│   ├── set-rcon-loop.py
│   ├── setup-data-links.sh
│   ├── ufw-fix.sh
│   ├── unblock-ip.sh
│   ├── update-pavlov-api.sh
│   ├── validate-resources.py
│   │
│   └── servers/
│       ├── LIVEserversArray.sh
│       ├── LIVEserversIMG.sh
│       ├── build-string-array.sh
│       ├── generate-server-image.py
│       ├── send-discord.sh
│       └── send-server-list.sh
│
└── systemd/
    ├── jtwp-admin-monitor.service
    ├── jtwp-collector.service
    ├── jtwp-collector.timer
    ├── jtwp-connection-watcher.service
    ├── jtwp-ddos-watcher.service
    ├── jtwp-discord-bot.service
    ├── jtwp-rcon-loop.service
    ├── jtwp-rcon-trigger-watcher.service
    └── jtwp-ssh-watcher.service
    ```


# JTWP Latest Updated Scripts Package

This package consolidates the corrected JTWP scripts from the earlier review and
updates them for the reviewed `resource/` folder.

## Important changes in this package

### RCON resources

`rcon_trigger_watcher.py` and `config.json` now use:

```text
resource/rcon_commands.json
resource/game_modes.json
resource/default_maps.json
resource/limited_ammo_types.json
```

The RCON resource refresh also writes back to:

```text
resource/rcon_commands.json
```

### Live-server commands

`custom_commands.json` now points to the retained layout:

```text
scripts/servers/LIVEserversArray.sh
scripts/servers/LIVEserversIMG.sh
```

instead of the old project-level live-server wrappers.

### Resource validator

Run:

```bash
/home/steam/jtwp-collector/venv/bin/python3     scripts/validate-resources.py
```

It validates the resource JSON schemas, RCON command count, limited-ammo keys,
and balancing table.

## Validation performed

- Main Python files: syntax OK
- Python files under scripts/: syntax OK
- Shell scripts: `bash -n` OK
- Project/resource JSON: parse OK
- Resource validation helper: passed

## Install

Back up the existing project before replacing files.

Then copy the contents of this package into:

```text
/home/steam/jtwp-collector/Pavlov-Data-Collector-/
```

preserving the `scripts/`, `scripts/servers/`, `resource/`, and `systemd/`
directories.

Before restarting services:

```bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-

jq empty config.json
jq empty active.json

/home/steam/jtwp-collector/venv/bin/python3     -m compileall -q .

/home/steam/jtwp-collector/venv/bin/python3     scripts/validate-resources.py
```
