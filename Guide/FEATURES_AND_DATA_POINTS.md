# 🎮 JTWP Pavlov Data Collector --- Complete Feature & Data Point List

> A detailed inventory of the data the JTWP Pavlov Data Collector can
> collect, derive, enrich, correlate, monitor, and store.

------------------------------------------------------------------------

## 👤 Player Identity

Each player is primarily keyed by **`productId`**, allowing the same
player record to remain linked even when names or other session
information changes.

Data points include:

-   🆔 `productId` --- primary persistent player key
-   🪪 `uniqueId`
-   🎮 Steam ID / platform-specific unique identifier when available
-   👤 Current player name
-   📝 Previous player names / name history
-   🕒 First-seen information
-   🕒 Last-seen information
-   🔎 Name → ProductID index
-   🔎 UniqueID → ProductID index
-   🔎 ProductID lookup index
-   🌐 IP-hash → ProductID index

------------------------------------------------------------------------

## 🎯 Player Combat Statistics

Persistent combat statistics can include:

-   💀 Total kills
-   ☠️ Total deaths
-   🎯 Total headshots
-   💣 Total suicides
-   🔴 Total teamkills
-   🤖 Bot kills
-   ⚠️ Kills with an unverified team relationship
-   🔫 Total weapon kills
-   🏆 Favorite weapon
-   🔢 Favorite-weapon kill count
-   🎮 Matches played
-   🔌 Times connected

Older kill records that do not contain enough team information can
optionally still count toward kills while being separately marked as
having an unverified team relationship.

------------------------------------------------------------------------

## 🔫 Weapon Statistics

Weapon usage is tracked per player.

For each weapon, the collector can store:

-   🔫 Weapon/item name
-   💀 Kills with that weapon
-   🎯 Headshots with that weapon
-   📥 Source of the weapon statistic
-   🔢 Total weapon kills
-   🏆 Favorite weapon

The favorite weapon is determined from the weapon with the highest
recorded kill count.

------------------------------------------------------------------------

## 💥 Individual Kill / Death Events

Kill records can contain:

-   🕒 Timestamp
-   🆔 Killer identifier
-   🆔 Victim identifier
-   🔵 Killer team ID
-   🔴 Victim team ID
-   🔫 Weapon / `KilledBy`
-   🎯 Headshot state
-   🤝 Enemy-kill/team relationship classification
-   🔴 Teamkill classification
-   💀 Suicide classification
-   ⚠️ Unverified-team classification
-   🎮 Associated server
-   🗺️ Match/round context when available

Player directories can maintain separate:

-   `kills.jsonl`
-   `deaths.jsonl`

------------------------------------------------------------------------

## 🔌 Player Connection Data

The collector recognizes and correlates connection activity such as:

-   `AddClientConnection`
-   `Login request`
-   `Join request`
-   `Join succeeded`
-   `UChannel::Close`

Connection-related data can include:

-   🕒 Connection timestamp
-   🕒 Disconnection timestamp
-   👤 Player name
-   🆔 Product ID
-   🪪 Unique ID
-   🌐 Stable IP hash
-   🎮 Client platform
-   ✋ Right-handed setting
-   🦾 VStock setting
-   📏 Player height
-   🖥️ Server ID
-   🌎 Network enrichment
-   🔐 Admin state
-   🚫 Ban state

Connection events can be stored in `connections.jsonl`.

------------------------------------------------------------------------

## ⚙️ Player Settings & State

Observed player settings can include:

-   ✋ Right-handed / handedness
-   🦾 VStock enabled/disabled
-   📏 Player height
-   🎮 Client platform
-   🛡️ Admin status
-   🚫 Banned status

Changes can be written to player change history so old and new values
can be compared.

------------------------------------------------------------------------

## 📝 Player Change History

The collector can track changes over time, including:

-   👤 Player-name changes
-   🌐 IP-hash changes
-   🏢 Network organisation changes
-   🌎 Country changes
-   🕵️ Proxy-status changes
-   🔐 VPN-status changes
-   🖥️ Hosting-status changes
-   🧅 Tor-status changes
-   ✋ Handedness changes
-   🦾 VStock changes
-   📏 Height changes
-   🎮 Platform changes
-   🛡️ Admin-status changes
-   🚫 Ban-status changes

These historical changes can be stored in `changes.jsonl`.

------------------------------------------------------------------------

## 🌐 Player Network / IP Data

Normal player records do **not** need to expose raw IP addresses.

The collector uses a stable:

`HMAC-SHA256(IP, JTWP_IP_HASH_SECRET)`

Normal network data can include:

-   🔐 Current IP hash
-   🔢 Number of known IPs
-   📚 Historical IP hashes
-   🏢 Organisation / ISP
-   🌎 Country code
-   🕵️ Proxy status
-   🔐 VPN status
-   🖥️ Hosting/datacenter status
-   🧅 Tor status
-   📡 Network type when available
-   🔎 IP-enrichment source/provider

Raw player IP information is isolated in the private dataset rather than
normal public-facing player records.

------------------------------------------------------------------------

## 🔒 Raw-IP Privacy

The collector separates raw IP information from normal records.

Privacy features include:

-   🔐 HMAC-SHA256 identifiers in normal datasets
-   🗄️ Raw player IPs isolated under private storage
-   🗄️ Raw SSH IPs isolated under private storage
-   🧠 DDoS source IPs used in memory for hashing/correlation
-   🚫 DDoS event records do not persist raw source IPs
-   🔗 The same hash secret allows player/RCON/SSH/network correlation
    without exposing the raw address in normal records

The hashing secret must remain stable or historical hashes will no
longer correlate.

------------------------------------------------------------------------

## 🌎 IP Intelligence / Enrichment

Network enrichment can include:

-   🏢 Provider / organisation
-   🌎 Country / country code
-   📡 Network type
-   🕵️ Proxy detection
-   🔐 VPN detection
-   🖥️ Hosting/datacenter detection
-   🧅 Tor detection
-   ⚠️ Risk/confidence information when supplied by the lookup provider
-   🔎 Lookup provider/source

The collector can use ProxyCheck as the primary provider with ipapi as a
fallback and can cache lookup results to reduce API usage.

------------------------------------------------------------------------

## 🖥️ Pavlov Server Identity & Configuration

For each configured server, the collector can maintain:

-   🆔 Server ID derived from its path
-   📁 Server log path
-   📁 Stats path
-   🎮 Platform
    -   PCVR
    -   SHACK
-   🏷️ Server name
-   ⚡ Tick rate
-   🗺️ Active map rotation
-   🧩 Additional mods
-   🔌 RCON configuration
-   🔌 RCON port
-   🖥️ Server path
-   📜 Game.ini-derived configuration
-   🚫 Blacklist data
-   🛡️ Admin configuration

------------------------------------------------------------------------

## ⚙️ systemd Service Information

Where service discovery is enabled, server/service records can include:

-   ⚙️ systemd service name
-   📁 Working directory
-   ▶️ `ExecStart`
-   📄 Unit/fragment path
-   🟢 Active state
-   ⚡ Enabled/disabled state
-   🕒 Detection timestamp

Useful commands can also be generated for:

-   📊 Status
-   ▶️ Start
-   🛑 Stop
-   🔄 Restart
-   ⚡ Enable
-   ⛔ Disable
-   ⚡ Enable + start
-   ⛔ Disable + stop
-   📜 Recent logs
-   👀 Live logs
-   ❓ `is-active`
-   ❓ `is-enabled`

------------------------------------------------------------------------

## 🧹 Server Maintenance / Mod Cleanup

The mod-cleanup helper can record:

-   🕒 Maintenance timestamp
-   🧹 Maintenance action type
-   🆔 Server ID
-   ⚙️ Detected service
-   📁 Mods path
-   🔢 Number of removed entries
-   ✅ Success/failure
-   📝 Result message

The cleanup workflow can:

1.  Find the exact service for the configured server path.
2.  Stop the service.
3.  Confirm it stopped.
4.  Remove the contents of `Pavlov/Saved/Mods`.
5.  Restart the service.
6.  Confirm the service returned to active.
7.  Save service metadata and a maintenance log.

------------------------------------------------------------------------

## 🗺️ Map Rotation Data

Active `MapRotation` entries from `Game.ini` can provide:

-   🗺️ Map ID / UGC ID
-   🎮 Game mode
-   ✅ Configured state
-   🔢 Mod.io ID
-   🧩 Mod.io enrichment

Commented map-rotation entries can be ignored.

------------------------------------------------------------------------

## 🧩 Installed / Configured Mod Data

Mods can be discovered from:

-   ⚙️ `AdditionalMods` in `Game.ini`
-   📜 Mods actually observed loading in Pavlov logs

For each mod, the collector can distinguish:

-   ⚙️ Configured in `Game.ini`
-   👀 Observed loading
-   🔗 Seen from both sources
-   🆔 UGC ID
-   🔢 Mod.io ID
-   🧩 Mod.io metadata

A shared Mod.io cache avoids unnecessary repeat lookups.

------------------------------------------------------------------------

## 🌐 Mod.io Metadata

