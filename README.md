# JTWP RCON Bridge — 32 additional commands

This package adds the 32 RCON commands supplied in chat to the existing
file-trigger bridge.

Existing command count before merge: 44
New commands added: 32
Total command definitions after merge: 76

## Files

- `rcon_trigger_watcher.py` — updated to accept decimal `number`/`float`
  arguments, needed by `MovementSpeed`, `GameSpeed`, and `SetGravity`.
- `rcon_commands.json` — existing command resource plus all 32 new commands.

## File bridge examples

Notify:

```json
{
  "player": "PlayerName",
  "message": "Server restart in 5 minutes"
}
```

Save as:

```text
IN-notify.json
```

Movement speed:

```json
{
  "player": "PlayerName",
  "multiplier": 1.5
}
```

Save as:

```text
IN-movementspeed.json
```

Set vitality:

```json
{
  "player": "PlayerName",
  "health": 100,
  "armor": 50,
  "helmet": -1
}
```

Save as:

```text
IN-setvitality.json
```

Spawn loot crate with no ID:

```json
{}
```

Save as:

```text
IN-spawnlootcrate.json
```

## Install

Back up your existing files first, then replace:

```text
/home/steam/jtwp-collector/Pavlov-Data-Collector-/rcon_trigger_watcher.py
/home/steam/jtwp-collector/Pavlov-Data-Collector-/resource/rcon_commands.json
```

Validate:

```bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-

/home/steam/jtwp-collector/venv/bin/python3   -m py_compile rcon_trigger_watcher.py

jq empty resource/rcon_commands.json
jq '.command_count' resource/rcon_commands.json
```

Restart:

```bash
sudo systemctl restart jtwp-rcon-trigger-watcher.service
sudo systemctl status jtwp-rcon-trigger-watcher.service --no-pager
```
