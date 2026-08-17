# 🧩 JTWP Tool Components & Manual Trigger Guide

This guide explains the major parts of the **JTWP Pavlov Data
Collector**, what each component does, whether it runs continuously or
on demand, and how to manually trigger or test it.

> \[!NOTE\] Commands below use the current project layout:
>
> ``` text
> /home/steam/jtwp-collector/Pavlov-Data-Collector-
> ```
>
> Python virtual environment:
>
> ``` text
> /home/steam/jtwp-collector/venv
> ```
>
> Collector data:
>
> ``` text
> /home/steam/jtwp-collector-data
> ```

------------------------------------------------------------------------

# 🗺️ Tool Overview

The project is split into several independent pieces:

``` text
                         JTWP TOOL
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
   📊 Collector        🔐 SSH Watcher      🎛️ RCON Bridge
        │                   │                   │
        ▼                   ▼                   ▼
 Pavlov logs/data      SSH journal        ModSave triggers
        │                   │                   │
        ▼                   ▼                   ▼
 Player/server DB      Security DB        RCON response JSON
        │
        ├──────────────► 🗺️ Mod.io enrichment
        │
        ├──────────────► 🌐 IP enrichment
        │
        └──────────────► 🌍 Pavlov API data

Additional helper scripts:
        │
        ├── 🚫 block-ip
        ├── 🔓 unblock-ip
        ├── 🔎 playerLookup
        ├── 🕵️ check-player-connections
        ├── 🔗 setup-data-links
        └── 🔐 rcon-md5
```

Each part can be tested separately.

------------------------------------------------------------------------

# 🟢 Before Running Anything Manually

Enter the project:

``` bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-
```

Activate the virtual environment:

``` bash
source /home/steam/jtwp-collector/venv/bin/activate
```

Load private environment variables:

``` bash
set -a
source .env
set +a
```

Validate the main configuration:

``` bash
jq empty config.json && echo "✅ config.json VALID"
```

You can also verify the important JSON support files:

``` bash
for file in \
    config.json \
    rcon_commands.json \
    game_modes.json \
    default_maps.json \
    limited_ammo_types.json
do
    printf '%-30s ' "$file"

    if [[ ! -f "$file" ]]; then
        echo "❌ MISSING"
    elif jq empty "$file" 2>/dev/null; then
        echo "✅ VALID"
    else
        echo "❌ INVALID JSON"
    fi
done
```

------------------------------------------------------------------------

# 1️⃣ 📊 Main Collector

## What It Does

`collector.py` is the main data-processing component.

It processes Pavlov server data and builds the persistent collector
database under:

``` text
/home/steam/jtwp-collector-data
```

Depending on the enabled configuration, collection can include:

-   👤 player records
-   🏷️ player name history
-   🎯 combat statistics
-   🔫 weapon statistics
-   🎮 server information
-   🗺️ maps and mods
-   🌐 network/IP enrichment
-   🗺️ Mod.io enrichment
-   🎛️ RCON-derived information
-   📚 indexes used by lookup tools

The collector is intended to be a **batch job**, rather than something
that must run continuously.

------------------------------------------------------------------------

## ▶️ Manually Run the Collector

``` bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-

source /home/steam/jtwp-collector/venv/bin/activate

set -a
source .env
set +a

python3 collector.py -c config.json
```

Using the virtual environment directly:

``` bash
/home/steam/jtwp-collector/venv/bin/python3 \
    /home/steam/jtwp-collector/Pavlov-Data-Collector-/collector.py \
    -c /home/steam/jtwp-collector/Pavlov-Data-Collector-/config.json
```

------------------------------------------------------------------------

## ⏰ Trigger the Scheduled Collector Manually

If installed as:

``` text
jtwp-collector.service
```

run:

``` bash
sudo systemctl start jtwp-collector.service
```

Then inspect its output:

``` bash
sudo journalctl -u jtwp-collector.service -n 100 --no-pager
```

The timer itself can be checked with:

