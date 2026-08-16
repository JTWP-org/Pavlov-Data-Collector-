JTWP Pavlov Data Collector

JTWP Pavlov Data Collector is a Python-based logging and data collection system for Pavlov VR dedicated servers.

It is designed to collect and organize information from:

Pavlov server logs
Pavlov stats logs
Player connection events
RCON events
HTTP and EOS errors
Custom guns and loot
Loaded mods
Game.ini
Admin lists
Ban lists
SSH failed-login attempts
Player IP background data
Mod.io metadata

The collector stores most historical events in JSONL files and current state or summary data in JSON files.

Requirements
Linux server
Python 3
Python virtual environment
requests
systemd for watcher services
Access to Pavlov server files
Access to the system journal for SSH monitoring

Example install:

sudo apt update
sudo apt install python3 python3-venv -y

Create the virtual environment:

cd /home/steam/jtwp-collector

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
Project Structure

Example:

/home/steam/jtwp-collector/
├── venv/
│
└── Pavlov-Data-Collector-/
    ├── collector.py
    ├── connection_watcher.py
    ├── ssh_watcher.py
    ├── config.json
    ├── items.json
    ├── requirements.txt
    ├── .env
    ├── jtwp-connection-watcher.service
    └── jtwp-ssh-watcher.service
Environment Variables

Sensitive values are stored in .env instead of the normal JSON configuration.

Create:

nano /home/steam/jtwp-collector/Pavlov-Data-Collector-/.env

Example:

JTWP_IP_HASH_SECRET=YOUR_LONG_RANDOM_SECRET
PROXYCHECK_API_KEY=YOUR_PROXYCHECK_API_KEY
MODIO_API_KEY=YOUR_MODIO_API_KEY
JTWP_CONNECTION_WEBHOOK_URL=https://discord.com/api/webhooks/...

Optional:

IPAPI_API_KEY=YOUR_IPAPI_KEY
JTWP_SSH_WEBHOOK_URL=https://discord.com/api/webhooks/...

Protect the file:

chmod 600 /home/steam/jtwp-collector/Pavlov-Data-Collector-/.env
IP Hash Secret

Generate the IP hashing secret once:

openssl rand -hex 32

Store that result as:

JTWP_IP_HASH_SECRET=...

Do not change this secret after data collection begins.

The same IP always produces the same hash only when the same secret is used. Changing the secret will prevent historical IP hashes from matching new ones.

Configuration

The main collector configuration is stored in:

config.json

Example:

{
  "data_path": "/home/steam/jtwp-collector-data",
  "archive_path": "/home/steam/jtwp-log-archive",

  "request_timeout_seconds": 8,

  "modio_game_id": 3959,
  "modio_cache_ttl_hours": 24,
  "ip_lookup_cache_ttl_days": 30,

  "rotate_active_logs": true,
  "count_unverified_player_kills": true,

  "servers": [
    {
      "log_path": "/home/steam/pavlovserver/Pavlov/Saved/Logs/",
      "platform": "auto"
    },
    {
      "log_path": "/home/steam/pavlovserver0/Pavlov/Saved/Logs/",
      "platform": "auto"
    },
    {
      "log_path": "/home/steam/pavlovserver1/Pavlov/Saved/Logs/",
      "platform": "auto"
    }
  ],

  "connection_watcher": {
    "poll_interval_seconds": 0.5,
    "start_at_end": true,
    "webhook_mode": "discord",
    "webhook_timeout_seconds": 8,
    "webhook_retries": 2
  },

  "ssh_watcher": {
    "units": [
      "ssh.service",
      "sshd.service"
    ],
    "enrich_ips": true,
    "include_invalid_user_events": false
  }
}
Pavlov Server Detection

The collector derives the server ID from the log path.

Example:

/home/steam/pavlovserver/Pavlov/Saved/Logs/

becomes:

pavlovserver

And:

/home/steam/pavlovserver1/Pavlov/Saved/Logs/

becomes:

pavlovserver1

The related directories are then automatically derived.

Stats:

/home/steam/{serverID}/Pavlov/Saved/Stats/

Config:

/home/steam/{serverID}/Pavlov/Saved/Config/
Shack and PCVR Detection

The collector supports both Pavlov platforms.

If the server logs contain:

PavlovLog: SHACK SERVER BUILD

the server is identified as:

