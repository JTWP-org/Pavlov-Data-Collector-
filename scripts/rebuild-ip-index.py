#!/usr/bin/env python3

import json
from pathlib import Path


RECORDS_ROOT = Path(
    "/home/steam/jtwp-collector-data/players/records"
)

INDEX_FILE = Path(
    "/home/steam/jtwp-collector-data/players/index/by_ip_hash.json"
)

BACKUP_FILE = Path(
    "/home/steam/jtwp-collector-data/players/index/by_ip_hash.json.bak"
)


def main():

    index = {}

    files = list(
        RECORDS_ROOT.rglob("*ips.json")
    )

    print(
        f"Found {len(files)} ips.json files"
    )

    for path in files:

        try:
            data = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )

        except Exception as exc:
            print(
                f"SKIP {path}: {exc}"
            )
            continue

        product_id = data.get(
            "product_id"
        )

        if not product_id:
            continue

        ips = data.get(
            "ips",
            {}
        )

        if not isinstance(
            ips,
            dict
        ):
            continue

        for ip_hash in ips.keys():

            if not isinstance(
                ip_hash,
                str
            ):
                continue

            if len(ip_hash) != 64:
                continue

            players = index.setdefault(
                ip_hash,
                []
            )

            if product_id not in players:
                players.append(
                    product_id
                )

    # Sort product IDs for stable output
    for players in index.values():
        players.sort()

    # Backup existing index
    if INDEX_FILE.exists():
        BACKUP_FILE.write_bytes(
            INDEX_FILE.read_bytes()
        )

        print(
            f"Backup created: {BACKUP_FILE}"
        )

    INDEX_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    INDEX_FILE.write_text(
        json.dumps(
            index,
            indent=2,
            sort_keys=True
        ) + "\n",
        encoding="utf-8"
    )

    shared = sum(
        1
        for players in index.values()
        if len(players) > 1
    )

    total_links = sum(
        len(players)
        for players in index.values()
    )

    print()
    print("Rebuild complete")
    print(f"Unique IP hashes: {len(index)}")
    print(f"Player/hash links: {total_links}")
    print(f"Shared IP hashes: {shared}")
    print(f"Index: {INDEX_FILE}")


if __name__ == "__main__":
    main()
