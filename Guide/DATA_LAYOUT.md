# 🗂️ JTWP Collector Data Layout

This guide explains the normal persistent data tree used by the JTWP Pavlov
Data Collector.

Primary root:

```text
/home/steam/jtwp-collector-data
```

The exact files present depend on which features are enabled.

## 🌳 High-Level Layout

```text
jtwp-collector-data/
├── global/
│   ├── modio/
│   ├── network/
│   │   └── ddos/
│   ├── pavlov_api/
│   └── ssh/
├── players/
│   ├── index/
│   └── records/
├── private/
└── servers/
```

## 👤 `players/`

Persistent player identity/statistics are organized primarily by Product ID.

Typical layout:

```text
players/
├── index/
│   ├── by_name.json
│   ├── by_unique_id.json
│   └── ...
└── records/
    └── PRODUCT_ID/
        ├── player.json
        ├── ips.json
        ├── stats.json
        ├── guns.json
        ├── kills.jsonl
        ├── deaths.jsonl
        ├── connections.jsonl
        └── changes.jsonl
```

Not every record necessarily has every file.

### `players/index/`

Lookup/index files are derived navigation structures that map values such as
names or IDs to player records.

### `players/records/PRODUCT_ID/`

This is the persistent per-player record.

Treat these files as primary collector data, not temporary output.

## 🔐 `private/`

```text
private/
```

is for private/sensitive collector state such as raw-IP mappings or lookup
caches.

Examples used by the project include:

```text
private/ip_lookup_cache.json
private/ssh_ips.json
```

Recommended permissions:

```bash
chmod 700 /home/steam/jtwp-collector-data/private
```

Do not publish the contents of this folder.

## 🔐 `global/ssh/`

SSH watcher output normally includes:

```text
global/ssh/
├── events.jsonl
├── failed_hosts.json
├── ssh.log
├── discord_status.json
└── connection_correlations.json
```

`failed_hosts.json` uses stable IP hashes in normal/public-facing records.

Raw SSH source IP state belongs under `private/`, not here.

## 🌐 `global/network/ddos/`

The DDoS/network watcher writes:

```text
global/network/ddos/
├── network_stats.json
├── events.jsonl
├── last_event.json
└── hosts.json
```

Normal DDoS host records use HMAC IP hashes.

A shared hash can correlate a source with player/RCON/SSH records, but a shared
hash by itself does **not** prove that a player generated the observed traffic.

## 🌍 `global/pavlov_api/`

Public Pavlov-server API snapshots are stored under:

```text
global/pavlov_api/
```

Common outputs can include:

```text
servers.json
network_hosts.json
network_hosts_cache.json
summary.json
last_update.json
index/
```

This directory is refreshed by `update_pavlov_api.py` or by the configured
Pavlov API trigger.

The live-server scripts under `scripts/servers/` consume this data.

## 🗺️ `global/modio/`

Mod.io enrichment/cache data is stored below:

```text
global/modio/
```

A commonly used cache is:

```text
global/modio/mods.json
```

This cache can be recreated by future API lookups, although rebuilding it may
require working API credentials and network access.

## 🖥️ `servers/SERVER_ID/`

Each Pavlov server can have its own data tree:

```text
servers/
└── SERVER_ID/
    ├── rcon/
    ├── server/
    └── ...
```

Examples:

```text
servers/pavlovserver/
servers/pavlovserver0/
servers/pavlovserver1/
```

### Server RCON records

Depending on the enabled collectors/watchers:

```text
servers/SERVER_ID/rcon/
├── known_hosts.json
├── failed_hosts.json
└── ...
```

### Server service/maintenance metadata

The mod-cleanup/service-discovery tools can write:

```text
servers/SERVER_ID/server/service.json
servers/SERVER_ID/server/maintenance.jsonl
```

## 📚 Logs vs Collector Data vs Archive

These are different things.

### Live Pavlov logs

Examples:

```text
/home/steam/pavlovserver/Pavlov/Saved/Logs/
/home/steam/pavlovserver0/Pavlov/Saved/Logs/
/home/steam/pavlovserver1/Pavlov/Saved/Logs/
```

### Collector database

```text
/home/steam/jtwp-collector-data
```

### Collector/Pavlov log archive

Configured by:

```json
"archive_path": "/home/steam/jtwp-log-archive"
```

Historical archive paths can also be configured, for example:

```json
"old_archive_paths": [
  "/home/steam/logs"
]
```

Moving logs to the archive does not make the persistent collector database a
backup. Back up `/home/steam/jtwp-collector-data` separately.

## 🔄 Rebuildable vs Important-to-Preserve

### Generally important to preserve

```text
players/records/
servers/
global/ssh/
global/network/ddos/
private/
```

and your stable `.env` value:

```text
JTWP_IP_HASH_SECRET
```

### Often rebuildable/refreshable

Some indexes and API caches/snapshots can be regenerated, depending on the
source data and APIs still being available.

Examples include portions of:

```text
players/index/
global/pavlov_api/
global/modio/
```

Do not delete anything solely because it appears rebuildable unless you know
which component recreates it.

## 🧹 What `clear-data.sh` Does

The maintenance script removes the contents of:

```text
/home/steam/jtwp-collector-data
```

and recreates at least:

```text
global/
private/
players/records/
players/index/
servers/
```

It restores ownership to `steam:steam` and makes `private/` mode `700`.

The noninteractive form is:

```bash
sudo scripts/clear-data.sh --yes
```

That command is destructive.

## 🔎 Inspect the Data Tree

Size:

```bash
du -sh /home/steam/jtwp-collector-data
```

Largest top-level areas:

```bash
du -h --max-depth=2 /home/steam/jtwp-collector-data \
    2>/dev/null | sort -hr | head -40
```

File count:

```bash
find /home/steam/jtwp-collector-data -type f | wc -l
```

Find a full IP hash recursively:

```bash
grep -Rni \
    --include='*.json' \
    'FULL_IP_HASH' \
    /home/steam/jtwp-collector-data
```

Find a Product ID:

```bash
grep -Rni \
    'PRODUCT_ID' \
    /home/steam/jtwp-collector-data/players
```

## 🔐 Privacy Boundary

The normal design is:

```text
raw IP
  ↓
private collector state
  ↓
HMAC-SHA256 using JTWP_IP_HASH_SECRET
  ↓
normal player / SSH / RCON / network records
```

Keep raw-IP files and the HMAC secret private.
