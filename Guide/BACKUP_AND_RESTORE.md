# 💾 JTWP Backup & Restore Guide

This guide documents the collector's two data-protection formats and the safe
procedure for restoring collector data.

## 📁 Current Paths

```text
Collector data:
/home/steam/jtwp-collector-data

Backups:
/home/steam/jtwp-collector-output/backups

Portable exports:
/home/steam/jtwp-collector-output/exports

Project .env:
/home/steam/jtwp-collector/Pavlov-Data-Collector-/.env
```

## 🧭 Backup vs Export

### `backup-data.py`

Creates a compressed `.tar.gz` containing:

```text
jtwp-collector-data/
```

Default destination:

```text
/home/steam/jtwp-collector-output/backups/
```

The backup contains the collector data directory. It does **not** separately
include `JTWP_IP_HASH_SECRET`.

Run:

```bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-

/home/steam/jtwp-collector/venv/bin/python3 \
    scripts/backup-data.py
```

### `export-data.py`

Creates:

```text
JTWP-data-export-YYYYMMDDTHHMMSSZ.zip
```

under:

```text
/home/steam/jtwp-collector-output/exports/
```

The export contains:

```text
JTWP-export/
├── data/
├── JTWP_IP_HASH_SECRET.txt
└── README-RESTORE.txt
```

Because the export includes the IP-hash secret, treat the entire ZIP as a
**sensitive credential-bearing archive**.

Run:

```bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-

/home/steam/jtwp-collector/venv/bin/python3 \
    scripts/export-data.py
```

## 🔐 Why the Hash Secret Matters

The collector uses `JTWP_IP_HASH_SECRET` to produce stable HMAC IP hashes.

If you restore old data but use a different secret:

- existing player IP hashes will no longer match new ones;
- SSH correlations will no longer line up;
- RCON correlations will no longer line up;
- network/DDoS correlation will no longer line up.

Do not rotate this value accidentally after data has been collected.

## 🧪 Verify an Archive Before Depending on It

List a backup:

```bash
tar -tzf /home/steam/jtwp-collector-output/backups/BACKUP.tar.gz | head -50
```

Test gzip/tar integrity:

```bash
tar -tzf /home/steam/jtwp-collector-output/backups/BACKUP.tar.gz >/dev/null \
    && echo "✅ backup readable"
```

List an export:

```bash
unzip -l /home/steam/jtwp-collector-output/exports/EXPORT.zip | head -50
```

Test ZIP integrity:

```bash
unzip -t /home/steam/jtwp-collector-output/exports/EXPORT.zip
```

## 🛑 Stop Writers Before a Restore

Do not restore while collector/watchers are writing to the data tree.

Stop the collector timer and service first:

```bash
sudo systemctl stop jtwp-collector.timer
sudo systemctl stop jtwp-collector.service
```

Stop long-running JTWP data writers:

```bash
sudo systemctl stop \
    jtwp-admin-monitor.service \
    jtwp-connection-watcher.service \
    jtwp-ddos-watcher.service \
    jtwp-rcon-loop.service \
    jtwp-rcon-trigger-watcher.service \
    jtwp-ssh-watcher.service
```

The Discord bot can also be stopped during a full maintenance window:

```bash
sudo systemctl stop jtwp-discord-bot.service
```

## ♻️ Restore a Data-Only `.tar.gz` Backup

First preserve the current tree instead of deleting it immediately:

```bash
sudo mv \
    /home/steam/jtwp-collector-data \
    /home/steam/jtwp-collector-data.before-restore
```

Extract the backup into `/home/steam`:

```bash
sudo tar -xzf \
    /home/steam/jtwp-collector-output/backups/BACKUP.tar.gz \
    -C /home/steam
```

The archive was created with the top-level name:

```text
jtwp-collector-data
```

so extraction recreates:

```text
/home/steam/jtwp-collector-data
```

Restore ownership and private-directory permissions:

```bash
sudo chown -R steam:steam /home/steam/jtwp-collector-data
sudo chmod 755 /home/steam/jtwp-collector-data

sudo mkdir -p /home/steam/jtwp-collector-data/private
sudo chown steam:steam /home/steam/jtwp-collector-data/private
sudo chmod 700 /home/steam/jtwp-collector-data/private
```

