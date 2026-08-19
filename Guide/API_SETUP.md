# 🌐 JTWP API Setup Guide

This guide covers external APIs and private environment values used by
the JTWP Pavlov Data Collector.

Keep secrets in `.env` rather than directly inside source code or
`config.json` whenever the collector supports an environment variable
for that value.

------------------------------------------------------------------------

# 🔐 `.env`

The project should contain a safe example:

``` text
.env.example
```

Create the real environment file:

``` bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-

cp .env.example .env
nano .env
```

Protect it:

``` bash
chmod 600 .env
```

Add `.env` to `.gitignore`:

``` gitignore
.env
```

> \[!WARNING\] Never commit real API keys, Discord webhook URLs, or RCON
> passwords.

------------------------------------------------------------------------

# 🧾 Example `.env`

Adjust the variable names to match your current collector configuration:

``` dotenv
# ============================================
# Mod.io
# ============================================

MODIO_API_KEY=YOUR_MODIO_API_KEY


# ============================================
# IP / Network Lookup
# ============================================

PROXYCHECK_API_KEY=YOUR_PROXYCHECK_API_KEY

# Optional fallback provider, if configured:
IP_LOOKUP_FALLBACK_API_KEY=YOUR_FALLBACK_API_KEY


# ============================================
# Discord Webhooks
# ============================================

SSH_WEBHOOK_URL=
RCON_WEBHOOK_URL=


# ============================================
# Pavlov RCON
# ============================================

PAVLOVSERVER_RCON_PASSWORD=
PAVLOVSERVER0_RCON_PASSWORD=
PAVLOVSERVER1_RCON_PASSWORD=


# ============================================
# Optional SSH Auto-Block Whitelist
# ============================================

JTWP_SSH_AUTOBLOCK_WHITELIST=
```

Use the exact environment-variable names referenced by your current
scripts/configuration.

------------------------------------------------------------------------

# 📥 Loading `.env`

For a manual shell run:

``` bash
set -a
source .env
set +a
```

Then start the collector:

``` bash
python3 collector.py -c config.json
```

Check whether a variable exists without printing its secret:

``` bash
if [[ -n "${MODIO_API_KEY:-}" ]]; then
    echo "✅ MODIO_API_KEY loaded"
else
    echo "❌ MODIO_API_KEY missing"
fi
```

------------------------------------------------------------------------

# 🗺️ Mod.io

The collector uses Mod.io information to enrich Pavlov map/mod data.

The Pavlov game ID used by the project is:

``` text
3959
```

Typical `config.json` values include:

``` json
"modio_game_id": 3959,
"modio_cache_ttl_hours": 24
```

The API key itself should be stored in `.env`.

## 🔑 Getting a Mod.io API Key

Create/sign in to your Mod.io account and obtain an API key from the
API/access section of your Mod.io account/developer settings.

The exact Mod.io account UI can change, so use Mod.io's current API
documentation/account pages when creating the key.

Once created:

``` dotenv
MODIO_API_KEY=YOUR_KEY
```

Do not commit the key.

------------------------------------------------------------------------

# 🌐 IP / Network Lookup

The collector can enrich IP/network records with provider information.

The fields currently useful to the project include values such as:

``` json
{
  "provider": "Amazon.com, Inc.",
  "organisation": "Amazon.com, Inc.",
  "type": "Hosting",
  "continent_code": "NA",
  "country_name": "United States",
  "country_code": "US",
  "region_name": "Washington",
  "region_code": "WA",
  "city_name": "Seattle",
  "risk": 33,
  "confidence": 100,
  "hosting": true,
  "proxy": false,
  "vpn": false
}
```

Not every provider returns exactly the same field names. The collector
should normalize the useful values into its own data structure.

------------------------------------------------------------------------

# 🛡️ ProxyCheck

ProxyCheck can be used as the primary network-enrichment source.

Store its key in `.env`, for example:

``` dotenv
PROXYCHECK_API_KEY=YOUR_PROXYCHECK_API_KEY
```

Useful information may include:

-   provider
-   organisation
-   network type
-   country
-   region
-   city
-   proxy status
-   VPN status
-   hosting status
-   risk
-   confidence

The collector caches network lookups.

A typical configuration value is:

``` json
"ip_lookup_cache_ttl_days": 30
```
This prevents repeatedly querying the same IP every collector run.

to get a API key sign up for free at https://proxycheck.io/dashboard/



------------------------------------------------------------------------

# 🔁 Fallback IP Provider

The collector may use a fallback lookup provider if the primary lookup
fails.

Because providers expose different schemas, fallback responses may not
contain every ProxyCheck field.

The collector should preserve a normalized structure and indicate which
source was used, for example:

``` json
{
  "lookup_status": "success",
  "source": "proxycheck",
  "fallback": false
}
```

A fallback result can instead record:

``` json
{
  "lookup_status": "success",
  "source": "fallback-provider",
  "fallback": true
}
```

Do not assume `risk`, `confidence`, `proxy`, `vpn`, or hosting
classifications are directly equivalent across different providers.

------------------------------------------------------------------------

# 🌍 Pavlov Public Server API

The project also uses public Pavlov server-browser data.

Configured endpoint:

``` text
https://pavlovservers.com/api/servers?all=true
```

This endpoint does not require ModSave file access because the collector
or ModKit can make an HTTP request directly where supported.

Example server data can contain:

``` json
{
  "_id": "0f488261d0c25c80fb2d59caedbc8a36",
  "bPasswordProtected": 1,
  "bSecured": 1,
  "game_mode": "TDM",
  "ip": "15.204.243.166",
  "map_id": "UGC3283728",
  "map_label": "Overpass Shack [Temp]",
  "max_slots": 10,
  "name": "SMM Match-20128",
  "port": 7777,
  "server_type": "Shack Live",
  "slots": 3,
  "updated": "2026-08-16T19:00:24.280Z",
  "version": "1.0.28"
}
```

