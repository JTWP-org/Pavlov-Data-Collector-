#!/usr/bin/env python3
"""Lightweight Pavlov public server-list updater.

Runs only Collector.collect_pavlov_api(); it does not archive or parse Pavlov
logs/Stats files.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from collector import Collector, DEFAULT_CONFIG


def main() -> None:
    ap = argparse.ArgumentParser(description="Refresh JTWP Pavlov public API data only")
    ap.add_argument("-c", "--config", default="config.json")
    args = ap.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        raise SystemExit(f"Config not found: {cfg_path}")

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
