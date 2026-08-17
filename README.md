# JTWP Pavlov Collector

## Install

```bash
sudo apt update
sudo apt install python3 python3-venv -y

mkdir -p /home/steam/jtwp-collector
cd /home/steam/jtwp-collector

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Copy `collector.py` and `config.example.json` into that directory:

```bash
cp config.example.json config.json
nano config.json
```

## Secrets

Do **not** put API keys into generated JSON.

```bash
export JTWP_IP_HASH_SECRET="$(openssl rand -hex 32)"
export PROXYCHECK_API_KEY="YOUR_PROXYCHECK_KEY"
export MODIO_API_KEY="YOUR_MODIO_KEY"

# Optional if you have a paid/authenticated ipapi.is key:
export IPAPI_API_KEY="YOUR_IPAPI_KEY"
```

Keep `JTWP_IP_HASH_SECRET` unchanged. Changing it changes every IP hash and breaks historical IP correlation.

For a systemd service, put secrets in a root-readable EnvironmentFile rather than directly in the unit.

## Run

```bash
source /home/steam/jtwp-collector/venv/bin/activate
python3 collector.py -c config.json
```

## Important behavior

- `Pavlov-backup-*.log` files are moved into the archive.
- Active `Pavlov.log` is copied to the archive and then truncated.
- `Stats-*.log` files are moved into the archive.
- Active `Stats.log` is copied to the archive and then truncated.
- A SHA-256 processing index prevents the same archived content from being processed twice.
- Player folders use `productId`.
- Raw player IP addresses only live in `private/player_ips.json` and `private/ip_lookup_cache.json`.
- Everything else uses a HMAC-SHA256 IP hash.
- ProxyCheck is primary; ipapi.is is fallback.
- Mod.io responses are cached.
- `#MapRotation` and other `#`/`;` commented Game.ini lines are ignored.

## Kill classification note

Older `KillData` can omit team IDs. Such player-vs-player events are marked
`normal_unverified_team_relation`. By default they count toward kills so historical
data is useful, while `kills_unverified_team_relation` shows how many could not be
verified as enemy-vs-enemy. Set:

```json
"count_unverified_player_kills": false
```

if you only want kills with a provable non-team relationship counted.

## Output overview

```text
data/
├── global/
│   ├── admins.json
│   ├── processing_state.json
│   ├── stats_combat_state.json
│   ├── modio/mods.json
│   └── reference/unknown_items.json
├── private/
│   ├── player_ips.json
│   └── ip_lookup_cache.json
├── players/
│   ├── index/
│   │   ├── by_name.json
│   │   ├── by_unique_id.json
│   │   └── by_product_id.json
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
└── servers/{serverID}/
    ├── server.json
    ├── game_ini.json
    ├── rounds/*.json
    ├── bans/current_bans.json
    ├── bans/changes.jsonl
    ├── rcon/
    ├── http/
    └── server/
```

## Item list

The built-in Pavlov item list is stored separately in `items.json` next to
`collector.py`. The main `config.json` no longer needs a `base_items` section.

To add or remove a known base item, edit `items.json`:

```json
{
  "items": [
    "ak47",
    "m16",
    "mp5"
  ]
}
```

Items observed through `PavlovLog: Added Gun ...` are still detected as custom guns.


## Live connection watcher

`connection_watcher.py` tails each configured live `Pavlov.log`. It starts at the
end of the file by default, so existing historical joins do not fire webhooks.

On each new successful join it:
- correlates AddClientConnection/Login request/Join request/Join succeeded;
- derives productId from `userId: NULL:<32 hex>` when available;
- updates the productId player folder;
- increments times connected;
- updates height, handedness, VStock and client platform;
- hashes and enriches the IP;
- refreshes admin and ban status;
- correlates the IP hash with known RCON hosts;
- sends the webhook without exposing the raw IP.

Set these in `.env`:

```bash
JTWP_IP_HASH_SECRET=...
PROXYCHECK_API_KEY=...
MODIO_API_KEY=...
JTWP_CONNECTION_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

Run manually:

```bash
source venv/bin/activate
set -a
source .env
set +a
python3 connection_watcher.py -c config.json
```

For systemd, copy `jtwp-connection-watcher.service` to `/etc/systemd/system/`,
then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now jtwp-connection-watcher
sudo journalctl -u jtwp-connection-watcher -f
```

`webhook_mode` can be `discord` (default Discord embed) or `generic` (raw JSON event).


## SSH failed-login watcher

`ssh_watcher.py` follows the OpenSSH systemd journal and records failed SSH
authentication attempts.

Normal data uses the same HMAC-SHA256 IP hash as player/RCON data:

```text
data/global/ssh/
├── events.jsonl
├── failed_hosts.json
└── ssh.log
```

