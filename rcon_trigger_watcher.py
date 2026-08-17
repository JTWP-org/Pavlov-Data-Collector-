#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pavlov import PavlovRCON


DEFAULT_CONFIG = {
    "rcon_bridge": {
        "enabled": True,
        "poll_interval_seconds": 0.25,
        "command_file": "rcon_commands.json",
        "game_modes_file": "game_modes.json",
        "default_maps_file": "default_maps.json",
        "limited_ammo_types_file": "limited_ammo_types.json",
        "remove_input_on_error": True
    }
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path, default: Any):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def atomic_write_json(path: Path, data: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(temp, path)


def bool_arg(v: Any) -> str:
    if isinstance(v, bool):
        return "True" if v else "False"
    if isinstance(v, str):
        s = v.strip().lower()
        if s in {"true", "1", "yes", "on"}:
            return "True"
        if s in {"false", "0", "no", "off"}:
            return "False"
    raise ValueError(f"Invalid boolean value: {v!r}")


class RconBridge:
    def __init__(self, cfg: dict, config_path: Path):
        self.cfg = cfg
        self.config_path = config_path
        self.project_root = Path(__file__).resolve().parent

        bcfg = cfg.get("rcon_bridge", {})
        self.enabled = bool(bcfg.get("enabled", True))
        self.poll_interval = float(bcfg.get("poll_interval_seconds", 0.25))
        self.remove_input_on_error = bool(bcfg.get("remove_input_on_error", True))

        self.command_defs = load_json(
            self.project_root / bcfg.get("command_file", "rcon_commands.json"),
            {"commands": {}}
        )
        self.game_modes = load_json(
            self.project_root / bcfg.get("game_modes_file", "game_modes.json"),
            {"game_modes": {}}
        ).get("game_modes", {})
        self.default_maps = load_json(
            self.project_root / bcfg.get("default_maps_file", "default_maps.json"),
            {"default_maps": {}}
        ).get("default_maps", {})
        self.ammo_types = load_json(
            self.project_root / bcfg.get("limited_ammo_types_file", "limited_ammo_types.json"),
            {"limited_ammo_types": {}}
        ).get("limited_ammo_types", {})

        self.servers = []
        for raw in cfg.get("servers", []):
            log_path = Path(raw["log_path"])
            server_id = log_path.parents[2].name
            rcon = raw.get("rcon", {})
            if not rcon.get("enabled", False):
                continue

            modsave_rcon = Path(
                rcon.get(
                    "trigger_path",
                    str(log_path.parents[1] / "Config" / "ModSave" / "JTWP" / "Rcon")
                )
            )
            modsave_rcon.mkdir(parents=True, exist_ok=True)

            platform = str(raw.get("platform", "auto")).upper()
            if platform == "AUTO":
                platform = "SHACK" if self._detect_shack(log_path) else "PCVR"

            self.servers.append({
                "server_id": server_id,
                "host": rcon.get("host", "127.0.0.1"),
                "port": int(rcon["port"]),
                "password_env": rcon["password_env"],
                "trigger_path": modsave_rcon,
                "platform": platform
            })

    def _detect_shack(self, log_path: Path) -> bool:
        p = log_path / "Pavlov.log"
        try:
            with p.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if "PavlovLog: SHACK SERVER BUILD" in line:
                        return True
        except FileNotFoundError:
            pass
        return False

    def _validate_and_build(self, key: str, body: dict, server: dict) -> tuple[str, dict]:
        defs = self.command_defs.get("commands", {})
        c = defs.get(key)
        if not c:
            raise ValueError(f"Unknown RCON command key: {key}")
        if not c.get("supported", False):
            raise ValueError(f"RCON command is disabled: {key}")

        parts = [c["rcon_command"]]
        normalized = {}

        for arg in c.get("args", []):
            name = arg["name"]
            required = bool(arg.get("required", False))
            if name not in body:
                if required:
                    raise ValueError(f"Missing required field: {name}")
                continue

            value = body[name]
            typ = arg.get("type", "string")

            if typ == "boolean":
                rendered = bool_arg(value)
                normalized[name] = rendered == "True"
            elif typ == "integer":
                try:
                    iv = int(value)
                except Exception:
                    raise ValueError(f"{name} must be an integer")
                if "minimum" in arg and iv < int(arg["minimum"]):
                    raise ValueError(f"{name} must be >= {arg['minimum']}")
                if "maximum" in arg and iv > int(arg["maximum"]):
                    raise ValueError(f"{name} must be <= {arg['maximum']}")
                if key == "setmaxplayers":
                    max_allowed = arg.get("maximum_shack" if server["platform"] == "SHACK" else "maximum_pcvr")
                    if max_allowed is not None and iv > int(max_allowed):
                        raise ValueError(f"{name} exceeds {server['platform']} maximum of {max_allowed}")
                rendered = str(iv)
                normalized[name] = iv
            else:
                rendered = str(value).strip()
                if not rendered and required:
                    raise ValueError(f"{name} cannot be empty")
                normalized[name] = rendered

            parts.append(rendered)

        # Extra validation for known reference-backed values.
        if key in {"addmaprotation", "removemaprotation", "switchmap"}:
            gm = body.get("game_mode")
            if gm is not None and gm not in self.game_modes:
                raise ValueError(f"Unknown game_mode: {gm}")

            map_value = body.get("map_name_or_id") or body.get("map_id")
            if map_value:
                if str(map_value).upper().startswith("UGC"):
                    pass
                else:
                    m = self.default_maps.get(str(map_value))
                    if m and server["platform"] not in m.get("platforms", []):
                        raise ValueError(
                            f"Map {map_value} is not valid for platform {server['platform']}"
                        )

        if key == "setlimitedammotype" and "ammo_type" in body:
            if str(body["ammo_type"]) not in self.ammo_types:
                raise ValueError(f"Unknown ammo_type: {body['ammo_type']}")

        return " ".join(parts), normalized

    async def _send(self, server: dict, command: str):
        password = os.getenv(server["password_env"], "").strip()
        if not password:
            raise RuntimeError(f"Missing environment variable: {server['password_env']}")
        client = PavlovRCON(server["host"], server["port"], password)
        return await client.send(command)

    async def process_file(self, server: dict, input_path: Path):
        name = input_path.name
        if not (name.startswith("IN-") and name.endswith(".json")):
            return

        key = name[3:-5].lower()
        output_path = input_path.with_name(f"OUT-{key}.json")

        # Remove stale response so the ModKit cannot mistake it for a fresh one.
        output_path.unlink(missing_ok=True)

        try:
            body = load_json(input_path, {})
            if not isinstance(body, dict):
                raise ValueError("Input JSON must be an object")

            command, normalized_args = self._validate_and_build(key, body, server)

            response = await self._send(server, command)

            result = {
                "timestamp": now_iso(),
                "server_id": server["server_id"],
                "platform": server["platform"],
                "request": key,
                "rcon_command": command,
                "success": True,
                "args": normalized_args,
                "response": response
            }

            # Add useful resolved reference labels.
            if key == "setlimitedammotype" and "ammo_type" in body:
                result["ammo_type"] = self.ammo_types.get(str(body["ammo_type"]))
            if key in {"addmaprotation", "removemaprotation", "switchmap"}:
                gm = body.get("game_mode")
                if gm in self.game_modes:
                    result["game_mode"] = {
                        "id": gm,
                        "name": self.game_modes[gm]
                    }

            atomic_write_json(output_path, result)
            input_path.unlink(missing_ok=True)
            print(f"[{server['server_id']}] {command} -> OK")

        except Exception as e:
            result = {
                "timestamp": now_iso(),
                "server_id": server["server_id"],
                "platform": server["platform"],
                "request": key,
                "success": False,
                "error": str(e)
            }
            atomic_write_json(output_path, result)
            if self.remove_input_on_error:
                input_path.unlink(missing_ok=True)
            print(f"[{server['server_id']}] {key} -> ERROR: {e}", file=sys.stderr)

    async def run(self):
        if not self.enabled:
            print("RCON bridge disabled.")
            return
        if not self.servers:
            raise SystemExit("No servers have rcon.enabled=true in config.json")

        print("JTWP RCON file bridge started.")
        for s in self.servers:
            print(f"  {s['server_id']}: {s['trigger_path']} -> {s['host']}:{s['port']}")

        while True:
            did_work = False
            for server in self.servers:
                for p in sorted(server["trigger_path"].glob("IN-*.json")):
                    did_work = True
                    await self.process_file(server, p)
            if not did_work:
                await asyncio.sleep(self.poll_interval)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-c", "--config", default="config.json")
    args = ap.parse_args()

    p = Path(args.config)
    if not p.exists():
        raise SystemExit(f"Config not found: {p}")

    cfg = json.loads(p.read_text(encoding="utf-8"))
    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg)
    asyncio.run(RconBridge(merged, p).run())


if __name__ == "__main__":
    main()
