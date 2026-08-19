# JTWP Fix Pass

- Validated all uploaded Python files and JSON files.
- Replaced fixed .tmp atomic JSON writes with unique same-directory temp files in admin_monitor, ddos_watcher, rcon_loop, and rcon_trigger_watcher.
- Hardened rcon_trigger_watcher load_json against malformed/unreadable JSON.
- Added automatic .env loading beside config.json to collector, admin_monitor, connection_watcher, ddos_watcher, discord_bot, rcon_loop, and rcon_trigger_watcher.
- Resolved config paths and relative active.json paths from the config directory so scripts do not depend on current working directory.
- Added the missing !backupdata handler to discord_bot.py.
- Aligned exportdata/backupdata custom commands with the Python scripts used by the Discord bot; made cleardata noninteractive sudo --yes; detached restartjtwp.
- Added ActiveConfig.last_error diagnostics while retaining existing fail-open behavior.

## Not changed

- No pavlovserver2 entry was invented because the uploaded config does not provide its RCON port/password environment variable.
- No missing scripts such as scripts/export-data.py, scripts/backup-data.py, clear-data.sh, run-collector.sh, or live-server scripts were generated because they were not part of this upload.