``` bash
systemctl list-timers --all | grep jtwp-collector
```

The current planned schedule is:

``` text
03:00 UTC every night
```

------------------------------------------------------------------------

# 2️⃣ 🌍 Pavlov Public API Updater

## What It Does

The lightweight Pavlov API updater refreshes public server-browser
information without requiring a complete historical log collection.

The public server data includes fields such as:

-   server name
-   server IP
-   port
-   game mode
-   map ID
-   map label
-   slots
-   maximum slots
-   server type
-   version
-   password/security flags
-   last API update time

The project uses the configured Pavlov public server endpoint.

------------------------------------------------------------------------

## ▶️ Manually Trigger the Pavlov API Update

If your updater is:

``` text
update_pavlov_api.py
```

run:

``` bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-

source /home/steam/jtwp-collector/venv/bin/activate

set -a
source .env
set +a

python3 update_pavlov_api.py -c config.json
```

Or:

``` bash
/home/steam/jtwp-collector/venv/bin/python3 \
    /home/steam/jtwp-collector/Pavlov-Data-Collector-/update_pavlov_api.py \
    -c /home/steam/jtwp-collector/Pavlov-Data-Collector-/config.json
```

> \[!NOTE\] If the current version of `update_pavlov_api.py` uses
> different command-line arguments, run its supported help/options
> before using the example above.

If you created a systemd unit:

``` bash
sudo systemctl start jtwp-pavlov-api-update.service
```

View its output:

``` bash
sudo journalctl -u jtwp-pavlov-api-update.service -n 100 --no-pager
```

------------------------------------------------------------------------

# 3️⃣ 🗺️ Mod.io Enrichment

## What It Does

Mod.io enrichment adds additional information about Pavlov mods and maps
found by the collector.

The configured Pavlov Mod.io game ID is:

``` text
3959
```

Typical configuration:

``` json
"modio_game_id": 3959,
"modio_cache_ttl_hours": 24
```

The Mod.io API key is loaded from `.env`.

------------------------------------------------------------------------

## ▶️ Manually Trigger Mod.io Collection

Mod.io enrichment is part of the collector workflow rather than a
separate continuously running watcher.

Run the main collector:

``` bash
python3 collector.py -c config.json
```

This allows the collector to refresh Mod.io information when its
cache/configuration says a lookup is needed.

See:

``` text
Guides/API_SETUP.md
```

for API-key configuration.

------------------------------------------------------------------------

# 4️⃣ 🌐 IP / Network Enrichment

## What It Does

Network enrichment adds background information to collected IP-related
records.

Depending on the provider response, this can include:

``` text
Provider
Organisation
Network Type
Country
Region
City
Hosting
Proxy
VPN
Tor
Risk
Confidence
```

Lookup results are cached so the collector does not repeatedly request
the same information.

Typical setting:

``` json
"ip_lookup_cache_ttl_days": 30
```

------------------------------------------------------------------------

## ▶️ Manually Trigger Network Enrichment

Network enrichment is normally triggered by the collector when it
encounters an address requiring a lookup.

Run:

``` bash
python3 collector.py -c config.json
```

The collector will use the configured primary/fallback lookup provider
as needed.

See:

``` text
Guides/API_SETUP.md
```

for provider and API-key setup.

------------------------------------------------------------------------

# 5️⃣ 🔐 SSH Watcher

## What It Does

`ssh_watcher.py` runs continuously and watches the Linux SSH journal.

It can:

-   detect failed SSH authentication
-   count attempts by host
-   store failed-host information
-   enrich source network information
-   send Discord webhook events
-   cross-reference collected data
-   automatically block an address after the configured threshold

The current auto-block design uses the watcher's **existing**:

``` text
failed_attempts
```

counter.

No second SSH counter is required.

------------------------------------------------------------------------

## ▶️ Manually Run the SSH Watcher

First stop the systemd copy so you do not have two watchers processing
the same events:

``` bash
sudo systemctl stop jtwp-ssh-watcher
```

Then:

``` bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-

source /home/steam/jtwp-collector/venv/bin/activate

set -a
source .env
set +a

python3 ssh_watcher.py -c config.json
```

Press:

``` text
Ctrl+C
```

to stop the manual watcher.

Then restore the service:

``` bash
sudo systemctl start jtwp-ssh-watcher
```

------------------------------------------------------------------------

## 🔄 Restart the Normal SSH Watcher

``` bash
sudo systemctl restart jtwp-ssh-watcher
```

Follow it:

``` bash
sudo journalctl -u jtwp-ssh-watcher -f
```

Check status:

``` bash
sudo systemctl status jtwp-ssh-watcher --no-pager
```

------------------------------------------------------------------------

## 🚫 Manually Test Its Block Command

The watcher executes the blocker as the `steam` user through
non-interactive sudo.

Test the same path:

``` bash
sudo -u steam sudo -n /usr/local/bin/block-ip 203.0.113.123
```

Check:

``` bash
sudo ufw status
```

Then remove the test rule:

``` bash
sudo /usr/local/bin/unblock-ip 203.0.113.123
```

See:

``` text
Guides/SSHblocking.MD
```

for the full SSH auto-block setup.

------------------------------------------------------------------------

# 6️⃣ 👁️ Connection / Security Watcher

## What It Does

The collector configuration contains a connection-watcher section such
as:

``` json
"connection_watcher": {
  "poll_interval_seconds": 0.5,
  "start_at_end": true,
  "webhook_mode": "discord",
  "webhook_timeout_seconds": 8,
  "webhook_retries": 2
}
```

This part of the project handles connection/security event monitoring
according to the current watcher implementation.

Its collected information can be used by the player/security
cross-reference tools.

------------------------------------------------------------------------

## ▶️ Manual Trigger

If connection watching is implemented as its own Python entry point in
your current repository, run that entry point with the same project
`config.json`.

If it is integrated into another watcher/collector process, start that
parent component instead.

> \[!IMPORTANT\] The configuration alone does not identify a separate
> connection-watcher filename. Do not create a second watcher just to
> manually trigger it unless your repository actually contains one.

Check available watcher files:

``` bash
find . -maxdepth 1 -type f -name '*watcher*.py' -print
```

------------------------------------------------------------------------

# 7️⃣ 🎛️ RCON Trigger Watcher

## What It Does

`rcon_trigger_watcher.py` is the bridge between the Pavlov ModKit and
Pavlov RCON.

The ModKit can manipulate files inside ModSave, so the bridge watches
directories such as:

``` text
~/pavlovserver/Pavlov/Saved/Config/ModSave/JTWP/Rcon
~/pavlovserver0/Pavlov/Saved/Config/ModSave/JTWP/Rcon
~/pavlovserver1/Pavlov/Saved/Config/ModSave/JTWP/Rcon
```

The workflow is:

``` text
ModKit
   ↓
IN-command.json
   ↓
rcon_trigger_watcher.py
   ↓
Pavlov RCON
   ↓
response
   ↓
OUT-command.json
```

The input trigger is removed after processing.

------------------------------------------------------------------------

## ▶️ Manually Run the RCON Watcher

Stop the service first:

``` bash
sudo systemctl stop jtwp-rcon-trigger-watcher
```

Then:

``` bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-

source /home/steam/jtwp-collector/venv/bin/activate

set -a
source .env
set +a

python3 rcon_trigger_watcher.py -c config.json
```

When finished:

``` text
Ctrl+C
```

Then:

``` bash
sudo systemctl start jtwp-rcon-trigger-watcher
```

------------------------------------------------------------------------

## 🔄 Restart the RCON Watcher

``` bash
sudo systemctl restart jtwp-rcon-trigger-watcher
```

Follow:

``` bash
sudo journalctl -u jtwp-rcon-trigger-watcher -f
```

------------------------------------------------------------------------

# 8️⃣ 📄 Manually Trigger an RCON Request

This is one of the most useful manual tests because it simulates what
the ModKit does.

