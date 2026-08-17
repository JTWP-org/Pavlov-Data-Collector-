# 🎮 JTWP Pavlov Collector

A data collection, monitoring, enrichment, and automation system for **Pavlov VR dedicated servers**.

The collector processes Pavlov logs and server  configuration data into structured JSON/JSONL datasets while providing  live connection monitoring, SSH/RCON security tracking, Mod.io metadata  enrichment, IP intelligence, Discord notifications, and a file-based  RCON bridge for Pavlov ModKit workflows.

---

## ✨ Features

- 📊 Collects player, server, combat, connection, and round data
- 👤 Maintains persistent player records using `productId`
- 🔫 Tracks kills, deaths, weapons, and combat statistics
- 🌐 Privately stores and enriches player IP information
- 🔐 Uses HMAC-SHA256 hashes outside private datasets
- 🛡️ Detects proxy, VPN, hosting, and other IP intelligence
- 🗺️ Enriches maps and mods with Mod.io metadata
- 🔌 Watches live Pavlov player connections
- 🔑 Watches failed SSH authentication attempts
- 🎛️ Provides a file-based RCON trigger bridge
- 🚨 Correlates SSH/RCON source networks with known player networks
- 💬 Supports Discord security and connection webhooks
- 📦 Archives and deduplicates processed Pavlov logs
- ⚙️ Includes systemd services for continuous operation

---

# 📦 Installation

## 1. Install Python

```
sudo apt update
sudo apt install python3 python3-venv -y
```

## 2. Create the collector directory

```
mkdir -p /home/steam/jtwp-collector
cd /home/steam/jtwp-collector
```

## 3. Create the virtual environment

```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 4. Create the configuration

Copy `collector.py` and `config.example.json` into the collector directory, then:

```
cp config.example.json config.json
nano config.json
```

---

# 🔐 Secrets & Environment Variables

> ⚠️ **Never place API keys, RCON passwords, webhook URLs, or other secrets inside generated public JSON data.**

Generate a stable secret for IP hashing:

```
export JTWP_IP_HASH_SECRET="$(openssl rand -hex 32)"
```

Configure the external APIs:

```
export PROXYCHECK_API_KEY="YOUR_PROXYCHECK_KEY"
export MODIO_API_KEY="YOUR_MODIO_KEY"
```

Optionally configure an authenticated ipapi.is key:

```
export IPAPI_API_KEY="YOUR_IPAPI_KEY"
```

## ⚠️ Keep the IP hash secret

`JTWP_IP_HASH_SECRET` must remain unchanged.

Changing this value changes every generated IP hash and breaks historical correlation between:

- players
- RCON attempts
- SSH attempts
- previously collected network data

For systemd services, store secrets in a root-readable `EnvironmentFile` rather than directly inside the service unit.

---

# ▶️ Running the Collector

Activate the virtual environment:

```
source /home/steam/jtwp-collector/venv/bin/activate
```

Run:

```
python3 collector.py -c config.json
```

---

# ⚙️ Collector Behavior

The collector handles Pavlov logs differently depending on whether they are archived or currently active.

### 📜 Pavlov Logs

- `Pavlov-backup-*.log` files are moved into the archive.
- Active `Pavlov.log` is copied into the archive and then truncated.

### 📊 Stats Logs

- `Stats-*.log` files are moved into the archive.
- Active `Stats.log` is copied into the archive and then truncated.

### ♻️ Duplicate Protection

A SHA-256 processing index prevents the same archived content from being processed more than once.

### 👤 Player Identification

Player directories use:

```
productId

```

### 🌐 IP Privacy

Raw player IP addresses exist only inside:

```
private/player_ips.json
private/ip_lookup_cache.json

```

All other datasets use a stable:

```
HMAC-SHA256 IP hash

```

### 🔎 IP Intelligence

Lookup priority:

```
ProxyCheck
    ↓
ipapi.is fallback

```

### 🗺️ Mod.io

Mod.io API responses are cached to reduce unnecessary requests.

### ⚙️ Game.ini

Commented configuration lines beginning with:

```
#
;

```

are ignored.

This includes entries such as:

```
#MapRotation

