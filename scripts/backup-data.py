#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import tarfile
from datetime import datetime, timezone
from pathlib import Path


def stamp(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="/home/steam/jtwp-collector-data")
    ap.add_argument("--output", default="/home/steam/jtwp-collector-output/backups")
    args = ap.parse_args()

    data_root = Path(args.data)
    out_dir = Path(args.output)

    if not data_root.is_dir():
        raise SystemExit(f"Missing data folder: {data_root}")

    mtimes = []
    for p in data_root.rglob("*"):
        if p.is_file():
            try:
                mtimes.append(p.stat().st_mtime)
            except OSError:
                pass

    now = datetime.now(timezone.utc)
    if mtimes:
        first = stamp(min(mtimes))
        last = stamp(max(mtimes))
    else:
        first = last = now.strftime("%Y%m%dT%H%M%SZ")

    made = now.strftime("%Y%m%dT%H%M%SZ")
    out_dir.mkdir(parents=True, exist_ok=True)
    archive = out_dir / f"JTWP-data-backup_{first}--{last}_made-{made}.tar.gz"

    with tarfile.open(archive, "w:gz") as tar:
        tar.add(data_root, arcname=data_root.name)

    os.chmod(archive, 0o600)
    print(f"✅ Backup created: {archive}")


if __name__ == "__main__":
    main()
