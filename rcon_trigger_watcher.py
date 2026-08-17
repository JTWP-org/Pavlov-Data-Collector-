#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
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
        "remove_input_on_error": True,

        # Pavlov Public API updater trigger.
        "ppapi_trigger_enabled": True,
        "ppapi_trigger_file": "EXE_PPAPI.json",
        "ppapi_updater": "update_pavlov_api.py",
        "ppapi_timeout_seconds": 300,

        # Resource refresh trigger.
        "rcon_resource_trigger_enabled": True,
        "rcon_resource_trigger_file": "IN-RCON.json",
        "rcon_resource_output_file": "OUT--RCON.json",
        "rcon_resource_url": "https://raw.githubusercontent.com/JTWP-org/Pavlov-Data-Collector-/refs/heads/main/resource/rcon_commands.json",
        "rcon_resource_local_file": "rcon_commands.json",
        "rcon_resource_timeout_seconds": 30
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
        self.config_path = config_path.resolve()
        self.project_root = Path(__file__).resolve().parent

        bcfg = cfg.get("rcon_bridge", {})

        self.enabled = bool(bcfg.get("enabled", True))
        self.poll_interval = float(
            bcfg.get("poll_interval_seconds", 0.25)
        )

        self.remove_input_on_error = bool(
            bcfg.get("remove_input_on_error", True)
        )

        # ----------------------------------------------------
        # PPAPI file trigger
        # ----------------------------------------------------

        self.ppapi_trigger_enabled = bool(
            bcfg.get("ppapi_trigger_enabled", True)
        )

        self.ppapi_trigger_file = str(
            bcfg.get("ppapi_trigger_file", "EXE_PPAPI.json")
        )

        self.ppapi_updater = self.project_root / str(
            bcfg.get("ppapi_updater", "update_pavlov_api.py")
        )

        self.ppapi_timeout_seconds = int(
            bcfg.get("ppapi_timeout_seconds", 300)
        )

        self.ppapi_running = False

        # ----------------------------------------------------
        # RCON command resource refresh trigger
        # ----------------------------------------------------

        self.rcon_resource_trigger_enabled = bool(
            bcfg.get("rcon_resource_trigger_enabled", True)
        )

        self.rcon_resource_trigger_file = str(
            bcfg.get("rcon_resource_trigger_file", "IN-RCON.json")
        )

        self.rcon_resource_output_file = str(
            bcfg.get("rcon_resource_output_file", "OUT--RCON.json")
        )

        self.rcon_resource_url = str(
            bcfg.get(
                "rcon_resource_url",
                "https://raw.githubusercontent.com/JTWP-org/Pavlov-Data-Collector-/refs/heads/main/resource/rcon_commands.json",
            )
        )

        self.rcon_resource_local_file = self.project_root / str(
            bcfg.get("rcon_resource_local_file", "rcon_commands.json")
        )

        self.rcon_resource_timeout_seconds = int(
            bcfg.get("rcon_resource_timeout_seconds", 30)
        )

        self.rcon_resource_running = False

        # ----------------------------------------------------
        # RCON support/reference files
        # ----------------------------------------------------

        self.command_defs = load_json(
            self.project_root
            / bcfg.get("command_file", "rcon_commands.json"),
            {"commands": {}},
        )

        self.game_modes = load_json(
            self.project_root
            / bcfg.get("game_modes_file", "game_modes.json"),
            {"game_modes": {}},
        ).get("game_modes", {})

        self.default_maps = load_json(
            self.project_root
            / bcfg.get("default_maps_file", "default_maps.json"),
            {"default_maps": {}},
        ).get("default_maps", {})

        self.ammo_types = load_json(
            self.project_root
            / bcfg.get(
                "limited_ammo_types_file",
                "limited_ammo_types.json",
            ),
            {"limited_ammo_types": {}},
        ).get("limited_ammo_types", {})

        # ----------------------------------------------------
        # Pavlov servers
        # ----------------------------------------------------

        self.servers = []

        for raw in cfg.get("servers", []):
            log_path = Path(raw["log_path"])

            # /home/steam/pavlovserver/Pavlov/Saved/Logs/
            # parents[2] -> pavlovserver
            server_id = log_path.parents[2].name

            rcon = raw.get("rcon", {})

            if not rcon.get("enabled", False):
                continue

            modsave_rcon = Path(
                rcon.get(
                    "trigger_path",
                    str(
                        log_path.parent
                        / "Config"
                        / "ModSave"
                        / "JTWP"
                        / "Rcon"
                    ),
                )
            )

            modsave_rcon.mkdir(
                parents=True,
                exist_ok=True,
            )

            platform = str(
                raw.get("platform", "auto")
            ).upper()

            if platform == "AUTO":
                platform = (
                    "SHACK"
                    if self._detect_shack(log_path)
                    else "PCVR"
                )

            self.servers.append(
                {
                    "server_id": server_id,
                    "host": rcon.get(
                        "host",
                        "127.0.0.1",
                    ),
                    "port": int(rcon["port"]),
                    "password_env": rcon["password_env"],
                    "trigger_path": modsave_rcon,
                    "platform": platform,
                }
            )

    def _detect_shack(self, log_path: Path) -> bool:
        p = log_path / "Pavlov.log"

        try:
            with p.open(
                "r",
                encoding="utf-8",
                errors="replace",
            ) as f:
                for line in f:
                    if (
                        "PavlovLog: SHACK SERVER BUILD"
                        in line
                    ):
                        return True

        except FileNotFoundError:
            pass

        return False

    # ========================================================
    # RCON COMMAND BUILDING
    # ========================================================

    def _validate_and_build(
        self,
        key: str,
        body: dict,
        server: dict,
    ) -> tuple[str, dict]:

        defs = self.command_defs.get(
            "commands",
            {},
        )

        c = defs.get(key)

        if not c:
            raise ValueError(
                f"Unknown RCON command key: {key}"
            )

        if not c.get("supported", False):
            raise ValueError(
                f"RCON command is disabled: {key}"
            )

        parts = [
            c["rcon_command"]
        ]

        normalized = {}

        for arg in c.get("args", []):
            name = arg["name"]

            required = bool(
                arg.get("required", False)
            )

            if name not in body:
                if required:
                    raise ValueError(
                        f"Missing required field: {name}"
                    )

                continue

            value = body[name]
            typ = arg.get("type", "string")

            if typ == "boolean":
                rendered = bool_arg(value)

                normalized[name] = (
                    rendered == "True"
                )

            elif typ == "integer":
                try:
                    iv = int(value)
                except Exception:
                    raise ValueError(
                        f"{name} must be an integer"
                    )

                if (
                    "minimum" in arg
                    and iv < int(arg["minimum"])
                ):
                    raise ValueError(
                        f"{name} must be >= "
                        f"{arg['minimum']}"
                    )

                if (
                    "maximum" in arg
                    and iv > int(arg["maximum"])
                ):
                    raise ValueError(
                        f"{name} must be <= "
                        f"{arg['maximum']}"
                    )

                if key == "setmaxplayers":
                    maximum_key = (
                        "maximum_shack"
                        if server["platform"] == "SHACK"
                        else "maximum_pcvr"
                    )

                    max_allowed = arg.get(
                        maximum_key
                    )

                    if (
                        max_allowed is not None
                        and iv > int(max_allowed)
                    ):
                        raise ValueError(
                            f"{name} exceeds "
                            f"{server['platform']} "
                            f"maximum of {max_allowed}"
                        )

                rendered = str(iv)
                normalized[name] = iv

            else:
                rendered = str(value).strip()

                if not rendered and required:
                    raise ValueError(
                        f"{name} cannot be empty"
                    )

                normalized[name] = rendered

            parts.append(rendered)

        # ----------------------------------------------------
        # Reference-backed validation
        # ----------------------------------------------------

        if key in {
            "addmaprotation",
            "removemaprotation",
            "switchmap",
        }:
            gm = body.get("game_mode")

            if (
                gm is not None
                and gm not in self.game_modes
            ):
                raise ValueError(
                    f"Unknown game_mode: {gm}"
                )

            map_value = (
                body.get("map_name_or_id")
                or body.get("map_id")
            )

            if map_value:
                if (
                    str(map_value)
                    .upper()
                    .startswith("UGC")
                ):
                    pass
                else:
                    m = self.default_maps.get(
                        str(map_value)
                    )

                    if (
                        m
                        and server["platform"]
                        not in m.get(
                            "platforms",
                            [],
                        )
                    ):
                        raise ValueError(
                            f"Map {map_value} "
                            f"is not valid for "
                            f"platform "
                            f"{server['platform']}"
                        )

        if (
            key == "setlimitedammotype"
            and "ammo_type" in body
        ):
            if (
                str(body["ammo_type"])
                not in self.ammo_types
            ):
                raise ValueError(
                    f"Unknown ammo_type: "
                    f"{body['ammo_type']}"
                )

        return (
            " ".join(parts),
            normalized,
        )

    # ========================================================
    # RCON
    # ========================================================

    async def _send(
        self,
        server: dict,
        command: str,
    ):
        password = os.getenv(
            server["password_env"],
            "",
        ).strip()

        if not password:
            raise RuntimeError(
                "Missing environment variable: "
                f"{server['password_env']}"
            )

        client = PavlovRCON(
            server["host"],
            server["port"],
            password,
        )

        return await client.send(command)

    # ========================================================
    # PPAPI TRIGGER
    # ========================================================

    def _find_ppapi_triggers(self) -> list[Path]:
        if not self.ppapi_trigger_enabled:
            return []

        triggers = []

        for server in self.servers:
            p = (
                server["trigger_path"]
                / self.ppapi_trigger_file
            )

            if p.is_file():
                triggers.append(p)

        return triggers

    def _consume_ppapi_triggers(
        self,
        triggers: list[Path],
    ) -> None:

        for trigger in triggers:
            try:
                trigger.unlink()
                print(
                    "[PPAPI] Removed trigger: "
                    f"{trigger}",
                    flush=True,
                )
            except FileNotFoundError:
                pass
            except Exception as exc:
                print(
                    "[PPAPI] Could not remove "
                    f"{trigger}: {exc}",
                    file=sys.stderr,
                    flush=True,
                )

    def _run_ppapi_sync(self) -> dict:
        if not self.ppapi_updater.is_file():
            return {
                "success": False,
                "error": (
                    "Pavlov API updater not found: "
                    f"{self.ppapi_updater}"
                ),
            }

        cmd = [
            sys.executable,
            str(self.ppapi_updater),
            "-c",
            str(self.config_path),
        ]

        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=self.ppapi_timeout_seconds,
                check=False,
            )

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": (
                    "Pavlov API updater timed out "
                    f"after "
                    f"{self.ppapi_timeout_seconds} "
                    "seconds"
                ),
            }

        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }

        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }

    async def process_ppapi_trigger(
        self,
        triggers: list[Path],
    ) -> None:

        if not triggers:
            return

        if self.ppapi_running:
            # Consume additional trigger files instead
            # of queueing duplicate API updates.
            self._consume_ppapi_triggers(
                triggers
            )

            print(
                "[PPAPI] Update already running; "
                "duplicate trigger consumed.",
                flush=True,
            )

            return

        # Remove every detected EXE_PPAPI.json first.
        # This guarantees the same trigger is not
        # processed again on the next polling cycle.
        self._consume_ppapi_triggers(
            triggers
        )

        self.ppapi_running = True

        print(
            "[PPAPI] EXE_PPAPI.json detected.",
            flush=True,
        )

        print(
            "[PPAPI] Running "
            "update_pavlov_api.py...",
            flush=True,
        )

        try:
            # subprocess.run() is blocking, so execute
            # it outside the asyncio event loop thread.
            result = await asyncio.to_thread(
                self._run_ppapi_sync
            )

            if result.get("stdout"):
                print(
                    "[PPAPI] "
                    + result["stdout"],
                    flush=True,
                )

            if result.get("success"):
                print(
                    "[PPAPI] Pavlov Public API "
                    "update completed successfully.",
                    flush=True,
                )
            else:
                error = (
                    result.get("stderr")
                    or result.get("error")
                    or "Unknown PPAPI updater error"
                )

                print(
                    "[PPAPI] Update failed: "
                    f"{error}",
                    file=sys.stderr,
                    flush=True,
                )

        finally:
            self.ppapi_running = False

    # ========================================================
    # RCON COMMAND RESOURCE TRIGGER
    # ========================================================

    def _find_rcon_resource_triggers(self) -> list[Path]:
        if not self.rcon_resource_trigger_enabled:
            return []

        triggers = []

        for server in self.servers:
            p = (
                server["trigger_path"]
                / self.rcon_resource_trigger_file
            )

            if p.is_file():
                triggers.append(p)

        return triggers

    def _consume_rcon_resource_triggers(
        self,
        triggers: list[Path],
    ) -> None:
        for trigger in triggers:
            try:
                trigger.unlink()
                print(
                    "[RCON-RESOURCE] Removed trigger: "
                    f"{trigger}",
                    flush=True,
                )
            except FileNotFoundError:
                pass
            except Exception as exc:
                print(
                    "[RCON-RESOURCE] Could not remove "
                    f"{trigger}: {exc}",
                    file=sys.stderr,
                    flush=True,
                )

    def _download_rcon_resource_sync(self) -> dict:
        temp_path = self.rcon_resource_local_file.with_name(
            self.rcon_resource_local_file.name + ".download"
        )

        temp_path.unlink(missing_ok=True)

        cmd = [
            "wget",
            "-q",
            "--timeout",
            str(self.rcon_resource_timeout_seconds),
            "--tries",
            "1",
            "-O",
            str(temp_path),
            self.rcon_resource_url,
        ]

        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=self.rcon_resource_timeout_seconds + 5,
                check=False,
            )
        except subprocess.TimeoutExpired:
            temp_path.unlink(missing_ok=True)

            return {
                "success": False,
                "error": (
                    "wget timed out while downloading "
                    "rcon_commands.json"
                ),
            }
        except Exception as exc:
            temp_path.unlink(missing_ok=True)

            return {
                "success": False,
                "error": str(exc),
            }

        if result.returncode != 0:
            temp_path.unlink(missing_ok=True)

            return {
                "success": False,
                "error": (
                    result.stderr.strip()
                    or result.stdout.strip()
                    or f"wget exited with code {result.returncode}"
                ),
            }

        try:
            downloaded = json.loads(
                temp_path.read_text(encoding="utf-8")
            )
        except Exception as exc:
            temp_path.unlink(missing_ok=True)

            return {
                "success": False,
                "error": (
                    "Downloaded rcon_commands.json is invalid JSON: "
                    f"{exc}"
                ),
            }

        if not isinstance(downloaded, dict):
            temp_path.unlink(missing_ok=True)

            return {
                "success": False,
                "error": (
                    "Downloaded rcon_commands.json "
                    "must contain a JSON object"
                ),
            }

        # Replace the local resource only after the download
        # has successfully parsed as JSON.
        os.replace(
            temp_path,
            self.rcon_resource_local_file,
        )

        # Reload definitions immediately so subsequent RCON
        # requests use the new command resource without a
        # watcher restart.
        self.command_defs = downloaded

        return {
            "success": True,
            "data": downloaded,
        }

    async def process_rcon_resource_trigger(
        self,
        triggers: list[Path],
    ) -> None:
        if not triggers:
            return

        if self.rcon_resource_running:
            self._consume_rcon_resource_triggers(
                triggers
            )

            print(
                "[RCON-RESOURCE] Refresh already running; "
                "duplicate trigger consumed.",
                flush=True,
            )

            return

        # Capture every directory that requested the resource
        # so each caller receives OUT--RCON.json.
        output_paths = [
            trigger.with_name(
                self.rcon_resource_output_file
            )
            for trigger in triggers
        ]

        # Remove stale output before beginning.
        for output_path in output_paths:
            output_path.unlink(missing_ok=True)

        # Consume the trigger first so it cannot be executed
        # repeatedly while wget is running.
        self._consume_rcon_resource_triggers(
            triggers
        )

        self.rcon_resource_running = True

        print(
            "[RCON-RESOURCE] IN-RCON.json detected.",
            flush=True,
        )

        print(
            "[RCON-RESOURCE] Downloading latest command "
            "resource with wget...",
            flush=True,
        )

        try:
            result = await asyncio.to_thread(
                self._download_rcon_resource_sync
            )

            if result.get("success"):
                data = result["data"]

                # OUT--RCON.json intentionally contains the
                # resource JSON itself, not a response wrapper.
                for output_path in output_paths:
                    atomic_write_json(
                        output_path,
                        data,
                    )

                print(
                    "[RCON-RESOURCE] Local "
                    "rcon_commands.json updated.",
                    flush=True,
                )

                print(
                    "[RCON-RESOURCE] Wrote "
                    f"{self.rcon_resource_output_file}.",
                    flush=True,
                )
            else:
                error = result.get(
                    "error",
                    "Unknown resource refresh error",
                )

                # On failure, return a small valid JSON error
                # so the ModKit does not wait forever for a
                # response file.
                error_response = {
                    "success": False,
                    "error": error,
                    "timestamp": now_iso(),
                }

                for output_path in output_paths:
                    atomic_write_json(
                        output_path,
                        error_response,
                    )

                print(
                    "[RCON-RESOURCE] Refresh failed: "
                    f"{error}",
                    file=sys.stderr,
                    flush=True,
                )

        finally:
            self.rcon_resource_running = False

    # ========================================================
    # RCON TRIGGER PROCESSING
    # ========================================================

    async def process_file(
        self,
        server: dict,
        input_path: Path,
    ):
        name = input_path.name

        if not (
            name.startswith("IN-")
            and name.endswith(".json")
        ):
            return

        key = name[3:-5].lower()

        output_path = input_path.with_name(
            f"OUT-{key}.json"
        )

        # Remove stale response so the ModKit cannot
        # mistake it for the new request.
        output_path.unlink(
            missing_ok=True
        )

        try:
            body = load_json(
                input_path,
                {},
            )

            if not isinstance(body, dict):
                raise ValueError(
                    "Input JSON must be an object"
                )

            command, normalized_args = (
                self._validate_and_build(
                    key,
                    body,
                    server,
                )
            )

            response = await self._send(
                server,
                command,
            )

            result = {
                "timestamp": now_iso(),
                "server_id": server["server_id"],
                "platform": server["platform"],
                "request": key,
                "rcon_command": command,
                "success": True,
                "args": normalized_args,
                "response": response,
            }

            if (
                key == "setlimitedammotype"
                and "ammo_type" in body
            ):
                result["ammo_type"] = (
                    self.ammo_types.get(
                        str(body["ammo_type"])
                    )
                )

            if key in {
                "addmaprotation",
                "removemaprotation",
                "switchmap",
            }:
                gm = body.get("game_mode")

                if gm in self.game_modes:
                    result["game_mode"] = {
                        "id": gm,
                        "name": self.game_modes[gm],
                    }

            atomic_write_json(
                output_path,
                result,
            )

            input_path.unlink(
                missing_ok=True
            )

            print(
                f"[{server['server_id']}] "
                f"{command} -> OK",
                flush=True,
            )

        except Exception as e:
            result = {
                "timestamp": now_iso(),
                "server_id": server["server_id"],
                "platform": server["platform"],
                "request": key,
                "success": False,
                "error": str(e),
            }

            atomic_write_json(
                output_path,
                result,
            )

            if self.remove_input_on_error:
                input_path.unlink(
                    missing_ok=True
                )

            print(
                f"[{server['server_id']}] "
                f"{key} -> ERROR: {e}",
                file=sys.stderr,
                flush=True,
            )

    # ========================================================
    # MAIN WATCHER LOOP
    # ========================================================

    async def run(self):
        if not self.enabled:
            print(
                "RCON bridge disabled.",
                flush=True,
            )

            return

        if not self.servers:
            raise SystemExit(
                "No servers have "
                "rcon.enabled=true "
                "in config.json"
            )

        print(
            "JTWP RCON file bridge started.",
            flush=True,
        )

        for s in self.servers:
            print(
                f"  {s['server_id']}: "
                f"{s['trigger_path']} "
                f"-> {s['host']}:{s['port']}",
                flush=True,
            )

        if self.ppapi_trigger_enabled:
            print(
                "  PPAPI trigger: "
                f"{self.ppapi_trigger_file}",
                flush=True,
            )

        if self.rcon_resource_trigger_enabled:
            print(
                "  RCON resource trigger: "
                f"{self.rcon_resource_trigger_file} "
                f"-> {self.rcon_resource_output_file}",
                flush=True,
            )

        while True:
            did_work = False

            # ------------------------------------------------
            # Pavlov Public API update trigger
            # ------------------------------------------------

            ppapi_triggers = (
                self._find_ppapi_triggers()
            )

            if ppapi_triggers:
                did_work = True

                await self.process_ppapi_trigger(
                    ppapi_triggers
                )

            # ------------------------------------------------
            # RCON command resource refresh trigger
            # ------------------------------------------------

            resource_triggers = (
                self._find_rcon_resource_triggers()
            )

            if resource_triggers:
                did_work = True

                await self.process_rcon_resource_trigger(
                    resource_triggers
                )

            # ------------------------------------------------
            # Normal RCON IN-*.json triggers
            # ------------------------------------------------

            for server in self.servers:
                for p in sorted(
                    server[
                        "trigger_path"
                    ].glob("IN-*.json")
                ):
                    if (
                        p.name
                        == self.rcon_resource_trigger_file
                    ):
                        continue

                    did_work = True

                    await self.process_file(
                        server,
                        p,
                    )

            if not did_work:
                await asyncio.sleep(
                    self.poll_interval
                )


def main():
    ap = argparse.ArgumentParser()

    ap.add_argument(
        "-c",
        "--config",
        default="config.json",
    )

    args = ap.parse_args()

    p = Path(args.config)

    if not p.exists():
        raise SystemExit(
            f"Config not found: {p}"
        )

    cfg = json.loads(
        p.read_text(
            encoding="utf-8"
        )
    )

    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg)

    asyncio.run(
        RconBridge(
            merged,
            p,
        ).run()
    )


if __name__ == "__main__":
    main()
