# ⚙️ JTWP `config.json` Reference

This guide documents the major configuration sections used by the current JTWP
collector stack.

The current file is:

```text
/home/steam/jtwp-collector/Pavlov-Data-Collector-/config.json
```

Validate after every edit:

```bash
jq empty config.json && echo "✅ config.json VALID"
```

## 📁 Core Paths

```json
{
  "data_path": "/home/steam/jtwp-collector-data",
  "archive_path": "/home/steam/jtwp-log-archive",
  "old_archive_paths": [
    "/home/steam/logs"
  ]
}
```

### `data_path`

Persistent collector database root.

### `archive_path`

Primary archive destination for Pavlov logs handled by the collector.

### `old_archive_paths`

Additional historical locations that can be scanned/indexed.

## 🌐 General API / Cache Settings

```json
{
  "request_timeout_seconds": 8,
  "modio_game_id": 3959,
  "modio_cache_ttl_hours": 24,
  "ip_lookup_cache_ttl_days": 30,
  "rotate_active_logs": true,
  "count_unverified_player_kills": true
}
```

Secrets for these features belong in `.env`.

See `API_SETUP.md`.

## 🖥️ `servers`

Each Pavlov instance is an element of:

```json
"servers": []
```

Example:

```json
{
  "log_path": "/home/steam/pavlovserver/Pavlov/Saved/Logs/",
  "platform": "auto",
  "rcon": {
    "enabled": true,
    "host": "127.0.0.1",
    "port": 9000,
    "password_env": "PAVLOVSERVER_RCON_PASSWORD"
  }
}
```

### `log_path`

Pavlov log directory for that instance.

The collector derives the server ID from the path where possible.

### `platform`

Typical value:

```text
auto
```

### `rcon.enabled`

Enables RCON use for that server.

### `rcon.host`

For a Pavlov server on the same Linux host:

```text
127.0.0.1
```

### `rcon.port`

Must match the RCON/game instance configuration.

Current examples have used:

```text
pavlovserver   9000
pavlovserver0  9100
pavlovserver1  9200
```

### `rcon.password_env`

Name of the `.env` variable containing the plaintext RCON password.

Do not place the password itself in `config.json`.

## 🔌 `connection_watcher`

Example:

```json
"connection_watcher": {
  "poll_interval_seconds": 0.5,
  "start_at_end": true,
  "webhook_mode": "discord",
  "webhook_timeout_seconds": 8,
  "webhook_retries": 2
}
```

This controls the continuous player/network connection watcher.

## 🔐 `ssh_watcher`

Example:

```json
"ssh_watcher": {
  "units": [
    "ssh.service",
    "sshd.service"
  ],
  "enrich_ips": true,
  "include_invalid_user_events": false,
  "webhook_timeout_seconds": 8,
  "webhook_retries": 2,
  "auto_block_enabled": true,
  "auto_block_after": 20,
  "auto_block_command": "/usr/local/bin/block-ip",
  "auto_block_use_sudo": true,
  "auto_block_private_ips": false
}
```

With:

```json
"auto_block_after": 20
```

the current watcher blocks after the count goes **over** 20, so the 21st failed
attempt triggers blocking.

See `SSH_BLOCKING.md`.

## 🌊 `ddos_watcher`

Example:

```json
"ddos_watcher": {
  "enabled": true,
  "interface": "any",
  "window_seconds": 5,
  "cooldown_seconds": 60,
  "packets_per_second_threshold": 5000,
  "bytes_per_second_threshold": 5000000,
  "unique_sources_threshold": 100,
  "per_source_packets_per_second_threshold": 1500,
  "minimum_trigger_conditions": 2,
  "top_sources": 20,
  "monitored_ports": [],
  "capture_filter": "",
  "tcpdump_path": "/usr/bin/tcpdump"
}
```

Thresholds are starting points and should be tuned from normal traffic.

See `DDOS_AND_MAINTENANCE.md`.

## 🌍 Pavlov Public API

```json
{
  "pavlov_api_enabled": true,
  "pavlov_api_host_cache_ttl_days": 30
}
```

The actual endpoint/key material is obtained from environment/config logic used
by the collector.

Output is stored under:

```text
global/pavlov_api/
```

## 🎛️ `rcon_bridge`

Example:

```json
"rcon_bridge": {
  "enabled": true,
  "poll_interval_seconds": 0.25,
  "command_file": "rcon_commands.json",
  "game_modes_file": "game_modes.json",
  "default_maps_file": "default_maps.json",
  "limited_ammo_types_file": "limited_ammo_types.json",
  "remove_input_on_error": true,

  "ppapi_trigger_enabled": true,
  "ppapi_trigger_file": "EXE_PPAPI.json",
  "ppapi_updater": "update_pavlov_api.py",
  "ppapi_timeout_seconds": 300,

  "rcon_resource_trigger_enabled": true,
  "rcon_resource_trigger_file": "IN-RCON.json",
  "rcon_resource_output_file": "OUT--RCON.json",
  "rcon_resource_url": "...",
  "rcon_resource_local_file": "rcon_commands.json",
  "rcon_resource_timeout_seconds": 30
}
```

