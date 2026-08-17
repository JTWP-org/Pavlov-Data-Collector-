# 🧩 JTWP Full Update — DDoS Watcher + Mod Cleanup + Service Metadata

## Included files

```text
collector.py
ddos_watcher.py
config.json
scripts/
└── clear-pavlov-mods.sh
systemd/
└── jtwp-ddos-watcher.service
```

## 🌐 Install DDoS watcher dependency

```bash
sudo apt update
sudo apt install -y tcpdump
```

## 📄 Copy files

From your project directory:

```bash
cp collector.py /home/steam/jtwp-collector/Pavlov-Data-Collector-/collector.py
cp ddos_watcher.py /home/steam/jtwp-collector/Pavlov-Data-Collector-/ddos_watcher.py
cp config.json /home/steam/jtwp-collector/Pavlov-Data-Collector-/config.json
```

Install the cleanup helper:

```bash
dos2unix scripts/clear-pavlov-mods.sh
chmod +x scripts/clear-pavlov-mods.sh

sudo install -m 755 \
    scripts/clear-pavlov-mods.sh \
    /usr/local/bin/clear-pavlov-mods
```

Install the DDoS service:

```bash
sudo install -m 644 \
    systemd/jtwp-ddos-watcher.service \
    /etc/systemd/system/jtwp-ddos-watcher.service

sudo systemctl daemon-reload
sudo systemctl enable --now jtwp-ddos-watcher
```

## 🔐 Required IP-hash secret

The DDoS watcher uses the same:

```text
JTWP_IP_HASH_SECRET
```

as player/RCON/SSH records. Keep the existing secret unchanged or hashes will not correlate.

## 👀 Check the DDoS watcher

```bash
sudo systemctl status jtwp-ddos-watcher --no-pager
sudo journalctl -u jtwp-ddos-watcher -f
```

Data is written under:

```text
/home/steam/jtwp-collector-data/global/network/ddos/
├── network_stats.json
├── events.jsonl
├── last_event.json
└── hosts.json
```

Normal DDoS data stores HMAC hashes, not raw source IPs.

## 🧹 Clear installed mods

Edit the `SERVER_PATHS` block near the top of:

```text
scripts/clear-pavlov-mods.sh
```

Then:

```bash
sudo clear-pavlov-mods pavlovserver1
```

The helper discovers the actual systemd unit by the configured server path, stops it, confirms it stopped, clears only:

```text
SERVER/Pavlov/Saved/Mods/*
```

then starts the service and confirms it is active again.

It writes:

```text
servers/{serverID}/server/service.json
servers/{serverID}/server/maintenance.jsonl
```

## ⚙️ Service metadata

The updated `collector.py` also performs systemd service discovery on normal collector runs and writes:

```text
/home/steam/jtwp-collector-data/servers/{serverID}/server/service.json
```

That file contains the detected unit and ready-to-copy commands for:

```text
status
start
stop
restart
enable
disable
enable_now
disable_now
logs
logs_live
is_active
is_enabled
```

## ⚠️ DDoS thresholds

The included values are starting points, not universal proof of a DDoS. Pavlov traffic varies by server population, maps, mods and host networking.

The watcher requires at least two configured conditions to be true before recording a `possible_ddos` event. Tune the values after observing your normal `network_stats.json`.

It intentionally does not auto-block DDoS source addresses.
