# JTWP Pavlov Data Collector

> A Pavlov VR server data collector for building long-term server, player, RCON, connection, security, map, mod, and statistics records from Pavlov server logs.

you need 2 api keys and 2 webhooks to use this tool 

-get a mod.io api key get it free at https://mod.io/me/access#api

-get a proxycheck api key free at https://proxycheck.io/dashboard/
---

## Features

The collector is designed to turn Pavlov's raw logs and stats files into organized JSON/JSONL data that can be searched and used by other scripts, websites, bots, or admin tools.

### Server data

- Archives `Pavlov.log` and historical `Pavlov-backup-*.log` files.
- Detects **SHACK** automatically; servers without the SHACK marker are treated as **PCVR**.
- Records server events, match-state changes, ports, engine/build information, custom guns, loot meshes, mods, and HTTP/network errors.
- Reads `Game.ini` for:
  - `ServerName`
  - `TickRate`
  - active `MapRotation`
  - `AdditionalMods`
- Ignores commented `#MapRotation` and `;MapRotation` entries.
- Reads each server's `blacklist.txt`.
- Reads global admin IDs from `mods.txt` and RconPlus `MenuAccesscfg.txt`.

### Player data

Player folders are keyed by **productId**, which is the primary permanent player identifier.

The collector can track:

- current and previous player names;
- SHACK `uniqueId` / PCVR Steam ID;
- total kills;
- total deaths;
- headshots;
- suicides;
- teamkills;
- times connected;
- matches played;
- kills by weapon;
- favorite weapon;
- admin status;
- banned status;
- handedness;
- VStock setting;
- player height;
- client platform;
- IP history using secure HMAC-SHA256 hashes;
- IP network information;
- player-data changes over time.

### Security and network data

- Successful RCON authentication.
- Failed RCON authentication.
- RCON commands and associated connections where possible.
- Unique successful/failed RCON hosts.
- Failed SSH authentication attempts.
- IP enrichment through ProxyCheck with ipapi fallback.
- Player ↔ RCON IP-hash correlation.
- Player ↔ SSH IP-hash correlation.
- Discord alerts for player connections, failed RCON authentication, and failed SSH authentication.

> [!IMPORTANT]
> An IP-hash match means a player has previously been observed using the same public IP. It does **not** prove that player performed an SSH or RCON attempt. VPNs, shared networks, carrier NAT, hosting providers, and other shared connections can produce matches.

### Mod.io data

UGC maps and mods can be enriched with:

- name;
- `thumb_320x180`;
- downloads today;
- total downloads;
- summary.

Mod.io results are cached so the same UGC ID does not need to be requested repeatedly.

---

# 1. Requirements

Recommended environment:

- Ubuntu Linux
- Python 3
- Pavlov dedicated server
- systemd
- Internet access for IP and Mod.io lookups

Install the basic packages:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip openssl -y
```

---

# 2. Installation

This README assumes the project is installed here:

```text
/home/steam/jtwp-collector/Pavlov-Data-Collector-
```

and the Python virtual environment is here:

```text
/home/steam/jtwp-collector/venv
```

Create the directories if needed:

```bash
mkdir -p /home/steam/jtwp-collector
cd /home/steam/jtwp-collector
```

Create the virtual environment:

```bash
python3 -m venv venv
```

Activate it:

```bash
source /home/steam/jtwp-collector/venv/bin/activate
```

Install the Python requirements from inside the project directory:

```bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-
pip install -r requirements.txt
```

---

# 3. Configuration

Copy the example configuration:

```bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-
cp config.example.json config.json
nano config.json
```

A simplified configuration looks like:

```json
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
    "include_invalid_user_events": false,
    "webhook_timeout_seconds": 8,
    "webhook_retries": 2
  }
}
```

## Server IDs

You do not need to manually assign a server ID.

The collector derives it from the path:

```text
/home/steam/pavlovserver/Pavlov/Saved/Logs/
→ pavlovserver

/home/steam/pavlovserver0/Pavlov/Saved/Logs/
→ pavlovserver0

/home/steam/pavlovserver1/Pavlov/Saved/Logs/
→ pavlovserver1
```

## Stats path

The stats directory is derived from the same Pavlov `Saved` directory.

For example:

```text
Logs:
/home/steam/pavlovserver1/Pavlov/Saved/Logs/