UGC map/mod enrichment can include:

-   🆔 Mod.io ID
-   🏷️ Name
-   🖼️ Thumbnail URL
-   📥 Downloads today
-   📥 Total downloads
-   📝 Summary/description

Additional Mod.io fields may be retained when supported by the
collector/provider response.

------------------------------------------------------------------------

## 🔫 Custom Guns & Items

The server logs can reveal custom content such as:

-   🔫 Added custom gun name
-   📦 Added loot-mesh name
-   ❌ Failed item additions
-   🧩 UGC/mod ID associated with a failed addition
-   ❓ Unknown/custom items not present in the built-in item reference

Unknown items can be stored in a global reference dataset.

------------------------------------------------------------------------

## 🏁 Match / Round Data

Pavlov Stats `allStats` records can provide:

-   🕒 Round/match timestamp
-   🗺️ `MapLabel`
-   🎮 `GameMode`
-   ⏱️ `MatchDuration`
-   👥 `PlayerCount`
-   🔵/🔴 `bTeams`
-   🔵 `Team0Score`
-   🔴 `Team1Score`
-   👤 Player name
-   🆔 Player ProductID
-   🪪 Player UniqueID
-   👥 Player team ID
-   📊 Per-player stat types
-   🔢 Per-player stat amounts

Individual round records can be preserved separately for later
inspection.

------------------------------------------------------------------------

## 🚫 Ban Data

Each server's blacklist can be collected.

Ban information can include:

-   🆔 Banned player/identifier
-   🖥️ Server ID
-   📋 Current ban state
-   ➕ Ban additions
-   ➖ Ban removals
-   🕒 Ban change history

The collector can maintain both `current_bans.json` and a historical
`changes.jsonl`.

------------------------------------------------------------------------

## 🛡️ Admin Data

Admin identifiers can be collected from sources such as:

-   `mods.txt`
-   RconPlus `MenuAccesscfg.txt`

Admin data can include:

-   🆔 Admin identifier
-   🛡️ Current admin state
-   🖥️ Source/configured server

The collector can treat an ID found as an admin on any configured server
as a global admin across the collected server network.

------------------------------------------------------------------------

## 🖥️ RCON Authentication Data

RCON monitoring can detect:

-   ✅ Successful authentication
-   ❌ Failed authentication
-   🔌 Client disconnects
-   🎛️ Commands sent

RCON host records can include:

-   🔐 IP hash
-   🕒 First seen
-   🕒 Last seen
-   ✅ Successful connection count
-   ❌ Failed-attempt count
-   🖥️ Server ID
-   🔎 Known/failed host classification

Raw RCON IPs do not need to be exposed in normal RCON records.

------------------------------------------------------------------------

## 🎛️ RCON Command Data

Where a command can be associated with the authenticated connection,
records can include:

-   🕒 Timestamp
-   🖥️ Server ID
-   🔐 Source host/IP hash
-   🎛️ RCON command
-   🔌 Connection context
-   ✅ Authentication/connection relationship

This makes it possible to review both **what command was sent** and
**which known RCON connection was active** when it was observed.

------------------------------------------------------------------------

## 🔗 RCON ↔ Player Correlation

Because player and RCON addresses use the same HMAC secret, the
collector can determine whether an RCON source hash has also been seen
on a player connection.

Correlation data can include:

-   🔐 IP hash
-   👤 Matching player name
-   🆔 Matching ProductID
-   🪪 Matching UniqueID
-   🛡️ Player admin state
-   🚫 Player ban state

> ⚠️ A shared IP hash is a correlation only. It does **not** prove that
> a particular player sent an RCON command or authentication attempt.

------------------------------------------------------------------------

## 🔑 SSH Security Monitoring

The SSH watcher can recognize:

-   🔑 Failed password authentication
-   👤 Invalid-user attempts
-   🔐 Failed public-key authentication
-   🚨 Maximum authentication attempts exceeded

SSH event/host data can include:

-   🕒 First seen
-   🕒 Last seen
-   🔢 Failed-attempt count
-   👤 Attempted usernames
-   🔌 Source ports
-   🔐 IP hash
-   🏢 Organisation
-   🌎 Country
-   🕵️ Proxy status
-   🔐 VPN status
-   🖥️ Hosting status
-   🧅 Tor status
-   🔎 IP lookup source
-   👤 Pavlov players seen on the same IP hash
-   🚫 Blocked state
-   🕒 Blocked timestamp

------------------------------------------------------------------------

## 🚫 Automatic SSH Blocking

The SSH watcher can automatically block a source after a configured
failure threshold.

The current configuration can control:

-   ✅ Auto-block enabled/disabled
-   🔢 Failed-attempt threshold
-   🛠️ Block command
-   🔐 Whether `sudo` is used
-   🏠 Whether private IPs may be blocked

The existing SSH failure counter is reused rather than maintaining a
second independent attempt counter.

------------------------------------------------------------------------

## 🔗 SSH ↔ Player Correlation

A failed SSH source can be checked against known player IP hashes.

Matching player data can include:

-   👤 Player name
-   🆔 ProductID
-   🪪 UniqueID
-   🛡️ Admin status
-   🚫 Ban status

> ⚠️ Shared IP correlation does not prove the player performed the SSH
> attempt.

------------------------------------------------------------------------

## 🌐 HTTP / Network Reliability Events

The Pavlov logs can be parsed for HTTP/network failures such as:

-   ⏱️ Request timeout
-   ❌ libcurl request failure
-   ⚠️ Invalid HTTP response code
-   🔄 Retry exhausted
-   🌐 Backend connection failure
-   🚫 `EOS_NoConnection`
-   🔐 `ConnectClientAuthTask Failure`

These events allow network/API reliability history to be stored
separately from ordinary server events.

------------------------------------------------------------------------

## 🛡️ DDoS / Network Abuse Monitoring

The DDoS watcher can monitor inbound packet activity using `tcpdump`.

Aggregate data points include:

-   🕒 Timestamp
-   ⏱️ Measurement-window duration
-   📦 Total packets
-   💾 Total bytes
-   ⚡ Packets per second
-   📶 Bytes per second
-   🌐 Number of unique sources
-   🚀 Highest single-source packets per second
-   🎯 Destination ports and packet counts
-   🚨 Trigger reasons

Possible trigger reasons include:

-   🚀 High packet rate
-   💾 High byte rate
-   🌐 High unique-source count
-   🎯 High single-source packet rate

------------------------------------------------------------------------

## 🚨 DDoS Detection Events

When enough configured conditions are met, a possible-DDoS event can
include:

-   🕒 Timestamp
-   🚨 Event type
-   ⚠️ Severity
    -   Medium
    -   High
    -   Critical
-   🔎 Detection-only state
-   🚫 Automatic-blocking state
-   🌐 Capture interface
-   ⏱️ Window duration
-   📦 Packet count
-   💾 Byte count
-   ⚡ Packets per second
-   📶 Bytes per second
-   🌐 Unique-source count
-   🚀 Highest-source packet rate
-   🎯 Destination ports
-   🚨 Trigger reasons
-   👥 Top source records
-   🔒 Privacy metadata

------------------------------------------------------------------------

## 👥 DDoS Source Data

For top sources involved in a triggered event, persisted records can
include:

-   🔐 HMAC IP hash
-   📦 Packet count
-   💾 Byte count
-   ⚡ Packets per second
-   📶 Bytes per second
-   🎯 Destination ports
-   🔗 Correlation information

Raw source IPs are used only in memory for hashing/correlation and are
not written into normal DDoS event data.

------------------------------------------------------------------------

## 📚 DDoS Host History

Per hashed source, `hosts.json` can maintain:

-   🕒 First seen
-   🕒 Last seen
-   🚨 Number of DDoS events
-   📦 Total packets across triggered events
-   💾 Total bytes across triggered events
-   🔗 Latest correlation data

------------------------------------------------------------------------

## 🔗 Cross-System IP Correlation

A DDoS/network source hash can be checked against all major collector
datasets.

Correlation can report:

### 👤 Player matches

-   ProductID
-   UniqueID
-   Player name
-   Admin state
-   Ban state

### 🎛️ RCON matches

-   Server ID
-   Known/failed classification
-   First seen
-   Last seen
-   Successful connections
-   Failed attempts

### 🔑 SSH match

-   First seen
-   Last seen
-   Failed attempts
-   Blocked state
-   Blocked timestamp

### 🚦 Correlation flags

-   Has player match
-   Has RCON match
-   Has SSH match

> ⚠️ Correlation means the same HMAC IP identifier was observed. It is
> not proof that the same person generated each type of traffic.

------------------------------------------------------------------------

## 🌍 Pavlov Public API Data

The public-server updater can collect live Pavlov public-server
information such as:

-   🏷️ Server name
-   🌐 Server IP
-   🔌 Port when supplied
-   🎮 Game mode
-   🗺️ Map ID
-   🗺️ Map label/name
-   👥 Current player slots
-   👥 Maximum slots
-   🖥️ Server type
-   🔢 Server version
-   🔐 Password-protected state
-   🛡️ Secured state
-   🕒 API/update timestamp
-   🌐 Host/network enrichment

