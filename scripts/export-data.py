#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def read_secret(env_file: Path) -> str:
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("JTWP_IP_HASH_SECRET="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError(f"JTWP_IP_HASH_SECRET not found in {env_file}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="/home/steam/jtwp-collector-data")
    ap.add_argument("--env", default="/home/steam/jtwp-collector/Pavlov-Data-Collector-/.env")
    ap.add_argument("--output", default="/home/steam/jtwp-collector-output/exports")
    args = ap.parse_args()

    data_root = Path(args.data)
    env_file = Path(args.env)
    out_dir = Path(args.output)

    if not data_root.is_dir():
        raise SystemExit(f"Missing data folder: {data_root}")

    if not env_file.is_file():
        raise SystemExit(f"Missing environment file: {env_file}")

    secret = read_secret(env_file)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir.mkdir(parents=True, exist_ok=True)
    archive = out_dir / f"JTWP-data-export-{stamp}.zip"

    with tempfile.TemporaryDirectory(prefix="jtwp-export-") as td:
        root = Path(td) / "JTWP-export"
        shutil.copytree(data_root, root / "data")

        secret_file = root / "JTWP_IP_HASH_SECRET.txt"
        secret_file.write_text(secret + "\n", encoding="utf-8")
        os.chmod(secret_file, 0o600)

        (root / "README-RESTORE.txt").write_text(
            "JTWP portable data export\n"
            f"Created UTC: {datetime.now(timezone.utc).isoformat()}\n\n"
            "This archive contains the collector data AND JTWP_IP_HASH_SECRET.\n"
            "The hash secret is sensitive. Store this archive securely and do not publish it.\n",
            encoding="utf-8",
        )

        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for p in root.rglob("*"):
                if p.is_file():
                    z.write(p, p.relative_to(root.parent))

    os.chmod(archive, 0o600)
    print(f"✅ Export created: {archive}")


if __name__ == "__main__":
    main()
