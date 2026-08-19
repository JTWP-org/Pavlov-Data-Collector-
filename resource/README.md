# JTWP Resource Folder

This folder is the reviewed resource set for the JTWP Pavlov collector.

## Important compatibility fix

The supplied `limitedAmmoTypes.json` is useful as a source/reference file, but
the current RCON watcher expects a different machine-readable schema:

```text
limited_ammo_types.json
└── limited_ammo_types
    ├── "0"
    ├── "1"
    ├── "2"
    ├── "3"
    ├── "4"
    └── "5"
```

Use `limited_ammo_types.json` for the RCON watcher.

The original `limitedAmmoTypes.json` is retained only so no supplied information
is lost.

## Item list

`items.json` was expanded with the two exact identifiers present in the supplied
`BalancingTable.csv` but missing from the supplied item list:

```text
thompson_drum
ppsh_drum
```

No aliases were guessed for them.

## Files

```text
BalancingTable.csv
WebhookResponseCodes.json
default_maps.json
game_modes.json
gunEmoji.json
icon.json
items.json
limitedAmmoTypes.json
limited_ammo_types.json
rcon_commands.json
resource_audit.json
resource_manifest.json
```

## Validation

All JSON files in this reviewed folder parse successfully.

`rcon_commands.json` contains 57 commands and its `command_count` was normalized
to the actual number of command definitions.

The supplied RCON definitions contain the standard fields expected by the bridge
and have no duplicate IN/OUT filenames.

## Coverage report

See:

```text
resource_audit.json
```

It lists item identifiers that do not currently have a case-insensitive match
in `icon.json`, `gunEmoji.json`, or `BalancingTable.csv`.

Those gaps were intentionally **not** filled with made-up URLs/emojis/stats.

## Recommended config.json paths

If these files live in:

```text
/home/steam/jtwp-collector/Pavlov-Data-Collector-/resource/
```

configure the RCON bridge with explicit resource-relative paths:

```json
{
  "rcon_bridge": {
    "command_file": "resource/rcon_commands.json",
    "game_modes_file": "resource/game_modes.json",
    "default_maps_file": "resource/default_maps.json",
    "limited_ammo_types_file": "resource/limited_ammo_types.json"
  }
}
```

This matters because the current watcher resolves those names from the project
root.

## Quick validation

```bash
cd /home/steam/jtwp-collector/Pavlov-Data-Collector-

for f in resource/*.json; do
    jq empty "$f" || exit 1
done

echo "All resource JSON valid"
```