Stats:
/home/steam/pavlovserver1/Pavlov/Saved/Stats/
```

## Platform detection

Use:

```json
"platform": "auto"
```

The collector looks for:

```text
PavlovLog: SHACK SERVER BUILD
```

If found, the server is SHACK. Otherwise it is treated as PCVR.

You can also explicitly configure:

```json
"platform": "SHACK"
```

or:

```json
"platform": "PCVR"
```

---

# 4. Item List

The known Pavlov item list is stored separately in:

```text
items.json
```

This keeps the large item list out of `config.json`.

Example:

```json
{
  "items": [
    "ak47",
    "m16",
    "mp5",
    "awp"
  ]
}
```

Custom guns found in the logs are still recorded automatically, for example:

```text
PavlovLog: Added Gun cak
PavlovLog: Added Gun funnygun5
```

Unknown/custom items can be recorded separately from the built-in item list.

---

# 5. Secrets and API Keys

Do **not** place API keys or webhook URLs in generated player/server JSON files.

Create:

```text
/home/steam/jtwp-collector/Pavlov-Data-Collector-/.env
```

You can start from the example:

```bash
cp .env.example .env
nano .env
```

Example:

```bash
JTWP_IP_HASH_SECRET=YOUR_LONG_RANDOM_SECRET

PROXYCHECK_API_KEY=YOUR_PROXYCHECK_KEY
MODIO_API_KEY=YOUR_MODIO_KEY

JTWP_CONNECTION_WEBHOOK_URL=https://discord.com/api/webhooks/...

JTWP_SECURITY_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Optional separate security webhooks:
# JTWP_SSH_WEBHOOK_URL=https://discord.com/api/webhooks/...
# JTWP_RCON_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Optional ipapi key:
# IPAPI_API_KEY=YOUR_IPAPI_KEY
```

## Generate the IP hashing secret

Generate a strong secret:

```bash
openssl rand -hex 32
```

Put the result in:

```bash
JTWP_IP_HASH_SECRET=PASTE_RESULT_HERE
```

> [!CAUTION]
> **Do not change `JTWP_IP_HASH_SECRET` after collecting data.**
>
> The same secret is required to generate the same IP hash. Changing it will break correlation between historical player, RCON, and SSH records.

Protect the `.env` file:

```bash
chmod 600 /home/steam/jtwp-collector/Pavlov-Data-Collector-/.env
```

---

# 6. IP Privacy and Enrichment

Raw player IP addresses are not stored in normal player/server records.

Normal records use:

```text
HMAC-SHA256(IP, JTWP_IP_HASH_SECRET)
```

Raw player IP information is isolated under the private data directory.

The collector uses:

1. **ProxyCheck** — primary
2. **ipapi** — fallback

The normalized network information can include:

```json
{
  "organisation": "Example ISP",
  "country_code": "US",
  "proxy": false,
  "vpn": false,
  "hosting": false,
  "tor": false
}
```

The raw provider responses are normalized so the rest of the collector does not need to care which provider answered.

---

# 7. Initial Collector Run

Load the environment:

```bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-

