# 🛡️ JTWP Security, Permissions & sudoers Guide

JTWP contains both read-only data tools and host-level administrative tools.
Keep those permission boundaries explicit.

## 🔐 Core Rules

1. Store secrets in `.env`, not source code.
2. Keep `.env` mode `600`.
3. Keep `JTWP_IP_HASH_SECRET` stable once data exists.
4. Keep raw IP files under the private data directory.
5. Do not grant the Discord bot unrestricted passwordless sudo.
6. Use the least Linux/Discord permissions required for each component.
7. Make destructive operations OWNER-only.
8. Test the exact `sudo -n` command as the service account before enabling it.

## 📁 `.env`

```bash
chmod 600 \
    /home/steam/jtwp-collector/Pavlov-Data-Collector-/.env
```

Do not commit it.

Check Git:

```bash
git status --short
git check-ignore .env
```

## 🔒 Private Data

```bash
sudo chown -R steam:steam /home/steam/jtwp-collector-data
sudo chmod 755 /home/steam/jtwp-collector-data
sudo chmod 700 /home/steam/jtwp-collector-data/private
```

Sensitive examples include:

```text
private/ssh_ips.json
private/ip_lookup_cache.json
JTWP_IP_HASH_SECRET
Discord bot token
Discord webhook URLs
RCON passwords
API keys
```

## 👑 Discord ADMIN vs OWNER

ADMIN should be limited to safe/read-oriented commands and explicitly
allowlisted RCON operations.

OWNER can be allowed to perform host-level maintenance such as:

- systemd control;
- collector runs;
- backup/export;
- clear-data;
- clear Pavlov mods;
- full configured RCON access.

Destructive commands should remain OWNER-only.

## 🧰 Use `/etc/sudoers.d/`

Do not edit `/etc/sudoers` with a normal text editor.

Create a dedicated file:

```bash
sudo visudo -f /etc/sudoers.d/jtwp
```

Validate afterward:

```bash
sudo visudo -cf /etc/sudoers.d/jtwp
```

## 🚫 SSH Auto-Block Permission

`ssh_watcher.py` can call:

```text
sudo -n /usr/local/bin/block-ip <IP>
```

A narrowly scoped sudoers entry can allow the installed blocker rather than all
root commands.

Example:

```sudoers
steam ALL=(root) NOPASSWD: /usr/local/bin/block-ip *
```

The blocker itself should validate that the supplied argument is an IP address.

Check what `steam` may run:

```bash
sudo -l -U steam
```

Test noninteractive execution with a documentation/test IP:

```bash
sudo -u steam sudo -n /usr/local/bin/block-ip 203.0.113.123
```

Then remove the test rule if one was created:

```bash
sudo /usr/local/bin/unblock-ip 203.0.113.123
```

## 🧹 Clear-Data Permission

The automated/destructive form is:

```text
/home/steam/jtwp-collector/Pavlov-Data-Collector-/scripts/clear-data.sh --yes
```

If the Discord OWNER command is expected to invoke it through sudo, restrict the
sudoers entry to that exact command and argument:

```sudoers
steam ALL=(root) NOPASSWD: /home/steam/jtwp-collector/Pavlov-Data-Collector-/scripts/clear-data.sh --yes
```

Test exactly what the bot/service will execute:

```bash
sudo -u steam sudo -n \
    /home/steam/jtwp-collector/Pavlov-Data-Collector-/scripts/clear-data.sh \
    --yes
```

**Do not run that test unless you actually intend to delete the collector
data.**

## 🧹 Clear Pavlov Mods

The installed helper is normally:

```text
/usr/local/bin/clear-pavlov-mods
```

It accepts a configured server ID and performs service stop/start plus mod
deletion.

Because the command has an argument and performs destructive maintenance,
review the helper's own server-ID validation before adding passwordless sudo.

Prefer exposing only this validated wrapper rather than granting general
`rm`, `systemctl` or shell access.

## ⚙️ systemd Control From Discord

The bot can be configured for actions such as:

