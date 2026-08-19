#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def read_secret(env_file: Path) -> str:
    for raw_line in env_file.read_text(
        encoding="utf-8"
    ).splitlines():

        line = raw_line.strip()

        if not line or line.startswith("#"):
            continue

        if line.startswith(
            "JTWP_IP_HASH_SECRET="
        ):
            value = line.split(
                "=",
                1,
            )[1].strip()

            if (
                len(value) >= 2
                and value[0] == value[-1]
                and value[0] in {"'", '"'}
            ):
                value = value[1:-1]

            return value

    raise RuntimeError(
        f"JTWP_IP_HASH_SECRET not found in {env_file}"
    )


def main():
    ap = argparse.ArgumentParser()

    ap.add_argument(
        "--data",
        default="/home/steam/jtwp-collector-data",
    )

    ap.add_argument(
        "--env",
        default=(
            "/home/steam/jtwp-collector/"
            "Pavlov-Data-Collector-/.env"
        ),
    )

    ap.add_argument(
        "--output",
        default=(
            "/home/steam/"
            "jtwp-collector-output/exports"
        ),
    )

    args = ap.parse_args()

    data_root = Path(
        args.data
    )

    env_file = Path(
        args.env
    )

    out_dir = Path(
        args.output
    )

    if not data_root.is_dir():
        raise SystemExit(
            f"Missing data folder: {data_root}"
        )

    if not env_file.is_file():
        raise SystemExit(
            f"Missing environment file: {env_file}"
        )

    secret = read_secret(
        env_file
    )

    stamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y%m%dT%H%M%SZ"
    )

    out_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    archive = (
        out_dir
        / f"JTWP-data-export-{stamp}.zip"
    )

    print(
        "📦 Starting JTWP data export...",
        flush=True,
    )

    print(
        f"📁 Source: {data_root}",
        flush=True,
    )

    print(
        f"💾 Output: {archive}",
        flush=True,
    )

    file_count = 0

    with zipfile.ZipFile(
        archive,
        "w",
        zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as z:

        for path in data_root.rglob("*"):

            if not path.is_file():
                continue

            relative = path.relative_to(
                data_root
            )

            z.write(
                path,
                Path(
                    "JTWP-export/data"
                )
                / relative,
            )

            file_count += 1

            if file_count % 500 == 0:
                print(
                    f"📄 Added {file_count:,} files...",
                    flush=True,
                )

        z.writestr(
            (
                "JTWP-export/"
                "JTWP_IP_HASH_SECRET.txt"
            ),
            secret + "\n",
        )

        z.writestr(
            (
                "JTWP-export/"
                "README-RESTORE.txt"
            ),
            (
                "JTWP portable data export\n"
                f"Created UTC: "
                f"{datetime.now(timezone.utc).isoformat()}\n\n"
                "This archive contains the collector "
                "data AND JTWP_IP_HASH_SECRET.\n"
                "The hash secret is sensitive. "
                "Store this archive securely and "
                "do not publish it.\n"
            ),
        )

    os.chmod(
        archive,
        0o600,
    )

    size = (
        archive.stat().st_size
        / 1024
        / 1024
    )

    print(
        f"✅ Export created: {archive}",
        flush=True,
    )

    print(
        f"📄 Files exported: {file_count:,}",
        flush=True,
    )

    print(
        f"📦 Archive size: {size:.2f} MB",
        flush=True,
    )


if __name__ == "__main__":
    main()
