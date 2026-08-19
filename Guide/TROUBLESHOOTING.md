# 🧯 JTWP Troubleshooting Guide

Use this guide when a component is failing and you need to identify the actual
cause before changing configuration.

## 1. Start With the Exact Error

Service status:

```bash
sudo systemctl status UNIT.service --no-pager -l
```

Recent journal:

```bash
sudo journalctl -u UNIT.service -n 100 --no-pager
```

Follow live:

```bash
sudo journalctl -u UNIT.service -n 100 -f
```

Show the installed unit:

```bash
sudo systemctl cat UNIT.service
```

## 2. Python Syntax / Import Errors

Validate one file:

```bash
/home/steam/jtwp-collector/venv/bin/python3 \
    -m py_compile FILE.py
```

Validate the project:

```bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-

/home/steam/jtwp-collector/venv/bin/python3 \
    -m compileall -q .
```

Typical errors:

```text
IndentationError
SyntaxError
NameError
ModuleNotFoundError
```

Do not keep restarting a service with a syntax error. Stop it first, fix the
file, compile it, then restart.

## 3. `config.json` Not Found

Symptom:

```text
[Errno 2] No such file or directory: 'config.json'
```

Prefer an absolute config path:

```bash
/home/steam/jtwp-collector/venv/bin/python3 \
    /home/steam/jtwp-collector/Pavlov-Data-Collector-/collector.py \
    -c /home/steam/jtwp-collector/Pavlov-Data-Collector-/config.json
```

Check systemd's working directory:

```bash
systemctl show UNIT.service -p WorkingDirectory -p ExecStart
```

## 4. Invalid JSON

```bash
jq empty config.json
jq empty active.json
jq empty custom_commands.json
jq empty resource/rcon_commands.json
```

Or:

```bash
python3 -m json.tool config.json >/dev/null
```

## 5. `.env` / Missing Secret

Check that a variable exists without printing it:

```bash
[[ -n "${JTWP_IP_HASH_SECRET:-}" ]] \
    && echo "loaded" \
    || echo "missing"
```

Check the systemd unit:

```bash
systemctl show UNIT.service -p EnvironmentFiles -p Environment
```

Services that depend on secrets should normally use the project `.env`.

## 6. Data Directory Permission Errors

Common symptom:

```text
PermissionError: [Errno 13] Permission denied
```

Inspect every path component:

```bash
namei -l /home/steam/jtwp-collector-data/private
```

Inspect ownership:

```bash
ls -ld \
    /home/steam/jtwp-collector-data \
    /home/steam/jtwp-collector-data/private
```

Expected collector ownership is normally:

```text
steam:steam
```

Repair the collector tree when appropriate:

```bash
sudo chown -R steam:steam /home/steam/jtwp-collector-data
sudo chmod 755 /home/steam/jtwp-collector-data
sudo chmod 700 /home/steam/jtwp-collector-data/private
```

Avoid `chmod 777`.

## 7. Atomic `.tmp` / `os.replace` Failures

Example:

```text
FileNotFoundError:
...ip_lookup_cache.json.tmp -> ...ip_lookup_cache.json
```

Possible causes:

- two writers use the exact same temporary filename;
- the directory was deleted while a process was writing;
- permissions/ownership changed;
- one process moved the temp file before another did.

Current shared JSON writers should use unique same-directory temporary files
before `os.replace`.

Also verify:

```bash
find /home/steam/jtwp-collector-data -name '*.tmp' -ls
```

and check whether multiple services write the same JSON.

## 8. Collector Won't Stay Stopped

If systemd says:

```text
Stopping 'jtwp-collector.service', but its triggering units are still active:
jtwp-collector.timer
```

stop the timer too:

```bash
sudo systemctl stop jtwp-collector.timer
sudo systemctl stop jtwp-collector.service
```

Disable the timer across reboots:

```bash
sudo systemctl disable --now jtwp-collector.timer
```

## 9. Service Restart Loop

Stop it before debugging:

```bash
sudo systemctl stop UNIT.service
```

Clear recorded failure after fixing the cause:

```bash
sudo systemctl reset-failed UNIT.service
```

Then:

```bash
sudo systemctl start UNIT.service
sudo journalctl -u UNIT.service -n 100 -f
```

## 10. RCON Connection Refused

Check the configured port:

```bash
jq '.servers[] | {log_path, rcon}' config.json
```

Check listeners:

```bash
ss -lntp | grep -E ':9000|:9100|:9200'
```

