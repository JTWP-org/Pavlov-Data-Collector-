#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path


def atomic_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=path.parent,
    )
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-c", "--config", default="config.json")

    sub = ap.add_subparsers(
        dest="command",
        required=True,
    )

    start = sub.add_parser("start")
    start.add_argument("server_id")
    start.add_argument("loop_seconds", type=int)

    sub.add_parser("stop")
    sub.add_parser("status")

    args = ap.parse_args()

    cfg = json.loads(
        Path(args.config).read_text(encoding="utf-8")
    )

    loop_cfg = cfg.get("rcon_loop", {})

    control_path = Path(
        loop_cfg["control_path"]
    )

    output_path = Path(
        loop_cfg["output_path"]
    )

    if args.command == "start":
        known = {
            Path(server["log_path"]).parents[2].name
            for server in cfg.get("servers", [])
            if server.get("rcon", {}).get("enabled")
        }

        if args.server_id not in known:
            raise SystemExit(
                f"Unknown RCON server: {args.server_id}"
            )

        minimum = int(
            loop_cfg.get("min_loop_seconds", 1)
        )
        maximum = int(
            loop_cfg.get("max_loop_seconds", 3600)
        )

        if not minimum <= args.loop_seconds <= maximum:
            raise SystemExit(
                f"loop_seconds must be {minimum}..{maximum}"
            )

        atomic_write(
            control_path,
            {
                "server_id": args.server_id,
                "loop_seconds": args.loop_seconds,
            },
        )

        print(
            f"✅ RCON loop control created: "
            f"{control_path}"
        )

    elif args.command == "stop":
        control_path.unlink(missing_ok=True)

        print(
            f"✅ Deleted {control_path}.\n"
            f"The watcher will delete "
            f"{output_path.name} and disconnect."
        )

    else:
        if control_path.exists():
            print(
                control_path.read_text(
                    encoding="utf-8"
                )
            )
        else:
            print(
                json.dumps(
                    {
                        "running": False,
                        "control_file_exists": False,
                    },
                    indent=2,
                )
            )


if __name__ == "__main__":
    main()