```

---

# 🔫 Kill Classification

Older `KillData` entries can omit team IDs.

When this happens, player-vs-player events are classified as:

```
normal_unverified_team_relation

```

By default, these events count toward kills so historical data remains useful.

The collector separately records:

```
kills_unverified_team_relation

```

so you can determine how many kills could not be verified as enemy-vs-enemy.

To only count kills with a provable non-team relationship:

```
{
  "count_unverified_player_kills": false
}
```

---

# 📂 Output Structure

```
data/
├── global/
│   ├── admins.json
│   ├── processing_state.json
│   ├── stats_combat_state.json
│   ├── modio/
│   │   └── mods.json
│   └── reference/
│       └── unknown_items.json
│
├── private/
│   ├── player_ips.json
│   └── ip_lookup_cache.json
│
├── players/
│   ├── index/
│   │   ├── by_name.json
│   │   ├── by_unique_id.json
│   │   └── by_product_id.json
│   │
│   └── records/{productId}/
│       ├── player.json
│       ├── names.json
│       ├── stats.json
│       ├── weapons.json
│       ├── ips.json
│       ├── matches.jsonl
│       ├── kills.jsonl
│       ├── deaths.jsonl
│       ├── connections.jsonl
│       └── changes.jsonl
│
└── servers/{serverID}/
    ├── server.json
    ├── game_ini.json
    ├── rounds/
    │   └── *.json
    ├── bans/
    │   ├── current_bans.json
    │   └── changes.jsonl
    ├── rcon/
    ├── http/
    └── server/

```

---

# 🔫 Pavlov Item Database

The built-in Pavlov item list is stored in the shared resource directory:

```text
resource/items.json
```

The main `config.json` no longer requires a `base_items` section.

To add or remove known Pavlov items, edit `resource/items.json`:

```
{
  "items": [
    "ak47",
    "m16",
    "mp5"
  ]
}
```

Custom guns observed through log entries such as:

```
PavlovLog: Added Gun ...

```

are still automatically detected.

---

# 👁️ Live Connection Watcher

`connection_watcher.py` monitors each configured live:

```
Pavlov.log

```

The watcher starts at the **end of the file by default**, preventing existing historical joins from triggering new webhook events.

## 🔗 Join Correlation

For every new successful connection, the watcher correlates:

```
AddClientConnection
        ↓
Login request
        ↓
Join request
        ↓
Join succeeded

```

It then:

- 👤 Derives `productId` from `userId: NULL:<32 hex>` when available
- 📁 Updates the player's `productId` directory
- 🔢 Increments connection count
- 📏 Updates player height
- ✋ Updates handedness
- 🎮 Updates VStock
- 💻 Updates client platform
- 🔐 Hashes the source IP
- 🌐 Enriches IP information
- 👑 Refreshes admin status
- 🚫 Refreshes ban status
- 🎛️ Correlates the IP hash with known RCON hosts
- 💬 Sends the configured webhook
- 🛡️ Never exposes the raw IP through the webhook

---

## 🔑 Connection Watcher Environment

Add to `.env`:

```
JTWP_IP_HASH_SECRET=...
PROXYCHECK_API_KEY=...
MODIO_API_KEY=...
JTWP_CONNECTION_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

Run manually:

```
source venv/bin/activate
set -a
source .env
set +a

python3 connection_watcher.py -c config.json
```

---

# ⚙️ Connection Watcher — systemd

Copy:

```
[Unit]
Description=JTWP Pavlov Connection Watcher
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=steam
Group=steam

WorkingDirectory=/home/steam/jtwp-collector
EnvironmentFile=-/home/steam/jtwp-collector/.env

ExecStart=/home/steam/jtwp-collector/venv/bin/python3 /home/steam/jtwp-collector/connection_watcher.py -c /home/steam/jtwp-collector/config.json

Restart=always
RestartSec=5

StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target

```

to:

```
sudo nano /etc/systemd/system/jtwp-connection-watcher.service

```

Then enable it:

```
sudo systemctl daemon-reload
sudo systemctl enable --now jtwp-connection-watcher
```

Follow the logs:

```
sudo journalctl -u jtwp-connection-watcher -f
```

## 💬 Webhook Modes

