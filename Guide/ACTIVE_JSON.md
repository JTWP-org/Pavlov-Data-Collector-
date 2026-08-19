# ⚙️ `active.json` Configuration Guide

`active.json` is the **feature switchboard** for the JTWP Pavlov Data
Collector.

It lets you decide which parts of the project are active for **your**
server. The supplied configuration may have many features enabled, but
you do **not** need to use everything.

> ## 🛑 Recommended first step
>
> **Turn everything off first, then enable only the features you
> actually want to use.**

This is especially important when first setting up the project. Some
features depend on external APIs, RCON access, Discord credentials,
packet capture permissions, SSH logs, background services, or other
configuration. Starting with a minimal setup makes installation easier
to test and troubleshoot.

------------------------------------------------------------------------

## 🤔 Why start with features disabled?

The collector contains a lot more than basic Pavlov log parsing.
Depending on what you enable, it can also process historical logs,
maintain player history, enrich network information, correlate IP
hashes, monitor RCON and SSH activity, watch for possible DDoS events,
send Discord notifications, query Mod.io, control services, and run
maintenance tools.

Enabling only what you need gives you several benefits:

-   🧩 **Simpler setup** --- configure one feature at a time.
-   🐛 **Easier troubleshooting** --- if something fails, there are
    fewer possible causes.
-   ⚡ **Less unnecessary work** --- disabled features do not need to be
    part of your deployment.
-   🌐 **Fewer external API requests** --- useful when you do not need
    network or Mod.io enrichment.
-   🔐 **Better privacy control** --- do not collect or retain
    information you do not need.
-   🛡️ **Reduced permissions** --- features such as packet capture,
    service control, RCON, SSH monitoring, and auto-blocking may require
    additional privileges.
-   🤖 **Optional integrations stay optional** --- you do not need
    Discord, RCON, Mod.io, SSH monitoring, or DDoS monitoring just to
    use the portions of the collector you want.

------------------------------------------------------------------------

# 🔴 Starting with everything off

The safest way to begin is to set the top-level feature groups to
`false`.

For example:

``` json
{
  "collector": {
    "enabled": false
  },
  "players": {
    "enabled": false
  },
  "server_data": {
    "enabled": false
  },
  "matches": {
    "enabled": false
  },
  "maps": {
    "enabled": false
  },
  "mods": {
    "enabled": false
  },
  "custom_content": {
    "enabled": false
  },
  "rcon": {
    "enabled": false
  },
  "rcon_bridge": {
    "enabled": false
  },
  "rcon_loop": {
    "enabled": false
  },
  "ssh": {
    "enabled": false
  },
  "ddos": {
    "enabled": false
  },
  "pavlov_public_api": {
    "enabled": false
  },
  "modio": {
    "enabled": false
  },
  "admins": {
    "enabled": false
  },
  "discord_bot": {
    "enabled": false
  },
  "data_tools": {
    "enabled": false
  },
  "maintenance": {
    "enabled": false
  },
  "service_discovery": {
    "enabled": false
  },
  "privacy": {
    "enabled": false
  },
  "scripts": {
    "enabled": false
  }
}
```

> ⚠️ This example is a **starting point**, not a replacement for your
> complete `active.json`.
>
> Keep the full file and its individual switches. Set the relevant
> `enabled` values to `false`, then turn features back on as you
> configure them.

------------------------------------------------------------------------

# 🧱 Parent and child switches

Most sections use a parent `enabled` switch plus more specific child
switches.

For example:

``` json
"players": {
  "enabled": true,
  "identity": {
    "enabled": true,
    "product_id": true,
    "unique_id": true,
    "current_name": true,
    "name_history": false
  }
}
```

This lets you enable the player system while selecting only the player
information you want.

A good configuration philosophy is:

``` text
Top-level feature
    ↓
Sub-feature
    ↓
Individual data fields/actions
```

Do not assume that enabling a child option should override a disabled
parent. Configure the parent and its required children consistently.

------------------------------------------------------------------------

# 📥 Collector

The `collector` section controls core log processing.

``` json
"collector": {
  "enabled": true,
  "historical_logs": true,
  "active_logs": true,
  "stats_logs": true,
  "archive_logs": true,
  "rotate_active_logs": true,
  "processing_state": true,
  "duplicate_detection": true
}
```

