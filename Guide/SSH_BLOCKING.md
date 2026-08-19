# 🔐 JTWP SSH Auto-Blocking Guide

This guide explains how the JTWP SSH protection works, how
`ssh_watcher.py` detects repeated failed SSH logins, how it calls
`block-ip`, how UFW blocks the offending address, and how to verify or
undo a block.

------------------------------------------------------------------------

## 🧭 How It Works

The SSH protection uses the **existing failed-attempt counter**
maintained by `ssh_watcher.py`.

``` text
Failed SSH login
       ↓
ssh_watcher.py detects the event
       ↓
failed_attempts increases
       ↓
Is failed_attempts > 20?
       │
   No  │  Yes
   ↓   │   ↓
Record │ /usr/local/bin/block-ip <IP>
only   │   ↓
       │  UFW
       │   ↓
       │ Incoming + outgoing traffic blocked
       │   ↓
       └ blocked=true saved in failed_hosts.json
```

> \[!IMPORTANT\] With `"auto_block_after": 20`, the current watcher
> blocks the address when it goes **over 20 failures**, meaning the
> **21st failed attempt** triggers the block.

There is no separate SSH failure counter and no second SSH monitoring
service. Auto-blocking reuses the data already collected by
`ssh_watcher.py`.

------------------------------------------------------------------------

## 📁 Important Files

  -----------------------------------------------------------------------
  File                                Purpose
  ----------------------------------- -----------------------------------
  `ssh_watcher.py`                    Watches SSH failures and maintains
                                      host statistics

  `config.json`                       Controls the SSH watcher and
                                      auto-block settings

  `/usr/local/bin/block-ip`           Adds UFW deny rules for an IP

  `/usr/local/bin/unblock-ip`         Removes the UFW deny rules

  `failed_hosts.json`                 Stores failed-attempt counts and
                                      blocking state

  `autoblock.log` / service journal   Useful for troubleshooting blocking
                                      activity
  -----------------------------------------------------------------------

The SSH host database is located at:

``` text
/home/steam/jtwp-collector-data/global/ssh/failed_hosts.json
```

The project is located at:

``` text
/home/steam/jtwp-collector/Pavlov-Data-Collector-
```

------------------------------------------------------------------------

## ⚙️ `config.json` Setup

Inside the existing `"ssh_watcher"` object, configure:

``` json
"ssh_watcher": {
  "units": [
    "ssh.service",
    "sshd.service"
  ],
  "enrich_ips": true,
  "include_invalid_user_events": false,
  "webhook_timeout_seconds": 8,
  "webhook_retries": 2,
  "auto_block_enabled": true,
  "auto_block_after": 20,
  "auto_block_command": "/usr/local/bin/block-ip",
  "auto_block_use_sudo": true,
  "auto_block_private_ips": false
}
```

### 📝 What the settings mean

  -----------------------------------------------------------------------
  Setting                             Meaning
  ----------------------------------- -----------------------------------
  `auto_block_enabled`                Turns automatic blocking on or off

  `auto_block_after`                  Number of failures allowed before
                                      blocking; `20` means block on
                                      attempt 21

  `auto_block_command`                Command the watcher executes to
                                      block the IP

  `auto_block_use_sudo`               Makes the watcher call the blocker
                                      through `sudo -n`

  `auto_block_private_ips`            When `false`, private/local
                                      addresses are protected from
                                      automatic blocking
  -----------------------------------------------------------------------

Validate the configuration after editing:

``` bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-

jq empty config.json && echo "✅ VALID JSON"
```

Check only the auto-block settings:

``` bash
jq '.ssh_watcher | {
  auto_block_enabled,
  auto_block_after,
  auto_block_command,
  auto_block_use_sudo,
  auto_block_private_ips
}' config.json
```

Expected output:

``` json
{
  "auto_block_enabled": true,
  "auto_block_after": 20,
  "auto_block_command": "/usr/local/bin/block-ip",
  "auto_block_use_sudo": true,
  "auto_block_private_ips": false
}
```

------------------------------------------------------------------------