`webhook_mode` supports:

| Mode Behavior  |                |
| -------------- | -------------- |
| `discord`      | Discord embed  |
| `generic`      | Raw JSON event |

The default is:

```
discord

```

---

# 🔑 SSH Failed-Login Watcher

`ssh_watcher.py` follows the OpenSSH systemd journal and records failed SSH authentication attempts.

Normal datasets use the same stable HMAC-SHA256 IP hash used by player and RCON data.

## 📂 SSH Data

```
data/global/ssh/
├── events.jsonl
├── failed_hosts.json
└── ssh.log

```

Raw SSH source IPs are isolated inside:

```
data/private/ssh_ips.json

```

---

## 📊 Failed SSH Host Information

Each failed host can accumulate:

- 🕐 First seen
- 🕐 Last seen
- 🔢 Total failed attempts
- 👤 Usernames attempted
- 📊 Attempt counts per username
- 🔌 Recent source ports
- 🌐 ISP
- 🏢 Organisation
- 🌎 Country
- 🖥️ Hosting detection
- 🕵️ Proxy detection
- 🔐 VPN detection
- 🧅 Tor detection
- 🔎 ProxyCheck/ipapi lookup source

---

## 🔓 Allow Journal Access

The `steam` user must be allowed to read the systemd journal.

On Ubuntu:

```
sudo usermod -aG systemd-journal steam
```

Restart the service or login session afterward so the new group membership takes effect.

---

## ⚙️ Install SSH Watcher

```
sudo cp jtwp-ssh-watcher.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now jtwp-ssh-watcher
```

Follow its logs:

```
sudo journalctl -u jtwp-ssh-watcher -f
```

---

## 👤 Invalid SSH Users

By default:

```
Invalid user ...

```

messages are **not counted separately**.

OpenSSH commonly emits an `Invalid user` message immediately before the corresponding:

```
Failed password ...

```

Counting both would therefore double-count a single authentication attempt.

To treat them as separate events, enable:

```
{
  "include_invalid_user_events": true
}
```

---

# 🛡️ Security Correlation

The collector maintains:

```
players/index/by_ip_hash.json

```

This index maps each stable HMAC-SHA256 IP hash to player product IDs previously observed using that public IP.

SSH and failed-RCON events automatically check this index.

> ⚠️ **Important:** An IP hash match only means the same public IP address was observed. It does **not** prove that a particular Pavlov player performed the SSH or RCON attempt.

This distinction is especially important for:

- shared households
- carrier-grade NAT
- VPN services
- hosting providers
- university/business networks
- other shared public IPs

---

# 🚨 Security Webhooks

You can use one shared Discord webhook for security events:

```
JTWP_SECURITY_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

Or configure separate RCON and SSH webhooks:

```
JTWP_SSH_WEBHOOK_URL=https://discord.com/api/webhooks/...
JTWP_RCON_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

> 🔒 Raw IP addresses are never posted to Discord.

---

# 🗺️ Mod.io Map & Mod Metadata

Active `Game.ini` map rotation entries are enriched and written to:

```
servers/{serverID}/server/maps.json

```

`AdditionalMods` entries are merged with log-discovered `ModInitializer` entries and written to:

```
servers/{serverID}/server/mods.json

```

For UGC entries, Mod.io metadata includes:

```
name
thumb_320x180
downloads_today
downloads_total
summary

```

Results reuse the global Mod.io cache to minimize API requests.

---

# 🎛️ RCON File Trigger Bridge

The collector includes a file-based RCON bridge designed for **Pavlov ModKit workflows**.

Instead of requiring the ModKit to establish an RCON connection itself, the ModKit creates JSON request files.

The Linux-side watcher detects those files, executes the appropriate RCON command, and writes the result back as JSON.

## 🔄 Basic Flow

```
Pavlov ModKit
     │
     ▼
IN-command.json
     │
     ▼
RCON Trigger Watcher
     │
     ├── Validate command
     ├── Validate arguments
     ├── Connect to RCON
     └── Execute command
     │
     ▼
OUT-command.json
     │
     ▼
Pavlov ModKit

```

---

# 📁 RCON Trigger Directories