set -a
source .env
set +a
```

Activate Python:

```bash
source /home/steam/jtwp-collector/venv/bin/activate
```

Run:

```bash
python3 collector.py -c config.json
```

The first run can process all configured historical logs.

---

# 8. Log Archiving

For each configured server, the collector handles Pavlov logs and Stats logs.

## Pavlov logs

Historical logs:

```text
Pavlov-backup-2026.08.02-21.58.44.log
Pavlov-backup-2026.08.05-17.28.30.log
```

Active log:

```text
Pavlov.log
```

When active-log rotation is enabled, the collector:

1. moves/copies historical backups into the configured archive;
2. copies `Pavlov.log` into the archive with a timestamped backup name;
3. truncates the original `Pavlov.log` so the server can continue writing to it.

## Stats logs

Historical stats:

```text
Stats-2026.08.08-00.28.29.log
```

Active stats:

```text
Stats.log
```

The same archive/truncate process is used for active Stats data.

A processing index prevents the same archived content from being processed repeatedly.

---

# 9. Stats Parsing

Pavlov Stats logs contain timestamp-prefixed JSON objects rather than one normal JSON document.

The collector reconstructs these records and processes objects such as:

```json
{
  "KillData": {
    "Killer": "PlayerA",
    "Killed": "PlayerB",
    "KilledBy": "ak47",
    "Headshot": true
  }
}
```

and:

```json
{
  "allStats": [
    {
      "uniqueId": "PlayerA",
      "productId": "00024a4843dc40b8950029db3cd7b111",
      "playerName": "PlayerA",
      "teamId": 0,
      "stats": [
        {
          "statType": "Kill",
          "amount": 20
        }
      ]
    }
  ],
  "MapLabel": "UGC2815354",
  "GameMode": "TDM",
  "MatchDuration": 3590,
  "PlayerCount": 19,
  "bTeams": true,
  "Team0Score": 1608,
  "Team1Score": 1448
}
```

Round `allStats` records are also saved separately so individual matches can be inspected later.

---

# 10. Player Identity

The primary player key is:

```text
productId
```

Example:

```text
00024a4843dc40b8950029db3cd7b111
```

Each product ID receives its own directory:

```text
players/records/{productId}/
```

The collector also maintains lookup indexes for:

- player name;
- unique ID;
- product ID;
- hashed IP.

This allows a player who changes names to remain connected to the same permanent product ID.

---

# 11. Player Statistics

The player statistics system can maintain:

```text
Kills
Deaths
Headshots
Suicides
Teamkills
Times Connected
Matches
Favorite Weapon
```

Kills by weapon are stored so the favorite weapon can be determined from the highest recorded kill count.

## Teamkill classification

Some older `KillData` records do not contain team IDs.

Those kills cannot be positively classified as enemy kills or teamkills.

With:

```json
"count_unverified_player_kills": true
```

they are counted as kills but also marked as having an unverified team relationship.

Set:

```json
"count_unverified_player_kills": false
```

if you only want kills where the collector can verify the killer and victim were on different teams.

---

# 12. Player Connection Data

The collector can correlate connection lines such as:

```text
AddClientConnection
Login request
Join request
Join succeeded
UChannel::Close
```

Connection data can provide:

- player name;
- product ID;
- unique ID;
- IP hash;
- client platform;
- handedness;
- VStock;
- player height;
- connection/disconnection timestamps.

When a value changes, the player's change history can record the previous and new value.

---

# 13. Admin Detection

Admin IDs are loaded globally from the configured Pavlov servers.

Sources include:

```text
/home/steam/{serverID}/Pavlov/Saved/Config/mods.txt
```

and:

```text
/home/steam/{serverID}/Pavlov/Saved/Config/ModSave/RconPlus/MenuAccesscfg.txt
```

Admins are treated as **global**.

If an ID is an admin on one configured server, the player is considered an admin across the collected server network.

Player records contain:

```json
{
  "admin": true
}
```

or:

```json
{
  "admin": false
}
```

---

# 14. Ban Collection

Each server's blacklist is read from:

```text
/home/steam/{serverID}/Pavlov/Saved/Config/blacklist.txt
```

Unique banned IDs are stored per server.

Current bans and ban changes are kept separately so the collector can track additions/removals over time.

---

# 15. RCON Collection

The collector recognizes successful authentication:

```text
Rcon: User authenticated 96.28.65.210:52194
```

commands:

```text
Rcon: InspectAll
```

disconnects:

```text
Rcon: Client Disconnect 96.28.65.210:52194
```

and failed authentication:

```text
Rcon: User Failed authentication! Closing connection to client 115.231.78.3:56785
```

RCON data is stored per server.

Where possible, commands are associated with the currently authenticated RCON connection.

Raw RCON IPs are not exposed in normal logs; the stable HMAC IP hash is used.

---

# 16. RCON ↔ Player Correlation

When a player connection is observed, its IP is hashed using the same secret used for RCON hosts.

The collector maintains:

```text
players/index/by_ip_hash.json
```

Conceptually:

```json
{
  "HASHED_IP": [
    "0002955012464183890448e567280576"
  ]
}
```

A failed RCON attempt can therefore be compared with known player IP hashes.

A security alert may report:

```text
Players Seen On Same IP:
• ExamplePlayer (0002955012464183890448e567280576)
```

Again, this is a **correlation**, not proof of who made the RCON request.

---

# 17. Live Connection and RCON Watcher

`connection_watcher.py` follows each configured live:

```text
Pavlov.log
```

By default:

```json
"start_at_end": true
```

This means starting the watcher does not send webhooks for every old connection already in the log.

When a new player joins, the watcher can:

1. correlate the network connection;
2. resolve the player product ID;
3. update the player record;
4. increment connection count;
5. update player settings;
6. hash/enrich the IP;
7. refresh admin status;
8. refresh ban status;
9. update the IP-hash lookup index;
10. send a Discord webhook.

The same watcher handles live failed RCON authentication alerts.

## Run manually

```bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-