## 🚫 `block-ip` Script

The blocker accepts an IP as its argument:

``` bash
sudo /usr/local/bin/block-ip 203.0.113.123
```

The script validates the IP and then adds UFW rules similar to:

``` bash
ufw deny from "$IP" to any
ufw deny out to "$IP"
```

This means the selected address is blocked from making incoming
connections to the server and the server is also prevented from
initiating outgoing connections to it.

### 🛡️ SSH-session safety

The script checks `SSH_CONNECTION` when that environment variable is
available:

``` bash
SSH_IP=""

if [[ -n "${SSH_CONNECTION:-}" ]]; then
    SSH_IP="${SSH_CONNECTION%% *}"
fi

if [[ -n "$SSH_IP" && "$IP" == "$SSH_IP" ]]; then
    echo "ERROR: $IP is the IP of your current SSH connection."
    echo "Blocking it would disconnect you."
    exit 1
fi
```

Using `${SSH_CONNECTION:-}` is important because the variable may not
exist when the script is started by systemd/sudo.

------------------------------------------------------------------------

## 🔓 `unblock-ip` Script

To remove a block manually:

``` bash
sudo /usr/local/bin/unblock-ip 203.0.113.123
```

If you want the `steam` account to call this through passwordless sudo
as well, grant permission for both helper scripts.

------------------------------------------------------------------------

## 🔑 Sudo Permission

`ssh_watcher.py` runs as the `steam` user, while UFW requires elevated
privileges.

The watcher therefore needs permission to run `block-ip` without an
interactive password.

A dedicated sudoers file is recommended:

``` bash
sudo visudo -f /etc/sudoers.d/zz-jtwp-block-ip
```

Add:

``` sudoers
steam ALL=(root) NOPASSWD: /usr/local/bin/block-ip *
steam ALL=(root) NOPASSWD: /usr/local/bin/unblock-ip *
```

Validate the sudo configuration:

``` bash
sudo visudo -c
```

Check the permissions assigned to `steam`:

``` bash
sudo -l -U steam
```

You should see `NOPASSWD` entries for the blocker and unblocker.

> \[!CAUTION\] Always use `visudo` when changing sudo configuration. It
> performs syntax validation and helps prevent a broken sudoers file
> from locking you out of administrative access.

------------------------------------------------------------------------

## 🧪 Test the Permission Exactly Like the Watcher

Test `block-ip` as `steam` with non-interactive sudo:

``` bash
sudo -u steam sudo -n /usr/local/bin/block-ip 203.0.113.123
```

The important part is `-n`. It tells sudo **never to ask for a
password**.

If permission is wrong, you may see:

``` text
sudo: interactive authentication is required
```

If the command succeeds, inspect UFW:

``` bash
sudo ufw status
```

Then remove the test rule:

``` bash
sudo /usr/local/bin/unblock-ip 203.0.113.123
```

------------------------------------------------------------------------

## 🔥 Checking UFW

Show current firewall rules:

``` bash
sudo ufw status
```

Show numbered rules:

``` bash
sudo ufw status numbered
```

A blocked address may appear like:

``` text
Anywhere       DENY        203.0.113.123
203.0.113.123  DENY OUT    Anywhere
```

This indicates both directions were blocked.

Show verbose firewall information:

``` bash
sudo ufw status verbose
```

------------------------------------------------------------------------

## 👀 Check the SSH Watcher

Check whether the service is running:

``` bash
sudo systemctl status jtwp-ssh-watcher --no-pager
```

You want:

``` text
Active: active (running)
```

Restart after changing `ssh_watcher.py` or `config.json`:

``` bash
sudo systemctl restart jtwp-ssh-watcher
```

Follow its output live:

``` bash
sudo journalctl -u jtwp-ssh-watcher -f
```

Show the most recent 100 lines:

``` bash
sudo journalctl -u jtwp-ssh-watcher -n 100 --no-pager
```

Search specifically for automatic blocks:

``` bash
sudo journalctl -u jtwp-ssh-watcher --no-pager | grep -i "AUTO-BLOCKED"
```