### Options

  -----------------------------------------------------------------------
  Setting                             Purpose
  ----------------------------------- -----------------------------------
  `enabled`                           Master collector switch.

  `historical_logs`                   Process configured historical log
                                      archives.

  `active_logs`                       Process current Pavlov logs.

  `stats_logs`                        Process Pavlov stats files.

  `archive_logs`                      Enable archive-related log
                                      processing.

  `rotate_active_logs`                Allow active logs to be
                                      rotated/archived.

  `processing_state`                  Maintain processing state so
                                      already handled files can be
                                      tracked.

  `duplicate_detection`               Enable duplicate-processing
                                      protection.
  -----------------------------------------------------------------------

### 💡 Minimal setup

If you only want to work with current logs, you may not need
historical/archive processing immediately.

------------------------------------------------------------------------

# 👤 Players

The `players` section controls player records.

It is divided into:

-   🪪 `identity`
-   🔌 `connections`
-   🎮 `settings`
-   📊 `stats`
-   🔫 `weapons`
-   🌐 `network`
-   🚦 `status`
-   📜 `history`
-   🔎 `indexes`

This is intentionally granular so you can decide exactly what your
installation should retain.

------------------------------------------------------------------------

## 🪪 Player identity

Controls fields such as:

``` text
product_id
unique_id
current_name
name_history
first_seen
last_seen
```

If you only need basic player identification, enable the minimum fields
required by your use case.

------------------------------------------------------------------------

## 🔌 Player connections

Controls:

``` text
connect_events
disconnect_events
times_connected
connection_history
server_history
```

Enable connection history only if you need long-term connection
tracking.

------------------------------------------------------------------------

## 🎮 Player settings

Controls observed player settings such as:

``` text
right_handed
vstock
player_height
client_platform
```

If your project does not use these values, this entire section can
remain disabled.

------------------------------------------------------------------------

## 📊 Player statistics

Controls:

``` text
kills
deaths
headshots
suicides
teamkills
bot_kills
unverified_team_kills
matches
times_connected
```

You can use the collector as a simple connection/player database without
enabling every gameplay statistic.

------------------------------------------------------------------------

## 🔫 Weapons

Controls weapon statistics including:

``` text
weapon_kills
weapon_headshots
favorite_weapon
favorite_weapon_kills
total_weapon_kills
weapon_source
```

Disable this section if weapon analytics are not part of your server
setup.

------------------------------------------------------------------------

# 🌐 Player network data

This is one of the most important sections to review before deployment.

``` json
"network": {
  "enabled": true,
  "ip_hash": true,
  "ip_history": true,
  "known_ip_count": true,
  "network_enrichment": true,
  "provider": true,
  "organisation": true,
  "network_type": true,
  "country": true,
  "country_code": true,
  "region": true,
  "city": true,
  "proxy": true,
  "vpn": true,
  "hosting": true,
  "tor": true,
  "risk": true,
  "confidence": true,
  "lookup_source": true
}
```

### 🔐 IP hashing

`ip_hash` allows the system to use stable private IP hashes for
correlation rather than exposing raw IP addresses in ordinary player
records.

This supports features such as:

-   detecting that multiple player records have used the same IP hash;
-   correlating player history;
-   comparing player IP hashes with RCON activity;
-   comparing player IP hashes with SSH activity;
-   correlating network/security events without placing raw IPs in
    normal output.

### 🌎 Network enrichment

`network_enrichment` can add information such as:

-   provider;
-   organisation;
-   country;
-   region;
-   city;
-   network type;
-   proxy/VPN/hosting/Tor indicators;
-   risk/confidence information;
-   lookup source.

This can require external API requests.

> 💡 If you do not need network intelligence, leave `network_enrichment`
> and its related fields disabled.

This can make large historical imports simpler and avoids unnecessary
external lookups.

------------------------------------------------------------------------

# 🔎 Player indexes

The collector can maintain indexes by:

``` text
by_name
by_unique_id
by_product_id
by_ip_hash
```

`by_ip_hash` is particularly useful for correlation because a hash can
be associated with one or more known Product IDs.

If you do not need a particular lookup method, its index can be
disabled.

------------------------------------------------------------------------

# 🖥️ Server data

`server_data` controls collection of server-specific information:

``` text
server_identity
server_name
server_path
platform
game_ini
runtime
admins
bans
http_events
service_info
```

Only enable fields useful to your deployment.

For example, a basic log collector may not need service metadata or HTTP
event tracking.

------------------------------------------------------------------------

