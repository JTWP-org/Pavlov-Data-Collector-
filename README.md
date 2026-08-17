# 📊 JTWP Pavlov Data Collector

A collection of tools for collecting, organizing, enriching, and
exposing data from Pavlov dedicated servers.

The project combines Pavlov log collection, player history, server
information, Mod.io data, public Pavlov server data, RCON integration,
SSH/RCON security monitoring, Discord webhooks, and ModKit-accessible
data.

> \[!NOTE\] This README intentionally contains only the **basic
> installation**, **main configuration**, and **feature overview**.
>
> Detailed setup and usage instructions are kept in the
> [`Guide/`](Guide/) folder.

------------------------------------------------------------------------

## ✨ Features

### 🎮 Pavlov Server Collection

-   Collects data from multiple Pavlov server installations.
-   Supports automatic PCVR/Shack platform detection.
-   Processes Pavlov server logs.
-   Tracks server activity and historical information.
-   Supports multiple server instances from one configuration.

### 👤 Player Data

-   Tracks player names and name history.
-   Tracks ProductIDs/UniqueIDs.
-   Tracks server activity and connection history.
-   Tracks combat statistics and weapon usage.
-   Maintains searchable player indexes.
-   Stores network information using hashed IP identifiers.

### 🌐 Network Enrichment

-   Enriches network information using configured IP lookup services.
-   Can store provider, organisation, network type, location, hosting,
    proxy/VPN/Tor, risk, and confidence information when available.
-   Caches lookup data to reduce API usage.
-   Keeps player ip's hidden and uses a hash of the ip for tracking 

### 🗺️ Mod.io Integration

-   Retrieves additional information for Pavlov maps and mods.
-   Uses the Pavlov Mod.io game ID.
-   Caches Mod.io responses.

### 🌍 Pavlov Public Server Data

-   Collects live public-server information from the configured Pavlov
    server API.
-   Can track server name, IP, mode, map, slots, server type, version,
    security state, timestamps, and network enrichment.

### 🎛️ RCON Integration

-   Uses `async-pavlov`.
-   Supports multiple server RCON configurations.
-   Provides a ModSave file-trigger bridge for the Pavlov ModKit.
-   `IN-*.json` files can trigger RCON commands.
-   Responses are written as `OUT-*.json`.
-   Command definitions and arguments are stored in JSON files.

### 🔐 SSH Monitoring

-   Watches failed SSH login attempts.
-   Records failed hosts and attempt counts.
-   Supports IP enrichment and Discord notifications.
-   Can automatically block hosts after a configured failure threshold.
-   Reuses the existing SSH failure counter.

### 🛡️ Connection / RCON Monitoring

-   Tracks connection activity.
-   Can record failed RCON activity.
-   Provides tools for cross-referencing player network history with
    SSH/RCON activity.

### 🚫 Administration Scripts

Helper scripts include tools to: - block an IP - unblock an IP - check
player connection history - look up player data - expose collector data
to Pavlov ModSave - generate a manual RCON MD5 value when needed

### 🔗 ModKit Data Access

Collector data can be exposed through symbolic links inside Pavlov's
`ModSave/JTWP/Data` directory for compatible ModKit workflows.

### 🔔 Discord Webhooks

Supported monitoring events can be sent to Discord webhooks.

------------------------------------------------------------------------

# 📦 Requirements

Recommended environment: - Ubuntu Linux - Python 3 - `python3-venv` -
`pip` - `git` - `jq` - `curl` - `dos2unix` - UFW - systemd - Pavlov
dedicated server

Install the basic packages:

``` bash
sudo apt update

sudo apt install -y \
    python3 \
    python3-venv \
    python3-pip \
    git \
    jq \
    curl \
    dos2unix \
    ufw
```

------------------------------------------------------------------------

# 🚀 Basic Installation

## 1️⃣ Clone the Repository

``` bash
mkdir -p /home/steam/jtwp-collector
cd /home/steam/jtwp-collector

git clone <YOUR_REPOSITORY_URL> Pavlov-Data-Collector-

cd /home/steam/jtwp-collector/Pavlov-Data-Collector-
```

## 2️⃣ Create the Virtual Environment

``` bash
python3 -m venv /home/steam/jtwp-collector/venv

source /home/steam/jtwp-collector/venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

## 3️⃣ Create `.env`

If `.env.example` is included:

``` bash
cp /home/steam/jtwp-collector/Pavlov-Data-Collector-/examples/env.example /home/steam/jtwp-collector/Pavlov-Data-Collector-/.env.env
nano /home/steam/jtwp-collector/Pavlov-Data-Collector-/.env
```

The `.env` file is used for private values such as: - API keys - Discord
webhook URLs - RCON passwords

Protect it:

``` bash
chmod 600 .env
```

> \[!WARNING\] Never commit the real `.env` file to Git.

## 4️⃣ Configure `config.json`

``` bash
nano /home/steam/jtwp-collector/Pavlov-Data-Collector-/config.json
```

At minimum, configure: - data path - archive path - Pavlov server log
paths - server platform settings - the features you want enabled

Example server:

``` json
{
  "log_path": "/home/steam/pavlovserver/Pavlov/Saved/Logs/",
  "platform": "auto",
  "rcon": {
    "enabled": true,
    "host": "127.0.0.1",
    "port": 9000,
    "password_env": "PAVLOVSERVER_RCON_PASSWORD"
  }
}
```

Validate:

``` bash
jq empty /home/steam/jtwp-collector/Pavlov-Data-Collector-/config.json && echo "✅ config.json is valid"
```

## 5️⃣ Create the Data Directory

``` bash
mkdir -p /home/steam/jtwp-collector-data
sudo chown -R steam:steam /home/steam/jtwp-collector-data
```

## 6️⃣ Run the Collector

``` bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-