Raw SSH source IPs are isolated to:

```text
data/private/ssh_ips.json
```

Each failed host can accumulate:
- first/last seen;
- total failed attempts;
- usernames attempted and counts;
- recent source ports;
- ISP/organisation;
- country;
- hosting/proxy/VPN/Tor status;
- ProxyCheck/ipapi lookup source.

The `steam` user must be allowed to read the systemd journal. On Ubuntu:

```bash
sudo usermod -aG systemd-journal steam
```

Then restart the service/session so the new group membership applies.

Install the included service:

```bash
sudo cp jtwp-ssh-watcher.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now jtwp-ssh-watcher
sudo journalctl -u jtwp-ssh-watcher -f
```

By default `Invalid user ...` lines are not counted separately because OpenSSH
often emits one immediately before a corresponding `Failed password ...`, which
would otherwise double-count a single authentication attempt. Set
`include_invalid_user_events` to `true` if you want those as separate events.


## Security correlation and webhooks

The collector maintains `players/index/by_ip_hash.json`, mapping each stable
HMAC-SHA256 IP hash to player product IDs seen on that network.

SSH and failed-RCON events automatically check this index. A match means the
same public IP was observed; it does not prove the player made the attempt.

Use one shared Discord security webhook:

```bash
JTWP_SECURITY_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

or separate URLs:

```bash
JTWP_SSH_WEBHOOK_URL=https://discord.com/api/webhooks/...
JTWP_RCON_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

Raw IPs are never posted to Discord.

## Mod.io metadata for maps and mods

Active Game.ini map rotation entries are enriched and written to:

```text
servers/{serverID}/server/maps.json
```

AdditionalMods entries are merged with log-discovered ModInitializer entries in:

```text
servers/{serverID}/server/mods.json
```

For UGC entries, Mod.io metadata includes name, `thumb_320x180`,
`downloads_today`, `downloads_total`, and summary. Results reuse the global
Mod.io cache.


# 🎛️ RCON File Trigger Bridge

The collector now includes a file-based RCON bridge for Pavlov ModKit workflows.

The ModKit can create JSON files inside each server's ModSave directory:

```text
/home/steam/pavlovserver/Pavlov/Saved/Config/ModSave/JTWP/Rcon
/home/steam/pavlovserver0/Pavlov/Saved/Config/ModSave/JTWP/Rcon
/home/steam/pavlovserver1/Pavlov/Saved/Config/ModSave/JTWP/Rcon
```

The folder determines the target server.

## Request/response naming

Create:

```text
IN-serverinfo.json
```

The watcher:

1. detects the `IN-*.json` file;
2. removes any stale matching `OUT-*.json`;
3. validates the command against `rcon_commands.json`;
4. validates required arguments;
5. sends the RCON command;
6. atomically writes the fresh `OUT-*.json`;
7. removes the `IN-*.json`.

Example output:

```text
OUT-serverinfo.json
```

A successful response contains:

```json
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

Errors are also returned through the matching OUT file:

```json
{
  "success": false,
  "error": "Missing required field: unique_id"
}
```

## Commands with arguments

`IN-setbotsenabled.json`:

```json
{
  "enabled": true
}
```

`IN-setmaxplayers.json`:

```json
{
  "amount": 10
}
```

`IN-giveitem.json`:

```json
{
  "unique_id": "12345678901234567",
  "item_id": "syringe"
}
```

`IN-switchmap.json`:

```json
{
  "map_id": "datacenter",
  "game_mode": "SND"
}
```

## Reference files

The bridge uses:

```text
rcon_commands.json
game_modes.json
default_maps.json
limited_ammo_types.json
```

All commands currently listed in `rcon_commands.json` are enabled.

## RCON configuration

Each server in `config.json` needs an RCON block:

```json
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

RCON passwords belong in `.env`:

```bash
PAVLOVSERVER_RCON_PASSWORD=YOUR_PASSWORD
PAVLOVSERVER0_RCON_PASSWORD=YOUR_PASSWORD
PAVLOVSERVER1_RCON_PASSWORD=YOUR_PASSWORD
```

## Install dependencies

```bash
source /home/steam/jtwp-collector/venv/bin/activate
pip install -r requirements.txt
```

## Install the systemd service

```bash
sudo install -m 644 jtwp-rcon-trigger-watcher.service /etc/systemd/system/jtwp-rcon-trigger-watcher.service
sudo systemctl daemon-reload
sudo systemctl enable --now jtwp-rcon-trigger-watcher
```

Check it:

```bash
sudo systemctl status jtwp-rcon-trigger-watcher --no-pager
```

Follow it:

```bash
sudo journalctl -u jtwp-rcon-trigger-watcher -f
```

Or use the included installer:

```bash
sudo ./scripts/install-rcon-bridge.sh
```