------------------------------------------------------------------------

## 📦 Log Collection & Archiving

The collector handles:

-   📜 Historical `Pavlov-backup-*.log`
-   📜 Active `Pavlov.log`
-   📊 Historical `Stats-*.log`
-   📊 Active `Stats.log`

When active-log rotation is enabled it can:

-   📥 Archive historical backups
-   📋 Copy active logs to timestamped archive files
-   🧹 Truncate active logs after copying
-   🔎 Maintain processing state to avoid duplicate processing

------------------------------------------------------------------------

## 🔎 Search / Index Data

Generated indexes can include:

-   👤 `by_name.json`
-   🪪 `by_unique_id.json`
-   🆔 `by_product_id.json`
-   🌐 `by_ip_hash.json`

These make it possible to locate a persistent player record by several
different identifiers.

------------------------------------------------------------------------

## 🔔 Discord Webhook Data

Supported webhook categories include:

-   🔌 Player connection alerts
-   🎛️ Failed RCON authentication alerts
-   🔑 Failed SSH authentication alerts

Webhook data can include relevant:

-   👤 Player identity
-   📊 Player statistics
-   🛡️ Admin status
-   🚫 Ban status
-   🌎 Normalized network information
-   🔐 IP hash
-   🔗 Player/network correlation
-   🔢 Failure counts
-   🚫 Blocked state

Raw IP addresses are not intended to be sent in normal Discord alerts.

------------------------------------------------------------------------

## 🎛️ File-Based RCON Bridge

The ModSave trigger system can support:

-   📥 `IN-*.json` request files
-   📤 `OUT-*.json` response files
-   🖥️ Server ID
-   🎮 Platform
-   🎛️ Requested RCON command
-   🧩 Command arguments
-   🕒 Timestamp
-   ✅ Success state
-   ❌ Error information
-   📦 RCON response payload

Command definitions and supported arguments can be stored in JSON
resource files.

------------------------------------------------------------------------

## 📂 Main Data Layout

``` text
/home/steam/jtwp-collector-data/
│
├── global/
│   ├── admins.json
│   ├── processing_state.json
│   ├── stats_combat_state.json
│   ├── modio/
│   │   └── mods.json
│   ├── reference/
│   │   └── unknown_items.json
│   ├── network/
│   │   └── ddos/
│   │       ├── network_stats.json
│   │       ├── events.jsonl
│   │       ├── last_event.json
│   │       └── hosts.json
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
        ├── server/
        │   ├── maps.json
        │   ├── mods.json
        │   ├── service.json
        │   └── maintenance.jsonl
        ├── rounds/
        │   └── *.json
        ├── bans/
        │   ├── current_bans.json
        │   └── changes.jsonl
        ├── rcon/
        │   ├── events.jsonl
        │   ├── known_hosts.json
        │   └── failed_hosts.json
        └── http/
            └── ...
```

------------------------------------------------------------------------

## 🧭 Feature Summary

The collector combines:

-   🎮 Pavlov server history
-   👤 Persistent player identity
-   🎯 Combat statistics
-   🔫 Weapon statistics
-   🔌 Connection history
-   ⚙️ Player settings
-   🌐 Privacy-preserving network history
-   🛡️ Admin tracking
-   🚫 Ban tracking
-   🗺️ Map rotation
-   🧩 Mod tracking
-   🌐 Mod.io enrichment
-   🔫 Custom-item discovery
-   🏁 Match/round history
-   🖥️ RCON authentication
-   🎛️ RCON command history
-   🔑 SSH security monitoring
-   🚫 Automatic SSH blocking
-   🛡️ DDoS/network-abuse detection
-   🔗 Player ↔ RCON ↔ SSH ↔ network correlation
-   🌍 Pavlov public API collection
-   🌐 HTTP/network reliability history
-   🔔 Discord notifications
-   📦 Log archiving
-   🔎 Search indexes
-   ⚙️ systemd service discovery
-   🧹 Server maintenance logging
-   🎛️ ModSave file-trigger automation

The goal is to turn raw Pavlov/server/network activity into long-term
structured JSON/JSONL datasets that can be consumed by mods, websites,
Discord bots, administration tools, authentication systems, and other
server-side automation.

---

## 📚 Documentation Ownership

For installation/update order use `INSTALL_AND_UPDATE.md`. For systemd use
`SERVICES.md`; secrets/API values use `API_SETUP.md`; helper installation uses
`SCRIPTS.md`; quick commands use `USEFUL_COMMANDS.md`. This guide should remain
focused on its named component so setup instructions do not drift between files.