A successful automatic block should produce output similar to:

``` text
AUTO-BLOCKED SSH host abc123... after 21 failures
```

------------------------------------------------------------------------

## 📊 Inspect Failed SSH Hosts

Pretty-print the entire database:

``` bash
jq . /home/steam/jtwp-collector-data/global/ssh/failed_hosts.json
```

Show the failure count for every host:

``` bash
jq 'to_entries[] | {
  ip_hash: .key,
  failed_attempts: .value.failed_attempts
}' /home/steam/jtwp-collector-data/global/ssh/failed_hosts.json
```

Show only hosts with more than 20 failed attempts:

``` bash
jq 'to_entries[] |
  select((.value.failed_attempts // 0) > 20) |
  {
    ip_hash: .key,
    failed_attempts: .value.failed_attempts,
    blocked: (.value.blocked // false),
    blocked_at: (.value.blocked_at // null)
  }' /home/steam/jtwp-collector-data/global/ssh/failed_hosts.json
```

Show only hosts marked as blocked:

``` bash
jq 'to_entries[] |
  select(.value.blocked == true) |
  {
    ip_hash: .key,
    failed_attempts: .value.failed_attempts,
    blocked: .value.blocked,
    blocked_at: .value.blocked_at,
    blocked_after_attempts: .value.blocked_after_attempts
  }' /home/steam/jtwp-collector-data/global/ssh/failed_hosts.json
```

A blocked record should look conceptually like:

``` json
{
  "failed_attempts": 21,
  "blocked": true,
  "blocked_at": "2026-08-17T03:30:00Z",
  "blocked_after_attempts": 21
}
```

------------------------------------------------------------------------

## 🧪 Safe End-to-End Test

You can verify each component separately rather than deliberately
generating large numbers of failed SSH logins.

### 1️⃣ Validate the JSON

``` bash
jq empty config.json && echo "✅ CONFIG OK"
```

### 2️⃣ Confirm auto-blocking is enabled

``` bash
jq '.ssh_watcher.auto_block_enabled' config.json
```

Expected:

``` text
true
```

### 3️⃣ Check the blocker exists

``` bash
command -v block-ip
```

Expected:

``` text
/usr/local/bin/block-ip
```

### 4️⃣ Check sudo permission

``` bash
sudo -u steam sudo -n /usr/local/bin/block-ip 203.0.113.123
```

### 5️⃣ Confirm UFW received the rule

``` bash
sudo ufw status
```

### 6️⃣ Remove the test rule

``` bash
sudo /usr/local/bin/unblock-ip 203.0.113.123
```

### 7️⃣ Restart the watcher

``` bash
sudo systemctl restart jtwp-ssh-watcher
```

### 8️⃣ Follow the watcher

``` bash
sudo journalctl -u jtwp-ssh-watcher -f
```

If all of these work, the individual components required for automatic
blocking are configured correctly.

------------------------------------------------------------------------

## 🧯 Troubleshooting

### ❌ `sudo: interactive authentication is required`

Check:

``` bash
sudo -l -U steam
```

Verify the appropriate `NOPASSWD` rule exists.

------------------------------------------------------------------------

### ❌ `/usr/local/bin/block-ip: command not found`

Install the repo script:

``` bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-/scripts

dos2unix block-ip.sh
chmod +x block-ip.sh

sudo install -m 755 block-ip.sh /usr/local/bin/block-ip
```

For the unblocker:

``` bash
dos2unix unblock-ip.sh
chmod +x unblock-ip.sh

sudo install -m 755 unblock-ip.sh /usr/local/bin/unblock-ip
```

------------------------------------------------------------------------

### ❌ `/bin/bash^M: bad interpreter`

The script has Windows CRLF line endings.

Fix it:

``` bash
dos2unix block-ip.sh
dos2unix unblock-ip.sh
```

Or:

``` bash
sed -i 's/\r$//' block-ip.sh
sed -i 's/\r$//' unblock-ip.sh
```

To prevent this in Git, add:

``` gitattributes
*.sh text eol=lf
```

to `.gitattributes`.

------------------------------------------------------------------------

### ❌ `SSH_CONNECTION: unbound variable`

When using:

``` bash
set -euo pipefail
```

do not directly assume `SSH_CONNECTION` exists.

Use:

``` bash
if [[ -n "${SSH_CONNECTION:-}" ]]; then
    SSH_IP="${SSH_CONNECTION%% *}"
fi
```

------------------------------------------------------------------------

### ❌ Auto-block settings show `null`

Example:

``` bash
jq '.ssh_watcher.auto_block_enabled' config.json
```

returning:

``` text
null
```

means that key is missing from the `"ssh_watcher"` object.

Add the auto-block settings and restart the service.

------------------------------------------------------------------------

### ❌ JSON parse error

Validate:

``` bash
jq . config.json
```

Show a section with line numbers:

``` bash
nl -ba config.json | sed -n '50,90p'
```

If the JSON was copied from a rich-text source and contains non-breaking
spaces, clean them with:

``` bash
sed -i 's/\xC2\xA0/ /g' config.json
```

Then validate again:

``` bash
jq empty config.json && echo "✅ VALID JSON"
```

------------------------------------------------------------------------

## 🧰 Useful Commands Cheat Sheet

  --------------------------------------------------------------------------------------------------------------
  Task                                Command
  ----------------------------------- --------------------------------------------------------------------------
  Watch SSH service                   `sudo journalctl -u jtwp-ssh-watcher -f`

  Restart watcher                     `sudo systemctl restart jtwp-ssh-watcher`

  Check watcher                       `sudo systemctl status jtwp-ssh-watcher --no-pager`

  View UFW                            `sudo ufw status`

  Number UFW rules                    `sudo ufw status numbered`

  Block IP                            `sudo block-ip <IP>`

  Unblock IP                          `sudo unblock-ip <IP>`

  Check sudo permission               `sudo -l -U steam`

  Validate config                     `jq empty config.json`

  View SSH host data                  `jq . /home/steam/jtwp-collector-data/global/ssh/failed_hosts.json`

  Find auto-block log entries         `sudo journalctl -u jtwp-ssh-watcher --no-pager \| grep -i AUTO-BLOCKED`
  --------------------------------------------------------------------------------------------------------------

------------------------------------------------------------------------

## 🔒 Security Notes

-   Keep SSH available only where you actually need it.
-   Use SSH keys where practical.
-   Do not disable your current SSH access until you have confirmed
    another administrative path works.
-   Keep trusted management addresses out of automatic blocking.
-   Review UFW periodically for stale or accidental rules.
-   Keep `/usr/local/bin/block-ip` owned by root and non-writable by the
    `steam` user, because `steam` is allowed to execute it as root.
-   Keep the sudo permission narrowly limited to the specific helper
    commands rather than granting broad passwordless root access.

Check ownership and permissions with:

``` bash
ls -l /usr/local/bin/block-ip /usr/local/bin/unblock-ip
```

A typical secure setup is that the files are owned by `root:root` and
are executable but not writable by `steam`.

------------------------------------------------------------------------

## ✅ Final Flow

Once configured, normal operation is automatic:

``` text
Attacker fails SSH authentication
              ↓
      ssh_watcher.py
              ↓
 existing failed_attempts counter
              ↓
      attempts become 21
              ↓
 sudo -n /usr/local/bin/block-ip <IP>
              ↓
             UFW
        ↙           ↘
   DENY inbound   DENY outbound
              ↓
 failed_hosts.json updated
              ↓
        blocked = true
```

No second watcher and no duplicate failed-attempt counter are required.

---

## 📚 Documentation Ownership

For installation/update order use `INSTALL_AND_UPDATE.md`. For systemd use
`SERVICES.md`; secrets/API values use `API_SETUP.md`; helper installation uses
`SCRIPTS.md`; quick commands use `USEFUL_COMMANDS.md`. This guide should remain
focused on its named component so setup instructions do not drift between files.
