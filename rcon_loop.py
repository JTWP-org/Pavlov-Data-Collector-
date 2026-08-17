#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pavlov import PavlovRCON

from active_config import ActiveConfig


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")

    with temp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    os.replace(temp, path)


class RconLoopWatcher:
    def __init__(self, cfg: dict, active_path: Path):
        self.cfg = cfg
        self.active = ActiveConfig(active_path)

        lc = cfg.get("rcon_loop", {})

        self.control_path = Path(lc["control_path"])
        self.output_path = Path(lc["output_path"])
        self.poll_interval = float(lc.get("poll_interval_seconds", 0.5))
        self.min_loop_seconds = int(lc.get("min_loop_seconds", 1))
        self.max_loop_seconds = int(lc.get("max_loop_seconds", 3600))

        self.servers = {}

        for raw in cfg.get("servers", []):
            log_path = Path(raw["log_path"])
            server_id = log_path.parents[2].name
            rcon = raw.get("rcon", {})

            if not rcon.get("enabled", False):
                continue

            self.servers[server_id] = {
                "server_id": server_id,
                "host": rcon.get("host", "127.0.0.1"),
                "port": int(rcon["port"]),
                "password_env": rcon["password_env"],
            }

        self.client = None
        self.client_server = None

    def read_control(self) -> dict | None:
        if not self.control_path.exists():
            return None

        try:
            data = json.loads(self.control_path.read_text(encoding="utf-8"))
        except Exception as e:
            raise ValueError(f"invalid JSON: {e}") from e

        if not isinstance(data, dict):
            raise ValueError("loopData.json must contain a JSON object")

        server_id = data.get("server_id")
        loop_seconds = data.get("loop_seconds")

        if not isinstance(server_id, str) or server_id not in self.servers:
            raise ValueError(f"unknown server_id: {server_id!r}")

        if type(loop_seconds) is not int:
            raise ValueError("loop_seconds must be an integer")

        if not self.min_loop_seconds <= loop_seconds <= self.max_loop_seconds:
            raise ValueError(
                f"loop_seconds must be between {self.min_loop_seconds} "
                f"and {self.max_loop_seconds}"
            )

        return {
            "server_id": server_id,
            "loop_seconds": loop_seconds,
        }

    async def disconnect(self) -> None:
        client = self.client
        self.client = None
        self.client_server = None

        if client is None:
            return

        # async-pavlov versions differ. If a close/disconnect API exists,
        # use it. If send() manages its own socket, there may be nothing
        # additional to close.
        for method_name in ("disconnect", "close"):
            method = getattr(client, method_name, None)
            if method is None:
                continue

            try:
                result = method()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                print(
                    f"RCON {method_name} cleanup warning: {e}",
                    file=sys.stderr,
                    flush=True,
                )
            break

    async def cleanup_active_loop(self, reason: str) -> None:
        self.output_path.unlink(missing_ok=True)
        await self.disconnect()

        print(
            f"RCON loop inactive: {reason}",
            flush=True,
        )

    async def ensure_client(self, server_id: str) -> None:
        if self.client is not None and self.client_server == server_id:
            return

        await self.disconnect()

        server = self.servers[server_id]
        password = os.getenv(server["password_env"], "").strip()

        if not password:
            raise RuntimeError(
                f"Missing environment variable: {server['password_env']}"
            )

        self.client = PavlovRCON(
            server["host"],
            server["port"],
            password,
        )
        self.client_server = server_id

    async def send(self, command: str) -> dict:
        try:
            response = await self.client.send(command)

            return {
                "success": True,
                "response": response,
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"{type(e).__name__}: {e}",
            }

    async def run(self) -> None:
        print(
            f"JTWP RCON loop watcher started.\n"
            f"Control: {self.control_path}\n"
            f"Output:  {self.output_path}",
            flush=True,
        )

        invalid_message = None

        while True:
            self.active.reload()

            if (
                not self.active.enabled("scripts", "rcon_loop")
                or not self.active.enabled("rcon_loop")
            ):
                if self.client is not None or self.output_path.exists():
                    await self.cleanup_active_loop("disabled by active.json")

                await asyncio.sleep(self.poll_interval)
                continue

            if not self.control_path.exists():
                if self.client is not None or self.output_path.exists():
                    await self.cleanup_active_loop("loopData.json deleted")

                await asyncio.sleep(self.poll_interval)
                continue

            try:
                control = self.read_control()

            except Exception as e:
                message = str(e)

                if message != invalid_message:
                    print(
                        f"Invalid loopData.json; ending active loop: {message}",
                        file=sys.stderr,
                        flush=True,
                    )

                invalid_message = message
                await self.cleanup_active_loop(message)
                await asyncio.sleep(self.poll_interval)
                continue

            invalid_message = None

            server_id = control["server_id"]
            loop_seconds = control["loop_seconds"]

            try:
                await self.ensure_client(server_id)

            except Exception as e:
                await self.cleanup_active_loop(str(e))
                await asyncio.sleep(self.poll_interval)
                continue

            # Check file existence before each RCON call.
            if not self.control_path.exists():
                await self.cleanup_active_loop("loopData.json deleted")
                continue

            if self.active.enabled("rcon_loop", "serverinfo"):
                serverinfo = await self.send("ServerInfo")
            else:
                serverinfo = {"success": False, "disabled": True}

            if not self.control_path.exists():
                await self.cleanup_active_loop("loopData.json deleted")
                continue

            if self.active.enabled("rcon_loop", "inspectall"):
                inspectall = await self.send("InspectAll")
            else:
                inspectall = {"success": False, "disabled": True}

            try:
                after = self.read_control()

            except Exception as e:
                await self.cleanup_active_loop(str(e))
                continue

            if after is None:
                await self.cleanup_active_loop("loopData.json deleted")
                continue

            # If the server changes, the next iteration disconnects the
            # current client and connects to the newly selected server.
            if self.active.enabled("rcon_loop", "output"):
                atomic_write_json(
                    self.output_path,
                    {
                        "timestamp": now_iso(),
                        "server_id": server_id,
                        "loop_seconds": loop_seconds,
                        "success": bool(
                            serverinfo.get("success")
                            and inspectall.get("success")
                        ),
                        "serverinfo": serverinfo,
                        "inspectall": inspectall,
                    },
                )

            # Short-slice sleep so deleting loopData.json stops quickly.
            deadline = asyncio.get_running_loop().time() + loop_seconds

            while asyncio.get_running_loop().time() < deadline:
                if not self.control_path.exists():
                    await self.cleanup_active_loop("loopData.json deleted")
                    break

                remaining = (
                    deadline
                    - asyncio.get_running_loop().time()
                )

                await asyncio.sleep(
                    min(
                        self.poll_interval,
                        max(0.05, remaining),
                    )
                )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-c", "--config", default="config.json")
    ap.add_argument("-a", "--active", default="active.json")
    args = ap.parse_args()

    cfg = json.loads(
        Path(args.config).read_text(encoding="utf-8")
    )

    asyncio.run(
        RconLoopWatcher(
            cfg,
            Path(args.active),
        ).run()
    )


if __name__ == "__main__":
    main()