The collector can combine public-server information with network
enrichment.

A typical configuration includes:

``` json
"pavlov_api_enabled": true,
"pavlov_api_host_cache_ttl_days": 30
```

------------------------------------------------------------------------

# 🎮 RCON Passwords

Each configured Pavlov server can reference its password through an
environment variable.

Example:

``` json
"rcon": {
  "enabled": true,
  "host": "127.0.0.1",
  "port": 9000,
  "password_env": "PAVLOVSERVER_RCON_PASSWORD"
}
```

Then `.env` contains:

``` dotenv
PAVLOVSERVER_RCON_PASSWORD=YOUR_PASSWORD
```

For multiple servers:

``` dotenv
PAVLOVSERVER_RCON_PASSWORD=
PAVLOVSERVER0_RCON_PASSWORD=
PAVLOVSERVER1_RCON_PASSWORD=
```

> \[!IMPORTANT\] Use the password representation expected by the RCON
> component you are running. Your project also includes `rcon-md5.sh`
> for workflows where a manual MD5 representation is required.

See:

``` text
Guides/RCON_COMMANDS.md
```

for RCON-specific setup.

------------------------------------------------------------------------

# 🔔 Discord Webhooks

Webhook URLs should be treated like passwords.

Store them in `.env`:

``` dotenv
SSH_WEBHOOK_URL=
RCON_WEBHOOK_URL=
```

Never place a live webhook URL in:

-   README files
-   screenshots
-   Git commits
-   public issue reports
-   example JSON

If a webhook URL is accidentally exposed, regenerate it in Discord.

------------------------------------------------------------------------

# 🧪 Check Environment Variables

Check several values without printing the secrets:

``` bash
for var in \
    MODIO_API_KEY \
    PROXYCHECK_API_KEY \
    PAVLOVSERVER_RCON_PASSWORD \
    PAVLOVSERVER0_RCON_PASSWORD \
    PAVLOVSERVER1_RCON_PASSWORD
do
    if [[ -n "${!var:-}" ]]; then
        echo "✅ $var"
    else
        echo "❌ $var"
    fi
done
```

------------------------------------------------------------------------

# 🔒 Recommended Git Protection

`.gitignore` should include at least:

``` gitignore
.env
*.log
__pycache__/
*.pyc
```

Collected data should remain outside the repository:

``` text
/home/steam/jtwp-collector-data
```

------------------------------------------------------------------------

# 🛠️ Troubleshooting

## API key appears missing

Make sure `.env` has been loaded:

``` bash
set -a
source .env
set +a
```

Then:

``` bash
env | grep '^MODIO_API_KEY=' >/dev/null \
    && echo "✅ loaded" \
    || echo "❌ missing"
```

## Works manually but not under systemd

systemd does not automatically inherit your interactive shell's `.env`.

The service needs an `EnvironmentFile=` entry.

See:

``` text
Guides/SERVICES.md
```

## API requests are repeated too frequently

Check cache settings such as:

``` json
"modio_cache_ttl_hours": 24,
"ip_lookup_cache_ttl_days": 30,
"pavlov_api_host_cache_ttl_days": 30
```

------------------------------------------------------------------------

# ✅ API Setup Checklist

-   [ ] `.env` created
-   [ ] `.env` permissions set to `600`
-   [ ] `.env` ignored by Git
-   [ ] Mod.io key configured if Mod.io enrichment is enabled
-   [ ] network lookup key configured if enrichment is enabled
-   [ ] fallback key configured if required
-   [ ] RCON password variables configured
-   [ ] Discord webhook variables configured where needed
-   [ ] systemd services load the environment file
-   [ ] cache settings reviewed


---

# 🧩 Current Environment-Variable Naming

Use the exact names referenced by the current scripts. Common variables include:

```dotenv
JTWP_IP_HASH_SECRET=
MODIO_API_KEY=
PROXYCHECK_API_KEY=
IPAPI_API_KEY=
PAVLOV_API=

JTWP_DISCORD_BOT_TOKEN=
JTWP_CMD_OUTPUT_WEBHOOK_URL=
JTWP_ADMIN_WEBHOOK_URL=
JTWP_SSH_WEBHOOK_URL=
JTWP_SECURITY_WEBHOOK_URL=
JTWP_SSH_STATUS_CHANNEL_ID=
JTWP_SSH_AUTOBLOCK_WHITELIST=

PAVLOVSERVER_RCON_PASSWORD=
PAVLOVSERVER0_RCON_PASSWORD=
PAVLOVSERVER1_RCON_PASSWORD=
PAVLOVSERVER2_RCON_PASSWORD=
```

Older documentation may use generic webhook/fallback names. The source code's
`os.getenv(...)` or a server's `password_env` setting is authoritative.

Find every environment variable referenced by the Python source:

```bash
grep -RhoE 'os\.getenv\("[A-Za-z0-9_]+"' \
    --include='*.py' . \
    | sed -E 's/.*"([^"]+)".*/\1/' \
    | sort -u
```

Check which expected variables are set **without printing their values**:

```bash
for v in \
    JTWP_IP_HASH_SECRET \
    MODIO_API_KEY \
    PROXYCHECK_API_KEY \
    PAVLOV_API \
    JTWP_DISCORD_BOT_TOKEN
do
    if [[ -n "${!v:-}" ]]; then
        echo "OK      $v"
    else
        echo "MISSING $v"
    fi
done
```