set -a
source .env
set +a

/home/steam/jtwp-collector/venv/bin/python3 connection_watcher.py -c config.json
```

---

# 18. Connection Watcher systemd Service

An example service is included:

```text
jtwp-connection-watcher.service
```

Install it:

```bash
sudo cp jtwp-connection-watcher.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now jtwp-connection-watcher
```

Check status:

```bash
sudo systemctl status jtwp-connection-watcher
```

Follow its logs:

```bash
sudo journalctl -u jtwp-connection-watcher -f
```

The service should use:

```ini
ExecStart=/home/steam/jtwp-collector/venv/bin/python3 /home/steam/jtwp-collector/Pavlov-Data-Collector-/connection_watcher.py -c /home/steam/jtwp-collector/Pavlov-Data-Collector-/config.json
```

---

# 19. SSH Failed-Login Watcher

`ssh_watcher.py` watches the OpenSSH systemd journal for failed authentication.

Recognized activity includes events such as:

```text
Failed password for invalid user admin from 1.2.3.4 port 51234 ssh2
Failed password for root from 1.2.3.4 port 51234 ssh2
Failed publickey for user from 1.2.3.4 port 51234 ssh2
maximum authentication attempts exceeded for invalid user test from 1.2.3.4 port 51234 ssh2
```

Normal SSH output is stored under:

```text
data/global/ssh/
```

including:

```text
events.jsonl
failed_hosts.json
ssh.log
```

Raw SSH source IPs are isolated under:

```text
data/private/ssh_ips.json
```

Failed-host information can include:

- first seen;
- last seen;
- number of attempts;
- attempted usernames;
- source ports;
- organisation;
- country;
- proxy status;
- VPN status;
- hosting status;
- Tor status;
- IP lookup source;
- matching Pavlov players seen on the same IP hash.

---

# 20. Allow the Watcher to Read SSH Logs

The `steam` account must be able to read the systemd journal.

Run:

```bash
sudo usermod -aG systemd-journal steam
```

Then either log out and back in or restart the service/session so the new group membership is applied.

Test journal access:

```bash
sudo -u steam journalctl -u ssh.service -n 10 --no-pager
```

Depending on the Ubuntu/OpenSSH configuration, the service may be named `ssh.service` or `sshd.service`. The watcher configuration supports both.

---

# 21. SSH Watcher systemd Service

Install:

```bash
sudo cp jtwp-ssh-watcher.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now jtwp-ssh-watcher
```

Check it:

```bash
sudo systemctl status jtwp-ssh-watcher
```

Follow its output:

```bash
sudo journalctl -u jtwp-ssh-watcher -f
```

The service should use the actual Python virtual environment:

```ini
ExecStart=/home/steam/jtwp-collector/venv/bin/python3 /home/steam/jtwp-collector/Pavlov-Data-Collector-/ssh_watcher.py -c /home/steam/jtwp-collector/Pavlov-Data-Collector-/config.json
```

---

# 22. Discord Webhooks

## Player connections

Set:

```bash
JTWP_CONNECTION_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

The connection alert can contain player identity, statistics, admin/ban status, and normalized network information.

Raw IP addresses are not sent to Discord.

## Shared security webhook

To send both SSH and failed RCON alerts to one webhook:

```bash
JTWP_SECURITY_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

## Separate SSH/RCON webhooks

You can override the shared security webhook:

```bash
JTWP_SSH_WEBHOOK_URL=https://discord.com/api/webhooks/...
JTWP_RCON_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

If a dedicated URL exists, it is used for that alert type.

---

# 23. Mod.io Maps

Active `MapRotation` entries from `Game.ini` are collected.

Example:

```ini
MapRotation=(MapId="UGC2815354",GameMode="TDM")
```

The `UGC` prefix is removed for the Mod.io API lookup:

```text
UGC2815354
→ 2815354
```

Enriched map information is stored under:

```text
servers/{serverID}/server/maps.json
```

A map can contain:

```json
{
  "UGC2815354": {
    "configured": true,
    "game_modes": [
      "TDM"
    ],
    "modio_id": "2815354",
    "modio": {
      "name": "Example Map",
      "thumb_320x180": "https://...",
      "downloads_today": 25,
      "downloads_total": 50000,
      "summary": "Example map description"
    }
  }
}
```

---

# 24. Mod.io Additional Mods

`Game.ini` entries such as:

```ini
AdditionalMods=UGC3793776
AdditionalMods=UGC6279197
```

are collected and enriched.

They are merged with mods actually observed loading through lines such as:

```text
PavlovLog: ModInitializer Found UGC3978505 path /UGC3978505/...
```

The combined catalog is stored at:

```text
servers/{serverID}/server/mods.json
```

This lets you distinguish:

- mods configured in `Game.ini`;
- mods actually observed loading;
- mods seen from both sources.

The Mod.io cache is shared globally:

```text
global/modio/mods.json
```

---

# 25. Custom Guns and Loot

Custom guns can be detected from:

```text
PavlovLog: Added Gun cak
PavlovLog: Added Gun funny0
```

Loot meshes can be detected from:

```text
PavlovLog: Added Loot Mesh mg42_bipod
```

Failed additions can also be recorded, including lines such as:

```text
PavlovLog: Error: Failed to add item m4_debug it already exists in the list
```

and mod-associated failures such as:

```text
LogTemp: Error: 3395365Failed to addrgw90
```

where the numeric ID can be interpreted as:

```text
UGC3395365
```

---

# 26. HTTP Events

HTTP/network problems can be collected separately from the normal server event stream.

Examples include:

```text
request failed, libcurl error: 28 (Timeout was reached)
invalid HTTP response code received
Retry exhausted
Failed to connect to the backend
EOS_NoConnection
ConnectClientAuthTask Failure
```

These events make it possible to build structured HTTP/network reliability history instead of storing only raw log lines.

---

# 27. Output Structure

The exact contents grow as data is discovered, but the main layout is:

```text
/home/steam/jtwp-collector-data/
│
├── global/
│   ├── admins.json
│   ├── processing_state.json
│   ├── stats_combat_state.json
│   │
│   ├── modio/
│   │   └── mods.json
│   │
│   ├── reference/
│   │   └── unknown_items.json
│   │
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
│   │   ├── by_product_id.json
│   │   └── by_ip_hash.json
│   │
│   └── records/
│       └── {productId}/
│           ├── player.json
│           ├── names.json
│           ├── stats.json
│           ├── weapons.json
│           ├── ips.json
│           ├── matches.jsonl
│           ├── kills.jsonl
│           ├── deaths.jsonl
│           ├── connections.jsonl
│           └── changes.jsonl
│
└── servers/
    └── {serverID}/
        ├── server.json
        ├── game_ini.json
        │
        ├── server/
        │   ├── maps.json
        │   └── mods.json
        │
        ├── rounds/
        │   └── *.json
        │
        ├── bans/
        │   ├── current_bans.json
        │   └── changes.jsonl
        │
        ├── rcon/
        │   ├── events.jsonl
        │   ├── known_hosts.json
        │   └── failed_hosts.json
        │
        └── http/
            └── ...
```

---

# 28. Useful Commands

## Validate the config

```bash
python3 -m json.tool config.json >/dev/null && echo "config.json OK"
```

## Validate generated JSON

```bash
python3 -m json.tool /home/steam/jtwp-collector-data/global/ssh/failed_hosts.json
```

## Check both watcher services

```bash
sudo systemctl status jtwp-connection-watcher jtwp-ssh-watcher
```

## Follow connection/RCON watcher

```bash
sudo journalctl -u jtwp-connection-watcher -f
```

## Follow SSH watcher

```bash
sudo journalctl -u jtwp-ssh-watcher -f
```

## Restart both watchers

```bash
sudo systemctl restart jtwp-connection-watcher jtwp-ssh-watcher
```

## Check running Python processes

```bash
ps aux | grep -E '[c]onnection_watcher.py|[s]sh_watcher.py'
```

## Inspect failed SSH hosts

```bash
python3 -m json.tool /home/steam/jtwp-collector-data/global/ssh/failed_hosts.json
```

## Inspect the IP-hash player index

```bash
python3 -m json.tool /home/steam/jtwp-collector-data/players/index/by_ip_hash.json
```

## Inspect a server's maps