The ModKit can create JSON files inside each server's `ModSave` directory.

Examples:

```
/home/steam/pavlovserver/Pavlov/Saved/Config/ModSave/JTWP/Rcon
/home/steam/pavlovserver0/Pavlov/Saved/Config/ModSave/JTWP/Rcon
/home/steam/pavlovserver1/Pavlov/Saved/Config/ModSave/JTWP/Rcon

```

The directory determines which Pavlov server receives the RCON command.

---

# 📥 RCON Request / Response Naming

Create a request such as:

```
IN-serverinfo.json

```

The watcher:

1. 👁️ Detects the `IN-*.json` request
2. 🧹 Removes any stale matching `OUT-*.json`
3. ✅ Validates the command against `rcon_commands.json`
4. 🔎 Validates required arguments
5. 📡 Sends the RCON command
6. 💾 Atomically writes a fresh `OUT-*.json`
7. 🗑️ Removes the original `IN-*.json`

The resulting file is:

```
OUT-serverinfo.json

```

---

# ✅ Successful RCON Response

```
{
  "timestamp": "2026-08-17T00:00:00Z",
  "server_id": "pavlovserver1",
  "platform": "SHACK",
  "request": "serverinfo",
  "rcon_command": "ServerInfo",
  "success": true,
  "args": {},
  "response": {}
}
```

---

# ❌ RCON Error Response

Errors are returned through the corresponding `OUT-*.json` file:

```
{
  "success": false,
  "error": "Missing required field: unique_id"
}
```

This allows the ModKit to handle both successful and failed requests using the same file workflow.

---

# 🕹️ RCON Commands With Arguments

## 🤖 Enable / Disable Bots

Create:

```
IN-setbotsenabled.json

```

```
{
  "enabled": true
}
```

---

## 👥 Set Maximum Players

Create:

```
IN-setmaxplayers.json

```

```
{
  "amount": 10
}
```

---

## 🔫 Give Player an Item

Create:

```
IN-giveitem.json

```

```
{
  "unique_id": "12345678901234567",
  "item_id": "syringe"
}
```

---

## 🗺️ Switch Map

Create:

```
IN-switchmap.json

```

```
{
  "map_id": "datacenter",
  "game_mode": "SND"
}
```

---

# 📚 RCON Reference Files

The bridge uses static reference and validation files stored in the `resource/` directory:

```text
resource/
├── items.json
├── rcon_commands.json
├── game_modes.json
├── default_maps.json
└── limited_ammo_types.json
```

All commands currently listed inside:

```text
resource/rcon_commands.json
```

are enabled.

---

# ⚙️ RCON Server Configuration

Each server in `config.json` requires an RCON block.

Example:

```
{
  "log_path": "/home/steam/pavlovserver1/Pavlov/Saved/Logs/",
  "platform": "auto",
  "rcon": {
    "enabled": true,
    "host": "127.0.0.1",
    "port": 9304,
    "password_env": "PAVLOVSERVER1_RCON_PASSWORD"
  }
}
```

The password itself is **not stored in** **`config.json`**.

Instead, `password_env` specifies which environment variable contains the password.

---

# 🔐 RCON Passwords

Store passwords in `.env`:

```
PAVLOVSERVER_RCON_PASSWORD=YOUR_PASSWORD
PAVLOVSERVER0_RCON_PASSWORD=YOUR_PASSWORD
PAVLOVSERVER1_RCON_PASSWORD=YOUR_PASSWORD
```

> 🔒 Do not commit `.env` to a public repository.

---

# 📦 RCON Bridge Dependencies

Activate the collector environment:

```
source /home/steam/jtwp-collector/venv/bin/activate
```

Install dependencies:

```
pip install -r requirements.txt
```

---

# ⚙️ Install the RCON Trigger Service

Install the service:

```
sudo install -m 644 jtwp-rcon-trigger-watcher.service /etc/systemd/system/jtwp-rcon-trigger-watcher.service
```

Reload systemd:

```
sudo systemctl daemon-reload
```

Enable and start the watcher:

```
sudo systemctl enable --now jtwp-rcon-trigger-watcher
```

---

## 🔎 Check RCON Watcher Status

