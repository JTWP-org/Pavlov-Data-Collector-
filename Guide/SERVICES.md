# ⚙️ JTWP Services & Scheduling Guide

This guide covers the systemd setup used to keep JTWP collector
components running and to schedule collector jobs.

Paths in this guide assume:

``` text
Repository:
/home/steam/jtwp-collector/Pavlov-Data-Collector-

Virtual environment:
/home/steam/jtwp-collector/venv

Data:
/home/steam/jtwp-collector-data
```

Adjust paths if your installation differs.

------------------------------------------------------------------------

# 🧭 Service Overview

The project can use separate systemd units for different jobs:

  -----------------------------------------------------------------------
  Component               Type                    Purpose
  ----------------------- ----------------------- -----------------------
  Collector               timer/oneshot           Runs the main data
                                                  collection job

  SSH watcher             long-running service    Watches failed SSH
                                                  logins

  RCON trigger watcher    long-running service    Watches ModSave RCON
                                                  trigger files

  Pavlov API updater      service/timer or manual Performs lightweight
                                                  public-server updates
  -----------------------------------------------------------------------

Keeping these separate makes it easier to restart or troubleshoot one
component without stopping everything else.

------------------------------------------------------------------------

# 🔐 Environment File

systemd does not automatically load your interactive shell's `.env`.

Services that need API keys, RCON passwords, or webhook values should
include:

``` ini
EnvironmentFile=/home/steam/jtwp-collector/Pavlov-Data-Collector-/.env
```

Protect the file:

``` bash
chmod 600 /home/steam/jtwp-collector/Pavlov-Data-Collector-/.env
```

------------------------------------------------------------------------

# 📊 Nightly Collector

The collector is intended to run every night at **03:00 UTC** on the
current server configuration.

Your server clock was configured as:

``` text
Time zone: Etc/UTC
```

So `03:00` means **03:00 UTC**.

## 1️⃣ Collector Service

Create:

``` bash
sudo nano /etc/systemd/system/jtwp-collector.service
```

Example:

``` ini
[Unit]
Description=JTWP Pavlov Data Collector
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=steam
Group=steam
WorkingDirectory=/home/steam/jtwp-collector/Pavlov-Data-Collector-
EnvironmentFile=/home/steam/jtwp-collector/Pavlov-Data-Collector-/.env
ExecStart=/home/steam/jtwp-collector/venv/bin/python3 /home/steam/jtwp-collector/Pavlov-Data-Collector-/collector.py -c /home/steam/jtwp-collector/Pavlov-Data-Collector-/config.json
```

------------------------------------------------------------------------

## 2️⃣ Collector Timer

Create:

``` bash
sudo nano /etc/systemd/system/jtwp-collector.timer
```

Use:

``` ini
[Unit]
Description=Run JTWP Pavlov Data Collector nightly

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true
Unit=jtwp-collector.service

[Install]
WantedBy=timers.target
```

`Persistent=true` means that if the machine was off at 03:00, systemd
can run the missed job after the machine comes back online.

Enable it:

``` bash
sudo systemctl daemon-reload
sudo systemctl enable --now jtwp-collector.timer
```

Check:

``` bash
systemctl list-timers --all | grep jtwp
```

Run the collector immediately without waiting for 03:00:

``` bash
sudo systemctl start jtwp-collector.service
```

View output:

``` bash
sudo journalctl -u jtwp-collector.service -n 100 --no-pager
```

------------------------------------------------------------------------

# 🔐 SSH Watcher Service

Create:

``` bash
sudo nano /etc/systemd/system/jtwp-ssh-watcher.service
```

Example:

``` ini
[Unit]
Description=JTWP SSH Failed Login Watcher
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=steam
Group=steam
WorkingDirectory=/home/steam/jtwp-collector/Pavlov-Data-Collector-
EnvironmentFile=/home/steam/jtwp-collector/Pavlov-Data-Collector-/.env
ExecStart=/home/steam/jtwp-collector/venv/bin/python3 /home/steam/jtwp-collector/Pavlov-Data-Collector-/ssh_watcher.py -c /home/steam/jtwp-collector/Pavlov-Data-Collector-/config.json
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Install/enable:

``` bash
sudo systemctl daemon-reload
sudo systemctl enable --now jtwp-ssh-watcher
```

Check:

``` bash
sudo systemctl status jtwp-ssh-watcher --no-pager
```

Follow:

``` bash
sudo journalctl -u jtwp-ssh-watcher -f
```

For SSH auto-block setup and sudo permissions, see:

``` text
Guides/SSHblocking.MD
```

------------------------------------------------------------------------

# 🎛️ RCON Trigger Watcher

The RCON bridge watches Pavlov ModSave directories for files such as:

``` text
IN-serverinfo.json
```

and writes responses such as:

``` text
OUT-serverinfo.json
```

Create:

``` bash
sudo nano /etc/systemd/system/jtwp-rcon-trigger-watcher.service
```

Example:

``` ini
[Unit]
Description=JTWP Pavlov RCON Trigger Watcher
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=steam
Group=steam
WorkingDirectory=/home/steam/jtwp-collector/Pavlov-Data-Collector-
EnvironmentFile=/home/steam/jtwp-collector/Pavlov-Data-Collector-/.env
ExecStart=/home/steam/jtwp-collector/venv/bin/python3 /home/steam/jtwp-collector/Pavlov-Data-Collector-/rcon_trigger_watcher.py -c /home/steam/jtwp-collector/Pavlov-Data-Collector-/config.json
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Enable:

``` bash
sudo systemctl daemon-reload
sudo systemctl enable --now jtwp-rcon-trigger-watcher
```

Check:

``` bash
sudo systemctl status jtwp-rcon-trigger-watcher --no-pager
```

Follow:

``` bash
sudo journalctl -u jtwp-rcon-trigger-watcher -f
```

See:

``` text
Guides/RCON_COMMANDS.md
```

for bridge configuration and command usage.

------------------------------------------------------------------------

# 🌍 Lightweight Pavlov API Update

If the repository contains:

``` text
update_pavlov_api.py
```

it can be run manually with the project virtual environment.

Example:

``` bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-

set -a
source .env
set +a

/home/steam/jtwp-collector/venv/bin/python3 update_pavlov_api.py -c config.json
```

If your updater uses different command-line arguments, use the options
supported by the current script.

## Optional systemd service

Create:

``` bash
sudo nano /etc/systemd/system/jtwp-pavlov-api-update.service
```

Example:

``` ini
[Unit]
Description=JTWP Pavlov Public API Update
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=steam
Group=steam
WorkingDirectory=/home/steam/jtwp-collector/Pavlov-Data-Collector-
EnvironmentFile=/home/steam/jtwp-collector/Pavlov-Data-Collector-/.env
ExecStart=/home/steam/jtwp-collector/venv/bin/python3 /home/steam/jtwp-collector/Pavlov-Data-Collector-/update_pavlov_api.py -c /home/steam/jtwp-collector/Pavlov-Data-Collector-/config.json
```

You can add a timer later if you want this update to run on a separate
schedule.

------------------------------------------------------------------------

# 🔄 Reload After Editing Service Files

Whenever a `.service` or `.timer` file changes:

``` bash
sudo systemctl daemon-reload
```

Then restart the affected service:

``` bash
sudo systemctl restart jtwp-ssh-watcher
```

or:

``` bash
sudo systemctl restart jtwp-rcon-trigger-watcher
```

For the collector timer:

``` bash
sudo systemctl restart jtwp-collector.timer
```

------------------------------------------------------------------------

# 🚀 Enable Services at Boot

``` bash
sudo systemctl enable jtwp-ssh-watcher
sudo systemctl enable jtwp-rcon-trigger-watcher
sudo systemctl enable jtwp-collector.timer
```

Start them:

``` bash
sudo systemctl start jtwp-ssh-watcher
sudo systemctl start jtwp-rcon-trigger-watcher
sudo systemctl start jtwp-collector.timer
```

Or combine enable + start:

``` bash
sudo systemctl enable --now jtwp-ssh-watcher
sudo systemctl enable --now jtwp-rcon-trigger-watcher
sudo systemctl enable --now jtwp-collector.timer
```

