# 📚 JTWP Guide Index

These Guides are organized so each subject has one **canonical** home.
The quick-reference files may repeat individual commands, but full setup
procedures should live only in the guide named below.

| Guide | Canonical purpose |
|---|---|
| `INSTALL_AND_UPDATE.md` | Installation order, upgrades and first-run validation |
| `CONFIG_REFERENCE.md` | `config.json` settings and section reference |
| `API_SETUP.md` | `.env`, secrets, API keys and RCON environment variables |
| `ACTIVE_JSON.md` | Feature enable/disable switches |
| `SERVICES.md` | systemd services, timers, permissions and service troubleshooting |
| `SECURITY_AND_SUDOERS.md` | Linux permissions, sudoers, secrets and privilege boundaries |
| `SCRIPTS.md` | Helper scripts and `/usr/local/bin` installation |
| `RCON_GUIDE.md` | RCON protocol, ModSave bridge, commands and RCON troubleshooting |
| `SSH_BLOCKING.md` | SSH watcher auto-block setup and UFW behavior |
| `DDOS_AND_MAINTENANCE.md` | DDoS watcher and Pavlov mod cleanup |
| `LIVE_SERVERS.md` | `scripts/servers/` text/image/Discord server-list pipeline |
| `DISCORD_BOT_SETUP.md` | Discord application/bot setup and permissions |
| `BACKUP_AND_RESTORE.md` | Data backup, portable export and restore procedure |
| `DATA_LAYOUT.md` | Persistent collector-data directory/file map |
| `TROUBLESHOOTING.md` | Symptom-driven failure diagnosis and recovery |
| `COMPONENTS_AND_MANUAL_TRIGGERS.md` | How to manually trigger/test each component |
| `FEATURES_AND_DATA_POINTS.md` | Inventory of collected/derived data |
| `USEFUL_COMMANDS.md` | Short command cheat sheet |

## Documentation Rules

1. Put secrets only in `.env`.
2. Keep `JTWP_IP_HASH_SECRET` stable once data exists.
3. Keep `scripts/` and `servers/` in their existing repository structure.
4. Put service installation details in `SERVICES.md`, not in every component guide.
5. Put helper installation details in `SCRIPTS.md`.
6. Put API-key acquisition/configuration in `API_SETUP.md`.
7. Put command examples in `USEFUL_COMMANDS.md` only as quick references.
8. Put destructive-operation warnings beside the destructive command.
9. Test Python/configuration manually before enabling services.
10. Never enable every optional component just because a unit file exists.

## Recommended Reading Order

```text
INSTALL_AND_UPDATE.md
        ↓
CONFIG_REFERENCE.md
        ↓
API_SETUP.md
        ↓
ACTIVE_JSON.md
        ↓
SERVICES.md + SECURITY_AND_SUDOERS.md
        ↓
component-specific guide(s)
        ↓
BACKUP_AND_RESTORE.md / DATA_LAYOUT.md as needed
        ↓
TROUBLESHOOTING.md
        ↓
USEFUL_COMMANDS.md
```
