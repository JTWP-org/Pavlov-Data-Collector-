# 🚀 JTWP Full Code Update

This update adds the feature-control system, data maintenance tools, the RCON loop, admin monitoring, and the Discord administration bot.

## 📦 Included

```text
active.json
active_config.py
config.json
collector.py
ssh_watcher.py
ddos_watcher.py
rcon_trigger_watcher.py
rcon_loop.py
admin_monitor.py
discord_bot.py
requirements-additions.txt

scripts/
├── clear-pavlov-mods.sh
├── clear-data.sh
├── export-data.py
├── backup-data.py
└── set-rcon-loop.py

systemd/
├── jtwp-rcon-loop.service
├── jtwp-admin-monitor.service
└── jtwp-discord-bot.service
```

## ⚙️ active.json

`active.json` is the feature-selection file.

Parent `enabled: false` values override child values.

The new components in this update read `active.json` directly. The older collector/watchers included in the bundle retain their existing collection behavior unless individual internal collection points are later wired to the deep switches. This avoids silently breaking an existing working collector.

## 🔐 Add to `.env`

```bash
JTWP_DISCORD_BOT_TOKEN=YOUR_BOT_TOKEN
JTWP_ADMIN_WEBHOOK_URL=YOUR_ADMIN_ALERT_WEBHOOK
```

Keep your existing:

```bash
JTWP_IP_HASH_SECRET=...
```

unchanged.

## 🤖 Discord settings

Edit these placeholders in `config.json`:

```json
"discord_bot": {
  "control_channel_id": "DISCORD_CONTROL_CHANNEL_ID",
  "roles": {
    "admin": "DISCORD_ADMIN_ROLE_ID",
    "owner": "DISCORD_OWNER_ROLE_ID"
  }
}
```

Also set:

```json
"admin_notifications": {
  "role_id": "ADMIN_DISCORD_ROLE_ID"
}
```

## 🛡️ Discord permissions

### ADMIN

ADMIN receives the read-only/data commands and only the RCON commands listed in:

```json
"admin_allowed_rcon_commands"
```

### OWNER

OWNER inherits ADMIN permissions and additionally gets:

- all RCON command strings;
- Pavlov `systemctl` controls;
- clear-mods;
- collector trigger;
- Pavlov Public API trigger;
- SSH report trigger;
- RCON loop start/stop.

## 🎛️ Bot commands

```text
!rcon pavlovserver serverinfo
!rcon pavlovserver1 inspectall

!systemCtl pavlovserver restart
!systemCtl pavlovserver stop
!systemCtl pavlovserver start
!systemCtl pavlovserver enable
!systemCtl pavlovserver status
!systemCtl pavlovserver disable

!getProductID oneSALTycrack3r
!getNETWORK PRODUCT_ID
!getNAMES PRODUCT_ID
!getSTATS PRODUCT_ID
!getGUNS PRODUCT_ID
!getPLAYER PRODUCT_ID
!getDUMP PRODUCT_ID
!checkCONS oneSALTycrack3r

!server clear-pavlov-mods pavlovserver1

!RUNcollector
!RUNpavlovApi
!RUNssh

!loop start pavlovserver1 5
!loop status
!loop stop
```

`!checkCONS` checks the player's known IP hashes against:

- other players;
- successful RCON hosts;
- failed RCON hosts;
- failed SSH hosts;
- DDoS/network-abuse hosts.

Raw private IP files are not exposed through these Discord commands.

## 🔁 RCON loop

The control file contains only settings:

```json
{
  "server_id": "pavlovserver1",
  "loop_seconds": 5
}
```

The loop produces:

```text
loopOutput.json
```

containing the latest `ServerInfo` and `InspectAll`.

Deleting `loopData.json`:

1. ends the active loop;
2. deletes `loopOutput.json`;
3. cleans up/disconnects the current RCON client;
4. leaves the watcher service alive waiting for a new control file.

Malformed settings have the same active-loop cleanup behavior.

Manual helper:

```bash
python3 scripts/set-rcon-loop.py -c config.json start pavlovserver1 5
python3 scripts/set-rcon-loop.py -c config.json status
python3 scripts/set-rcon-loop.py -c config.json stop
```

## 🛡️ Admin monitoring

`admin_monitor.py` consumes `loopOutput.json` and tracks known admins from the existing player `admin` field.

It records:

- admin join;
- admin leave;
- session start/end;
- session duration;
- total admin time;
- total sessions;
- time/sessions per server.

It also creates alerts for:

- players online with no admin;
- player score below the configured threshold;
- player teamkills reaching the configured threshold.

Alerts track whether a known admin joins the same server inside:

```json
"response_window_seconds": 900
```

which is 15 minutes by default.

## 💾 Data tools

### Clear data

```bash
sudo scripts/clear-data.sh --yes
```

This deletes the contents of:

```text
/home/steam/jtwp-collector-data
```

but preserves the root directory.

### Export data

```bash
python3 scripts/export-data.py
```

Creates a ZIP under:

```text
/home/steam/jtwp-collector-output/exports/
```

The export includes:

- all collector data;
- `JTWP_IP_HASH_SECRET.txt`;
- a restore/security note.

⚠️ The export is sensitive because it includes the HMAC secret.

### Backup data

```bash
python3 scripts/backup-data.py
```

Creates:

```text
/home/steam/jtwp-collector-output/backups/
JTWP-data-backup_FIRST--LAST_made-CREATED.tar.gz
```

The backup contains the data directory only. It does **not** include the hash secret.

## 📦 Install Python dependency

```bash
source /home/steam/jtwp-collector/venv/bin/activate
pip install -r requirements-additions.txt
```

Keep your existing async-pavlov dependency installed.

## ⚡ Install services

```bash
sudo install -m 644 systemd/jtwp-rcon-loop.service /etc/systemd/system/
sudo install -m 644 systemd/jtwp-admin-monitor.service /etc/systemd/system/
sudo install -m 644 systemd/jtwp-discord-bot.service /etc/systemd/system/

sudo systemctl daemon-reload

sudo systemctl enable --now jtwp-rcon-loop
sudo systemctl enable --now jtwp-admin-monitor
sudo systemctl enable --now jtwp-discord-bot
```

Check:

```bash
sudo systemctl status jtwp-rcon-loop --no-pager
sudo systemctl status jtwp-admin-monitor --no-pager
sudo systemctl status jtwp-discord-bot --no-pager
```

## 👑 OWNER sudo permissions

The bot runs as `steam`, so OWNER-only `systemctl` and clear-mods operations require carefully restricted NOPASSWD entries.

Review:

```text
sudoers-jtwp-discord-bot.example
```

and edit/install it with `visudo`.

Do not give the bot unrestricted passwordless sudo.
