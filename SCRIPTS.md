# 🧰 JTWP Scripts Guide

This guide covers installation and basic usage of the helper scripts
included in:

``` text
Pavlov-Data-Collector-/scripts/
```

The main project README stays focused on basic installation.
Script-specific setup belongs here.

------------------------------------------------------------------------

# 📁 Included Scripts

  ------------------------------------------------------------------------------------
  Script                          Installed Command            Purpose
  ------------------------------- ---------------------------- -----------------------
  `block-ip.sh`                   `block-ip`                   Blocks all connections
                                                               to/from an IP using UFW

  `unblock-ip.sh`                 `unblock-ip`                 Removes the UFW block
                                                               for an IP

  `check-player-connections.sh`   `check-player-connections`   Checks whether a
                                                               player's known network
                                                               activity appears in
                                                               SSH/RCON connection
                                                               data

  `playerLookup.sh`               `playerLookup`               Dumps collected data
                                                               for a player name

  `setup-data-links.sh`           `setup-data-links`           Creates ModSave links
                                                               to collector data

  `rcon-md5.sh`                   `rcon-md5`                   Generates the MD5 value
                                                               used when a manual RCON
                                                               MD5 value is required
  ------------------------------------------------------------------------------------

------------------------------------------------------------------------

# 🚀 Install the Scripts

Enter the scripts directory:

``` bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-/scripts
```

## 1️⃣ Fix Linux Line Endings

If scripts were edited on Windows:

``` bash
dos2unix *.sh
```

This prevents errors such as:

``` text
/bin/bash^M: bad interpreter
```

To force Linux line endings in Git, add this to `.gitattributes`:

``` gitattributes
*.sh text eol=lf
```

------------------------------------------------------------------------

## 2️⃣ Make the Scripts Executable

``` bash
chmod +x *.sh
```

Check:

``` bash
ls -l *.sh
```

Executable scripts should show permissions similar to:

``` text
-rwxr-xr-x
```

------------------------------------------------------------------------

## 3️⃣ Install Commands in `/usr/local/bin`

``` bash
sudo install -m 755 block-ip.sh /usr/local/bin/block-ip
sudo install -m 755 unblock-ip.sh /usr/local/bin/unblock-ip
sudo install -m 755 check-player-connections.sh /usr/local/bin/check-player-connections
sudo install -m 755 playerLookup.sh /usr/local/bin/playerLookup
sudo install -m 755 setup-data-links.sh /usr/local/bin/setup-data-links
sudo install -m 755 rcon-md5.sh /usr/local/bin/rcon-md5
```

This lets the commands be run without typing the full repository path.

------------------------------------------------------------------------

# ✅ Verify Installation

``` bash
for cmd in \
    block-ip \
    unblock-ip \
    check-player-connections \
    playerLookup \
    setup-data-links \
    rcon-md5
do
    command -v "$cmd" || echo "❌ MISSING: $cmd"
done
```

Expected paths should normally be:

``` text
/usr/local/bin/block-ip
/usr/local/bin/unblock-ip
/usr/local/bin/check-player-connections
/usr/local/bin/playerLookup
/usr/local/bin/setup-data-links
/usr/local/bin/rcon-md5
```

------------------------------------------------------------------------

# 🚫 `block-ip`

Blocks an IP using UFW.

Usage:

``` bash
sudo block-ip <IP>
```

Example:

``` bash
sudo block-ip 203.0.113.123
```

The current blocker creates inbound and outbound deny rules.

Check:

``` bash
sudo ufw status
```

For automatic SSH blocking, `ssh_watcher.py` calls:

``` bash
sudo -n /usr/local/bin/block-ip <IP>
```

See:

``` text
Guides/SSHblocking.MD
```

for the required sudo configuration and automatic-block setup.

------------------------------------------------------------------------

# 🔓 `unblock-ip`

Removes the firewall rules created for an IP.

Usage:

``` bash
sudo unblock-ip <IP>
```

Example:

``` bash
sudo unblock-ip 203.0.113.123
```

Then verify:

``` bash
sudo ufw status
```

------------------------------------------------------------------------

# 🔎 `playerLookup`

Looks up a player using the collector's player-name index and prints the
player's collected records.

Usage:

``` bash
playerLookup "<PLAYER_NAME>"
```

