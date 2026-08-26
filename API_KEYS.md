# JTWP API / Key Reference

This document lists the external APIs, tokens, webhooks, and server credentials used by the JTWP Pavlov Data Collector project.

## Quick `.env` Template

```env
# Discord bot
JTWP_DISCORD_BOT_TOKEN=
JTWP_DISCORD_GUILD_ID=

# Discord webhooks
JTWP_ADMIN_WEBHOOK_URL=
JTWP_COMMAND_LOG_WEBHOOK_URL=
JTWP_MODERATION_LOG_WEBHOOK_URL=

# Steam
STEAM_WEB_API_KEY=

# mod.io
MODIO_API_KEY=

# IP intelligence
PROXYCHECK_API_KEY=
IPAPI_API_KEY=

# Pavlov public server API
PAVLOV_API=

# Privacy / hashing
JTWP_IP_HASH_SECRET=

# Pavlov RCON passwords
PAVLOVSERVER_RCON_PASSWORD=
PAVLOVSERVER0_RCON_PASSWORD=
PAVLOVSERVER1_RCON_PASSWORD=
```

> Keep `.env` private. Never commit real keys, tokens, webhook URLs, or RCON passwords to Git.

---

## 1. Discord Bot API

**Purpose**

Runs the JTWP Discord administration bot, slash commands, dashboards, account linking, moderation tools, badges, RCON controls, and other Discord features.

**Environment variable**

```env
JTWP_DISCORD_BOT_TOKEN=
```

**Required?**

Yes, if `discord_bot.py` is enabled.

**Where to get it**

Create an application and bot in the Discord Developer Portal, then copy the bot token.

**Related value**

```env
JTWP_DISCORD_GUILD_ID=
```

The guild ID is not a secret/API key. It identifies the Discord server where slash commands should be synchronized.

---

## 2. Discord Webhooks

Discord webhooks are URLs rather than traditional API keys. Treat the complete webhook URL as a secret because anyone with it can post to that webhook.

### Admin Alerts

```env
JTWP_ADMIN_WEBHOOK_URL=
```

Used for administrative alerts such as account-link approval requests and other configured admin notifications.

### Command Log

```env
JTWP_COMMAND_LOG_WEBHOOK_URL=
```

Used by the Discord bot's command-log tailer to send command/audit activity to Discord.

### Moderation Log

```env
JTWP_MODERATION_LOG_WEBHOOK_URL=
```

Used for moderation-related webhook output.

**Required?**

These are optional individually. A feature that uses a particular webhook will not be able to send its Discord notification when that URL is not configured.

---

## 3. Steam Web API

**Purpose**

Looks up a Steam account by SteamID64 when linking PCVR/Steam accounts. The bot uses Steam's `GetPlayerSummaries` endpoint to retrieve information such as Steam username, profile URL, avatar, visibility, and last logoff.

**Environment variable**

```env
STEAM_WEB_API_KEY=
```

**Required?**

Required for Steam profile lookup/account linking features. It is not required for SHACK/Oculus-only player records.

**Endpoint used**

```text
https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/
```

**Input**

- API key
- 17-digit SteamID64

---

## 4. mod.io API

**Purpose**

Looks up Pavlov workshop/mod information, including UGC/map/mod metadata used by the collector and server-data enrichment.

**Environment variable**

```env
MODIO_API_KEY=
```

**Game ID**

```text
3959
```

This is the mod.io game ID used for Pavlov.

**Required?**

Required when mod.io enrichment is enabled or code attempts to resolve UGC/mod metadata.

**Typical API base**

```text
https://api.mod.io/v1/
```

The project should keep the key in `.env`, not directly in `config.json`.

---

## 5. ProxyCheck.io API

**Purpose**

Primary IP intelligence/enrichment provider. Used to enrich a source IP before the public-facing data is reduced to a stable hash.

Typical information can include:

- ISP/provider
- organization/network
- country/region/city
- proxy/VPN indicators
- hosting indicators
- TOR indicators
- risk information

**Environment variable**

```env
PROXYCHECK_API_KEY=
```

**Required?**

Required if ProxyCheck enrichment is enabled and you want authenticated API access.

**Important**

Raw IP addresses should not be placed in public player records. The project's intended flow is to enrich the address first, then use the stable HMAC hash for cross-record correlation.

---

## 6. ipapi.is API

**Purpose**

Fallback IP intelligence provider when the primary IP-enrichment provider is unavailable or fails.

**Environment variable**

```env
IPAPI_API_KEY=
```

**Required?**

Optional. It is useful as a fallback provider.

If the account/plan permits unauthenticated requests, some calls may work without a key, but the project supports keeping an API key in the environment.

---

## 7. Pavlov Public Server API

**Purpose**

Downloads the public Pavlov server list used for server information, network-host snapshots, player counts, maps, modes, and public server metadata.

**Environment variable**

```env
PAVLOV_API=
```

This value is the API **URL**, not an API secret.

Example format:

```env
PAVLOV_API=https://pavlovservers.com/api/servers?all=true
```

**Required?**

Required when the Pavlov public API updater is enabled.

**API key needed?**

No project API key is currently required for this endpoint.