First identify the server's RCON ModSave directory.

Example:

``` bash
RCON_DIR="/home/steam/pavlovserver1/Pavlov/Saved/Config/ModSave/JTWP/Rcon"
```

Create it if needed:

``` bash
mkdir -p "$RCON_DIR"
```

------------------------------------------------------------------------

## 🖥️ ServerInfo Example

Create the trigger:

``` bash
printf '{}\n' > "$RCON_DIR/IN-serverinfo.json"
```

Watch the directory:

``` bash
watch -n 0.5 "ls -lah '$RCON_DIR'"
```

The watcher should:

``` text
1. Detect IN-serverinfo.json
2. Execute the configured RCON command
3. Remove IN-serverinfo.json
4. Create OUT-serverinfo.json
```

Read the response:

``` bash
jq . "$RCON_DIR/OUT-serverinfo.json"
```

------------------------------------------------------------------------

## 📋 MapList Example

``` bash
printf '{}\n' > "$RCON_DIR/IN-maplist.json"
```

Then:

``` bash
jq . "$RCON_DIR/OUT-maplist.json"
```

------------------------------------------------------------------------

## 🧩 Mod List Example

If the command is mapped by your current `rcon_commands.json`:

``` bash
printf '{}\n' > "$RCON_DIR/IN-ugcmodlist.json"
```

Then inspect:

``` bash
jq . "$RCON_DIR/OUT-ugcmodlist.json"
```

> \[!IMPORTANT\] Trigger filenames must match the names expected by the
> current RCON bridge configuration. Use `rcon_commands.json` as the
> source of truth.

See:

``` text
Guides/RCON_COMMANDS.md
```

for the full command list.

------------------------------------------------------------------------

# 9️⃣ 📚 RCON Support JSON Files

The RCON bridge uses supporting JSON files:

``` text
rcon_commands.json
game_modes.json
default_maps.json
limited_ammo_types.json
```

These describe things such as:

-   available RCON commands
-   command arguments
-   supported game modes
-   built-in map IDs
-   limited-ammo values

------------------------------------------------------------------------

## ▶️ Manually Validate Them

