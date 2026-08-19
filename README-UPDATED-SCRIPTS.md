# JTWP Latest Updated Scripts Package

This package consolidates the corrected JTWP scripts from the earlier review and
updates them for the reviewed `resource/` folder.

## Important changes in this package

### RCON resources

`rcon_trigger_watcher.py` and `config.json` now use:

```text
resource/rcon_commands.json
resource/game_modes.json
resource/default_maps.json
resource/limited_ammo_types.json
```

The RCON resource refresh also writes back to:

```text
resource/rcon_commands.json
```

### Live-server commands

`custom_commands.json` now points to the retained layout:

```text
scripts/servers/LIVEserversArray.sh
scripts/servers/LIVEserversIMG.sh
```

instead of the old project-level live-server wrappers.

### Resource validator

Run:

```bash
/home/steam/jtwp-collector/venv/bin/python3     scripts/validate-resources.py
```

It validates the resource JSON schemas, RCON command count, limited-ammo keys,
and balancing table.

## Validation performed

- Main Python files: syntax OK
- Python files under scripts/: syntax OK
- Shell scripts: `bash -n` OK
- Project/resource JSON: parse OK
- Resource validation helper: passed

## Install

Back up the existing project before replacing files.

Then copy the contents of this package into:

```text
/home/steam/jtwp-collector/Pavlov-Data-Collector-/
```

preserving the `scripts/`, `scripts/servers/`, `resource/`, and `systemd/`
directories.

Before restarting services:

```bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-

jq empty config.json
jq empty active.json

/home/steam/jtwp-collector/venv/bin/python3     -m compileall -q .

/home/steam/jtwp-collector/venv/bin/python3     scripts/validate-resources.py
```