```bash
python3 -m json.tool /home/steam/jtwp-collector-data/servers/pavlovserver/server/maps.json
```

## Inspect a server's mods

```bash
python3 -m json.tool /home/steam/jtwp-collector-data/servers/pavlovserver/server/mods.json
```

---

# 29. Troubleshooting

## `JTWP_IP_HASH_SECRET is required`

The environment was not loaded.

For a manual run:

```bash
set -a
source .env
set +a
```

Verify:

```bash
test -n "$JTWP_IP_HASH_SECRET" && echo "secret loaded"
```

Do not print the secret itself.

---

## systemd says Python does not exist

Check the actual interpreter:

```bash
ls -l /home/steam/jtwp-collector/venv/bin/python3
```

The service must use:

```text
/home/steam/jtwp-collector/venv/bin/python3
```

not:

```text
/home/steam/jtwp-collector/Pavlov-Data-Collector-/venv/bin/python
```

After changing a service:

```bash
sudo systemctl daemon-reload
sudo systemctl restart jtwp-ssh-watcher
```

or:

```bash
sudo systemctl restart jtwp-connection-watcher
```

---

## Service still uses an old `ExecStart`

Inspect the installed unit:

```bash
sudo systemctl cat jtwp-ssh-watcher
```

or:

```bash
sudo systemctl cat jtwp-connection-watcher
```

Then reload:

```bash
sudo systemctl daemon-reload
sudo systemctl restart jtwp-ssh-watcher
```

---

## SSH watcher creates no files

First check whether it is running:

```bash
ps aux | grep '[s]sh_watcher.py'
```

Then check the service:

```bash
sudo systemctl status jtwp-ssh-watcher
```

Follow its log:

```bash
sudo journalctl -u jtwp-ssh-watcher -f
```

Confirm `steam` can read SSH journal entries:

```bash
sudo -u steam journalctl -u ssh.service -n 20 --no-pager
```

If permission is denied:

```bash
sudo usermod -aG systemd-journal steam
```

Then restart the session/service.

---

## Webhook does not post

Confirm the URL exists in the service environment file:

```bash
grep 'WEBHOOK' /home/steam/jtwp-collector/Pavlov-Data-Collector-/.env
```

Then restart the appropriate service:

```bash
sudo systemctl restart jtwp-connection-watcher
sudo systemctl restart jtwp-ssh-watcher
```

Watch for webhook errors:

```bash
sudo journalctl -u jtwp-connection-watcher -f
```

or:

```bash
sudo journalctl -u jtwp-ssh-watcher -f
```

---

## Mod.io information is missing

Confirm:

```bash
grep '^MODIO_API_KEY=' /home/steam/jtwp-collector/Pavlov-Data-Collector-/.env
```

Also verify that the map/mod actually uses a `UGC` ID.

Built-in Pavlov maps do not have a Mod.io UGC ID to query.

---

# 30. Recommended Services

For normal operation, the system can be thought of as three pieces:

| Component | Purpose |
|---|---|
| `collector.py` | Historical parsing, archive processing, server/player/stat collection |
| `connection_watcher.py` | Live Pavlov connections and failed RCON alerts |
| `ssh_watcher.py` | Live failed SSH authentication monitoring |

The watchers are intended to remain running continuously through systemd.

The historical collector can be run whenever you want to process/archive accumulated logs, or placed on its own schedule if desired.

---

# 31. Privacy Notes

The collector intentionally separates raw network identifiers from normal records.

### Normal data

Uses stable HMAC-SHA256 IP hashes for:

- player IP history;
- RCON hosts;
- SSH failed hosts;
- cross-system correlation.

### Private data

Raw IPs are isolated under:

```text
data/private/
```

Do not expose this directory through a public web server, Discord bot, or public API.

### Discord

Security and connection webhooks should contain only the hashed IP and normalized network information—not the raw IP.

---

# 32. Backup Recommendations

The most important data to back up is:

```text
/home/steam/jtwp-collector-data/
/home/steam/jtwp-log-archive/
/home/steam/jtwp-collector/Pavlov-Data-Collector-/.env
```

The `.env` file is especially important because losing `JTWP_IP_HASH_SECRET` means new IP hashes can no longer be correlated with the historical hashes.

Store backups of `.env` securely.

---

# JTWP

Built for long-term Pavlov server logging, statistics, player history, administration, and security monitoring.