SHACK

If that line is not detected, it defaults to:

PCVR

The platform can also be manually specified in config.json.

Main Collector

Run:

cd /home/steam/jtwp-collector/Pavlov-Data-Collector-

source /home/steam/jtwp-collector/venv/bin/activate

set -a
source .env
set +a

python3 collector.py -c config.json

The collector processes historical logs and builds the main dataset.

Log Archiving

The collector handles both Pavlov logs and Stats logs.

Pavlov logs:

Pavlov-backup-*.log
Pavlov.log

Stats logs:

Stats-*.log
Stats.log

Archived logs are moved to the configured archive directory.

The active:

Pavlov.log

and:

Stats.log

are copied to timestamped archive files before being truncated.

The original active files remain in place.

Player Identity

The permanent player key is:

productId

Each player receives a folder:

players/records/{productId}/

Example:

players/records/00024a4843dc40b8950029db3cd7b111/

The platform-specific uniqueId is stored separately.

For Shack:

uniqueId = Shack/Meta identifier

For PCVR:

uniqueId = SteamID

The display name is stored separately and name changes are tracked.

Player Data

Example player directory:

players/records/{productId}/
├── player.json
├── stats.json
├── names.json
├── weapons.json
├── ips.json
├── connections.jsonl
├── matches.jsonl
├── kills.jsonl
├── deaths.jsonl
└── changes.jsonl

Tracked player statistics include:

Total kills
Total deaths
Headshots
Suicides
Teamkills
Bot kills
Times connected
Match count
Favorite weapon

Normal kills do not include suicides or confirmed teamkills.

Player Changes

The collector tracks changes such as:

Player name
uniqueId
Player height
Right/left handed setting
VStock
Client platform
IP hash
ISP/organisation
Country
Proxy status
VPN status
Hosting status
Tor status

Changes are appended to:

changes.jsonl
Player Connection Watcher

The live player connection watcher is:

connection_watcher.py

It watches each active:

Pavlov.log

for new connections.

It correlates events such as:

AddClientConnection
Login request
Join request
Join succeeded
TeamAssign
UChannel::Close

When a player successfully joins, the watcher updates that player's stored data before sending the webhook.

It can update:

Times connected
Name
uniqueId
productId
Player height
Handedness
VStock
Client platform
IP history
IP background
Admin status
Ban status
RCON IP correlation
Connection Webhook

The Discord webhook URL is stored in:

JTWP_CONNECTION_WEBHOOK_URL

The watcher can send information such as:

Player name
Product ID
Unique ID
Platform
Admin status
Ban status
Times connected
Matches
Kills
Deaths
Headshots
Teamkills
Suicides
Favorite weapon
Player height
Handedness
VStock
ISP
Country
Proxy
VPN
Hosting status

Raw player IP addresses are not included in the webhook.

Connection Watcher Service

Create:

sudo nano /etc/systemd/system/jtwp-connection-watcher.service

Use:

[Unit]
Description=JTWP Pavlov Connection Watcher
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=steam
WorkingDirectory=/home/steam/jtwp-collector/Pavlov-Data-Collector-
EnvironmentFile=/home/steam/jtwp-collector/Pavlov-Data-Collector-/.env
ExecStart=/home/steam/jtwp-collector/venv/bin/python3 /home/steam/jtwp-collector/Pavlov-Data-Collector-/connection_watcher.py -c /home/steam/jtwp-collector/Pavlov-Data-Collector-/config.json
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target

Enable it:

sudo systemctl daemon-reload
sudo systemctl enable --now jtwp-connection-watcher

Check status:

sudo systemctl status jtwp-connection-watcher

Watch logs:

sudo journalctl -u jtwp-connection-watcher -f
IP Privacy

Raw IP addresses are not stored in normal player data.

The collector uses:

HMAC-SHA256

with:

JTWP_IP_HASH_SECRET

to produce a stable IP hash.

This allows the collector to recognize that the same IP was used again without placing the raw IP throughout the dataset.

Example player IP history:

{
  "current_ip_hash": "HASH123",

  "ips": {
    "HASH123": {
      "first_seen": "2026.08.01-12.00.00",
      "last_seen": "2026.08.16-18.00.00",
      "connections": 42
    }
  }
}
Raw Player IP Storage

Raw player IPs are isolated under:

