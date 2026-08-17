# 🌐 Pavlov Public API Collection

Add this to `.env`:

```bash
PAVLOV_API="https://pavlovservers.com/api/servers?all=true"
```

The normal nightly `collector.py` run refreshes the public-server snapshot automatically.

For a lightweight refresh that does **not** process Pavlov logs or Stats:

```bash
/home/steam/jtwp-collector/venv/bin/python3 update_pavlov_api.py -c config.json
```

Or install the helper command:

```bash
chmod +x scripts/update-pavlov-api.sh
sudo install -m 755 scripts/update-pavlov-api.sh /usr/local/bin/update-pavlov-api
```

Then trigger an update from anywhere:

```bash
update-pavlov-api
```

Output:

```text
/home/steam/jtwp-collector-data/global/pavlov_api/
├── servers.json
├── network_hosts.json
├── network_hosts_cache.json
├── summary.json
├── last_update.json
└── index/
    ├── by_name.json
    ├── by_ip.json
    ├── by_map.json
    ├── by_game_mode.json
    └── by_server_type.json
```

`servers.json` embeds the selected ProxyCheck/ipapi host fields. Each unique public IP is enriched once and then reused for every Pavlov instance on that host until the host-cache TTL expires.