```text
status
start
stop
restart
enable
disable
```

Avoid sudoers entries such as:

```text
steam ALL=(ALL) NOPASSWD: ALL
```

Also avoid giving passwordless access to an unrestricted shell.

The safest design is either:

- explicit service/action entries; or
- a validated root-owned wrapper that allowlists JTWP/Pavlov units and actions.

The bot's own `systemctl_actions` configuration is **not** a replacement for
Linux sudoers enforcement.

## 🔄 `restart-jtwp`

If `/usr/local/bin/restart-jtwp` is exposed to the bot, make the wrapper:

- root-owned;
- non-writable by `steam`;
- limited to the intended JTWP units;
- free of user-controlled shell evaluation.

Check:

```bash
ls -l /usr/local/bin/restart-jtwp
```

A root-owned locally administered wrapper should generally not be writable by
the service account.

## 📦 Backups and Exports

Backups and exports are created mode `600`.

The portable export includes:

```text
JTWP_IP_HASH_SECRET.txt
```

so treat the export as more sensitive than a normal data-only backup.

Do not upload it to a public Discord channel or public web directory.

## 📡 `tcpdump` / DDoS Watcher

The DDoS watcher needs packet-capture access.

Do not solve this by running every JTWP component as root.

Keep packet capture permission limited to the DDoS watcher/service mechanism you
choose.

Check how the installed service runs:

```bash
systemctl show jtwp-ddos-watcher.service \
    -p User \
    -p Group \
    -p ExecStart \
    -p AmbientCapabilities \
    -p CapabilityBoundingSet
```

If the service is intentionally configured with Linux capabilities, keep them
limited to the packet-capture requirements rather than full root privileges.

## 📓 Journal Access

`ssh_watcher.py` follows the SSH systemd journal.

Test as `steam`:

```bash
sudo -u steam journalctl -u ssh.service -n 5 --no-pager
```

The service account needs journal-read access, but does not need general root
shell access for that purpose.

## 🔗 File Ownership of Installed Helpers

Inspect locally installed root-level helpers:

```bash
ls -l \
    /usr/local/bin/block-ip \
    /usr/local/bin/unblock-ip \
    /usr/local/bin/clear-pavlov-mods \
    /usr/local/bin/restart-jtwp
```

Do not allow the `steam` service account to modify a root-executed helper.

## 🌐 Discord Webhooks

Webhook URLs are credentials.

Keep values such as:

```text
JTWP_CMD_OUTPUT_WEBHOOK_URL
JTWP_ADMIN_WEBHOOK_URL
JTWP_SSH_WEBHOOK_URL
JTWP_SECURITY_WEBHOOK_URL
```

inside `.env`.

If one is exposed, rotate/delete it in Discord and replace the stored value.

## 🔎 Secret Scan Before Publishing

Quick source scan:

```bash
grep -RniE \
    'discord(app)?\.com/api/webhooks|api_key=|BOT_TOKEN|RCON_PASSWORD' \
    /home/steam/jtwp-collector/Pavlov-Data-Collector- \
    --exclude='.env' \
    --exclude-dir='.git'
```

Also inspect Git history if a secret was ever committed. Rotating the credential
is still required even after deleting it from the current file.

## ✅ Security Checklist

```text
[ ] .env is mode 600
[ ] .env is ignored by Git
[ ] private/ is mode 700
[ ] collector data is writable by steam, not world-writable
[ ] JTWP_IP_HASH_SECRET is backed up securely
[ ] raw IP files are not published
[ ] bot token is not in source/config
[ ] webhook URLs are not hard-coded
[ ] RCON passwords are environment variables
[ ] ADMIN RCON commands are allowlisted
[ ] destructive Discord commands are OWNER-only
[ ] steam does not have NOPASSWD: ALL
[ ] root-run wrappers are not writable by steam
[ ] SSH blocker uses sudo -n and a narrow sudoers entry
[ ] packet-capture permission is limited to DDoS monitoring
[ ] exports containing the hash secret are stored securely
```
