#!/usr/bin/env python3
"""Lightweight Pavlov public server-list updater.

Runs only Collector.collect_pavlov_api(); it does not archive or parse Pavlov
logs/Stats files.

The updater automatically reads .env from the project/config directory when
present. Existing environment variables always take precedence.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path

from collector import Collector, DEFAULT_CONFIG


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE entries from .env without overriding existing env."""
    if not path.is_file():
        return

    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        os.environ.setdefault(key, value)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Refresh JTWP Pavlov public API data only"
    )
    ap.add_argument("-c", "--config", default="config.json")
    args = ap.parse_args()

    cfg_path = Path(args.config).expanduser().resolve()
    if not cfg_path.exists():
        raise SystemExit(f"Config not found: {cfg_path}")

    # Prefer .env beside config.json. Fall back to .env beside this script.
    load_env_file(cfg_path.parent / ".env")
    script_env = Path(__file__).resolve().parent / ".env"
    if script_env != cfg_path.parent / ".env":
        load_env_file(script_env)

    with cfg_path.open("r", encoding="utf-8") as f:
        cfg = json.load(f)

    merged = copy.deepcopy(DEFAULT_CONFIG)
    merged.update(cfg)
    if "servers" in cfg:
        merged["servers"] = cfg["servers"]

    collector = Collector(merged)
    result = collector.collect_pavlov_api()
    print(json.dumps(result, indent=2))

    if not result.get("success"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
