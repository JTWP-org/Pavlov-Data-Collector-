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
