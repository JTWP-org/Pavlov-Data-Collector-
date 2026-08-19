#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import tarfile
from datetime import datetime, timezone
from pathlib import Path


def stamp(ts: float) -> str:
    return datetime.fromtimestamp(
        ts,
        timezone.utc,
    ).strftime("%Y%m%dT%H%M%SZ")


def format_size(size: int) -> str:
    value = float(size)

    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if value < 1024 or unit == "TB":
            return f"{value:.2f} {unit}"
        value /= 1024

    return f"{size} B"


def main():
    ap = argparse.ArgumentParser()

    ap.add_argument(
        "--data",
        default="/home/steam/jtwp-collector-data",
    )

    ap.add_argument(
        "--output",
        default="/home/steam/jtwp-collector-output/backups",
    )

    args = ap.parse_args()

    data_root = Path(args.data)
    out_dir = Path(args.output)

    if not data_root.is_dir():
        raise SystemExit(
            f"❌ Missing data folder: {data_root}"
        )

    print(
        "📦 JTWP Collector Backup",
        flush=True,
    )
    print(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        flush=True,
    )
    print(
        f"📁 Source: {data_root}",
        flush=True,
    )
    print(
        f"💾 Destination: {out_dir}",
        flush=True,
    )
    print(
        "🔍 Scanning collector data...",
        flush=True,
    )

    mtimes = []
    file_count = 0
    total_size = 0

    for path in data_root.rglob("*"):
        if not path.is_file():
            continue

        try:
            stat = path.stat()

            mtimes.append(
                stat.st_mtime
            )

            total_size += (
                stat.st_size
            )

            file_count += 1

        except OSError:
            pass

    now = datetime.now(
        timezone.utc
    )

    if mtimes:
        first = stamp(
            min(mtimes)
        )
        last = stamp(
            max(mtimes)
        )
    else:
        first = last = now.strftime(
            "%Y%m%dT%H%M%SZ"
        )

    made = now.strftime(
        "%Y%m%dT%H%M%SZ"
    )

    print(
        f"📄 Files: {file_count:,}",
        flush=True,
    )
    print(
        f"📊 Uncompressed size: {format_size(total_size)}",
        flush=True,
    )
    print(
        f"🕒 Oldest data: {first}",
        flush=True,
    )
    print(
        f"🕒 Newest data: {last}",
        flush=True,
    )

    out_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    archive = out_dir / (
        f"JTWP-data-backup_"
        f"{first}--{last}_"
        f"made-{made}.tar.gz"
    )

    print(
        "🗜️ Creating compressed backup...",
        flush=True,
    )

    with tarfile.open(
        archive,
        "w:gz",
    ) as tar:
        tar.add(
            data_root,
            arcname=data_root.name,
        )

    os.chmod(
        archive,
        0o600,
    )

    archive_size = (
        archive.stat().st_size
    )

    if total_size > 0:
        ratio = (
            archive_size
            / total_size
            * 100
        )
    else:
        ratio = 0

    print(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        flush=True,
    )
    print(
        "✅ BACKUP COMPLETE",
        flush=True,
    )
    print(
        f"📄 Files backed up: {file_count:,}",
        flush=True,
    )
    print(
        f"📊 Original size: {format_size(total_size)}",
        flush=True,
    )
    print(
        f"📦 Backup size: {format_size(archive_size)}",
        flush=True,
    )
    print(
        f"🗜️ Compressed to: {ratio:.1f}% of original",
        flush=True,
    )
    print(
        f"📍 Backup: {archive}",
        flush=True,
    )


if __name__ == "__main__":
    main()
