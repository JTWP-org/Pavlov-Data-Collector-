# 🚀 JTWP Installation & Update Guide

This is the **canonical installation order** for the JTWP Pavlov Data Collector.

Detailed feature documentation is intentionally kept in the other Guides instead
of being repeated here.

## 📁 Expected Layout

```text
/home/steam/jtwp-collector/
├── venv/
└── Pavlov-Data-Collector-/
    ├── active.json
    ├── active_config.py
    ├── config.json
    ├── .env
    ├── collector.py
    ├── connection_watcher.py
    ├── ssh_watcher.py
    ├── ddos_watcher.py
    ├── rcon_trigger_watcher.py
    ├── rcon_loop.py
    ├── admin_monitor.py
    ├── discord_bot.py
    ├── update_pavlov_api.py
    ├── requirements.txt
    ├── resource/
    ├── scripts/
    ├── servers/
    ├── systemd/
    └── Guides/

/home/steam/jtwp-collector-data/
```

The `scripts/` and `servers/` directory structure should be kept intact.

## 1. Install OS Packages

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip jq dos2unix ufw tcpdump
```

`tcpdump` is needed only when the DDoS/network watcher is enabled.

## 2. Create / Update the Virtual Environment

```bash
cd /home/steam/jtwp-collector

python3 -m venv venv

source /home/steam/jtwp-collector/venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r \
    /home/steam/jtwp-collector/Pavlov-Data-Collector-/requirements.txt
```

## 3. Configure `.env`

```bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-
cp -n .env.example .env
chmod 600 .env
nano .env
```

Do not change an existing `JTWP_IP_HASH_SECRET` after data has been collected.
Changing it breaks IP-hash correlation with existing player, SSH, RCON and
network records.

See `API_SETUP.md` for the complete environment-variable guide.

## 4. Configure `config.json`

Validate it before starting services:

```bash
jq empty config.json && echo "config.json VALID"
```

Make sure every configured Pavlov server has the correct log path, RCON host,
RCON port and password environment-variable name.

## 5. Configure `active.json`

Start conservatively and enable only the components you have configured.

```bash
jq empty active.json && echo "active.json VALID"
```

See `ACTIVE_JSON.md`.

## 6. Validate Python Before Restarting Services

```bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-

/home/steam/jtwp-collector/venv/bin/python3 -m compileall -q .
```

A non-zero exit means at least one Python file has a syntax problem.

## 7. Prepare Helper Scripts

```bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-

find scripts -type f -name '*.sh' -exec dos2unix {} +
find scripts -type f -name '*.sh' -exec chmod +x {} +
```

Install only the helpers you actually use. See `SCRIPTS.md`.

## 8. Install systemd Units

If the repository contains the unit files:

```bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-

sudo install -m 644 systemd/*.service /etc/systemd/system/
sudo install -m 644 systemd/*.timer /etc/systemd/system/ 2>/dev/null || true

sudo systemctl daemon-reload
```

Do **not** blindly enable every service. Enable the components selected in
`active.json` and configured in `config.json`.

See `SERVICES.md` for service-by-service installation and permissions.

## 9. First-Run Data Directory Check

```bash
sudo -u steam mkdir -p /home/steam/jtwp-collector-data/private
sudo -u steam mkdir -p /home/steam/jtwp-collector-data/global
sudo -u steam mkdir -p /home/steam/jtwp-collector-data/servers

chmod 700 /home/steam/jtwp-collector-data/private
```

Check ownership:

```bash
namei -l /home/steam/jtwp-collector-data/private
```

The `steam` account must be able to create and atomically replace files in the
collector data tree.

## 10. Test the Collector Manually First

```bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-

set -a
source .env
set +a

/home/steam/jtwp-collector/venv/bin/python3 \
    collector.py -c config.json
```

Only after the manual run succeeds should the timer/service be enabled.

## 11. Enable the Selected Services

Examples:

```bash
sudo systemctl enable --now jtwp-connection-watcher.service
sudo systemctl enable --now jtwp-rcon-trigger-watcher.service
sudo systemctl enable --now jtwp-ssh-watcher.service
sudo systemctl enable --now jtwp-ddos-watcher.service
sudo systemctl enable --now jtwp-rcon-loop.service
sudo systemctl enable --now jtwp-admin-monitor.service
sudo systemctl enable --now jtwp-discord-bot.service
sudo systemctl enable --now jtwp-collector.timer
```

Only run the commands for components you actually configured.

## 12. Verify

```bash
systemctl list-units --type=service --all | grep -E 'jtwp|pavlov'
systemctl list-timers --all | grep jtwp
```

Recent JTWP errors:

```bash
sudo journalctl --since "30 minutes ago" \
    | grep -Ei 'jtwp|traceback|error|failed'
```

## Updating Existing Installations

Before replacing files:

```bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-
cp config.json config.json.backup
cp active.json active.json.backup
cp .env .env.backup
```

Stop JTWP services while changing a large set of files:

```bash
sudo systemctl stop \
    jtwp-admin-monitor.service \
    jtwp-connection-watcher.service \
    jtwp-ddos-watcher.service \
    jtwp-discord-bot.service \
    jtwp-rcon-loop.service \
    jtwp-rcon-trigger-watcher.service \
    jtwp-ssh-watcher.service

sudo systemctl stop jtwp-collector.timer
sudo systemctl stop jtwp-collector.service
```

After updating:

```bash
source /home/steam/jtwp-collector/venv/bin/activate
python -m pip install -r requirements.txt
python -m compileall -q .

jq empty config.json
jq empty active.json

sudo systemctl daemon-reload
```

Then start only the enabled components.

## Guide Map

- `CONFIG_REFERENCE.md` — `config.json` settings and examples.
- `API_SETUP.md` — `.env`, API keys, RCON password variables and secrets.
- `ACTIVE_JSON.md` — feature switches.
- `SERVICES.md` — systemd units, timers, permissions and logs.
- `SECURITY_AND_SUDOERS.md` — sudoers, service-account privileges and secrets.
- `SCRIPTS.md` — helper installation and usage.
- `RCON_GUIDE.md` — ModSave RCON bridge and RCON testing.
- `SSH_BLOCKING.md` — SSH detection and automatic UFW blocking.
- `DDOS_AND_MAINTENANCE.md` — DDoS watcher and mod cleanup.
- `DISCORD_BOT_SETUP.md` — Discord application, roles, token and bot setup.
- `COMPONENTS_AND_MANUAL_TRIGGERS.md` — manual tests/triggers.
- `LIVE_SERVERS.md` — live Pavlov server text/image pipeline.
- `BACKUP_AND_RESTORE.md` — backup/export/restore procedure.
- `DATA_LAYOUT.md` — persistent collector data tree.
- `TROUBLESHOOTING.md` — symptom-driven diagnostics.
- `FEATURES_AND_DATA_POINTS.md` — what the collector records.
- `USEFUL_COMMANDS.md` — quick command reference.