A data-only backup assumes you still have the **same existing**
`JTWP_IP_HASH_SECRET` in `.env`.

## ♻️ Restore a Portable ZIP Export

Use a temporary restore directory:

```bash
mkdir -p /home/steam/jtwp-restore
chmod 700 /home/steam/jtwp-restore

unzip \
    /home/steam/jtwp-collector-output/exports/EXPORT.zip \
    -d /home/steam/jtwp-restore
```

Inspect:

```bash
find /home/steam/jtwp-restore/JTWP-export -maxdepth 2 -type f | head -50
```

The data is under:

```text
/home/steam/jtwp-restore/JTWP-export/data/
```

and the saved secret is:

```text
/home/steam/jtwp-restore/JTWP-export/JTWP_IP_HASH_SECRET.txt
```

Before restoring the secret, compare it to the currently configured value
without printing either value:

```bash
CURRENT="$(
    sed -n 's/^JTWP_IP_HASH_SECRET=//p' \
    /home/steam/jtwp-collector/Pavlov-Data-Collector-/.env \
    | head -n1
)"

EXPORTED="$(
    head -n1 \
    /home/steam/jtwp-restore/JTWP-export/JTWP_IP_HASH_SECRET.txt
)"

if [[ "$CURRENT" == "$EXPORTED" ]]; then
    echo "✅ hash secret matches"
else
    echo "⚠️ hash secret differs"
fi

unset CURRENT EXPORTED
```

If the purpose of the restore is to continue the exported dataset, the secret
used by that dataset must be restored to the `.env` variable
`JTWP_IP_HASH_SECRET`.

Do not print or paste the secret into logs/Discord.

Restore the data tree:

```bash
sudo mv \
    /home/steam/jtwp-collector-data \
    /home/steam/jtwp-collector-data.before-restore

sudo mkdir -p /home/steam/jtwp-collector-data

sudo cp -a \
    /home/steam/jtwp-restore/JTWP-export/data/. \
    /home/steam/jtwp-collector-data/
```

Then repair ownership:

```bash
sudo chown -R steam:steam /home/steam/jtwp-collector-data
sudo chmod 755 /home/steam/jtwp-collector-data
sudo chmod 700 /home/steam/jtwp-collector-data/private
```

## ✅ Post-Restore Validation

Check the tree:

```bash
sudo -u steam find /home/steam/jtwp-collector-data -type f | wc -l
sudo -u steam du -sh /home/steam/jtwp-collector-data
```

Confirm `steam` can write:

```bash
sudo -u steam touch /home/steam/jtwp-collector-data/.write-test
sudo -u steam rm /home/steam/jtwp-collector-data/.write-test
```

Validate the project before restarting services:

```bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-

jq empty config.json
jq empty active.json

/home/steam/jtwp-collector/venv/bin/python3 \
    -m compileall -q .
```

Run one collector pass manually before enabling the timer:

```bash
set -a
source .env
set +a

/home/steam/jtwp-collector/venv/bin/python3 \
    collector.py -c config.json
```

## ▶️ Restart After Restore

Start only the components you currently use.

Example:

```bash
sudo systemctl start jtwp-connection-watcher.service
sudo systemctl start jtwp-rcon-trigger-watcher.service
sudo systemctl start jtwp-ssh-watcher.service
sudo systemctl start jtwp-ddos-watcher.service
sudo systemctl start jtwp-rcon-loop.service
sudo systemctl start jtwp-admin-monitor.service
sudo systemctl start jtwp-discord-bot.service
sudo systemctl start jtwp-collector.timer
```

Check:

```bash
systemctl list-units --type=service --all | grep -E 'jtwp|pavlov'
systemctl list-timers --all | grep jtwp
```

## 🧹 When It Is Safe to Delete the Pre-Restore Copy

Only remove:

```text
/home/steam/jtwp-collector-data.before-restore
```

after you have confirmed:

- the expected player records are present;
- SSH/RCON/network data is present;
- the hash secret is correct;
- the collector runs successfully;
- services can write new data;
- IP-hash correlation still works.
