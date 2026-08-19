#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


REQUIRED_JSON = {
    "rcon_commands.json": "commands",
    "game_modes.json": "game_modes",
    "default_maps.json": "default_maps",
    "limited_ammo_types.json": "limited_ammo_types",
    "items.json": "items",
    "gunEmoji.json": None,
    "icon.json": None,
    "WebhookResponseCodes.json": "discordResponseCodes",
}


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"Missing resource: {path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--resource",
        default=str(
            Path(__file__).resolve().parents[1] / "resource"
        ),
    )
    args = ap.parse_args()

    root = Path(args.resource).expanduser().resolve()

    if not root.is_dir():
        raise SystemExit(f"Resource directory not found: {root}")

    print(f"Resource directory: {root}")
    print()

    loaded = {}

    for filename, top_key in REQUIRED_JSON.items():
        path = root / filename
        obj = load_json(path)
        loaded[filename] = obj

        if top_key is not None and top_key not in obj:
            raise SystemExit(
                f"{filename}: missing top-level key {top_key!r}"
            )

        print(f"✅ {filename}")

    ammo = loaded["limited_ammo_types.json"]["limited_ammo_types"]
    expected_ammo = {str(i) for i in range(6)}
    missing_ammo = sorted(expected_ammo - set(ammo))
    if missing_ammo:
        raise SystemExit(
            "limited_ammo_types.json missing keys: "
            + ", ".join(missing_ammo)
        )

    rcon = loaded["rcon_commands.json"]
    commands = rcon["commands"]
    declared = rcon.get("command_count")

    if declared is not None and declared != len(commands):
        raise SystemExit(
            f"rcon_commands command_count={declared}, "
            f"actual={len(commands)}"
        )

    balance = root / "BalancingTable.csv"
    if not balance.is_file():
        raise SystemExit(f"Missing resource: {balance}")

    with balance.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        rows = list(csv.reader(handle))

    if len(rows) < 2:
        raise SystemExit("BalancingTable.csv has no data rows.")

    print(f"✅ BalancingTable.csv ({len(rows)-1} rows)")
    print()
    print(f"RCON commands: {len(commands)}")
    print(f"Limited ammo types: {len(ammo)}")
    print("✅ Resource validation complete.")


if __name__ == "__main__":
    main()
