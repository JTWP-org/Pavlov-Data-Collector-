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
import ipaddress
import json
import os
import re
import subprocess
import sys
import threading
import time
from collections import Counter, deque

import requests
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
        self.webhook_url = os.getenv("JTWP_SSH_WEBHOOK_URL", "").strip() or os.getenv("JTWP_SECURITY_WEBHOOK_URL", "").strip()
        self.webhook_timeout = int(sw.get("webhook_timeout_seconds", 8))
        self.webhook_retries = int(sw.get("webhook_retries", 2))
        self.http = requests.Session()
        self.http.headers.update({"User-Agent": "JTWP-SSH-Watcher/1.2"})

        # SSH auto-blocking reuses the existing failed_attempts counter.
        # "block_after": 20 means the IP is blocked on attempt 21.
        self.auto_block_enabled = bool(sw.get("auto_block_enabled", False))
        self.auto_block_after = int(sw.get("auto_block_after", 20))
        self.auto_block_command = str(
            sw.get("auto_block_command", "/usr/local/bin/block-ip")
        )
        self.auto_block_use_sudo = bool(sw.get("auto_block_use_sudo", True))
        self.auto_block_private_ips = bool(
            sw.get("auto_block_private_ips", False)
        )

        # Keep raw whitelist values out of config.json if desired:
        # JTWP_SSH_AUTOBLOCK_WHITELIST=1.2.3.4,5.6.7.8
        raw_whitelist = os.getenv(
            "JTWP_SSH_AUTOBLOCK_WHITELIST",
            ""
        )
        self.auto_block_whitelist = {
            value.strip()
            for value in raw_whitelist.split(",")
            if value.strip()
        }

        # Persistent Discord SSH status embed.
        self.status_channel_id = os.getenv(
            "JTWP_SSH_STATUS_CHANNEL_ID",
            "",
        ).strip()
        self.discord_bot_token = os.getenv(
            "JTWP_DISCORD_BOT_TOKEN",
            "",
        ).strip()
        self.status_interval = max(
            15,
            int(sw.get("discord_status_interval_seconds", 60)),
        )
        self.status_state_path = self.ssh_dir / "discord_status.json"
        self.status_webhook_url = os.getenv("JTWP_SSH_STATUS_WEBHOOK_URL", "").strip()
        self.status_stop = threading.Event()
        self.failure_times = deque()
        self.peak_rate_per_minute = 0
        self.last_attempt = None
        self._load_recent_ssh_events()
        self.status_http = requests.Session()
        self.status_http.headers.update({
            "Authorization": f"Bot {self.discord_bot_token}",
            "Content-Type": "application/json",
            "User-Agent": "JTWP-SSH-Status/1.0",
        })

    def _load_recent_ssh_events(self) -> None:
        if not self.events_path.exists():
            return
        now_epoch = time.time()
        cutoff = now_epoch - 86400
        minute_buckets = Counter()
        try:
            with self.events_path.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        item = json.loads(line)
                    except Exception:
                        continue
                    raw_ts = str(item.get("timestamp") or "")
                    try:
                        dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                    except Exception:
                        continue
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    epoch = dt.timestamp()
                    if epoch < cutoff:
                        continue
                    self.failure_times.append(epoch)
                    minute_buckets[int(epoch // 60)] += 1
                    self.last_attempt = item
            if minute_buckets:
                self.peak_rate_per_minute = max(minute_buckets.values())
        except OSError:
            pass

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

            player_matches = self.playerdb.players_for_ip_hash(ip_hash)
            event = {
                "timestamp": ts,
                "type": event_type,
                "ip_hash": ip_hash,
                "source_port": port,
                "username": username,
                "background": background,
                "player_matches": player_matches,
            }
            append_jsonl(self.events_path, event)
            now_epoch = time.time()
            self.failure_times.append(now_epoch)
            cutoff = now_epoch - 86400
            while self.failure_times and self.failure_times[0] < cutoff:
                self.failure_times.popleft()
            one_minute = sum(1 for t in self.failure_times if t >= now_epoch - 60)
            self.peak_rate_per_minute = max(self.peak_rate_per_minute, one_minute)
            self.last_attempt = event.copy()

            host = self.failed_hosts.setdefault(ip_hash, {
                "first_seen": ts,
                "last_seen": ts,
                "failed_attempts": 0,
                "usernames": {},
                "source_ports": [],
                "background": background,
                "players_seen_on_ip": [],
                "blocked": False,
            })

            # Older failed_hosts.json records may predate the blocked field.
            # Treat those records as not blocked until auto-block succeeds.
            host.setdefault("blocked", False)
            host["first_seen"] = min(host.get("first_seen") or ts, ts)
            host["last_seen"] = max(host.get("last_seen") or ts, ts)
            host["failed_attempts"] = int(host.get("failed_attempts", 0)) + 1
            host["background"] = background
            host["players_seen_on_ip"] = player_matches

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

            # Reuse the existing SSH failed-attempt counter for auto-blocking.
            self.auto_block_ip(ip, ip_hash, host, ts)

            if host.get("blocked"):
                raw["blocked"] = True
                raw["blocked_at"] = host.get("blocked_at")

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
            # Failed-auth Discord reporting is handled by the single static
            # status message instead of one webhook post per attempt.
            return

    def should_auto_block(self, ip: str, host: dict) -> tuple[bool, str]:
        if not self.auto_block_enabled:
            return False, "disabled"

        if host.get("blocked") is True:
            return False, "already_blocked"

        attempts = int(host.get("failed_attempts", 0))
        if attempts <= self.auto_block_after:
            return False, "below_threshold"

        if ip in self.auto_block_whitelist:
            return False, "whitelisted"

        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False, "invalid_ip"

        if not self.auto_block_private_ips:
            if addr.is_private or addr.is_loopback or addr.is_link_local:
                return False, "private_or_local"

        return True, "threshold_exceeded"

    def auto_block_ip(self, ip: str, ip_hash: str, host: dict, ts: str):
        should_block, reason = self.should_auto_block(ip, host)

        if not should_block:
            if reason == "whitelisted":
                host["auto_block_skipped"] = "whitelisted"
            elif reason == "private_or_local":
                host["auto_block_skipped"] = "private_or_local"
            return

        cmd = [self.auto_block_command, ip]
        if self.auto_block_use_sudo:
            # -n prevents the watcher from hanging waiting for a password.
            cmd = ["sudo", "-n"] + cmd

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=20,
                check=False,
            )
        except Exception as exc:
            host["block_error"] = str(exc)
            host["block_error_at"] = ts
            print(
                f"[{ts}] SSH auto-block failed for {ip_hash[:16]}…: {exc}",
                file=sys.stderr,
            )
            return

        if result.returncode == 0:
            host["blocked"] = True
            host["blocked_at"] = ts
            host["blocked_after_attempts"] = int(
                host.get("failed_attempts", 0)
            )
            host["block_command"] = self.auto_block_command
            host.pop("block_error", None)
            host.pop("block_error_at", None)

            append_human_log(
                self.log_path,
                ts,
                (
                    f"SSH host auto-blocked / IP Hash: {ip_hash} "
                    f"/ Failed Attempts: {host['blocked_after_attempts']}"
                ),
            )

            print(
                f"[{ts}] AUTO-BLOCKED SSH host "
                f"{ip_hash[:16]}… after "
                f"{host['blocked_after_attempts']} failures"
            )
        else:
            error = (
                result.stderr.strip()
                or result.stdout.strip()
                or f"exit code {result.returncode}"
            )
            host["block_error"] = error
            host["block_error_at"] = ts
            print(
                f"[{ts}] SSH auto-block failed for "
                f"{ip_hash[:16]}…: {error}",
                file=sys.stderr,
            )

    @staticmethod
    def _sanitize_background(value):
        if isinstance(value, dict):
            out = dict(value)
            out.pop("primary_failure", None)
            out.pop("fallback_failure", None)
            for key, child in list(out.items()):
                out[key] = SSHWatcher._sanitize_background(child)
            return out
        if isinstance(value, list):
            return [
                SSHWatcher._sanitize_background(child)
                for child in value
            ]
        return value

    def _ssh_recent_rates(self):
        now_epoch = time.time()
        cutoff = now_epoch - 86400
        while self.failure_times and self.failure_times[0] < cutoff:
            self.failure_times.popleft()
        def count(seconds):
            edge = now_epoch - seconds
            return sum(1 for t in self.failure_times if t >= edge)
        return count(60), count(300), count(3600), count(86400)

    def build_status_payload(self) -> dict:
        total_attempts = 0
        blocked_hosts = 0
        player_match_hosts = 0
        usernames = Counter()
        source_ports = Counter()
        ranked_hosts = []
        blocks_today = 0
        today = datetime.now(timezone.utc).date().isoformat()

        for ip_hash, raw_host in self.failed_hosts.items():
            if not isinstance(raw_host, dict):
                continue
            host = self._sanitize_background(raw_host)
            attempts = int(host.get("failed_attempts", 0) or 0)
            total_attempts += attempts
            blocked = bool(host.get("blocked", False))
            if blocked:
                blocked_hosts += 1
                if str(host.get("blocked_at") or "").startswith(today):
                    blocks_today += 1
            players = host.get("players_seen_on_ip") or []
            if players:
                player_match_hosts += 1
            for username, count in (host.get("usernames") or {}).items():
                try:
                    usernames[str(username)] += int(count)
                except (TypeError, ValueError):
                    pass
            # source_ports is a unique list in older records, so this is a
            # frequency-of-hosts view rather than exact attempt count.
            for port in host.get("source_ports") or []:
                source_ports[str(port)] += 1
            ranked_hosts.append((str(ip_hash), attempts, blocked, len(players)))

        unique_hosts = len(ranked_hosts)
        blocked_percent = (blocked_hosts / unique_hosts * 100.0) if unique_hosts else 0.0
        one, five, hour, day = self._ssh_recent_rates()

        if one >= 21:
            status = "🚨 ATTACK / FLOOD"
        elif one >= 11:
            status = "🔴 CRITICAL"
        elif one >= 6:
            status = "🟠 HIGH"
        elif one >= 3:
            status = "🟡 ELEVATED"
        else:
            status = "🟢 NORMAL"

        top_ports = [f"__{port} —__ `{count:,}`" for port, count in source_ports.most_common(5)]
        top_users = [f"__{user} —__ `{count:,}`" for user, count in usernames.most_common(10)]
        top_sources = sorted(ranked_hosts, key=lambda x: x[1], reverse=True)[:5]
        source_lines = [f"__{ih[:12]}… —__ `{attempts:,}`" for ih, attempts, _, _ in top_sources]
        recent = self.last_attempt or {}
        recent_hash = str(recent.get("ip_hash") or "None")

        description = (
            "-----------------------------------------------------------------\n"
            ":hash: **Most Seen Source Ports**\n" + ("\n".join(top_ports) if top_ports else "`None`") +
            "\n\n👤 **Most Targeted Usernames**\n" + ("\n".join(top_users) if top_users else "`None`") +
            "\n\n🔥 **Most Active Source Hashes**\n" + ("\n".join(source_lines) if source_lines else "`None`") +
            "\n-----------------------------------------------------------------"
        )

        fields = [
            {
                "name": ":shield: - SSH-focused IPS",
                "value": (
                    f":black_small_square: __Status:__ `{status}`\n"
                    f":black_small_square: __Failed Auth Rate:__ `{one}/min`\n"
                    f":black_small_square: __Peak Rate:__ `{self.peak_rate_per_minute}/min`\n"
                    f":black_small_square: __Blocked IPs:__ `{blocked_hosts}`\n"
                    f":black_small_square: __Blocks Today:__ `{blocks_today}`"
                ),
                "inline": True,
            },
            {
                "name": ":computer: - Recent Attempt",
                "value": (
                    f":black_small_square: __Type:__ `{recent.get('type') or 'None'}`\n"
                    f":black_small_square: __Username:__ `{recent.get('username') or 'None'}`\n"
                    f":black_small_square: __Source Hash:__ `{recent_hash[:12]}…`\n"
                    f":black_small_square: __Source Port:__ `{recent.get('source_port') or 'None'}`\n"
                    f":black_small_square: __Blocked:__ `{self._yn((self.failed_hosts.get(recent.get('ip_hash')) or {}).get('blocked'))}`"
                ),
                "inline": True,
            },
            {
                "name": "📊 - Current Statistics",
                "value": (
                    f"__Failed Login Attempts:__ `{total_attempts:,}`\n"
                    f"__Unique Source Hashes:__ `{unique_hosts:,}`\n"
                    f"__Blocked Sources:__ `{blocked_hosts} ({blocked_percent:.1f}%)`\n"
                    f"__Player IP Matches:__ `{player_match_hosts}`"
                ),
                "inline": True,
            },
            {
                "name": "⏱️ - Recent Activity",
                "value": (
                    f"__1 Minute:__ `{one}`\n"
                    f"__5 Minutes:__ `{five}`\n"
                    f"__1 Hour:__ `{hour}`\n"
                    f"__24 Hours:__ `{day}`"
                ),
                "inline": True,
            },
        ]

        return {
            "content": (
                "----------------------------------------------\n"
                "--  :octagonal_sign:    ** __SSH Server Status__ **  :octagonal_sign:    --\n"
                "----------------------------------------------\n"
                "*Continuously updated SSH authentication security summary.*"
            ),
            "embeds": [{
                "title": ":no_pedestrians:  __**Security Report**__ :exclamation:",
                "description": description,
                "color": 3618621,
                "fields": fields,
                "footer": {"text": f"JTWP SSH Watcher • Updated {now_iso()}"},
            }],
            "components": [],
        }

    def build_status_embed(self) -> dict:
        # Backward-compatible helper for bot-channel mode.
        return self.build_status_payload()["embeds"][0]

    def update_status_embed(self):
        payload = self.build_status_payload()
        state = load_json(self.status_state_path, {})
        message_id = str(state.get("message_id") or "").strip()

        # Preferred mode: dedicated webhook. It can create and edit its own
        # persistent message without requiring a bot channel ID.
        if self.status_webhook_url:
            if message_id and state.get("mode") == "webhook":
                url = self.status_webhook_url.rstrip("/") + f"/messages/{message_id}"
                response = self.status_http.patch(url, json=payload, timeout=self.webhook_timeout)
                if response.status_code in (200, 204):
                    state["updated_at"] = now_iso()
                    atomic_write_json(self.status_state_path, state)
                    return
                if response.status_code != 404:
                    print(f"SSH status webhook PATCH failed: HTTP {response.status_code}: {response.text[:300]}", file=sys.stderr)
                    return

            sep = "&" if "?" in self.status_webhook_url else "?"
            response = self.status_http.post(
                self.status_webhook_url + sep + "wait=true",
                json=payload,
                timeout=self.webhook_timeout,
            )
            if 200 <= response.status_code < 300:
                body = response.json()
                atomic_write_json(self.status_state_path, {
                    "mode": "webhook",
                    "message_id": str(body.get("id")),
                    "created_at": now_iso(),
                    "updated_at": now_iso(),
                })
            else:
                print(f"SSH status webhook POST failed: HTTP {response.status_code}: {response.text[:300]}", file=sys.stderr)
            return

        # Fallback: existing bot-token + channel mode.
        if not self.status_channel_id or not self.discord_bot_token:
            return
        embed = payload["embeds"][0]
        state_channel = str(state.get("channel_id") or "").strip()
        if state_channel and state_channel != self.status_channel_id:
            message_id = ""
        if message_id and state.get("mode") != "webhook":
            url = f"https://discord.com/api/v10/channels/{self.status_channel_id}/messages/{message_id}"
            response = self.status_http.patch(url, json={"content": payload["content"], "embeds": [embed]}, timeout=self.webhook_timeout)
            if response.status_code == 200:
                state["updated_at"] = now_iso()
                atomic_write_json(self.status_state_path, state)
                return
            if response.status_code != 404:
                print(f"SSH status embed PATCH failed: HTTP {response.status_code}: {response.text[:300]}", file=sys.stderr)
                return
        url = f"https://discord.com/api/v10/channels/{self.status_channel_id}/messages"
        response = self.status_http.post(url, json={"content": payload["content"], "embeds": [embed]}, timeout=self.webhook_timeout)
        if 200 <= response.status_code < 300:
            body = response.json()
            atomic_write_json(self.status_state_path, {
                "mode": "bot",
                "channel_id": self.status_channel_id,
                "message_id": str(body.get("id")),
                "created_at": now_iso(),
                "updated_at": now_iso(),
            })
        else:
            print(f"SSH status embed POST failed: HTTP {response.status_code}: {response.text[:300]}", file=sys.stderr)

    def status_loop(self):
        print(
            "SSH status embed thread started "
            f"(interval={self.status_interval}s)",
            flush=True,
        )

        while not self.status_stop.is_set():
            try:
                self.update_status_embed()
            except requests.RequestException as exc:
                print(
                    "SSH status Discord request failed: "
                    f"{type(exc).__name__}: {exc}",
                    file=sys.stderr,
                    flush=True,
                )
            except Exception as exc:
                print(
                    "SSH status embed error: "
                    f"{type(exc).__name__}: {exc}",
                    file=sys.stderr,
                    flush=True,
                )

            self.status_stop.wait(self.status_interval)

    @staticmethod
    def _yn(v):
        return "Yes" if v is True else "No" if v is False else "Unknown"

    def send_webhook(self, event: dict, host: dict):
        if not self.webhook_url:
            return

        bg = event.get("background") or {}
        matches = event.get("player_matches") or []

        match_text = "None" if not matches else "\n".join(
            f"• {x.get('player_name') or 'Unknown'} (`{x.get('product_id')}`)"
            for x in matches[:10]
        )

        payload = {
            "username": "JTWP Security",
            "embeds": [{
                "title": "SSH Authentication Failed",
                "description": "A failed SSH authentication attempt was detected.",
                "fields": [
                    {
                        "name": "Attempt",
                        "value":
                            f"Type: `{event.get('type')}`\n"
                            f"Username: `{event.get('username')}`\n"
                            f"Source Port: `{event.get('source_port')}`\n"
                            f"Attempts From Host: `{host.get('failed_attempts', 0)}`\n"
                            f"Blocked: `{self._yn(host.get('blocked', False))}`",
                        "inline": False
                    },
                    {
                        "name": "IP Hash",
                        "value": f"`{event.get('ip_hash')}`",
                        "inline": False
                    },
                    {
                        "name": "Network",
                        "value":
                            f"Organisation: `{bg.get('organisation') or 'Unknown'}`\n"
                            f"Country: `{bg.get('country_code') or 'Unknown'}`\n"
                            f"Type: `{bg.get('network_type') or 'Unknown'}`\n"
                            f"Proxy: `{self._yn(bg.get('proxy'))}` | "
                            f"VPN: `{self._yn(bg.get('vpn'))}` | "
                            f"Hosting: `{self._yn(bg.get('hosting'))}` | "
                            f"Tor: `{self._yn(bg.get('tor'))}`",
                        "inline": False
                    },
                    {
                        "name": "Players Seen On Same IP",
                        "value": match_text,
                        "inline": False
                    },
                ],
                "footer": {
                    "text": f"JTWP • {event.get('timestamp')}"
                }
            }]
        }

        import time

        last = None

        for attempt in range(self.webhook_retries + 1):
            try:
                r = self.http.post(
                    self.webhook_url,
                    json=payload,
                    timeout=self.webhook_timeout
                )

                if 200 <= r.status_code < 300:
                    return

                if r.status_code == 429:
                    retry_after = None

                    try:
                        body = r.json()
                        retry_after = body.get("retry_after")
                    except Exception:
                        pass

                    if retry_after is None:
                        retry_after = r.headers.get("Retry-After")

                    try:
                        retry_after = float(retry_after)
                    except (TypeError, ValueError):
                        retry_after = 5.0

                    # Avoid immediate retry loops if Discord sends 0 or
                    # an unusably small retry interval.
                    retry_after = max(retry_after, 1.0)

                    last = (
                        "HTTP 429 rate limited; "
                        f"retry_after={retry_after:.2f}s"
                    )

                    print(
                        "Discord webhook rate limited. "
                        f"Retrying after {retry_after:.2f}s...",
                        file=sys.stderr,
                    )

                    if attempt < self.webhook_retries:
                        time.sleep(retry_after)

                    continue

                last = f"HTTP {r.status_code}: {r.text[:200]}"

            except requests.RequestException as e:
                last = str(e)

            if attempt < self.webhook_retries:
                time.sleep(attempt + 1)

        print(
            f"SSH webhook failed: {last}",
            file=sys.stderr
        )

    def run(self):
        # journalctl accepts multiple -u arguments.
        cmd = ["journalctl", "-f", "-n", "0", "-o", "cat"]
        for unit in self.units:
            cmd.extend(["-u", unit])

        print("JTWP SSH watcher started.", flush=True)
        print("Following:", ", ".join(self.units), flush=True)

        if self.status_webhook_url or (self.status_channel_id and self.discord_bot_token):
            print(
                "SSH static security status enabled.",
                flush=True,
            )
            status_thread = threading.Thread(
                target=self.status_loop,
                name="ssh-discord-status",
                daemon=True,
            )
            status_thread.start()
        else:
            print(
                "SSH status embed disabled: set JTWP_SSH_STATUS_WEBHOOK_URL "
                "or the bot-token/channel fallback.",
                file=sys.stderr,
                flush=True,
            )

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError:
            self.status_stop.set()
            raise SystemExit("journalctl was not found.")

        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                self.record(line.rstrip("\n"))
        except KeyboardInterrupt:
            proc.terminate()
        finally:
            self.status_stop.set()


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