# 🏆 Matches

The `matches` section controls match and round information:

``` text
round_files
map_label
game_mode
match_duration
player_count
teams_enabled
team_scores
player_stats
```

Disable the entire section if you only need player/server activity and
do not need match analytics.

------------------------------------------------------------------------

# 🗺️ Maps

Map tracking includes:

``` text
map_rotation
map_id
map_label
game_mode
configured_state
observed_maps
modio
```

The `modio` option is relevant when you want map information enriched
with Mod.io data.

------------------------------------------------------------------------

# 📦 Mods

Mod tracking includes:

``` text
configured_mods
observed_mods
configured_vs_observed
ugc_id
modio
```

This can be useful for comparing what the server is configured to load
with what was actually observed.

If you run only default content or do not need mod reporting, leave it
disabled.

------------------------------------------------------------------------

# 🧰 Custom content

The `custom_content` group can track:

``` text
custom_guns
custom_items
loot_meshes
failed_items
unknown_items
```

This is optional and can remain disabled on installations that do not
need custom-content analysis.

------------------------------------------------------------------------

# 🎛️ RCON

The `rcon` section includes:

``` text
authentication
connections
commands
known_hosts
failed_hosts
ip_hash
network_enrichment
player_correlation
webhook
```

RCON monitoring can therefore do much more than simply execute commands.

### 🔗 Player correlation

When enabled, RCON IP hashes can be compared with known player IP
hashes.

> ⚠️ A shared IP/hash is evidence of an association, **not proof that a
> particular player performed an RCON action**.

Keep that distinction in mind when using correlation data.

If you only need basic RCON access, do not automatically enable every
monitoring, enrichment, correlation, and webhook option.

------------------------------------------------------------------------

# 🌉 RCON Bridge

The `rcon_bridge` section controls:

``` text
watcher
input_files
output_files
ppapi_trigger
rcon_resource_trigger
```

Use this when you want file-triggered or automated RCON workflows.

If your server does not use the bridge, disable the entire section.

------------------------------------------------------------------------

# 🔄 RCON Loop

The `rcon_loop` section controls recurring RCON polling:

``` text
watcher
serverinfo
inspectall
output
control_helper
```

This is useful when another component needs regularly refreshed RCON
information.

It is unnecessary if you only execute RCON commands manually.

------------------------------------------------------------------------

# 🔑 SSH monitoring

The SSH section includes:

``` text
watcher
failed_password
failed_publickey
invalid_user
max_auth_attempts
host_data
network_enrichment
player_correlation
auto_block
webhook
private_raw_ip_storage
```

This is a security-monitoring feature and should be configured
deliberately.

### 🚫 Auto-block

`auto_block` can cause automated blocking behavior when paired with the
corresponding SSH watcher configuration.

Do not enable it merely because the option exists. Configure and test
the blocking rules first.

### 🔐 Raw IP storage

`private_raw_ip_storage` allows private SSH records to retain raw IP
information.

If you do not require it, leave it disabled.

------------------------------------------------------------------------

# 🛡️ DDoS monitoring

The `ddos` section includes:

``` text
watcher
packet_capture
network_stats
events
host_history
player_correlation
rcon_correlation
ssh_correlation
webhook
```

Packet capture and network monitoring may require additional
operating-system permissions.

If you do not intend to use the server as a network/security monitoring
system, disable this entire section.

Correlation can compare observed sources with existing player, RCON, and
SSH information, but correlation should not be treated as definitive
attribution.

------------------------------------------------------------------------

# 🌍 Pavlov Public API

Controls:

``` text
updater
manual_update
file_trigger
server_data
network_enrichment
```

Enable this if you want the project to maintain Pavlov public-server/API
data.

If you only want local server information, you may not need it.

------------------------------------------------------------------------

# 🧩 Mod.io

The `modio` section controls:

``` text
api_requests
cache
map_lookup
mod_lookup
```

Disable it if you do not need Mod.io metadata.

This also avoids unnecessary external API requests.

------------------------------------------------------------------------

# 👮 Admin tracking

The `admins` section has three major groups:

### 📊 Tracking

``` text
admin_status
admin_sessions
admin_time
admin_server_time
connection_history
```

### 📝 Logs

``` text
admin_events
admin_actions
future_external_admin_log_ingest
```

### 🔔 Notifications

``` text
no_admin_online
negative_player_score
multiple_teamkills
ping_admin_role
```

