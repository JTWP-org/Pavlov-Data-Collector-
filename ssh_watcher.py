#!/usr/bin/env python3
"""
JTWP SSH failed-login watcher.

Follows the OpenSSH systemd journal and records failed authentication activity.

Normal output:
    data/global/ssh/events.jsonl
    data/global/ssh/failed_hosts.json
    data/global/ssh/ssh.log

Raw SSH source IPs are isolated to:
    data/private/ssh_ips.json

Normal SSH records use the same HMAC-SHA256 IP hashing secret as player/RCON data.

Recognized examples:
    Failed password for invalid user admin from 1.2.3.4 port 51234 ssh2
    Failed password for root from 1.2.3.4 port 51234 ssh2
    Failed publickey for user from 1.2.3.4 port 51234 ssh2
    Invalid user test from 1.2.3.4 port 51234
    maximum authentication attempts exceeded for invalid user x from 1.2.3.4 port 51234 ssh2

Run permissions:
The account running this watcher must be able to read the systemd journal.
On Ubuntu this can usually be provided with:

    sudo usermod -aG systemd-journal steam

Then log out/in or restart the service session.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from collector import DEFAULT_CONFIG, Enricher, PlayerDB, atomic_write_json, append_human_log, append_jsonl, load_json, now_iso


FAILED_PATTERNS = [
    (
        re.compile(
            r"Failed password for (?:(invalid user) )?(?P<user>\S+) "
            r"from (?P<ip>(?:\d{1,3}\.){3}\d{1,3}) port (?P<port>\d+)"
        ),
        "failed_password",
    ),
    (
        re.compile(
            r"Failed publickey for (?:(invalid user) )?(?P<user>\S+) "
            r"from (?P<ip>(?:\d{1,3}\.){3}\d{1,3}) port (?P<port>\d+)"
        ),
        "failed_publickey",
    ),
    (
        re.compile(
            r"Invalid user (?P<user>\S+) from "
            r"(?P<ip>(?:\d{1,3}\.){3}\d{1,3}) port (?P<port>\d+)"
        ),
        "invalid_user",
    ),
    (
        re.compile(
            r"maximum authentication attempts exceeded for "
            r"(?:(?:invalid user|authenticating user) )?(?P<user>\S+) "
            r"from (?P<ip>(?:\d{1,3}\.){3}\d{1,3}) port (?P<port>\d+)"
        ),
        "max_auth_attempts",
    ),
]


def journal_timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


class SSHWatcher:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.data_root = Path(cfg["data_path"]).expanduser()
        self.data_root.mkdir(parents=True, exist_ok=True)

        secret = os.getenv("JTWP_IP_HASH_SECRET", "")
        if not secret:
            raise SystemExit("JTWP_IP_HASH_SECRET is required.")

        self.enricher = Enricher(cfg, self.data_root)
        self.playerdb = PlayerDB(self.data_root, secret, self.enricher)

        self.ssh_dir = self.data_root / "global" / "ssh"
        self.ssh_dir.mkdir(parents=True, exist_ok=True)

        self.private_dir = self.data_root / "private"
        self.private_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.private_dir, 0o700)
        except OSError:
            pass

        self.failed_hosts_path = self.ssh_dir / "failed_hosts.json"
        self.events_path = self.ssh_dir / "events.jsonl"
        self.log_path = self.ssh_dir / "ssh.log"
        self.private_ips_path = self.private_dir / "ssh_ips.json"

        self.failed_hosts = load_json(self.failed_hosts_path, {})
        self.private_ips = load_json(self.private_ips_path, {})

        sw = cfg.get("ssh_watcher", {})
        units = sw.get("units", ["ssh.service", "sshd.service"])
        self.units = [str(x) for x in units]
        self.enrich_ips = bool(sw.get("enrich_ips", True))
        self.include_invalid_user_events = bool(sw.get("include_invalid_user_events", False))

    def save(self):
        atomic_write_json(self.failed_hosts_path, self.failed_hosts)
        atomic_write_json(self.private_ips_path, self.private_ips)
        try:
            os.chmod(self.private_ips_path, 0o600)
        except OSError:
            pass

    def record(self, line: str):
        for regex, event_type in FAILED_PATTERNS:
            m = regex.search(line)
            if not m:
                continue

            # "Invalid user" is commonly immediately followed by "Failed password".
            # Keep it optional to avoid doubling one password attempt.
            if event_type == "invalid_user" and not self.include_invalid_user_events:
                return

            ip = m.group("ip")
            port = int(m.group("port"))
            username = m.group("user")
            ip_hash = self.playerdb.ip_hash(ip)
            ts = journal_timestamp()

            background = self.enricher.lookup_ip(ip) if self.enrich_ips else {
                "lookup_status": "disabled",
                "source": None,
                "organisation": None,
                "country_code": None,
                "network_type": None,
                "hosting": None,
                "proxy": None,
                "vpn": None,
                "tor": None,
                "risk": None,
                "confidence": None,
            }

            event = {
                "timestamp": ts,
                "type": event_type,
                "ip_hash": ip_hash,
                "source_port": port,
                "username": username,
                "background": background,
            }
            append_jsonl(self.events_path, event)

            host = self.failed_hosts.setdefault(ip_hash, {
                "first_seen": ts,
                "last_seen": ts,
                "failed_attempts": 0,
                "usernames": {},
                "source_ports": [],
                "background": background,
            })
            host["first_seen"] = min(host.get("first_seen") or ts, ts)
            host["last_seen"] = max(host.get("last_seen") or ts, ts)
            host["failed_attempts"] = int(host.get("failed_attempts", 0)) + 1
            host["background"] = background

            users = host.setdefault("usernames", {})
            users[username] = int(users.get(username, 0)) + 1

            ports = host.setdefault("source_ports", [])
            if port not in ports:
                ports.append(port)
                # Keep this bounded; source ports aren't useful forever.
                if len(ports) > 100:
                    del ports[:-100]

            raw = self.private_ips.setdefault(ip, {
                "hash": ip_hash,
                "first_seen": ts,
                "last_seen": ts,
                "failed_attempts": 0,
            })
            raw["hash"] = ip_hash
            raw["first_seen"] = min(raw.get("first_seen") or ts, ts)
            raw["last_seen"] = max(raw.get("last_seen") or ts, ts)
            raw["failed_attempts"] = int(raw.get("failed_attempts", 0)) + 1

            self.save()

            append_human_log(
                self.log_path,
                ts,
                (
                    f"SSH authentication failed / Type: {event_type} "
                    f"/ IP Hash: {ip_hash} / Port: {port} "
                    f"/ Username: {username}"
                ),
            )

            print(
                f"[{ts}] {event_type}: {username} "
                f"from {ip_hash[:16]}…:{port}"
            )
            return

    def run(self):
        # journalctl accepts multiple -u arguments.
        cmd = ["journalctl", "-f", "-n", "0", "-o", "cat"]
        for unit in self.units:
            cmd.extend(["-u", unit])

        print("JTWP SSH watcher started.")
        print("Following:", ", ".join(self.units))

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError:
            raise SystemExit("journalctl was not found.")

        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                self.record(line.rstrip("\n"))
        except KeyboardInterrupt:
            proc.terminate()
            return


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
    if "servers" in cfg:
        merged["servers"] = cfg["servers"]

    SSHWatcher(merged).run()


if __name__ == "__main__":
    main()