```
sudo systemctl status jtwp-rcon-trigger-watcher --no-pager
```

## 📜 Follow RCON Watcher Logs

```
sudo journalctl -u jtwp-rcon-trigger-watcher -f
```

---

# 🚀 Automatic RCON Bridge Installation

You can alternatively use the included installer:

```
sudo ./scripts/install-rcon-bridge.sh
```

---

# 🌐 Pavlov Public API Collection

The collector can also maintain a lightweight snapshot of the public Pavlov server browser using the Pavlov public API.

## 🔗 API Configuration

Add the public API endpoint to `.env`:

```bash
PAVLOV_API="https://pavlovservers.com/api/servers?all=true"
```

The normal nightly `collector.py` run automatically refreshes the public-server snapshot.

## ⚡ Lightweight API Refresh

To refresh only the public Pavlov API data **without processing Pavlov logs or Stats**, run:

```bash
/home/steam/jtwp-collector/venv/bin/python3 update_pavlov_api.py -c config.json
```

### 🛠️ Install the Helper Command

```bash
chmod +x scripts/update-pavlov-api.sh
sudo install -m 755 scripts/update-pavlov-api.sh /usr/local/bin/update-pavlov-api
```

After installation, trigger an update from anywhere with:

```bash
update-pavlov-api
```

## 📂 Public API Output

```text
/home/steam/jtwp-collector-data/global/pavlov_api/
├── servers.json
├── network_hosts.json
├── network_hosts_cache.json
├── summary.json
├── last_update.json
└── index/
    ├── by_name.json
    ├── by_ip.json
    ├── by_map.json
    ├── by_game_mode.json
    └── by_server_type.json
```

### 🖥️ Server & Host Enrichment

`servers.json` embeds the selected ProxyCheck/ipapi host fields for each public Pavlov server.

Each unique public IP is enriched once and then reused for every Pavlov instance on that host until the host-cache TTL expires. This reduces duplicate IP-intelligence requests when multiple Pavlov servers share the same public host.

### 🗂️ Public API Indexes

The generated indexes make it easier to locate public servers by:

- 🏷️ Server name — `by_name.json`
- 🌐 Public IP — `by_ip.json`
- 🗺️ Map — `by_map.json`
- 🎮 Game mode — `by_game_mode.json`
- 🖥️ Server/platform type — `by_server_type.json`

---

# 🔒 Privacy Model

The collector intentionally separates raw network information from normal datasets.

```
                   Raw IP
                     │
                     ▼
              data/private/
                     │
                     ├── player_ips.json
                     ├── ip_lookup_cache.json
                     └── ssh_ips.json
                     │
                     ▼
               HMAC-SHA256
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
     Players        RCON          SSH

```

Normal player, server, RCON, SSH, and security datasets use the stable IP hash instead of the raw address.

This allows historical network correlation without unnecessarily duplicating raw IP addresses throughout the dataset.

---

# 🧰 Useful Service Commands

Check running JTWP services:

```
systemctl --type=service | grep jtwp
```

Restart the connection watcher:

```
sudo systemctl restart jtwp-connection-watcher
```

Restart the SSH watcher:

```
sudo systemctl restart jtwp-ssh-watcher
```

Restart the RCON bridge:

```
sudo systemctl restart jtwp-rcon-trigger-watcher
```

Follow all JTWP-related journal messages:

```
sudo journalctl -f | grep -i jtwp
```

---

# 🛡️ Security Notes

- 🔑 Keep API keys and passwords in environment variables.
- 🔒 Never expose the contents of `data/private/`.
- 🧂 Keep `JTWP_IP_HASH_SECRET` stable and private.
- 🚫 Do not commit `.env` to source control.
- 🌐 Treat IP intelligence as informational rather than proof of identity.
- 🔗 An IP correlation does not prove that two events came from the same individual.
- 💬 Raw IP addresses should never be included in Discord webhook messages.
- 👑 Restrict access to RCON configuration and passwords.
- 📁 Protect collector output using appropriate Linux ownership and permissions.

---

# 🎮 JTWP Pavlov Collector

**Collect. Correlate. Monitor. Automate.**

Built for Pavlov dedicated server data collection and administration.