------------------------------------------------------------------------

# 📊 Check Everything

``` bash
sudo systemctl status jtwp-ssh-watcher --no-pager
sudo systemctl status jtwp-rcon-trigger-watcher --no-pager
sudo systemctl status jtwp-collector.timer --no-pager
```

Show JTWP units:

``` bash
systemctl list-units --all | grep -i jtwp
```

Show timers:

``` bash
systemctl list-timers --all | grep -i jtwp
```

------------------------------------------------------------------------

# 📜 Logs

SSH watcher:

``` bash
sudo journalctl -u jtwp-ssh-watcher -n 100 --no-pager
```

RCON watcher:

``` bash
sudo journalctl -u jtwp-rcon-trigger-watcher -n 100 --no-pager
```

Collector:

``` bash
sudo journalctl -u jtwp-collector.service -n 100 --no-pager
```

Live output:

``` bash
sudo journalctl -u jtwp-ssh-watcher -f
```

------------------------------------------------------------------------

# 🧪 Validate Python Before Starting a Service

Test the exact Python executable:

``` bash
/home/steam/jtwp-collector/venv/bin/python3 --version
```

Check that a script exists:

``` bash
ls -l /home/steam/jtwp-collector/Pavlov-Data-Collector-/ssh_watcher.py
```

Compile-check Python:

``` bash
/home/steam/jtwp-collector/venv/bin/python3 -m py_compile \
    /home/steam/jtwp-collector/Pavlov-Data-Collector-/ssh_watcher.py
```

If no output is printed, the syntax check succeeded.

------------------------------------------------------------------------

# 🛠️ Troubleshooting

## Service repeatedly restarts

Check:

``` bash
sudo journalctl -u SERVICE-NAME -n 100 --no-pager
```

Common causes include:

-   missing Python module
-   wrong virtual-environment path
-   wrong script path
-   invalid `config.json`
-   missing `.env`
-   missing environment variable
-   file permissions

------------------------------------------------------------------------

## `NameError: requests is not defined`

Make sure the Python file contains:

``` python
import requests
```

and that the dependency is installed:

``` bash
source /home/steam/jtwp-collector/venv/bin/activate
pip install -r requirements.txt
```

------------------------------------------------------------------------

## Service cannot see API keys or passwords

Make sure the service contains:

``` ini
EnvironmentFile=/home/steam/jtwp-collector/Pavlov-Data-Collector-/.env
```

Then:

``` bash
sudo systemctl daemon-reload
sudo systemctl restart SERVICE-NAME
```

------------------------------------------------------------------------

## Collector timer did not run

Check:

``` bash
systemctl list-timers --all | grep jtwp
```

Then:

``` bash
sudo journalctl -u jtwp-collector.timer --no-pager
sudo journalctl -u jtwp-collector.service --no-pager
```

------------------------------------------------------------------------

## Wrong scheduled time

Check the server timezone:

``` bash
timedatectl
```

The current installation uses UTC, so:

``` ini
OnCalendar=*-*-* 03:00:00
```

means 03:00 UTC.

------------------------------------------------------------------------

# 🧹 Disable a Service

Stop:

``` bash
sudo systemctl stop SERVICE-NAME
```

Disable at boot:

``` bash
sudo systemctl disable SERVICE-NAME
```

Disable and stop:

``` bash
sudo systemctl disable --now SERVICE-NAME
```

------------------------------------------------------------------------

# 🗑️ Remove a Service

Example:

``` bash
sudo systemctl disable --now jtwp-example.service

sudo rm /etc/systemd/system/jtwp-example.service

sudo systemctl daemon-reload
sudo systemctl reset-failed
```

------------------------------------------------------------------------

# ✅ Recommended Setup

For the current project layout:

``` text
jtwp-collector.timer
    └── Runs collector nightly at 03:00 UTC

jtwp-ssh-watcher.service
    └── Runs continuously

jtwp-rcon-trigger-watcher.service
    └── Runs continuously

jtwp-pavlov-api-update.service
    └── Manual or optional scheduled lightweight update
```

This keeps scheduled collection separate from the always-running
monitoring services.