The current RCON watcher may also support a separate custom-command definition
file depending on the installed version.

See `RCON_GUIDE.md`.

## 🎚️ `active_file`

```json
"active_file": "active.json"
```

This points to the project's feature-switch configuration.

See `ACTIVE_JSON.md`.

## 💾 `data_tools`

Example:

```json
"data_tools": {
  "output_root": "/home/steam/jtwp-collector-output",
  "backup_dir": "/home/steam/jtwp-collector-output/backups",
  "export_dir": "/home/steam/jtwp-collector-output/exports",
  "env_file": "/home/steam/jtwp-collector/Pavlov-Data-Collector-/.env"
}
```

See `BACKUP_AND_RESTORE.md`.

## 🔁 `rcon_loop`

Example:

```json
"rcon_loop": {
  "enabled": true,
  "poll_interval_seconds": 0.5,
  "control_path": "/home/steam/pavlovserver/Pavlov/Saved/Config/ModSave/JTWP/Rcon/loopData.json",
  "output_path": "/home/steam/pavlovserver/Pavlov/Saved/Config/ModSave/JTWP/Rcon/loopOutput.json",
  "min_loop_seconds": 1,
  "max_loop_seconds": 3600
}
```

The loop repeatedly obtains RCON information according to its control file.

## 🛡️ `admin_notifications`

Example structure:

```json
"admin_notifications": {
  "enabled": true,
  "role_id": "DISCORD_ROLE_ID",
  "webhook_env": "JTWP_ADMIN_WEBHOOK_URL",
  "loop_output_path": "/home/steam/pavlovserver/Pavlov/Saved/Config/ModSave/JTWP/Rcon/loopOutput.json",
  "poll_interval_seconds": 2,
  "no_admin_delay_seconds": 60,
  "negative_score_threshold": 0,
  "teamkill_threshold": 2,
  "response_window_seconds": 900
}
```

Keep the webhook itself in `.env`.

## 🤖 `discord_bot`

Example:

```json
"discord_bot": {
  "enabled": true,
  "prefix": "!",
  "control_channel_id": "DISCORD_CHANNEL_ID",

  "roles": {
    "admin": "DISCORD_ADMIN_ROLE_ID",
    "owner": "DISCORD_OWNER_ROLE_ID"
  },

  "admin_allowed_rcon_commands": [
    "serverinfo",
    "inspectall",
    "maplist",
    "inspectplayer",
    "inspectteam",
    "help",
    "itemlist",
    "banlist",
    "ugcmodlist"
  ],

  "systemctl_actions": [
    "status",
    "start",
    "stop",
    "restart",
    "enable",
    "disable"
  ],

  "rcon_timeout_seconds": 15,
  "command_output_limit": 3500,
  "token_env": "JTWP_DISCORD_BOT_TOKEN"
}
```

### IDs are not secrets

Discord channel/role IDs are identifiers, but the bot token and webhooks are
credentials.

### `admin_allowed_rcon_commands`

Defines which RCON operations ADMIN users may perform through the bot.

### `systemctl_actions`

Application-level action allowlist. Linux sudoers must still independently
restrict what the `steam` account can execute.

## ➕ Adding `pavlovserver2`

Follow the existing server pattern and provide a unique RCON port and password
environment variable.

Example pattern:

```json
{
  "log_path": "/home/steam/pavlovserver2/Pavlov/Saved/Logs/",
  "platform": "auto",
  "rcon": {
    "enabled": true,
    "host": "127.0.0.1",
    "port": 9300,
    "password_env": "PAVLOVSERVER2_RCON_PASSWORD"
  }
}
```

`9300` above is only an example. Use the actual port assigned to that instance.

## 🔎 See the Effective Important Values

```bash
jq '{
  data_path,
  archive_path,
  old_archive_paths,
  servers,
  connection_watcher,
  ssh_watcher,
  ddos_watcher,
  pavlov_api_enabled,
  rcon_bridge,
  data_tools,
  rcon_loop,
  admin_notifications,
  discord_bot
}' config.json
```

## 🔐 Find Referenced Password Variables

```bash
jq -r \
    '.servers[] | select(.rcon.enabled == true) | .rcon.password_env' \
    config.json
```

## ✅ Config Change Checklist

```text
[ ] jq empty config.json succeeds
[ ] all configured server paths exist
[ ] every enabled RCON port is correct
[ ] every password_env exists in .env
[ ] active.json enables the intended component
[ ] service unit uses the expected config path
[ ] Python compiles before restart
[ ] only affected services are restarted
```
