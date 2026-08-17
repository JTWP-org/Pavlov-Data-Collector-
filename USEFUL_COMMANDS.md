# 🧰 JTWP Pavlov Data Collector — Useful Commands

A quick command reference for the JTWP Pavlov Data Collector, SSH watcher, RCON bridge, public-server updater, player tools, data links, firewall helpers, systemd, JSON inspection, and Git.

> [!NOTE]
> These examples assume the project is installed at:
>
> `/home/steam/jtwp-collector/Pavlov-Data-Collector-`
>
> and data is stored at:
>
> `/home/steam/jtwp-collector-data/`

---

## 📂 Project Shortcuts

Go to the collector:

```bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-
```

Activate the Python virtual environment:

```bash
source /home/steam/jtwp-collector/venv/bin/activate
```

Load variables from `.env` into the current shell:

```bash
set -a
source .env
set +a
```

Check Python:

```bash
/home/steam/jtwp-collector/venv/bin/python3 --version
```

Install/update dependencies:

```bash
/home/steam/jtwp-collector/venv/bin/pip install -r requirements.txt
```

---

## 📊 Main Collector

Run the full collector manually:

```bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-
source /home/steam/jtwp-collector/venv/bin/activate
set -a
source .env
set +a
python3 collector.py -c config.json
```

Validate `config.json`:

```bash
python3 -m json.tool config.json
```

Pretty-print it with `jq`:

```bash
jq . config.json
```

Check the collector data directory:

```bash
du -sh /home/steam/jtwp-collector-data
```

Show the largest directories:

```bash
du -h /home/steam/jtwp-collector-data | sort -h | tail -30
```

---

## 🌐 Pavlov Public Server API

Run only the lightweight public-server update:

```bash
update-pavlov-api
```

Or directly:

```bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-
set -a
source .env
set +a

/home/steam/jtwp-collector/venv/bin/python3 \
    update_pavlov_api.py -c config.json
```

Pretty-print the server snapshot:

```bash
jq . /home/steam/jtwp-collector-data/global/pavlov_api/servers.json
```

View the summary:

```bash
jq . /home/steam/jtwp-collector-data/global/pavlov_api/summary.json
```

Check the last update:

```bash
jq . /home/steam/jtwp-collector-data/global/pavlov_api/last_update.json
```

### 🔎 Find a server by name

```bash
jq '."server name"' \
    /home/steam/jtwp-collector-data/global/pavlov_api/index/by_name.json
```

Case-insensitive name search:

```bash
jq 'to_entries[] | select(.key | ascii_downcase | contains("jtwp"))' \
    /home/steam/jtwp-collector-data/global/pavlov_api/index/by_name.json
```

### 🗺️ Servers using a map

```bash
jq '."UGC3283728"' \
    /home/steam/jtwp-collector-data/global/pavlov_api/index/by_map.json
```

### 🎮 Servers using a game mode

```bash
jq '.TDM' \
    /home/steam/jtwp-collector-data/global/pavlov_api/index/by_game_mode.json
```

### 🌍 Network/hosting enrichment

```bash
jq . /home/steam/jtwp-collector-data/global/pavlov_api/network_hosts.json
```

List hosting providers:

```bash
jq -r 'to_entries[] | "\(.key) - \(.value.provider // "Unknown")"' \
    /home/steam/jtwp-collector-data/global/pavlov_api/network_hosts.json
```

---

## 👤 Player Lookup

Look up a player by name:

```bash
playerLookup oneSALTycrack3r
```

If the script is not installed system-wide:

```bash
/home/steam/jtwp-collector/Pavlov-Data-Collector-/scripts/playerLookup.sh oneSALTycrack3r
```

Search the player-name index manually:

```bash
jq '."onesaltycrack3r"' \
    /home/steam/jtwp-collector-data/players/index/by_name.json
```

Get the first ProductID associated with a name:

```bash
jq -r '.onesaltycrack3r[0]' \
    /home/steam/jtwp-collector-data/players/index/by_name.json
```

Dump all JSON records for that ProductID:

```bash
PRODUCT_ID="$(jq -r '.onesaltycrack3r[0]' \
    /home/steam/jtwp-collector-data/players/index/by_name.json)"

cat "/home/steam/jtwp-collector-data/players/records/$PRODUCT_ID"/*.json
```

Pretty-print them:

```bash
for file in "/home/steam/jtwp-collector-data/players/records/$PRODUCT_ID"/*.json; do
    echo "===== $file ====="
    jq . "$file"
done
```