Raw local test:

```bash
nc 127.0.0.1 PORT
```

If the game server itself is inactive, the RCON port may not be listening.

## 11. Missing RCON Password

Check the configured environment-variable name:

```bash
jq -r '.servers[] | .rcon.password_env' config.json
```

Then verify each variable exists without printing it:

```bash
for v in \
    PAVLOVSERVER_RCON_PASSWORD \
    PAVLOVSERVER0_RCON_PASSWORD \
    PAVLOVSERVER1_RCON_PASSWORD
do
    [[ -n "${!v:-}" ]] \
        && echo "OK $v" \
        || echo "MISSING $v"
done
```

## 12. Discord Bot Offline / Won't Start

Check:

```bash
sudo systemctl status jtwp-discord-bot.service --no-pager -l
sudo journalctl -u jtwp-discord-bot.service -n 100 --no-pager
```

Confirm the expected file exists:

```bash
ls -l \
    /home/steam/jtwp-collector/Pavlov-Data-Collector-/discord_bot.py
```

Compile it:

```bash
/home/steam/jtwp-collector/venv/bin/python3 \
    -m py_compile \
    /home/steam/jtwp-collector/Pavlov-Data-Collector-/discord_bot.py
```

Check the token variable exists without displaying it:

```bash
set -a
source /home/steam/jtwp-collector/Pavlov-Data-Collector-/.env
set +a

[[ -n "${JTWP_DISCORD_BOT_TOKEN:-}" ]] \
    && echo "token loaded" \
    || echo "token missing"
```

## 13. Discord HTTP Errors

Common meanings:

```text
401 / 403  credential/permission problem
404        channel/message/webhook/resource no longer exists
429        rate limited
```

Do not paste bot tokens or webhook URLs into troubleshooting logs.

If a webhook or bot token was exposed, rotate it.

## 14. SSH Watcher Doesn't See Journal Events

The service account must be able to read the system journal.

Check:

```bash
sudo -u steam journalctl -u ssh.service -n 5 --no-pager
```

If permission is denied, review the SSH watcher service permissions and group
membership.

After adding `steam` to a journal-reading group, restart the service/session.

## 15. SSH Auto-Block Does Not Work

Check watcher configuration:

```bash
jq '.ssh_watcher' config.json
```

Test the sudo command exactly as the watcher does:

```bash
sudo -u steam sudo -n /usr/local/bin/block-ip 203.0.113.123
```

Use a documentation/test address, not your current SSH client address.

Check sudoers:

```bash
sudo -l -U steam
```

Check UFW:

```bash
sudo ufw status numbered
```

## 16. DDoS Watcher / `tcpdump`

Check tcpdump:

```bash
command -v tcpdump
```

Check interface/listening configuration:

```bash
jq '.ddos_watcher' config.json
```

Check service journal:

```bash
sudo journalctl -u jtwp-ddos-watcher.service -n 100 --no-pager
```

The watcher requires packet-capture permissions. See
`SECURITY_AND_SUDOERS.md`.

## 17. Mod.io / IP Enrichment Failures

Look for:

```text
403 Forbidden
ConnectTimeout
ReadTimeout
```

Confirm API-key variables exist without printing them:

```bash
for v in MODIO_API_KEY PROXYCHECK_API_KEY IPAPI_API_KEY; do
    [[ -n "${!v:-}" ]] \
        && echo "SET $v" \
        || echo "UNSET $v"
done
```

A provider failure should not be copied into public output if it contains a raw
IP or secret-bearing URL.

## 18. Live-Server Output Missing

Run the builder first:

```bash
/home/steam/jtwp-collector/Pavlov-Data-Collector-/scripts/servers/build-string-array.sh
```

Check:

```bash
ls -lh \
    /home/steam/jtwp-collector/Pavlov-Data-Collector-/scripts/servers/servers.tsv \
    /home/steam/jtwp-collector/Pavlov-Data-Collector-/scripts/servers/stringArray.txt
```

Then test image generation:

```bash
/home/steam/jtwp-collector/Pavlov-Data-Collector-/scripts/servers/LIVEserversIMG.sh
```

See `LIVE_SERVERS.md`.

## 19. One-Pass Health Check

```bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-

jq empty config.json &&
jq empty active.json &&
/home/steam/jtwp-collector/venv/bin/python3 -m compileall -q . &&
systemctl list-units --type=service --all | grep -E 'jtwp|pavlov'
```