Example:

``` bash
playerLookup "oneSALTycrack3r"
```

The script uses the player index under:

``` text
/home/steam/jtwp-collector-data/players/index/
```

and records under:

``` text
/home/steam/jtwp-collector-data/players/records/
```

Names containing spaces should be quoted.

------------------------------------------------------------------------

# 🕵️ `check-player-connections`

Cross-references a player's collected network information with
security/connection records.

Usage:

``` bash
check-player-connections "<PLAYER_NAME>"
```

Example:

``` bash
check-player-connections "ExamplePlayer"
```

This is intended to help determine whether network information
associated with a collected player also appears in SSH or RCON
connection records.

> \[!NOTE\] Results are correlations in collected server data. They
> should not automatically be treated as proof that a particular person
> performed an SSH/RCON attempt.

------------------------------------------------------------------------

# 🔗 `setup-data-links`

Creates links from collector data into Pavlov's ModSave area so
compatible files can be accessed from ModKit workflows.

The collector source directories are:

``` text
/home/steam/jtwp-collector-data/servers
/home/steam/jtwp-collector-data/players
/home/steam/jtwp-collector-data/global
```

The ModSave destination follows the configured server path, for example:

``` text
/home/steam/pavlovserver1/Pavlov/Saved/Config/ModSave/JTWP/Data
```

Run:

``` bash
setup-data-links
```

If your version of the script contains configurable paths, edit those
settings in the script before running it.

Check links with:

``` bash
ls -lah /home/steam/pavlovserver1/Pavlov/Saved/Config/ModSave/JTWP/Data
```

------------------------------------------------------------------------

# 🔐 `rcon-md5`

Generates an MD5 hash for an RCON password when a manual MD5
representation is required by your RCON workflow.

Usage:

``` bash
rcon-md5
```

or, if your script accepts the password as an argument:

``` bash
rcon-md5 "password"
```

> \[!WARNING\] Avoid putting real passwords directly on a shared shell
> command line because shell history and process listings may expose
> them. Interactive input or environment variables are safer.

See:

``` text
Guides/RCON_COMMANDS.md
```

for the full RCON setup.

------------------------------------------------------------------------

# 🔄 Updating Installed Scripts

Editing a script in the repository does **not** automatically update its
`/usr/local/bin` copy.

After changing a script, reinstall it.

Example:

``` bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-/scripts

dos2unix block-ip.sh
chmod +x block-ip.sh

sudo install -m 755 block-ip.sh /usr/local/bin/block-ip
```

For all scripts:

``` bash
sudo install -m 755 block-ip.sh /usr/local/bin/block-ip
sudo install -m 755 unblock-ip.sh /usr/local/bin/unblock-ip
sudo install -m 755 check-player-connections.sh /usr/local/bin/check-player-connections
sudo install -m 755 playerLookup.sh /usr/local/bin/playerLookup
sudo install -m 755 setup-data-links.sh /usr/local/bin/setup-data-links
sudo install -m 755 rcon-md5.sh /usr/local/bin/rcon-md5
```

------------------------------------------------------------------------

# 🧪 Syntax Checks

Check every shell script:

``` bash
for file in *.sh; do
    printf '%-35s ' "$file"

    if bash -n "$file"; then
        echo "✅ OK"
    else
        echo "❌ ERROR"
    fi
done
```

------------------------------------------------------------------------

# 🛠️ Common Problems

## `Permission denied`

Run:

``` bash
chmod +x script-name.sh
```

## `/bin/bash^M: bad interpreter`

Run:

``` bash
dos2unix script-name.sh
```

## Installed command still behaves like the old version

Reinstall the repository copy:

``` bash
sudo install -m 755 script-name.sh /usr/local/bin/command-name
```

## `command not found`

Check:

``` bash
command -v command-name
```

Then confirm the file exists:

``` bash
ls -l /usr/local/bin/command-name
```

------------------------------------------------------------------------

# 🔒 Permissions

Security-sensitive helper scripts installed under `/usr/local/bin`
should normally be owned by root and not writable by the `steam`
account.

Check:

``` bash
ls -l \
    /usr/local/bin/block-ip \
    /usr/local/bin/unblock-ip
```

For SSH auto-block sudo configuration, follow:

``` text
Guides/SSHblocking.MD
```