---

## 🔗 Check Player SSH / RCON Connections

Run:

```bash
check-player-connections oneSALTycrack3r
```

This is intended to cross-reference the player's known IP information against SSH and RCON connection records.

Inspect SSH failed hosts manually:

```bash
jq . /home/steam/jtwp-collector-data/global/ssh/failed_hosts.json
```

Find records that have matched players:

```bash
jq '.[] | select(.players_seen_on_ip != null)' \
    /home/steam/jtwp-collector-data/global/ssh/failed_hosts.json
```

---

## 🔐 SSH Watcher

Check the service:

```bash
sudo systemctl status jtwp-ssh-watcher --no-pager
```

Restart it:

```bash
sudo systemctl restart jtwp-ssh-watcher
```

Start it:

```bash
sudo systemctl start jtwp-ssh-watcher
```

Stop it:

```bash
sudo systemctl stop jtwp-ssh-watcher
```

Enable it at boot:

```bash
sudo systemctl enable jtwp-ssh-watcher
```

Follow live logs:

```bash
sudo journalctl -u jtwp-ssh-watcher -f
```

Show the last 100 lines:

```bash
sudo journalctl -u jtwp-ssh-watcher -n 100 --no-pager
```

Check that the process is running:

```bash
ps aux | grep '[s]sh_watcher.py'
```

View SSH events:

```bash
tail -f /home/steam/jtwp-collector-data/global/ssh/events.jsonl
```

Pretty-print JSONL events:

```bash
tail -n 20 /home/steam/jtwp-collector-data/global/ssh/events.jsonl | jq .
```

---

## 🎛️ RCON File Bridge

Check the watcher:

```bash
sudo systemctl status jtwp-rcon-trigger-watcher --no-pager
```

Restart it:

```bash
sudo systemctl restart jtwp-rcon-trigger-watcher
```

Follow logs:

```bash
sudo journalctl -u jtwp-rcon-trigger-watcher -f
```

Show recent errors/output:

```bash
sudo journalctl -u jtwp-rcon-trigger-watcher -n 100 --no-pager
```

### 📡 ServerInfo test

For `pavlovserver1`:

```bash
echo '{}' > \
/home/steam/pavlovserver1/Pavlov/Saved/Config/ModSave/JTWP/Rcon/IN-serverinfo.json
```

Wait for the response:

```bash
cat \
/home/steam/pavlovserver1/Pavlov/Saved/Config/ModSave/JTWP/Rcon/OUT-serverinfo.json | jq .
```

Watch the RCON directory:

```bash
watch -n 0.5 'ls -lah /home/steam/pavlovserver1/Pavlov/Saved/Config/ModSave/JTWP/Rcon'
```

### 🤖 SetBotsEnabled

```bash
cat > /home/steam/pavlovserver1/Pavlov/Saved/Config/ModSave/JTWP/Rcon/IN-setbotsenabled.json <<'EOF'
{
  "enabled": true
}
EOF
```

### 💉 GiveItem

```bash
cat > /home/steam/pavlovserver1/Pavlov/Saved/Config/ModSave/JTWP/Rcon/IN-giveitem.json <<'EOF'
{
  "unique_id": "12345678901234567",
  "item_id": "syringe"
}
EOF
```

### 🗺️ SwitchMap

```bash
cat > /home/steam/pavlovserver1/Pavlov/Saved/Config/ModSave/JTWP/Rcon/IN-switchmap.json <<'EOF'
{
  "map_id": "datacenter",
  "game_mode": "SND"
}
EOF
```

### 📚 View RCON command definitions

```bash
jq . rcon_commands.json
```

List only RCON command names:

```bash
jq -r '.commands[].rcon_command' rcon_commands.json | sort
```

List command key + command:

```bash
jq -r '.commands | to_entries[] | "\(.key) -> \(.value.rcon_command)"' \
    rcon_commands.json
```

---

## 🔑 RCON MD5 Helper

> [!IMPORTANT]
> The current `async-pavlov` bridge expects the normal RCON password in `.env`.
> The helper below is useful when you specifically need to inspect the raw MD5 form.

Generate the MD5:

```bash
rcon-md5 'your-password'
```

Or:

```bash
./scripts/rcon-md5.sh 'your-password'
```

Equivalent Linux command:

```bash
printf '%s' 'your-password' | md5sum
```

---

## 🚫 Block / Unblock an IP