source /home/steam/jtwp-collector/venv/bin/activate

set -a
source .env
set +a

python3 collector.py -c config.json
```

Collector data is stored under:

``` text
/home/steam/jtwp-collector-data
```

------------------------------------------------------------------------

# 📁 Project Layout

``` text
Pavlov-Data-Collector-/
├── collector.py
├── ssh_watcher.py
├── rcon_trigger_watcher.py
├── update_pavlov_api.py
├── config.json
├── .env.example
├── requirements.txt
├── rcon_commands.json
├── game_modes.json
├── default_maps.json
├── limited_ammo_types.json
│
├── scripts/
│   ├── block-ip.sh
│   ├── unblock-ip.sh
│   ├── check-player-connections.sh
│   ├── playerLookup.sh
│   ├── setup-data-links.sh
│   └── rcon-md5.sh
│
└── Guides/
    ├── RCON_COMMANDS.md
    ├── SSHblocking.MD
    ├── USEFUL_COMMANDS.md
    ├── SSHblocking.MD
    ├── API_SETUP.md
    ├── SCRIPTS.MD
    ├── SERVICES.md
    └── ...
```

------------------------------------------------------------------------

# 📚 Guides

Detailed setup belongs in the [`Guides/`](Guides/) folder.

## 🎛️ RCON

See [`Guides/RCON_COMMANDS.md`](Guides/RCON_COMMANDS.md).

Covers RCON setup, passwords, ModKit `IN-*.json` triggers, `OUT-*.json`
responses, supported commands, arguments, and the RCON watcher service.

## 🔐 SSH Auto-Blocking

See [`Guides/SSHblocking.MD`](Guides/SSHblocking.MD).

Covers the SSH watcher, failed-attempt counting, automatic blocking,
UFW, `block-ip`, `unblock-ip`, sudo permissions, testing, and
troubleshooting.

## 🧰 Useful Commands

See [`Guides/USEFUL_COMMANDS.md`](Guides/USEFUL_COMMANDS.md).

Contains collector, player lookup, JSON/`jq`, systemd, RCON, SSH, UFW,
Git, and troubleshooting commands.

## 📜 Scripts

Detailed script installation and usage should live in:

``` text
Guides/SCRIPTS.md
```

This guide can cover: - `block-ip` - `unblock-ip` -
`check-player-connections` - `playerLookup` - `setup-data-links` -
`rcon-md5`

## 🌐 API Setup

Provider-specific API setup should live in:

``` text
Guides/API_SETUP.md
```

This guide can cover: - Mod.io - IP/network lookup providers - fallback
IP lookup services - Pavlov public server API - API caching

## ⚙️ Services & Scheduling

systemd and scheduled-task instructions should live in:

``` text
Guides/SERVICES.md
```

This guide can cover: - collector service/timer - nightly collection -
SSH watcher - RCON trigger watcher - public-server updater

------------------------------------------------------------------------

# 🔑 API Keys

Some optional features require API keys.

Store private values in:

``` text
.env
```

Keep only safe placeholders in:

``` text
.env.example
```

See `Guides/API_SETUP.md` for provider-specific instructions.

------------------------------------------------------------------------

# 🔒 Security

This project may process private or security-sensitive information,
including: - raw IP addresses - API keys - RCON passwords - Discord
webhook URLs - player/network records - SSH security records

Do not commit private data.

The real `.env` should be ignored by Git, and collected data should
normally remain outside the repository:

``` text
/home/steam/jtwp-collector-data
```

------------------------------------------------------------------------

# 🔄 Updating

``` bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-

git pull

source /home/steam/jtwp-collector/venv/bin/activate

pip install -r requirements.txt
```

If services or advanced features changed, follow the appropriate
document under `Guides/`.

------------------------------------------------------------------------

# 🧪 Quick Health Check

Validate configuration:

``` bash
jq empty config.json && echo "✅ Configuration OK"
```

Check Python:

``` bash
/home/steam/jtwp-collector/venv/bin/python3 --version
```

Check the data directory:

``` bash
ls -lah /home/steam/jtwp-collector-data
```

For additional commands and diagnostics, see
[`Guides/USEFUL_COMMANDS.md`](Guides/USEFUL_COMMANDS.md).

------------------------------------------------------------------------

# 📖 Documentation Structure

``` text
README.md
    ├── Features
    ├── Requirements
    ├── Basic installation
    └── Links to detailed guides

Guides/
    ├── RCON setup
    ├── SSH blocking
    ├── API setup
    ├── Scripts
    ├── Services
    ├── Useful commands
    └── Troubleshooting
```

Keeping advanced setup in `Guides/` makes the main README easier to
maintain and much easier for a new installation to follow.

------------------------------------------------------------------------

## 🎮 JTWP Pavlov Data Collector

Built for collecting and organizing Pavlov dedicated-server data while
providing additional tooling for administration, ModKit integration,
RCON automation, and server security.
