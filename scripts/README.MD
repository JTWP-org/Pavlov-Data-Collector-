# 🧰 JTWP Collector Helper Scripts

This folder contains helper scripts for the **JTWP Pavlov Data
Collector**.

## 📜 Included Scripts

  -----------------------------------------------------------------------
  Script                              Purpose
  ----------------------------------- -----------------------------------
  `block-ip.sh`                       Takes a raw player IP and blocks
                                      inbound/outbound connections
                                      involving it using UFW.

  `unblock-ip.sh`                     Takes a raw player IP and removes
                                      its UFW block rules.

  `check-player-connections.sh`       Checks whether known player IP
                                      hashes appear in collected SSH or
                                      RCON connection data.

  `playerLookup.sh`                   Takes a player name and dumps the
                                      JSON data associated with that
                                      player.

  `setup-data-links.sh`               Exposes configured collector
                                      folders through symlinks under
                                      Pavlov's `ModSave/JTWP/Data`
                                      directory.
  -----------------------------------------------------------------------

## 📦 Make the Scripts Executable

From the repository root:

``` bash
chmod +x scripts/*.sh
```

Verify:

``` bash
ls -lah scripts/
```

## 🚀 Install the Commands System-Wide

Use `/usr/local/bin/` for locally managed commands:

``` bash
sudo install -m 755 scripts/block-ip.sh /usr/local/bin/block-ip
sudo install -m 755 scripts/unblock-ip.sh /usr/local/bin/unblock-ip
sudo install -m 755 scripts/check-player-connections.sh /usr/local/bin/check-player-connections
sudo install -m 755 scripts/playerLookup.sh /usr/local/bin/playerLookup
sudo install -m 755 scripts/setup-data-links.sh /usr/local/bin/setup-data-links
```

> \[!NOTE\] The repository files keep their `.sh` extension. The
> installed commands omit `.sh` for convenience.

Verify:

``` bash
which block-ip
which unblock-ip
which check-player-connections
which playerLookup
which setup-data-links
```

Expected paths are under `/usr/local/bin/`.

## 🧱 block-ip.sh

Blocks inbound and outbound traffic associated with a supplied raw IP:

``` bash
sudo block-ip 1.2.3.4
```

Check UFW:

``` bash
sudo ufw status numbered
```

> \[!WARNING\] Do not block the address of your current SSH client or
> you may disconnect yourself.

## 🔓 unblock-ip.sh

Removes the corresponding UFW rules:

``` bash
sudo unblock-ip 1.2.3.4
```

## 🔎 check-player-connections.sh

Checks collected SSH and RCON data against known Pavlov player IP
hashes.

It can identify players associated with failed SSH authentication,
successful RCON connections, and failed RCON authentication attempts.

``` bash
check-player-connections
```

It reads collector data under:

``` text
/home/steam/jtwp-collector-data/
```

> \[!IMPORTANT\] Player, SSH, and RCON records must use the same
> `JTWP_IP_HASH_SECRET` for correlation to work.

## 👤 playerLookup.sh

Looks up a player by name and displays the player's stored JSON records:

``` bash
playerLookup oneSALTycrack3r
```

Quote names containing spaces:

``` bash
playerLookup "Example Player"
```

It uses:

``` text
/home/steam/jtwp-collector-data/players/index/
/home/steam/jtwp-collector-data/players/records/
```

## 🔗 setup-data-links.sh

Creates symbolic links from collector data into Pavlov's ModSave
directory.

Expected layout:

``` text
/home/steam/pavlovserver1/Pavlov/Saved/Config/ModSave/JTWP/Data/
├── servers -> /home/steam/jtwp-collector-data/servers
├── players -> /home/steam/jtwp-collector-data/players
└── global  -> /home/steam/jtwp-collector-data/global
```

Run:

``` bash
setup-data-links
```

Or directly from the repo:

``` bash
./scripts/setup-data-links.sh
```

Settings are configured near the top of the script, for example:

``` bash
SOURCE_ROOT="/home/steam/jtwp-collector-data"
DEST_ROOT="/home/steam/pavlovserver1/Pavlov/Saved/Config/ModSave/JTWP/Data"

LINKS=(
    "servers"
    "players"
    "global"
)
```

> \[!CAUTION\] Only expose data the Pavlov mod needs. Avoid exposing
> private raw-IP mappings unless intentional.

## 🔄 Updating Installed Scripts

The Git repository remains the source of truth. After:

``` bash
git pull
```

reinstall the commands:

``` bash
sudo install -m 755 scripts/block-ip.sh /usr/local/bin/block-ip
sudo install -m 755 scripts/unblock-ip.sh /usr/local/bin/unblock-ip
sudo install -m 755 scripts/check-player-connections.sh /usr/local/bin/check-player-connections
sudo install -m 755 scripts/playerLookup.sh /usr/local/bin/playerLookup
sudo install -m 755 scripts/setup-data-links.sh /usr/local/bin/setup-data-links
```

Updating files under `scripts/` does not automatically update their
installed copies in `/usr/local/bin`.

## 🧪 Quick Verification

``` bash
for cmd in block-ip unblock-ip check-player-connections playerLookup setup-data-links; do
    command -v "$cmd" || echo "MISSING: $cmd"
done
```

## 📁 Recommended Layout

``` text
scripts/
├── README.md
├── block-ip.sh
├── unblock-ip.sh
├── check-player-connections.sh
├── playerLookup.sh
└── setup-data-links.sh
```

## 🔐 Security Notes

-   Treat raw player IPs as private data.
-   Keep `JTWP_IP_HASH_SECRET` private and consistent.
-   Run `block-ip` and `unblock-ip` with `sudo`.
-   Review folders exposed by `setup-data-links`.
-   Never commit `.env`, API keys, webhook secrets, or credentials.