Block an IP:

```bash
sudo block-ip 203.0.113.10
```

Unblock it:

```bash
sudo unblock-ip 203.0.113.10
```

Check UFW:

```bash
sudo ufw status numbered
```

Check detailed UFW status:

```bash
sudo ufw status verbose
```

> [!CAUTION]
> Double-check an address before blocking it so you do not lock out a legitimate host or your own administrative connection.

---

## 🔗 ModSave Data Links

Create/update the ModSave data symlinks:

```bash
setup-data-links
```

Check them:

```bash
ls -lah \
/home/steam/pavlovserver1/Pavlov/Saved/Config/ModSave/JTWP/Data
```

Resolve where a link points:

```bash
readlink -f \
/home/steam/pavlovserver1/Pavlov/Saved/Config/ModSave/JTWP/Data/players
```

Expected exposed datasets include:

```text
servers
players
global
```

---

## 🛠️ Check Installed JTWP Commands

```bash
for cmd in \
    block-ip \
    unblock-ip \
    check-player-connections \
    playerLookup \
    setup-data-links \
    update-pavlov-api \
    rcon-md5
do
    command -v "$cmd" || echo "MISSING: $cmd"
done
```

Show where a command is installed:

```bash
command -v playerLookup
```

Check permissions:

```bash
ls -lah /usr/local/bin/playerLookup
```

---

## 📦 Install a Script into `/usr/local/bin`

Example:

```bash
chmod +x scripts/playerLookup.sh

sudo install -m 755 \
    scripts/playerLookup.sh \
    /usr/local/bin/playerLookup
```

General pattern:

```bash
sudo install -m 755 scripts/SCRIPT.sh /usr/local/bin/COMMAND
```

---

## 🧾 JSON / `jq` Commands

Validate a JSON file:

```bash
jq empty file.json && echo "VALID JSON"
```

Or:

```bash
python3 -m json.tool file.json >/dev/null && echo "VALID JSON"
```

Pretty-print:

```bash
jq . file.json
```

Read one field:

```bash
jq '.name' file.json
```

Raw string output:

```bash
jq -r '.name' file.json
```

Get object keys:

```bash
jq 'keys' file.json
```

Get array length:

```bash
jq 'length' file.json
```

Select records:

```bash
jq '.[] | select(.success == false)' file.json
```

Search recursively for JSON files:

```bash
find /home/steam/jtwp-collector-data -type f -name '*.json'
```

Validate every JSON file:

```bash
find /home/steam/jtwp-collector-data -type f -name '*.json' -print0 |
while IFS= read -r -d '' file; do
    jq empty "$file" 2>/dev/null || echo "INVALID: $file"
done
```

---

## 🔎 Search Collector Data

Find a player name:

```bash
grep -Rni --include='*.json' \
    'onesaltycrack3r' \
    /home/steam/jtwp-collector-data
```

Find a ProductID:

```bash
grep -Rni \
    '12345678901234567' \
    /home/steam/jtwp-collector-data
```

Find a server name:

```bash
grep -Rni --include='*.json' \
    'JTWP' \
    /home/steam/jtwp-collector-data/global/pavlov_api
```

Find recently modified files:

```bash
find /home/steam/jtwp-collector-data -type f -mmin -10 -ls
```

---

## ⚙️ systemd Cheat Sheet

List JTWP services:

```bash
systemctl list-units --type=service | grep -i jtwp
```

Check a service:

```bash
sudo systemctl status SERVICE --no-pager
```

Start:

```bash
sudo systemctl start SERVICE
```

Stop:

```bash
sudo systemctl stop SERVICE
```

Restart:

```bash
sudo systemctl restart SERVICE
```

Enable at boot:

```bash
sudo systemctl enable SERVICE
```

Enable and start immediately:

```bash
sudo systemctl enable --now SERVICE
```

Disable:

```bash
sudo systemctl disable SERVICE
```

Reload service definitions after editing a `.service` file:

```bash
sudo systemctl daemon-reload
```

Show the installed service file:

```bash
sudo systemctl cat SERVICE
```

Live logs:

```bash
sudo journalctl -u SERVICE -f
```

Recent logs:

```bash
sudo journalctl -u SERVICE -n 100 --no-pager
```

Logs since boot:

```bash
sudo journalctl -u SERVICE -b --no-pager
```

---

## ⏰ Timers / Scheduled Collector

List timers:

```bash
systemctl list-timers --all
```

Filter JTWP timers:

```bash
systemctl list-timers --all | grep -i jtwp
```

Check a timer:

```bash
sudo systemctl status jtwp-collector.timer --no-pager
```

Check its associated service:

```bash
sudo systemctl status jtwp-collector.service --no-pager
```

---

## 🐍 Python Troubleshooting

Check which Python is being used:

```bash
which python3
```

Check the collector venv Python:

```bash
/home/steam/jtwp-collector/venv/bin/python3 --version
```

Check a package:

```bash
/home/steam/jtwp-collector/venv/bin/pip show async-pavlov
```

List installed packages:

```bash
/home/steam/jtwp-collector/venv/bin/pip list
```

Compile-check a Python script without running it:

```bash
/home/steam/jtwp-collector/venv/bin/python3 -m py_compile rcon_trigger_watcher.py
```

---

## 📁 File / Permission Commands

Show ownership and permissions:

```bash
ls -lah FILE
```

Make a shell script executable:

```bash
chmod +x script.sh
```

Make the `steam` user own a file:

```bash
sudo chown steam:steam FILE
```

Recursively fix ownership:

```bash
sudo chown -R steam:steam /home/steam/jtwp-collector-data
```

Create a directory tree:

```bash
mkdir -p /path/to/folder
```

Follow a log:

```bash
tail -f file.log
```

Show the last 100 lines:

```bash
tail -n 100 file.log
```

---

## 💾 Disk / System Checks

Disk usage:

```bash
df -h
```

Memory:

```bash
free -h
```

Processes:

```bash
ps aux
```

Find Python collector processes:

```bash
ps aux | grep '[p]ython'
```

Check listening ports:

```bash
sudo ss -lntup
```

Check a specific port:

```bash
sudo ss -lntup | grep ':9104'
```

---

## 🧬 Git / Repository Commands

Check repository status:

```bash
git status
```

See changes:

```bash
git diff
```

Pull remote changes:

```bash
git pull
```

Stage everything:

```bash
git add .
```

Commit:

```bash
git commit -m "Update collector tools"
```

Push:

```bash
git push
```

Typical update workflow:

```bash
git status
git add .
git commit -m "Update collector and RCON tools"
git push
```

See recent commits:

```bash
git log --oneline -10
```

Check remotes:

```bash
git remote -v
```

> [!WARNING]
> Before `git add .`, make sure `.env`, collected player data, raw IP data, RCON passwords, API keys, and other private/generated files are covered by `.gitignore`.

---

## 🧹 Useful Combined Checks

### Check the important services

```bash
for service in \
    jtwp-ssh-watcher \
    jtwp-rcon-trigger-watcher
do
    echo
    echo "===== $service ====="
    systemctl is-active "$service"
done
```

### Check recent JTWP errors

```bash
sudo journalctl --since "1 hour ago" --no-pager |
    grep -iE 'jtwp|collector|ssh_watcher|rcon_trigger'
```

### Check data modified in the last five minutes

```bash
find /home/steam/jtwp-collector-data \
    -type f \
    -mmin -5 \
    -printf '%TY-%Tm-%Td %TH:%TM:%TS %p\n' |
    sort
```

### Validate the main configuration files

```bash
for file in \
    config.json \
    rcon_commands.json \
    game_modes.json \
    default_maps.json \
    limited_ammo_types.json
do
    printf '%-30s ' "$file"
    if jq empty "$file" 2>/dev/null; then
        echo "✅ VALID"
    else
        echo "❌ INVALID"
    fi
done
```

---

## 🆘 Quick Troubleshooting Order

When one of the tools stops working, these commands usually narrow it down quickly:

```bash
# 1. Is the service running?
sudo systemctl status SERVICE --no-pager

# 2. What error did it produce?
sudo journalctl -u SERVICE -n 100 --no-pager

# 3. Is config.json valid?
jq empty config.json

# 4. Are environment variables loaded?
grep -vE 'PASSWORD|SECRET|KEY|TOKEN' .env

# 5. Does the expected Python exist?
ls -lah /home/steam/jtwp-collector/venv/bin/python3

# 6. Are dependencies installed?
/home/steam/jtwp-collector/venv/bin/pip list

# 7. Are files being written?
find /home/steam/jtwp-collector-data -type f -mmin -10 -ls
```

> [!CAUTION]
> Do not paste the unfiltered output of `.env`, raw-IP files, API secrets, RCON passwords, or webhook URLs into public issues or Discord channels.