data/private/player_ips.json

This file is keyed by productId.

Example:

{
  "00024a4843dc40b8950029db3cd7b111": {
    "192.0.2.25": {
      "hash": "HASH123",
      "first_seen": "2026.08.01-12.00.00",
      "last_seen": "2026.08.16-18.00.00",
      "connections": 42
    }
  }
}

Protect the private directory appropriately.

IP Background Lookups

New IPs can be enriched before being stored as hashes.

Primary API:

ProxyCheck.io

Fallback API:

ipapi.is

Normalized fields include:

organisation
country_code
network_type
hosting
proxy
vpn
tor
risk
confidence

IP lookups are cached so the same IP does not repeatedly consume API quota.

RCON Tracking

The collector tracks:

Successful RCON authentication
Failed RCON authentication
RCON commands
RCON disconnects
Known RCON hosts
Failed RCON hosts

RCON IPs are stored as hashes.

If a player connects from an IP that has also connected to RCON, the player identity can be attached to that RCON host record.

This means the collector can show that a player and an RCON connection were observed using the same network address without exposing the raw address in normal data.

HTTP Events

HTTP and EOS errors are collected under:

servers/{serverID}/http/

Examples include:

libcurl errors
Request timeouts
Connection failures
Invalid HTTP responses
EOS backend failures
EOS token failures
Retry exhaustion
Authentication failures
Server Runtime Information

The collector can extract server runtime information including:

Physical CPU cores
Logical CPU cores
RAM
Unreal Engine build
Unreal Engine version
Unreal branch
Command line
Server port
Pavlov version
NetCL
Engine network version
Game network version
Network checksum

Current values are stored in:

server.json
Game.ini

The collector can load each server's Game.ini.

Tracked settings include:

ServerName
bVerboseLogging
TickRate
MapRotation
AdditionalMods

Commented lines beginning with:

#

or:

;

are ignored.

All active MapRotation entries are collected.

Example:

MapRotation=(MapId="UGC2815354",GameMode="TDM")
Mod.io Enrichment

UGC IDs are converted from:

UGC6279197

to:

6279197

before querying Mod.io.

The collector can save:

Mod name
thumb_320x180
Downloads today
Total downloads
Summary

Results are cached globally.

Custom Guns

The collector watches for:

PavlovLog: Added Gun cak

Custom guns are stored per server.

Tracked information includes:

Gun name
First seen
Last seen
Times loaded

Custom guns can also be identified in player kill statistics.

Custom Loot

The collector detects:

PavlovLog: Added Loot Mesh mg42_bipod

and stores unique custom loot names.

Failed Custom Items

Examples:

LogTemp: Error: 3395365Failed to addrgw90

The collector interprets:

3395365

as:

UGC3395365

and associates the failed item with that UGC ID.

It also tracks messages such as:

Failed to add item m4_debug it already exists in the list
Mods

The collector watches for mod initializers:

ModInitializer Found UGC3395365 path /UGC3395365/...

Stored information can include:

UGC ID
Initializer
Initializer path
First seen
Last seen
Times loaded
Mod.io metadata
Stats Logs

Pavlov Stats files are not one valid JSON document.

They contain multiple timestamped JSON objects such as:

[2026.08.15-04.58.13] StatManagerLog: {
    ...
}

The collector rebuilds each block into usable JSON.

Round Files

Every allStats block can generate its own round file.

Example filename:

pavlovserver-2026.08.15-04.58.13-UGC2815354-TDM-19.json

Round data can include:

Server
Timestamp
Map
Game mode
Match duration
Player count
Team scores
Player IDs
Player stats

Each player's match counter increases whenever that player's productId appears in an allStats block.

Admins

Admins are global across all tracked Pavlov servers.

Admin entries are loaded from:

/home/steam/{serverID}/Pavlov/Saved/Config/mods.txt

and:

/home/steam/{serverID}/Pavlov/Saved/Config/ModSave/RconPlus/MenuAccesscfg.txt

All unique entries are merged into:

global/admins.json

If a player is an admin on one tracked server, the player is considered an admin globally.

Bans

Each server's ban list is read from:

/home/steam/{serverID}/Pavlov/Saved/Config/blacklist.txt

The collector stores the current unique bans and tracks additions/removals.

Example:

servers/{serverID}/bans/current_bans.json
servers/{serverID}/bans/changes.jsonl
SSH Failed Login Watcher

