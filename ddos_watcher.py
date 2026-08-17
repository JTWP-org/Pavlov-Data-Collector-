#!/usr/bin/env python3
"""
JTWP DDoS / Network Abuse Watcher

Detection only:
- Captures inbound packet metadata with tcpdump.
- Keeps raw source IPs in memory only.
- Writes HMAC-SHA256 hashes to normal collector data.
- Correlates hashes against players, RCON and SSH records.
- Does NOT automatically block DDoS sources.

Requires:
    tcpdump
    JTWP_IP_HASH_SECRET

The service normally runs as root so tcpdump can capture packets. Raw source
addresses are never written to the normal JSON/JSONL dataset.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import ipaddress
import json
import os
import re
import select
import signal
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULTS = {
    "enabled": True,
    "interface": "any",
    "window_seconds": 5,
    "cooldown_seconds": 60,
    "packets_per_second_threshold": 5000,
    "bytes_per_second_threshold": 5_000_000,
    "unique_sources_threshold": 100,
    "per_source_packets_per_second_threshold": 1500,
    "minimum_trigger_conditions": 2,
    "top_sources": 20,
    "monitored_ports": [],
    "capture_filter": "",
    "tcpdump_path": "/usr/bin/tcpdump",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def append_jsonl(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n")


def hash_ip(secret: bytes, ip: str) -> str:
    return hmac.new(secret, ip.encode("utf-8"), hashlib.sha256).hexdigest()


def split_endpoint(value: str) -> tuple[str | None, int | None]:
    value = value.rstrip(":,")

    # Some tcpdump builds may print [IPv6].port.
    if value.startswith("[") and "]" in value:
        host, tail = value[1:].split("]", 1)
        try:
            ipaddress.ip_address(host)
        except ValueError:
            return None, None
        port = None
        if tail.startswith(".") and tail[1:].isdigit():
            port = int(tail[1:])
        return host, port

    # Endpoint with no port.
    try:
        ipaddress.ip_address(value)
        return value, None
    except ValueError:
        pass

    # tcpdump represents IPv4/IPv6 ports as ".PORT".
    if "." in value:
        host, maybe_port = value.rsplit(".", 1)
        if maybe_port.isdigit():
            try:
                ipaddress.ip_address(host)
                return host, int(maybe_port)
            except ValueError:
                pass

    return None, None


PACKET_RE = re.compile(
    r"\b(?P<family>IP6?|ARP)\s+"
    r"(?P<src>\S+)\s+>\s+(?P<dst>\S+):"
)
LENGTH_RE = re.compile(r"\blength\s+(?P<length>\d+)\b")


class Correlator:
    def __init__(self, data_root: Path):
        self.data_root = data_root

    def players(self, ip_hash: str) -> list[dict[str, Any]]:
        idx = load_json(
            self.data_root / "players" / "index" / "by_ip_hash.json",
            {},
        )
        product_ids = idx.get(ip_hash, [])
        out = []

        for pid in product_ids:
            p = load_json(
                self.data_root / "players" / "records" / str(pid) / "player.json",
                {},
            )
            out.append({
                "product_id": pid,
                "unique_id": p.get("unique_id"),
                "player_name": p.get("current_name"),
                "admin": bool(p.get("admin", False)),
                "banned": bool(p.get("banned", False)),
            })

        return out

    def rcon(self, ip_hash: str) -> list[dict[str, Any]]:
        out = []
        servers = self.data_root / "servers"

        if not servers.exists():
            return out

        for server_dir in servers.iterdir():
            if not server_dir.is_dir():
                continue

            for filename, kind in (
                ("known_hosts.json", "known"),
                ("failed_hosts.json", "failed"),
            ):
                data = load_json(server_dir / "rcon" / filename, {})
                host = data.get(ip_hash)
                if not isinstance(host, dict):
                    continue

                out.append({
                    "server_id": server_dir.name,
                    "kind": kind,
                    "first_seen": host.get("first_seen"),
                    "last_seen": host.get("last_seen"),
                    "successful_connections": int(host.get("successful_connections", 0) or 0),
                    "failed_attempts": int(host.get("failed_attempts", 0) or 0),
                })

        return out

    def ssh(self, ip_hash: str) -> dict[str, Any] | None:
        data = load_json(
            self.data_root / "global" / "ssh" / "failed_hosts.json",
            {},
        )
        host = data.get(ip_hash)

        if not isinstance(host, dict):
            return None

        # Only expose normal hashed/security fields here.
        return {
            "first_seen": host.get("first_seen"),
            "last_seen": host.get("last_seen"),
            "failed_attempts": int(host.get("failed_attempts", 0) or 0),
            "blocked": bool(host.get("blocked", False)),
            "blocked_at": host.get("blocked_at"),
        }

    def all(self, ip_hash: str) -> dict[str, Any]:
        players = self.players(ip_hash)
        rcon = self.rcon(ip_hash)
        ssh = self.ssh(ip_hash)

        return {
            "players_seen_on_ip": players,
            "rcon_matches": rcon,
            "ssh_match": ssh,
            "has_player_match": bool(players),
            "has_rcon_match": bool(rcon),
            "has_ssh_match": ssh is not None,
            "correlation_warning": (
                "Shared IP/hash correlation is not proof that a player generated the traffic."
            ),
        }


class DDoSWatcher:
    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        self.data_root = Path(cfg["data_path"]).expanduser()
        self.out_dir = self.data_root / "global" / "network" / "ddos"
        self.out_dir.mkdir(parents=True, exist_ok=True)

        raw = dict(DEFAULTS)
        raw.update(cfg.get("ddos_watcher", {}))
        self.settings = raw

        secret = os.getenv("JTWP_IP_HASH_SECRET", "")
        if not secret:
            raise SystemExit("JTWP_IP_HASH_SECRET is required.")
        self.secret = secret.encode("utf-8")

        self.correlator = Correlator(self.data_root)
        self.running = True
        self.last_event_at = 0.0

        ports = self.settings.get("monitored_ports", [])
        self.monitored_ports = {int(x) for x in ports} if ports else set()

    def build_tcpdump_cmd(self) -> list[str]:
        tcpdump = str(self.settings["tcpdump_path"])
        interface = str(self.settings["interface"])

        cmd = [
            tcpdump,
            "-tt",
            "-nn",
            "-l",
            "-q",
            "-s", "96",
            "-i", interface,
            "-Q", "in",
        ]

        capture_filter = str(self.settings.get("capture_filter", "")).strip()
        if capture_filter:
            cmd.append(capture_filter)

        return cmd

    def parse_packet(self, line: str) -> tuple[str, int | None, int] | None:
        m = PACKET_RE.search(line)
        if not m or m.group("family") == "ARP":
            return None

        src_ip, _src_port = split_endpoint(m.group("src"))
        _dst_ip, dst_port = split_endpoint(m.group("dst"))

        if not src_ip:
            return None

        if self.monitored_ports and dst_port not in self.monitored_ports:
            return None

        lm = LENGTH_RE.search(line)
        size = int(lm.group("length")) if lm else 0

        return src_ip, dst_port, size

    def make_source_record(
        self,
        raw_ip: str,
        stats: dict[str, Any],
        window_seconds: float,
    ) -> dict[str, Any]:
        ih = hash_ip(self.secret, raw_ip)
        return {
            "ip_hash": ih,
            "packets": stats["packets"],
            "bytes": stats["bytes"],
            "packets_per_second": round(stats["packets"] / window_seconds, 2),
            "bytes_per_second": round(stats["bytes"] / window_seconds, 2),
            "destination_ports": dict(
                sorted(stats["ports"].items(), key=lambda kv: (-kv[1], kv[0]))
            ),
            "correlation": self.correlator.all(ih),
        }

    def update_hosts(self, source_records: list[dict[str, Any]], event_ts: str) -> None:
        path = self.out_dir / "hosts.json"
        hosts = load_json(path, {})

        for source in source_records:
            ih = source["ip_hash"]
            ent = hosts.setdefault(ih, {
                "first_seen": event_ts,
                "last_seen": event_ts,
                "ddos_events": 0,
                "total_packets_in_events": 0,
                "total_bytes_in_events": 0,
                "correlation": source["correlation"],
            })

            ent["first_seen"] = min(ent.get("first_seen") or event_ts, event_ts)
            ent["last_seen"] = max(ent.get("last_seen") or event_ts, event_ts)
            ent["ddos_events"] = int(ent.get("ddos_events", 0)) + 1
            ent["total_packets_in_events"] = int(ent.get("total_packets_in_events", 0)) + int(source["packets"])
            ent["total_bytes_in_events"] = int(ent.get("total_bytes_in_events", 0)) + int(source["bytes"])
            ent["correlation"] = source["correlation"]

        atomic_write_json(path, hosts)

    def evaluate(
        self,
        started: float,
        ended: float,
        total_packets: int,
        total_bytes: int,
        sources: dict[str, dict[str, Any]],
        ports: dict[int, int],
    ) -> None:
        window = max(ended - started, 0.001)
        pps = total_packets / window
        bps = total_bytes / window
        unique_sources = len(sources)

        highest_source_pps = 0.0
        if sources:
            highest_source_pps = max(v["packets"] / window for v in sources.values())

        reasons = []

        if pps >= float(self.settings["packets_per_second_threshold"]):
            reasons.append("high_packet_rate")

        if bps >= float(self.settings["bytes_per_second_threshold"]):
            reasons.append("high_byte_rate")

        if unique_sources >= int(self.settings["unique_sources_threshold"]):
            reasons.append("high_unique_source_count")

        if highest_source_pps >= float(self.settings["per_source_packets_per_second_threshold"]):
            reasons.append("high_single_source_packet_rate")

        aggregate = {
            "timestamp": now_iso(),
            "window_seconds": round(window, 3),
            "packets": total_packets,
            "bytes": total_bytes,
            "packets_per_second": round(pps, 2),
            "bytes_per_second": round(bps, 2),
            "unique_sources": unique_sources,
            "highest_source_packets_per_second": round(highest_source_pps, 2),
            "destination_ports": dict(
                sorted(
                    ((str(k), v) for k, v in ports.items()),
                    key=lambda kv: (-kv[1], kv[0]),
                )
            ),
            "trigger_reasons": reasons,
        }

        # Aggregate-only live snapshot; contains no source addresses/hashes.
        atomic_write_json(self.out_dir / "network_stats.json", aggregate)

        min_conditions = int(self.settings["minimum_trigger_conditions"])
        if len(reasons) < min_conditions:
            return

        now_mono = time.monotonic()
        if now_mono - self.last_event_at < float(self.settings["cooldown_seconds"]):
            return

        self.last_event_at = now_mono

        top_n = int(self.settings["top_sources"])
        ranked = sorted(
            sources.items(),
            key=lambda kv: (-kv[1]["packets"], -kv[1]["bytes"]),
        )[:top_n]

        # IMPORTANT: raw IP is consumed here only to calculate the HMAC and
        # perform in-memory correlation. It is not written to event data.
        source_records = [
            self.make_source_record(raw_ip, stats, window)
            for raw_ip, stats in ranked
        ]

        severity = "medium"
        if len(reasons) >= 3:
            severity = "high"
        if len(reasons) >= 4:
            severity = "critical"

        event = {
            "timestamp": aggregate["timestamp"],
            "type": "possible_ddos",
            "severity": severity,
            "detection_only": True,
            "automatic_blocking": False,
            "interface": self.settings["interface"],
            **{k: v for k, v in aggregate.items() if k != "timestamp"},
            "sources": source_records,
            "privacy": {
                "raw_ips_persisted": False,
                "source_identifier": "HMAC-SHA256",
            },
        }

        append_jsonl(self.out_dir / "events.jsonl", event)
        atomic_write_json(self.out_dir / "last_event.json", event)
        self.update_hosts(source_records, event["timestamp"])

        print(
            f"[DDOS] {severity.upper()} possible flood: "
            f"{event['packets_per_second']} pps, "
            f"{event['unique_sources']} sources, "
            f"reasons={','.join(reasons)}",
            flush=True,
        )

    def run(self) -> None:
        if not bool(self.settings.get("enabled", True)):
            print("DDoS watcher disabled.", flush=True)
            return

        tcpdump = str(self.settings["tcpdump_path"])
        if not Path(tcpdump).exists():
            raise SystemExit(
                f"tcpdump not found at {tcpdump}. Install it with: sudo apt install tcpdump"
            )

        cmd = self.build_tcpdump_cmd()
        print("JTWP DDoS/network watcher started.", flush=True)
        print(f"Interface: {self.settings['interface']}", flush=True)
        print(
            "Raw source IPs are used in memory only; persisted source identifiers are HMAC hashes.",
            flush=True,
        )

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        if proc.stdout is None:
            raise SystemExit("Could not open tcpdump stdout.")

        def stop_handler(_sig, _frame):
            self.running = False

        signal.signal(signal.SIGTERM, stop_handler)
        signal.signal(signal.SIGINT, stop_handler)

        try:
            while self.running:
                started = time.monotonic()
                deadline = started + float(self.settings["window_seconds"])
                total_packets = 0
                total_bytes = 0
                sources: dict[str, dict[str, Any]] = {}
                ports: dict[int, int] = defaultdict(int)

                while self.running and time.monotonic() < deadline:
                    timeout = max(0.0, min(0.5, deadline - time.monotonic()))
                    ready, _, _ = select.select([proc.stdout], [], [], timeout)

                    if proc.poll() is not None:
                        err = ""
                        if proc.stderr is not None:
                            err = proc.stderr.read().strip()
                        raise RuntimeError(
                            f"tcpdump exited with code {proc.returncode}: {err}"
                        )

                    if not ready:
                        continue

                    line = proc.stdout.readline()
                    if not line:
                        continue

                    parsed = self.parse_packet(line)
                    if not parsed:
                        continue

                    raw_ip, dst_port, size = parsed
                    total_packets += 1
                    total_bytes += size

                    ent = sources.setdefault(
                        raw_ip,
                        {"packets": 0, "bytes": 0, "ports": defaultdict(int)},
                    )
                    ent["packets"] += 1
                    ent["bytes"] += size

                    if dst_port is not None:
                        ent["ports"][str(dst_port)] += 1
                        ports[dst_port] += 1

                self.evaluate(
                    started,
                    time.monotonic(),
                    total_packets,
                    total_bytes,
                    sources,
                    ports,
                )

        finally:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-c", "--config", default="config.json")
    args = ap.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        raise SystemExit(f"Config not found: {cfg_path}")

    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    DDoSWatcher(cfg).run()


if __name__ == "__main__":
    main()