Response tracking can additionally track:

``` text
admin_join
response_time
expired_alerts
admin_response_stats
```

Only enable administrative monitoring that is useful for your community
and moderation workflow.

------------------------------------------------------------------------

# 🤖 Discord bot

The Discord bot has several independently configurable capabilities.

## 🔐 Permissions

``` text
admin_role
owner_role
channel_restriction
```

These should be configured before exposing administrative bot commands.

## 🎛️ RCON

``` text
admin_limited_commands
owner_all_commands
response_embeds
command_logging
```

Use role restrictions carefully, especially for commands capable of
modifying a live server.

## ⚙️ systemctl

The bot can expose:

``` text
status
start
stop
restart
enable
disable
```

These are powerful host-management operations.

The configuration includes an `owner_only` control for this feature.
Keep service-control functionality tightly restricted.

## 🔎 Player lookup

Available lookup features include:

``` text
get_product_id
get_network
get_names
get_stats
get_guns
get_player
get_dump
check_cons
```

You can disable individual lookup commands you do not want exposed
through Discord.

## 👑 Owner commands

The configuration includes owner utilities for:

``` text
clear_pavlov_mods
run_collector
run_pavlov_api
run_ssh_report
```

## 🔄 Loop control

The bot can expose:

``` text
start
stop
status
```

for the RCON loop control system.

------------------------------------------------------------------------

# 💾 Data tools

The `data_tools` section controls:

``` text
clear_data
export_data
backup_data
include_hash_secret_in_export
```

### ⚠️ Hash secret exports

Pay special attention to:

``` json
"include_hash_secret_in_export": true
```

The IP hash secret is important because stable IP correlation depends on
it.

If you include that secret in an export, treat the export as sensitive.

Do not publicly distribute backups or exports containing secrets.

------------------------------------------------------------------------

# 🔧 Maintenance

Maintenance options include:

``` text
clear_mods
maintenance_logging
service_metadata_refresh
```

Enable only the maintenance operations you intend to use.

------------------------------------------------------------------------

# 🔍 Service discovery

The service-discovery system can:

``` text
discover_services
save_commands
```

This is useful for installations that want JTWP to discover and record
service information automatically.

It can remain disabled if you prefer to configure services manually.

------------------------------------------------------------------------

# 🔐 Privacy controls

The privacy section contains:

``` text
ip_hashing
private_player_ips
private_ssh_ips
ip_lookup_cache
raw_ip_in_webhooks
raw_ip_in_ddos_records
```

The supplied configuration has:

``` json
"raw_ip_in_webhooks": false,
"raw_ip_in_ddos_records": false
```

These are important privacy-oriented defaults.

### Recommended principle

> 🔒 **Do not expose raw IP addresses unless you have a specific
> operational reason to do so.**

Prefer hashed correlation for normal player/RCON relationships where
possible.

------------------------------------------------------------------------

# 📜 Scripts

The `scripts` section acts as another control layer for individual
project components:

``` text
collector
connection_watcher
ssh_watcher
ddos_watcher
rcon_trigger_watcher
rcon_loop
admin_monitor
discord_bot
pavlov_api_updater
clear_pavlov_mods
clear_data
export_data
backup_data
```

This allows you to disable scripts that are not part of your
installation.

------------------------------------------------------------------------

# 🚀 Recommended setup process

A good first-time installation flow is:

1.  🔴 **Disable all optional feature groups.**
2.  📁 Configure your basic paths in `config.json`.
3.  🔐 Configure required secrets/environment variables.
4.  📥 Enable the core collector.
5.  🧪 Run it manually and verify basic log processing.
6.  👤 Enable the player fields you actually need.
7.  📊 Enable stats/matches only if wanted.
8.  🌐 Enable network enrichment only if wanted and after API
    configuration is complete.
9.  🎛️ Configure and test RCON before enabling RCON automation.
10. 🤖 Configure Discord roles/channel restrictions before enabling
    administrative bot commands.
11. 🔑 Configure SSH monitoring separately if needed.
12. 🛡️ Configure DDoS monitoring separately if needed.
13. 🔔 Enable webhooks/notifications after the underlying feature works.
14. ⚙️ Enable the appropriate services/scripts for automatic operation.
15. 🔎 Review the generated data and privacy settings before leaving the
    system running unattended.

------------------------------------------------------------------------

# 🟢 Example: basic collector