The SSH watcher is:

ssh_watcher.py

It follows the OpenSSH systemd journal and records failed authentication attempts.

Recognized examples include:

Failed password for root from 1.2.3.4 port 51234 ssh2
Failed password for invalid user admin from 1.2.3.4 port 51234 ssh2
Failed publickey for user from 1.2.3.4 port 51234 ssh2
maximum authentication attempts exceeded ...

Normal output:

data/global/ssh/
├── events.jsonl
├── failed_hosts.json
└── ssh.log

Raw SSH source IPs are isolated to:

data/private/ssh_ips.json
SSH Watcher Permissions

The steam user needs access to the system journal.

Run:

sudo usermod -aG systemd-journal steam

Then log out and reconnect.

Verify:

groups

You should see:

systemd-journal

Test journal access:

journalctl -u ssh.service -n 20 -o cat
SSH Watcher Service

Create:

sudo nano /etc/systemd/system/jtwp-ssh-watcher.service

Use:

[Unit]
Description=JTWP SSH Failed Login Watcher
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=steam
WorkingDirectory=/home/steam/jtwp-collector/Pavlov-Data-Collector-
EnvironmentFile=/home/steam/jtwp-collector/Pavlov-Data-Collector-/.env
ExecStart=/home/steam/jtwp-collector/venv/bin/python3 /home/steam/jtwp-collector/Pavlov-Data-Collector-/ssh_watcher.py -c /home/steam/jtwp-collector/Pavlov-Data-Collector-/config.json
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target

Enable:

sudo systemctl daemon-reload
sudo systemctl enable --now jtwp-ssh-watcher

Status:

sudo systemctl status jtwp-ssh-watcher

Logs:

sudo journalctl -u jtwp-ssh-watcher -f

Last 50 lines:

sudo journalctl -u jtwp-ssh-watcher -n 50 --no-pager
Output Directory

Typical generated data structure:

/home/steam/jtwp-collector-data/
├── global/
│   ├── admins.json
│   ├── processing_state.json
│   ├── stats_combat_state.json
│   ├── modio/
│   │   └── mods.json
│   ├── reference/
│   │   └── unknown_items.json
│   └── ssh/
│       ├── events.jsonl
│       ├── failed_hosts.json
│       └── ssh.log
│
├── private/
│   ├── player_ips.json
│   ├── ip_lookup_cache.json
│   └── ssh_ips.json
│
├── players/
│   ├── index/
│   │   ├── by_name.json
│   │   ├── by_unique_id.json
│   │   └── by_product_id.json
│   │
│   └── records/
│       └── {productId}/
│           ├── player.json
│           ├── stats.json
│           ├── names.json
│           ├── weapons.json
│           ├── ips.json
│           ├── connections.jsonl
│           ├── matches.jsonl
│           ├── kills.jsonl
│           ├── deaths.jsonl
│           └── changes.jsonl
│
└── servers/
    └── {serverID}/
        ├── server.json
        ├── game_ini.json
        ├── rounds/
        ├── bans/
        ├── rcon/
        ├── http/
        ├── stats/
        └── server/
Useful Commands

Run main collector:

python3 collector.py -c config.json

Run live player watcher:

python3 connection_watcher.py -c config.json

Run SSH watcher:

python3 ssh_watcher.py -c config.json

Pretty-print JSON:

python3 -m json.tool filename.json

Watch connection watcher:

sudo journalctl -u jtwp-connection-watcher -f

Watch SSH watcher:

sudo journalctl -u jtwp-ssh-watcher -f

Restart services:

sudo systemctl restart jtwp-connection-watcher
sudo systemctl restart jtwp-ssh-watcher

Check both:

sudo systemctl status jtwp-connection-watcher
sudo systemctl status jtwp-ssh-watcher
Security Notes

Keep these values private:

ProxyCheck API key
Mod.io API key
Webhook URLs
IP hash secret
Raw IP databases

Do not put them in public repositories.

The following directory should be treated as private:

/home/steam/jtwp-collector-data/private/

The .env file should also be protected:

chmod 600 .env

The IP hashing secret should remain unchanged for the lifetime of the dataset.

JTWP

Pavlov Data Collector and server tooling created for JTWP server administration, logging, historical analysis, and player/server statistics.