---

## 8. Pavlov RCON

RCON is not a web API, but it is an authenticated service used heavily by JTWP.

Each Pavlov instance can have its own password.

```env
PAVLOVSERVER_RCON_PASSWORD=
PAVLOVSERVER0_RCON_PASSWORD=
PAVLOVSERVER1_RCON_PASSWORD=
```

Typical local configuration:

```text
pavlovserver   -> 127.0.0.1:9000
pavlovserver0  -> 127.0.0.1:9100
pavlovserver1  -> 127.0.0.1:9200
```

**Required?**

Required for any server where RCON functionality is enabled.

The password variable used by each server is selected through `password_env` in `config.json`.

---

## 9. JTWP IP Hash Secret

This is not an external API key, but it is a critical project secret.

```env
JTWP_IP_HASH_SECRET=
```

**Purpose**

Creates stable HMAC-based hashes for IP addresses so JTWP can correlate the same network address across player, SSH, and RCON security records without exposing the raw address in public data.

**Required?**

Yes for stable IP-hash correlation.

**Important**

Use a long random value and do not change it after data has been collected unless you intentionally want all future IP hashes to stop matching historical hashes.

Example generator:

```bash
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

---

## 10. GitHub Raw Resource Downloads

Some JTWP resource files may be downloaded from GitHub raw URLs, for example the RCON command resource.

Example:

```text
https://raw.githubusercontent.com/JTWP-org/Pavlov-Data-Collector-/refs/heads/main/resource/rcon_commands.json
```

**API key needed?**

No key is required for public raw GitHub files.

A GitHub token would only be needed if you later change this to private repositories or authenticated GitHub API operations.

---

# Required vs Optional

| Variable | Type | Needed For | Required |
|---|---|---|---|
| `JTWP_DISCORD_BOT_TOKEN` | Secret token | Discord bot | Yes for bot |
| `JTWP_DISCORD_GUILD_ID` | ID, not secret | Fast guild slash-command sync | Recommended |
| `JTWP_ADMIN_WEBHOOK_URL` | Secret URL | Admin/account alerts | Recommended |
| `JTWP_COMMAND_LOG_WEBHOOK_URL` | Secret URL | Discord command logging | Optional |
| `JTWP_MODERATION_LOG_WEBHOOK_URL` | Secret URL | Moderation logging | Optional |
| `STEAM_WEB_API_KEY` | API key | Steam account lookup | Required for Steam lookup |
| `MODIO_API_KEY` | API key | Pavlov mod/map enrichment | Required for mod.io enrichment |
| `PROXYCHECK_API_KEY` | API key | Primary IP enrichment | Required for authenticated ProxyCheck |
| `IPAPI_API_KEY` | API key | Fallback IP enrichment | Optional |
| `PAVLOV_API` | URL | Pavlov public server list | Required when updater enabled |
| `JTWP_IP_HASH_SECRET` | Secret | Stable IP hashing | Yes |
| `PAVLOVSERVER_RCON_PASSWORD` | Password | First Pavlov RCON server | If RCON enabled |
| `PAVLOVSERVER0_RCON_PASSWORD` | Password | Second Pavlov RCON server | If RCON enabled |
| `PAVLOVSERVER1_RCON_PASSWORD` | Password | Third Pavlov RCON server | If RCON enabled |

---

# Recommended `.env` Permissions

The `.env` file contains secrets and should only be readable by the account running JTWP.

```bash
chmod 600 /home/steam/jtwp-collector/Pavlov-Data-Collector-/.env
chown steam:steam /home/steam/jtwp-collector/Pavlov-Data-Collector-/.env
```

Do not commit `.env`:

```gitignore
.env
*.env
```

Also avoid putting real API keys into:

- `config.json`
- source code
- Git commits
- Discord messages
- public log files
- exported player records

---

# Example Safe `.env`

```env
JTWP_DISCORD_BOT_TOKEN=YOUR_DISCORD_BOT_TOKEN
JTWP_DISCORD_GUILD_ID=YOUR_GUILD_ID

JTWP_ADMIN_WEBHOOK_URL=YOUR_ADMIN_WEBHOOK
JTWP_COMMAND_LOG_WEBHOOK_URL=YOUR_COMMAND_LOG_WEBHOOK
JTWP_MODERATION_LOG_WEBHOOK_URL=YOUR_MODERATION_WEBHOOK

STEAM_WEB_API_KEY=YOUR_STEAM_WEB_API_KEY
MODIO_API_KEY=YOUR_MODIO_API_KEY
PROXYCHECK_API_KEY=YOUR_PROXYCHECK_API_KEY
IPAPI_API_KEY=YOUR_IPAPI_KEY

PAVLOV_API=https://pavlovservers.com/api/servers?all=true

JTWP_IP_HASH_SECRET=GENERATE_A_LONG_RANDOM_SECRET

PAVLOVSERVER_RCON_PASSWORD=SERVER_1_RCON_PASSWORD
PAVLOVSERVER0_RCON_PASSWORD=SERVER_2_RCON_PASSWORD
PAVLOVSERVER1_RCON_PASSWORD=SERVER_3_RCON_PASSWORD
```