A simple installation might start with only the collector and basic
player identity/connection information.

Conceptually:

``` json
{
  "collector": {
    "enabled": true,
    "active_logs": true
  },

  "players": {
    "enabled": true,

    "identity": {
      "enabled": true,
      "product_id": true,
      "unique_id": true,
      "current_name": true
    },

    "connections": {
      "enabled": true,
      "connect_events": true,
      "disconnect_events": true
    },

    "network": {
      "enabled": false
    }
  },

  "rcon": {
    "enabled": false
  },

  "ssh": {
    "enabled": false
  },

  "ddos": {
    "enabled": false
  },

  "discord_bot": {
    "enabled": false
  }
}
```

This demonstrates the intended setup philosophy: **begin small and add
functionality deliberately.**

------------------------------------------------------------------------

# 🟡 Example: enabling network correlation later

After the basic collector is working, you might enable private
hash-based network correlation:

``` json
"network": {
  "enabled": true,
  "ip_hash": true,
  "ip_history": true,
  "known_ip_count": true,
  "network_enrichment": false
}
```

This separates **IP/hash tracking** from external **network
enrichment**.

You can then enable enrichment later if you actually need provider,
country, proxy/VPN, or similar metadata.

------------------------------------------------------------------------

# ⚠️ Dependencies matter

Some options depend on other parts of the project.

For example:

``` text
Discord RCON commands
        ↓
Discord bot
        ↓
RCON configuration
        ↓
working Pavlov RCON connection
```

Similarly:

``` text
RCON player correlation
        ↓
RCON IP hashing
        +
Player IP/hash data
        +
Player IP-hash index
```

And:

``` text
Network enrichment
        ↓
external lookup provider/API
        ↓
valid credentials / limits / connectivity
```

If a feature is not behaving correctly, temporarily disable dependent
features and verify the underlying component first.

------------------------------------------------------------------------

# 🧪 Change one thing at a time

When setting up a new installation, avoid enabling every switch and then
trying to diagnose several systems simultaneously.

A better approach is:

``` text
Enable feature
      ↓
Run/test
      ↓
Check output
      ↓
Confirm it works
      ↓
Enable next feature
```

This makes `active.json` useful not only for customization, but also for
troubleshooting.

------------------------------------------------------------------------

# 🔒 Security & privacy checklist

Before considering your setup complete, review:

-   [ ] Raw player IP exposure is disabled unless explicitly required.
-   [ ] Raw IPs are not being sent to Discord webhooks.
-   [ ] Discord owner/admin roles are configured correctly.
-   [ ] Discord channel restrictions are configured.
-   [ ] `systemctl` controls are owner-only.
-   [ ] Destructive maintenance commands are restricted.
-   [ ] RCON credentials are not stored in public files.
-   [ ] API keys and Discord tokens are stored securely.
-   [ ] `JTWP_IP_HASH_SECRET` is persistent and protected.
-   [ ] Exports containing the hash secret are treated as sensitive.
-   [ ] SSH auto-blocking has been tested before enabling it.
-   [ ] Packet-capture permissions are only granted when DDoS monitoring
    is required.
-   [ ] External API/enrichment features are enabled only when needed.
-   [ ] Historical log collection is intentional.
-   [ ] Backups and archives have enough disk space.

------------------------------------------------------------------------

# 🔑 Important: keep the IP hash secret stable

If IP hashing is enabled, keep the same `JTWP_IP_HASH_SECRET`.

Changing the secret changes the resulting hashes, which prevents new
hashes from matching hashes generated with the old secret.

Store it securely and do not regenerate it every time the collector
starts.

------------------------------------------------------------------------

# 📝 Final recommendation

`active.json` is intended to let the JTWP collector scale from a
relatively small Pavlov data collector to a much larger monitoring and
administration system.

You **do not need to enable everything**.

> ### 🔴 Start OFF → 🧪 Test → 🟢 Enable what you need

That gives you a cleaner installation, fewer unnecessary dependencies,
easier troubleshooting, and much better control over what your server
collects and operates.

---

## 📚 Documentation Ownership

For installation/update order use `INSTALL_AND_UPDATE.md`. For systemd use
`SERVICES.md`; secrets/API values use `API_SETUP.md`; helper installation uses
`SCRIPTS.md`; quick commands use `USEFUL_COMMANDS.md`. This guide should remain
focused on its named component so setup instructions do not drift between files.