``` bash
for file in \
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

Pretty-print one:

``` bash
jq . rcon_commands.json
```

------------------------------------------------------------------------

# 🔟 🔎 Player Lookup Tool

## What It Does

`playerLookup` accepts a player name and uses the name index to locate
that player's stored records.

------------------------------------------------------------------------

## ▶️ Trigger It

``` bash
playerLookup "oneSALTycrack3r"
```

Or directly from the repository:

``` bash
bash scripts/playerLookup.sh "oneSALTycrack3r"
```

This provides a convenient full dump of the records associated with that
player.

------------------------------------------------------------------------

# 1️⃣1️⃣ 🕵️ Player Connection Cross-Check

## What It Does

`check-player-connections` checks collected player network data against
SSH/RCON connection information.

This is useful for finding correlations between a player's known network
history and security connection records.

------------------------------------------------------------------------

## ▶️ Trigger It

``` bash
check-player-connections "PLAYER_NAME"
```

Example:

``` bash
check-player-connections "oneSALTycrack3r"
```

> \[!CAUTION\] A network-data match is a correlation in collected
> records, not automatic proof of who personally initiated a connection
> attempt.

------------------------------------------------------------------------

# 1️⃣2️⃣ 🚫 Manual IP Block

## What It Does

`block-ip` creates UFW deny rules for the supplied IP.

------------------------------------------------------------------------

## ▶️ Trigger It

``` bash
sudo block-ip <IP>
```

Example:

``` bash
sudo block-ip 203.0.113.123
```

Check:

``` bash
sudo ufw status
```

------------------------------------------------------------------------

# 1️⃣3️⃣ 🔓 Manual IP Unblock

## ▶️ Trigger It

``` bash
sudo unblock-ip <IP>
```

Example:

``` bash
sudo unblock-ip 203.0.113.123
```

Verify:

``` bash
sudo ufw status
```

------------------------------------------------------------------------

# 1️⃣4️⃣ 🔗 ModSave Data Links

## What It Does

`setup-data-links` exposes collector directories to Pavlov ModSave using
symbolic links.

Source data:

``` text
/home/steam/jtwp-collector-data/servers
/home/steam/jtwp-collector-data/players
/home/steam/jtwp-collector-data/global
```

Example destination:

``` text
/home/steam/pavlovserver1/Pavlov/Saved/Config/ModSave/JTWP/Data
```

------------------------------------------------------------------------

## ▶️ Trigger It

``` bash
sudo setup-data-links
```

or, depending on the permissions used by your current script:

``` bash
setup-data-links
```

Inspect:

``` bash
ls -lah \
/home/steam/pavlovserver1/Pavlov/Saved/Config/ModSave/JTWP/Data
```

Check symlink targets:

``` bash
readlink -f \
/home/steam/pavlovserver1/Pavlov/Saved/Config/ModSave/JTWP/Data/*
```

------------------------------------------------------------------------

# 1️⃣5️⃣ 🔐 RCON MD5 Helper

## What It Does

`rcon-md5` generates the MD5 representation used by RCON-related
workflows that require a manually generated MD5 value.

------------------------------------------------------------------------

## ▶️ Trigger It

Run the installed helper:

``` bash
rcon-md5
```

Follow the input behavior implemented by your current script.

Avoid putting a real password directly into shell history unless the
script is specifically designed for that workflow.

------------------------------------------------------------------------

# 1️⃣6️⃣ 🔔 Discord Webhooks

## What They Do

Discord webhooks are outputs used by watcher components.

Depending on configuration, events can include:

-   failed SSH attempts
-   RCON/security events
-   connection events

Webhook URLs should remain in `.env`.

------------------------------------------------------------------------

## ▶️ Trigger Them

There is no need for a separate generic webhook process.

Trigger the component that owns the webhook.

For SSH:

``` bash
sudo systemctl restart jtwp-ssh-watcher
sudo journalctl -u jtwp-ssh-watcher -f
```

Then a matching SSH event will cause the watcher to process its
configured webhook behavior.

For RCON, trigger an RCON bridge request and follow:

``` bash
sudo journalctl -u jtwp-rcon-trigger-watcher -f
```

------------------------------------------------------------------------

# 1️⃣7️⃣ 🗄️ Collector Data

The main data tree is:

``` text
/home/steam/jtwp-collector-data
```

Major sections include:

``` text
jtwp-collector-data/
├── players/
├── servers/
└── global/
```

------------------------------------------------------------------------

## ▶️ Manually Inspect Data

Top level:

``` bash
find /home/steam/jtwp-collector-data \
    -maxdepth 2 \
    -type d \
    -print
```

JSON files:

``` bash
find /home/steam/jtwp-collector-data \
    -type f \
    -name '*.json' \
    | head -100
```

Pretty-print a known JSON file:

``` bash
jq . /path/to/file.json
```

------------------------------------------------------------------------

# 1️⃣8️⃣ 🧪 Manual Component Test Sequence

When troubleshooting, test components in this order.

### 1. Configuration

``` bash
jq empty config.json && echo "✅ CONFIG"
```

### 2. Python environment

``` bash
/home/steam/jtwp-collector/venv/bin/python3 --version
```

### 3. Python syntax

``` bash
/home/steam/jtwp-collector/venv/bin/python3 -m py_compile collector.py
/home/steam/jtwp-collector/venv/bin/python3 -m py_compile ssh_watcher.py
/home/steam/jtwp-collector/venv/bin/python3 -m py_compile rcon_trigger_watcher.py
```

### 4. Collector

``` bash
python3 collector.py -c config.json
```

### 5. SSH watcher

``` bash
sudo systemctl restart jtwp-ssh-watcher
sudo systemctl status jtwp-ssh-watcher --no-pager
```

### 6. RCON watcher

``` bash
sudo systemctl restart jtwp-rcon-trigger-watcher
sudo systemctl status jtwp-rcon-trigger-watcher --no-pager
```

### 7. Helper commands

``` bash
for cmd in \
    block-ip \
    unblock-ip \
    check-player-connections \
    playerLookup \
    setup-data-links \
    rcon-md5
do
    command -v "$cmd" || echo "❌ MISSING: $cmd"
done
```

### 8. Firewall

``` bash
sudo ufw status
```

### 9. Timers

``` bash
systemctl list-timers --all | grep -i jtwp
```

------------------------------------------------------------------------

# 📋 Quick Manual Trigger Table

  ----------------------------------------------------------------------------------------
  Component                           Manual Trigger
  ----------------------------------- ----------------------------------------------------
  📊 Full collector                   `python3 collector.py -c config.json`

  ⏰ Scheduled collector now          `sudo systemctl start jtwp-collector.service`

  🌍 Pavlov API updater               `python3 update_pavlov_api.py -c config.json`

  🗺️ Mod.io enrichment                Run `collector.py`

  🌐 IP enrichment                    Run `collector.py`

  🔐 SSH watcher                      `python3 ssh_watcher.py -c config.json`

  🔄 SSH service restart              `sudo systemctl restart jtwp-ssh-watcher`

  🎛️ RCON watcher                     `python3 rcon_trigger_watcher.py -c config.json`

  🔄 RCON service restart             `sudo systemctl restart jtwp-rcon-trigger-watcher`

  🖥️ ServerInfo trigger               Create the configured `IN-serverinfo.json`

  📋 MapList trigger                  Create the configured `IN-maplist.json`

  🔎 Player lookup                    `playerLookup "NAME"`

  🕵️ Connection check                 `check-player-connections "NAME"`

  🚫 Block IP                         `sudo block-ip IP`

  🔓 Unblock IP                       `sudo unblock-ip IP`

  🔗 Create ModSave links             `setup-data-links`

  🔐 RCON MD5                         `rcon-md5`
  ----------------------------------------------------------------------------------------

------------------------------------------------------------------------

# 📜 Watching Everything

SSH:

``` bash
sudo journalctl -u jtwp-ssh-watcher -f
```

RCON:

``` bash
sudo journalctl -u jtwp-rcon-trigger-watcher -f
```

Collector:

``` bash
sudo journalctl -u jtwp-collector.service -f
```

Show recent JTWP service activity:

``` bash
sudo journalctl \
    -u jtwp-collector.service \
    -u jtwp-ssh-watcher.service \
    -u jtwp-rcon-trigger-watcher.service \
    -n 200 \
    --no-pager
```

------------------------------------------------------------------------

# 🧠 Which Component Should I Run?

``` text
Need to rebuild/process collected data?
    └── 📊 collector.py

Need fresh public Pavlov server data?
    └── 🌍 update_pavlov_api.py

Need Mod.io or network enrichment?
    └── 📊 collector.py

Need to monitor failed SSH attempts?
    └── 🔐 ssh_watcher.py

Need the ModKit to execute RCON?
    └── 🎛️ rcon_trigger_watcher.py

Need to manually test ModKit RCON?
    └── 📄 Create an IN-*.json trigger

Need all data for one player?
    └── 🔎 playerLookup

Need to compare a player with SSH/RCON records?
    └── 🕵️ check-player-connections

Need to firewall an address?
    └── 🚫 block-ip

Need to restore access to an address?
    └── 🔓 unblock-ip

Need collector data visible in ModSave?
    └── 🔗 setup-data-links
```

------------------------------------------------------------------------

# 📚 Related Guides

For detailed configuration, use:

``` text
Guides/API_SETUP.md
Guides/RCON_COMMANDS.md
Guides/SCRIPTS.md
Guides/SERVICES.md
Guides/SSHblocking.MD
Guides/USEFUL_COMMANDS.md
```

This guide is intended to answer two questions for every major
component:

> **What does this part of JTWP do?**

and:

> **How do I run or trigger it manually?**
