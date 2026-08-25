#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import subprocess
import json
import os
import re
import sys
import threading
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from collections import Counter, deque
from pathlib import Path
from typing import Any, Optional

import requests
from pavlov import PavlovRCON

from collector import Collector, DEFAULT_CONFIG, NetSession, TS_RE, load_json

IP_PORT_RE = re.compile(r"RemoteAddr:\s*(?P<ip>(?:\d{1,3}\.){3}\d{1,3}):(?P<port>\d+)")
CONNECTION_RE = re.compile(r"\bName:\s*(?P<conn>IpConnection_\d+)")
UNIQUE_ID_RE = re.compile(r"UniqueId:\s*(?P<unique_id>[^\s,]+)", re.IGNORECASE)
PRODUCT_ID_VALUE_RE = re.compile(
    r"^(?:NULL:)?(?:localhost-)?(?P<product_id>[0-9a-f]{32})$",
    re.IGNORECASE,
)
PLAYER_JOIN_RE = re.compile(r"PavlovLog:\s*Player\s+(?P<product_id>[0-9a-fA-F]{32})\s+Joined\b")
JOIN_SUCCEEDED_RE = re.compile(r"LogNet:\s*Join succeeded:\s*(?P<name>.+)$")
DIRECT_TIMEOUT_RE = re.compile(
    r"UNetConnection::Tick:\s*Connection TIMED OUT\. Closing connection",
    re.IGNORECASE,
)
INVALID_VERSION_RE = re.compile(
    r"NotifyControlMessage:\s*Client\s+(?P<conn>IpConnection_\d+)\s+connecting with invalid version",
    re.IGNORECASE,
)
PENDING_LOST_RE = re.compile(
    r"UNetConnection::PendingConnectionLost\.",
    re.IGNORECASE,
)
RCON_FAIL_RE = re.compile(
    r"Rcon:\s*User Failed authentication! Closing connection to client "
    r"(?P<ip>(?:\d{1,3}\.){3}\d{1,3}):(?P<port>\d+)"
)


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def append_jsonl(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, sort_keys=True) + "\n")


def normalize_product_id(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    m = PRODUCT_ID_VALUE_RE.match(value.strip())
    return m.group("product_id").lower() if m else None


def product_id_from_network_user_id(value: Optional[str]) -> Optional[str]:
    return normalize_product_id(value)


def product_id_from_line(body: str) -> Optional[str]:
    m = UNIQUE_ID_RE.search(body)
    if not m:
        return None
    return normalize_product_id(m.group("unique_id"))


def parse_pavlov_timestamp(ts: Optional[str]):
    if not ts:
        return None
    from datetime import datetime
    try:
        return datetime.strptime(ts, "%Y.%m.%d-%H.%M.%S:%f")
    except (TypeError, ValueError):
        return None


def calc_duration(start: Optional[str], end: Optional[str]) -> Optional[float]:
    a = parse_pavlov_timestamp(start)
    b = parse_pavlov_timestamp(end)
    if not a or not b:
        return None
    return round((b - a).total_seconds(), 3)


def format_duration(seconds: Optional[float]) -> Optional[str]:
    if seconds is None:
        return None
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def coerce_number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def extract_inspect_list(response: Any) -> list[dict[str, Any]]:
    """Find an InspectList array in common PavlovRCON response shapes."""
    if isinstance(response, dict):
        direct = response.get("InspectList")
        if isinstance(direct, list):
            return [x for x in direct if isinstance(x, dict)]
        for value in response.values():
            found = extract_inspect_list(value)
            if found:
                return found
    elif isinstance(response, list):
        # Some clients may return the list itself.
        if response and all(isinstance(x, dict) for x in response):
            if any("PlayerName" in x or "UniqueId" in x for x in response):
                return response
        for value in response:
            found = extract_inspect_list(value)
            if found:
                return found
    return []


@dataclass
class TailState:
    path: Path
    offset: int = 0
    inode: Optional[int] = None

    def initialize(self, start_at_end: bool) -> None:
        if self.path.exists():
            st = self.path.stat()
            self.inode = st.st_ino
            self.offset = st.st_size if start_at_end else 0

    def read_new_lines(self) -> list[str]:
        if not self.path.exists():
            self.offset = 0
            self.inode = None
            return []
        st = self.path.stat()
        if self.inode is None or st.st_ino != self.inode or st.st_size < self.offset:
            self.inode = st.st_ino
            self.offset = 0
        if st.st_size == self.offset:
            return []
        with self.path.open("r", encoding="utf-8", errors="replace") as f:
            f.seek(self.offset)
            lines = f.readlines()
            self.offset = f.tell()
        return lines


class LiveConnectionWatcher:
    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        self.collector = Collector(cfg)
        wc = cfg.get("connection_watcher", {})
        self.poll = float(wc.get("poll_interval_seconds", 0.5))
        self.start_at_end = bool(wc.get("start_at_end", True))
        self.timeout = int(wc.get("webhook_timeout_seconds", 8))
        self.retries = int(wc.get("webhook_retries", 2))
        self.connection_webhook = os.getenv("JTWP_CONNECTION_WEBHOOK_URL", "").strip()
        self.rcon_webhook = (
            os.getenv("JTWP_RCON_WEBHOOK_URL", "").strip()
            or os.getenv("JTWP_SECURITY_WEBHOOK_URL", "").strip()
        )
        self.http = requests.Session()
        self.http.headers.update({"User-Agent": "JTWP-Live-Watcher/2.0"})

        self.tails: dict[str, TailState] = {}
        self.by_endpoint: dict[str, dict[str, NetSession]] = {}
        self.by_conn: dict[str, dict[str, NetSession]] = {}
        self.by_name: dict[str, dict[str, NetSession]] = {}
        self.active_rcon: dict[str, dict] = {}
        self.platforms: dict[str, str] = {}
        self.online: dict[str, dict[str, dict[str, Any]]] = {}
        self.closed_connections: dict[str, set[str]] = {}
        self.invalid_version_connections: dict[str, set[str]] = {}

        self.connections_root = self.collector.data_root / "global" / "connections"
        self.online_path = self.connections_root / "online_players.json"
        self.events_path = self.connections_root / "events.jsonl"

        # Admin monitoring now uses this watcher's live player state instead of
        # RCON loopOutput.json / InspectAll.
        self.admin_cfg = cfg.get("admin_notifications", {})
        self.admin_enabled = bool(self.admin_cfg.get("enabled", True))
        self.admin_role_id = str(self.admin_cfg.get("role_id", "") or "")
        self.admin_webhook = os.getenv(
            self.admin_cfg.get("webhook_env", "JTWP_ADMIN_WEBHOOK_URL"),
            "",
        ).strip()
        self.no_admin_delay = int(
            self.admin_cfg.get("no_admin_delay_seconds", 60)
        )
        self.response_window = int(
            self.admin_cfg.get("response_window_seconds", 900)
        )
        self.teamkill_threshold = int(
            self.admin_cfg.get("teamkill_threshold", 2)
        )

        self.admin_root = self.collector.data_root / "global" / "admins"
        self.admin_state_path = self.admin_root / "monitor_state.json"
        self.admin_events_path = self.admin_root / "events.jsonl"
        self.admin_sessions_path = self.admin_root / "sessions.jsonl"
        self.admin_alerts_path = self.admin_root / "alerts.jsonl"
        self.admin_stats_path = self.admin_root / "admin_stats.json"

        self.admin_state = load_json(
            self.admin_state_path,
            {"servers": {}, "open_alerts": []},
        )
        if not isinstance(self.admin_state, dict):
            self.admin_state = {"servers": {}, "open_alerts": []}
        self.admin_state.setdefault("servers", {})
        self.admin_state.setdefault("open_alerts", [])

        # Lightweight RCON InspectAll loop. It sleeps when fewer than the
        # configured number of players are online, so empty/quiet servers do
        # not receive continuous InspectAll requests.
        inspect_cfg = cfg.get("rcon_inspect_loop", {})
        self.inspect_enabled = bool(inspect_cfg.get("enabled", True))
        self.inspect_min_players = max(1, int(inspect_cfg.get("minimum_players", 2)))
        self.inspect_interval = max(1.0, float(inspect_cfg.get("poll_interval_seconds", 5)))
        self.inspect_timeout = max(1.0, float(inspect_cfg.get("timeout_seconds", 8)))
        self.record_ping_samples = bool(inspect_cfg.get("record_ping_samples", True))
        self.ping_samples_path = self.connections_root / "ping_samples.jsonl"
        self.inspect_stop = threading.Event()
        self.inspect_threads: list[threading.Thread] = []
        self.state_lock = threading.RLock()

        # RCON security / IPS / static Discord status.
        sec = cfg.get("rcon_security", {})
        self.rcon_security_enabled = bool(sec.get("enabled", True))
        self.rcon_rate_window = max(10, int(sec.get("rate_window_seconds", 60)))
        self.rcon_elevated_rate = max(1, int(sec.get("elevated_rate", 3)))
        self.rcon_high_rate = max(self.rcon_elevated_rate, int(sec.get("high_rate", 6)))
        self.rcon_critical_rate = max(self.rcon_high_rate, int(sec.get("critical_rate", 11)))
        self.rcon_attack_rate = max(self.rcon_critical_rate, int(sec.get("attack_rate", 21)))
        self.rcon_auto_block_enabled = bool(sec.get("auto_block_enabled", False))
        self.rcon_block_after = max(1, int(sec.get("block_after_failures", 5)))
        self.rcon_block_window = max(10, int(sec.get("block_window_seconds", 60)))
        self.rcon_block_command = str(sec.get("block_command", "/usr/local/bin/block-ip"))
        self.rcon_block_use_sudo = bool(sec.get("block_use_sudo", True))
        self.rcon_status_interval = max(15, int(sec.get("discord_status_interval_seconds", 30)))
        self.rcon_status_webhook = os.getenv("JTWP_RCON_STATUS_WEBHOOK_URL", "").strip()
        self.rcon_command_webhook = os.getenv("JTWP_RCON_COMMAND_WEBHOOK_URL", "").strip()
        self.rcon_command_exclude = {
            str(x).casefold() for x in sec.get(
                "command_webhook_exclude",
                ["InspectAll", "ServerInfo", "RefreshList"],
            )
        }
        self.rcon_security_root = self.collector.data_root / "global" / "rcon_security"
        self.rcon_security_root.mkdir(parents=True, exist_ok=True)
        self.rcon_security_state_path = self.rcon_security_root / "state.json"
        self.verified_connections_path = self.rcon_security_root / "verified_connections.json"
        self.rcon_status_state_path = self.rcon_security_root / "discord_status.json"
        self.rcon_security_events_path = self.rcon_security_root / "events.jsonl"
        self.rcon_security_state = load_json(self.rcon_security_state_path, {})
        if not isinstance(self.rcon_security_state, dict):
            self.rcon_security_state = {}
        self.rcon_security_state.setdefault("blocked_hashes", {})
        self.rcon_security_state.setdefault("blocks", [])
        self.rcon_security_state.setdefault("peak_rate_per_minute", 0)
        self.rcon_failure_times = deque()
        self.rcon_failure_times_by_hash = {}
        self.rcon_status_stop = threading.Event()
        self.rcon_status_thread = None
        self._load_recent_rcon_security_events()

        raw_whitelist = os.getenv("JTWP_RCON_AUTOBLOCK_WHITELIST", "")
        self.rcon_auto_block_whitelist = {
            x.strip() for x in raw_whitelist.split(",") if x.strip()
        }

        self.collector.load_global_admins()
        for server in self.collector.servers:
            self.collector.collect_bans(server)
            sid = server.server_id
            tail = TailState(server.log_path / "Pavlov.log")
            tail.initialize(self.start_at_end)
            self.tails[sid] = tail
            self.by_endpoint[sid] = {}
            self.by_conn[sid] = {}
            self.by_name[sid] = {}
            self.active_rcon[sid] = {}
            self.online[sid] = {}
            self.closed_connections[sid] = set()
            self.invalid_version_connections[sid] = set()

            self.admin_state["servers"].setdefault(
                sid,
                {
                    "admins": {},
                    "no_admin_since": None,
                    "no_admin_alert_active": False,
                    "players": {},
                },
            )

            if server.platform_override in {"SHACK", "PCVR"}:
                self.platforms[sid] = server.platform_override
            else:
                state = load_json(self.collector.data_root / "servers" / sid / "server.json", {})
                self.platforms[sid] = state.get("platform") or "PCVR"
        self.write_online_state()
        self.start_inspect_threads()
        self.start_rcon_status_thread()

    def start_inspect_threads(self) -> None:
        if not self.inspect_enabled:
            return

        for server in self.collector.servers:
            # ServerCfg deliberately only contains log-related fields, so map
            # back to the original server config by its resolved log path.
            scfg = None
            for item in self.cfg.get("servers", []):
                try:
                    if (
                        Path(item.get("log_path", "")).expanduser().resolve()
                        == Path(server.log_path).expanduser().resolve()
                    ):
                        scfg = item
                        break
                except Exception:
                    continue
            rcfg = (scfg or {}).get("rcon", {})
            if not rcfg.get("enabled", False):
                continue

            thread = threading.Thread(
                target=self.inspect_loop,
                args=(server, rcfg),
                name=f"jtwp-inspect-{server.server_id}",
                daemon=True,
            )
            thread.start()
            self.inspect_threads.append(thread)

    def inspect_loop(self, server, rcfg: dict[str, Any]) -> None:
        sid = server.server_id
        host = str(rcfg.get("host", "127.0.0.1"))
        port = int(rcfg.get("port", 0) or 0)
        password_env = str(rcfg.get("password_env") or "")

        while not self.inspect_stop.is_set():
            with self.state_lock:
                player_count = sum(
                    1 for item in self.online.get(sid, {}).values()
                    if item.get("product_id") and item.get("joined_at")
                )

            if player_count < self.inspect_min_players:
                self.inspect_stop.wait(1.0)
                continue

            password = os.getenv(password_env, "").strip() if password_env else ""
            if not password or not port:
                print(
                    f"[INSPECT] {sid}: RCON unavailable "
                    f"(missing {'password' if not password else 'port'})",
                    file=sys.stderr,
                )
                self.inspect_stop.wait(self.inspect_interval)
                continue

            try:
                response = asyncio.run(
                    self._inspect_once(host, port, password)
                )
                inspect_list = extract_inspect_list(response)
                self.apply_inspect_list(server, inspect_list)
            except Exception as exc:
                print(
                    f"[INSPECT] {sid}: {exc}",
                    file=sys.stderr,
                )

            self.inspect_stop.wait(self.inspect_interval)

    async def _inspect_once(
        self,
        host: str,
        port: int,
        password: str,
    ) -> Any:
        print(
            f"[RCON LOOP] -> {host}:{port} InspectAll",
            flush=True,
        )

        client = PavlovRCON(host, port, password)

        response = await asyncio.wait_for(
            client.send("InspectAll"),
            timeout=self.inspect_timeout,
        )

        inspect_list = extract_inspect_list(response)

        print(
            f"[RCON LOOP] <- {host}:{port} {len(inspect_list)} players",
            flush=True,
        )

        return response

    def find_online_for_inspect(
        self,
        sid: str,
        item: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        uid = str(item.get("UniqueId") or "").strip()
        name = str(item.get("PlayerName") or "").strip()

        # Prefer the unique ID because PCVR uses SteamID64 and SHACK uses the
        # account/player identifier stored by the connection watcher.
        if uid:
            for live in self.online.get(sid, {}).values():
                if str(live.get("unique_id") or "").strip() == uid:
                    return live

        if name:
            folded = name.casefold()
            for live in self.online.get(sid, {}).values():
                if str(live.get("player_name") or "").casefold() == folded:
                    return live

        return None

    def apply_inspect_list(
        self,
        server,
        inspect_list: list[dict[str, Any]],
    ) -> None:
        sid = server.server_id
        now = self._utc_iso()
        matched = 0

        with self.state_lock:
            for item in inspect_list:
                live = self.find_online_for_inspect(sid, item)
                if not live:
                    continue

                matched += 1
                score_num = coerce_number(item.get("Score"))
                ping_num = coerce_number(item.get("Ping"))
                cash_num = coerce_number(item.get("Cash"))

                live["score"] = (
                    int(score_num)
                    if score_num is not None and score_num.is_integer()
                    else score_num
                )
                live["kda"] = item.get("KDA")
                live["cash"] = (
                    int(cash_num)
                    if cash_num is not None and cash_num.is_integer()
                    else cash_num
                )
                live["team_id"] = item.get("TeamId")
                live["dead"] = item.get("Dead")
                live["gag"] = item.get("Gag")
                live["rcon_updated_at"] = now

                if ping_num is not None:
                    old = live.get("ping_stats")
                    if not isinstance(old, dict):
                        old = {}
                    samples = int(old.get("samples", 0) or 0)
                    avg = coerce_number(old.get("average_ms"))
                    if avg is None or samples <= 0:
                        new_avg = ping_num
                        samples = 1
                    else:
                        new_avg = ((avg * samples) + ping_num) / (samples + 1)
                        samples += 1

                    old_min = coerce_number(old.get("min_ms"))
                    old_max = coerce_number(old.get("max_ms"))
                    live["ping"] = round(ping_num, 2)
                    live["ping_stats"] = {
                        "current_ms": round(ping_num, 2),
                        "average_ms": round(new_avg, 2),
                        "min_ms": round(min(old_min, ping_num), 2) if old_min is not None else round(ping_num, 2),
                        "max_ms": round(max(old_max, ping_num), 2) if old_max is not None else round(ping_num, 2),
                        "samples": samples,
                        "updated_at": now,
                    }

                    if self.record_ping_samples:
                        append_jsonl(
                            self.ping_samples_path,
                            {
                                "timestamp": now,
                                "server_id": sid,
                                "connection_id": live.get("connection_id"),
                                "product_id": live.get("product_id"),
                                "unique_id": live.get("unique_id"),
                                "player_name": live.get("player_name"),
                                "ping_ms": round(ping_num, 2),
                            },
                        )

                self.apply_score_alert(sid, live, score_num)

            self.write_online_state()

        if inspect_list:
            print(
                f"[INSPECT] {sid}: {matched}/{len(inspect_list)} players matched"
            )

    def apply_score_alert(
        self,
        sid: str,
        live: dict[str, Any],
        score: Optional[float],
    ) -> None:
        if score is None or not self.admin_enabled:
            return

        product_id = live.get("product_id")
        if not product_id:
            return

        state = self.admin_state["servers"].setdefault(
            sid,
            {
                "admins": {},
                "no_admin_since": None,
                "no_admin_alert_active": False,
                "players": {},
            },
        )
        pstate = state["players"].setdefault(
            product_id,
            {
                "negative_score_alert": False,
                "teamkill_alert": False,
            },
        )

        threshold = float(self.admin_cfg.get("negative_score_threshold", 0))
        if score < threshold and not pstate.get("negative_score_alert"):
            pstate["negative_score_alert"] = True
            self.create_admin_alert(
                sid,
                "negative_score",
                {
                    "product_id": product_id,
                    "player_name": live.get("player_name"),
                },
                {"score": score},
            )
            self.send_admin_webhook(
                "📉 Player Score Below Zero",
                f"Player **{live.get('player_name') or product_id}** has a score of `{score:g}`.",
                [{"name": "Server", "value": f"`{sid}`", "inline": True}],
            )
        elif score >= threshold:
            pstate["negative_score_alert"] = False

        self.save_admin_state()

    def run(self) -> None:
        print("JTWP live connection/RCON watcher v2 started.")
        print(f"Online state: {self.online_path}")
        while True:
            did = False
            for server in self.collector.servers:
                sid = server.server_id
                for raw in self.tails[sid].read_new_lines():
                    did = True
                    self.process_line(server, raw.rstrip("\n"))
            self.evaluate_admin_state()
            self.expire_admin_alerts()
            if not did:
                time.sleep(self.poll)

    def process_line(self, server, raw: str) -> None:
        m = TS_RE.match(raw)
        if not m:
            return
        ts, body = m.group("ts"), m.group("body").strip()
        sid = server.server_id

        if "PavlovLog: SHACK SERVER BUILD" in body:
            self.platforms[sid] = "SHACK"

        fail = RCON_FAIL_RE.search(body)
        if "Rcon:" in body:
            self.collector.handle_rcon(server, ts, body, self.active_rcon[sid])

            # Successful/normal RCON command audit webhook. Exclude authentication
            # chatter and commands generated by our own InspectAll loop by default.
            if not fail:
                self.maybe_send_rcon_command_webhook(server, ts, body)

        if fail:
            ip, port = fail.group("ip"), int(fail.group("port"))
            ih = self.collector.players.ip_hash(ip)
            matches = self.collector.players.players_for_ip_hash(ih)
            self.record_rcon_failure(server, ts, ip, ih, port, matches)
            return

        # Invalid network version: remember the exact pending IpConnection.
        invalid = INVALID_VERSION_RE.search(body)
        if invalid:
            conn = invalid.group("conn")
            self.invalid_version_connections[sid].add(conn)
            sess = self.by_conn[sid].get(conn)
            if sess:
                self.handle_connection_failed(
                    server,
                    sess,
                    ts,
                    "InvalidNetworkVersion",
                )
            return

        # Direct timeout lines contain the exact endpoint/IpConnection and,
        # for joined players, the Product ID. Treat this as terminal immediately.
        if DIRECT_TIMEOUT_RE.search(body) and "IpConnection_" in body:
            sess = self.find_session_from_line(sid, body)
            if sess:
                pid = product_id_from_line(body)
                if pid and not sess.product_id:
                    sess.product_id = pid

                if sess.product_id or sess.joined_at:
                    self.handle_live_leave(
                        server,
                        sess,
                        ts,
                        body,
                        reason="ConnectionTimeout",
                    )
                else:
                    self.handle_connection_failed(
                        server,
                        sess,
                        ts,
                        "ConnectionTimeout",
                    )

        # PendingConnectionLost is terminal for a connection that never joined.
        if PENDING_LOST_RE.search(body):
            sess = self.find_session_from_line(sid, body)
            if sess:
                self.handle_connection_failed(
                    server,
                    sess,
                    ts,
                    "PendingConnectionLost",
                )

        # Normal cleanup path. Keep this as a fallback for ordinary disconnects.
        if "LogNet: UChannel::CleanUp:" in body and "Closing connection." in body:
            sess = self.find_session_from_line(sid, body)
            if sess:
                self.handle_live_leave(
                    server,
                    sess,
                    ts,
                    body,
                    reason="ConnectionClosed",
                )

        # UChannel::Close is another fallback and also cleans pending connections.
        if "LogNet: UChannel::Close:" in body:
            sess = self.find_session_from_line(sid, body)
            if sess:
                pid = product_id_from_line(body)
                if pid and not sess.product_id:
                    sess.product_id = pid

                if sess.product_id or sess.joined_at:
                    self.handle_live_leave(
                        server,
                        sess,
                        ts,
                        body,
                        reason="ConnectionClosed",
                    )
                else:
                    reason = (
                        "InvalidNetworkVersion"
                        if sess.connection_name in self.invalid_version_connections[sid]
                        else "ConnectionClosedBeforeJoin"
                    )
                    self.handle_connection_failed(
                        server,
                        sess,
                        ts,
                        reason,
                    )

        join_success = JOIN_SUCCEEDED_RE.search(body)
        join_name = join_success.group("name").strip() if join_success else None
        prior = bool(join_name and join_name in self.by_name[sid] and self.by_name[sid][join_name].counted_join)

        # Preserve all existing collector persistence/index/IP/RCON behavior.
        self.collector.handle_connection_line(
            server,
            self.platforms[sid],
            ts,
            body,
            self.by_endpoint[sid],
            self.by_conn[sid],
            self.by_name[sid],
        )

        if "AddClientConnection: Added client connection:" in body:
            sess = self.find_session_from_line(sid, body)
            if sess:
                self.register_pending_session(server, sess, ts)
            return

        if "LogNet: Login request:" in body:
            name = self.collector.query_field(body, "Name") or self.collector.query_field(body, "name")
            sess = self.by_name[sid].get(name) if name else None
            if sess:
                pid = product_id_from_network_user_id(sess.network_user_id)
                if pid and not sess.product_id:
                    sess.product_id = pid
                self.refresh_live_session(server, sess, ts)
            return

        # This Product-ID join event exists in both the PCVR and SHACK samples.
        player_join = PLAYER_JOIN_RE.search(body)
        if player_join:
            product_id = player_join.group("product_id").lower()
            sess = self.find_session_for_product(sid, product_id)
            if not sess:
                latest = self.find_latest_pending_session(sid)
                if latest and product_id_from_network_user_id(latest.network_user_id) == product_id:
                    sess = latest
            if sess:
                sess.product_id = product_id
                if not sess.joined_at:
                    sess.joined_at = ts
                self.mark_player_online(server, sess, ts)
            return

        # Keep the existing Join succeeded webhook behavior.
        if join_name:
            sess = self.by_name[sid].get(join_name)
            if sess and not prior and sess.counted_join and sess.product_id:
                self.mark_player_online(server, sess, ts)
                self.collector.load_global_admins()
                self.collector.collect_bans(server)
                self.collector.apply_admin_flags()
                self.collector.apply_ban_flags_from_snapshots()
                self.collector.players.flush_indexes()
                if self.connection_webhook:
                    self.send_connection_alert(server, sess, ts)

    def find_session_from_line(self, sid: str, body: str) -> Optional[NetSession]:
        cm = CONNECTION_RE.search(body)
        if cm:
            sess = self.by_conn[sid].get(cm.group("conn"))
            if sess:
                return sess
        ep = IP_PORT_RE.search(body)
        if ep:
            endpoint = f"{ep.group('ip')}:{ep.group('port')}"
            return self.by_endpoint[sid].get(endpoint)
        return None

    def find_session_for_product(self, sid: str, product_id: str) -> Optional[NetSession]:
        product_id = product_id.lower()
        for sess in reversed(list(self.by_endpoint[sid].values())):
            direct = sess.product_id.lower() if sess.product_id else None
            network_pid = product_id_from_network_user_id(sess.network_user_id)
            if direct == product_id or network_pid == product_id:
                return sess
        return None

    def find_latest_pending_session(self, sid: str) -> Optional[NetSession]:
        candidates = [
            sess for sess in self.by_endpoint[sid].values()
            if sess.disconnected_at is None and not sess.product_id
        ]
        return candidates[-1] if candidates else None

    @staticmethod
    def session_key(sess: NetSession) -> str:
        return sess.connection_name or sess.endpoint

    def register_pending_session(self, server, sess: NetSession, ts: str) -> None:
        sid, key = server.server_id, self.session_key(sess)
        self.online[sid][key] = {
            "server_id": sid,
            "connection_id": sess.connection_name,
            "ip_hash": self.collector.players.ip_hash(sess.ip) if sess.ip else None,
            "source_port": sess.port,
            "platform": self.platforms[sid],
            "product_id": None,
            "unique_id": None,
            "player_name": None,
            "connected_at": sess.started_at or ts,
            "login_at": None,
            "joined_at": None,
            "admin": None,
            "banned": None,
        }
        self.write_online_state()

    def refresh_live_session(self, server, sess: NetSession, ts: str) -> None:
        sid, key = server.server_id, self.session_key(sess)
        entry = self.online[sid].setdefault(key, {})
        entry.update({
            "server_id": sid,
            "connection_id": sess.connection_name,
            "ip_hash": self.collector.players.ip_hash(sess.ip) if sess.ip else None,
            "source_port": sess.port,
            "platform": self.platforms[sid],
            "product_id": sess.product_id or product_id_from_network_user_id(sess.network_user_id),
            "unique_id": sess.unique_id,
            "player_name": sess.player_name,
            "connected_at": sess.started_at or ts,
            "login_at": sess.login_at,
            "joined_at": sess.joined_at,
            "admin": entry.get("admin"),
            "banned": entry.get("banned"),
        })
        self.write_online_state()

    def mark_player_online(self, server, sess: NetSession, ts: str) -> None:
        if not sess.product_id:
            return
        sid, key = server.server_id, self.session_key(sess)
        self.collector.load_global_admins()
        self.collector.collect_bans(server)
        self.collector.apply_admin_flags()
        self.collector.apply_ban_flags_from_snapshots()
        player = load_json(self.collector.players.player_dir(sess.product_id) / "player.json", {})
        already = key in self.online[sid] and self.online[sid][key].get("product_id") == sess.product_id and self.online[sid][key].get("joined_at")
        self.online[sid][key] = {
            "server_id": sid,
            "connection_id": sess.connection_name,
            "ip_hash": sess.enriched_ip_hash or (self.collector.players.ip_hash(sess.ip) if sess.ip else None),
            "source_port": sess.port,
            "platform": self.platforms[sid],
            "product_id": sess.product_id,
            "unique_id": sess.unique_id,
            "player_name": sess.player_name,
            "connected_at": sess.started_at,
            "login_at": sess.login_at,
            "joined_at": sess.joined_at or ts,
            "admin": player.get("admin"),
            "banned": player.get("banned"),
        }
        self.write_online_state()
        if already:
            return
        append_jsonl(self.events_path, {
            "type": "player_joined",
            "server_id": sid,
            "at": sess.joined_at or ts,
            "connection_id": sess.connection_name,
            "ip_hash": self.online[sid][key].get("ip_hash"),
            "source_port": sess.port,
            "product_id": sess.product_id,
            "unique_id": sess.unique_id,
            "player_name": sess.player_name,
            "platform": self.platforms[sid],
            "admin": player.get("admin"),
            "banned": player.get("banned"),
        })
        print(f"[JOIN] {sid} {sess.player_name or 'Unknown'} ({sess.product_id}) {key}")
        self.handle_admin_player_join(self.online[sid][key])

    def _remove_session_maps(self, sid: str, sess: NetSession) -> None:
        self.by_endpoint[sid].pop(sess.endpoint, None)
        if sess.connection_name:
            self.by_conn[sid].pop(sess.connection_name, None)
        if sess.player_name and self.by_name[sid].get(sess.player_name) is sess:
            self.by_name[sid].pop(sess.player_name, None)

    def handle_connection_failed(
        self,
        server,
        sess: NetSession,
        ts: str,
        reason: str,
    ) -> None:
        sid, key = server.server_id, self.session_key(sess)

        if key in self.closed_connections[sid]:
            return
        self.closed_connections[sid].add(key)

        entry = self.online[sid].pop(key, None) or {}
        self._remove_session_maps(sid, sess)
        self.write_online_state()

        connected_at = sess.started_at or entry.get("connected_at")
        total_duration = calc_duration(connected_at, ts)

        append_jsonl(self.events_path, {
            "type": "connection_failed",
            "server_id": sid,
            "at": ts,
            "connection_id": sess.connection_name,
            "ip_hash": entry.get("ip_hash") or (
                self.collector.players.ip_hash(sess.ip) if sess.ip else None
            ),
            "source_port": sess.port,
            "product_id": sess.product_id or entry.get("product_id"),
            "unique_id": sess.unique_id or entry.get("unique_id"),
            "player_name": sess.player_name or entry.get("player_name"),
            "platform": self.platforms[sid],
            "connected_at": connected_at,
            "disconnected_at": ts,
            "duration_seconds": total_duration,
            "duration_formatted": format_duration(total_duration),
            "disconnect_reason": reason,
        })

        print(
            f"[DROP] {sid} "
            f"{sess.player_name or entry.get('player_name') or 'pending'} "
            f"{key} reason={reason}"
        )

    def handle_live_leave(
        self,
        server,
        sess: NetSession,
        ts: str,
        body: str,
        reason: str = "ConnectionClosed",
    ) -> None:
        sid, key = server.server_id, self.session_key(sess)

        if key in self.closed_connections[sid]:
            return
        self.closed_connections[sid].add(key)

        pid = product_id_from_line(body)
        if pid and not sess.product_id:
            sess.product_id = pid

        entry = self.online[sid].pop(key, None) or {}
        self._remove_session_maps(sid, sess)
        self.write_online_state()

        connected_at = sess.started_at or entry.get("connected_at")
        joined_at = sess.joined_at or entry.get("joined_at")
        total_duration = calc_duration(connected_at, ts)
        joined_duration = calc_duration(joined_at, ts)

        event = {
            "type": "player_left",
            "server_id": sid,
            "at": ts,
            "connection_id": sess.connection_name,
            "ip_hash": entry.get("ip_hash") or (
                sess.enriched_ip_hash
                or (self.collector.players.ip_hash(sess.ip) if sess.ip else None)
            ),
            "source_port": sess.port,
            "product_id": sess.product_id or entry.get("product_id"),
            "unique_id": sess.unique_id or entry.get("unique_id"),
            "player_name": sess.player_name or entry.get("player_name"),
            "platform": self.platforms[sid],
            "connected_at": connected_at,
            "joined_at": joined_at,
            "disconnected_at": ts,
            "duration_seconds": total_duration,
            "duration_formatted": format_duration(total_duration),
            "joined_duration_seconds": joined_duration,
            "joined_duration_formatted": format_duration(joined_duration),
            "disconnect_reason": reason,
            "admin": entry.get("admin"),
            "banned": entry.get("banned"),
        }

        append_jsonl(self.events_path, event)
        print(
            f"[LEAVE] {sid} "
            f"{event.get('player_name') or 'Unknown'} "
            f"({event.get('product_id') or 'unresolved'}) "
            f"{key} reason={reason} "
            f"duration={event.get('duration_formatted') or 'Unknown'}"
        )
        self.handle_admin_player_leave(event)

    # ------------------------------------------------------------------
    # Admin monitoring
    # ------------------------------------------------------------------

    @staticmethod
    def _utc_iso() -> str:
        return datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z")

    def save_admin_state(self) -> None:
        atomic_write_json(
            self.admin_state_path,
            self.admin_state,
        )

    def send_admin_webhook(
        self,
        title: str,
        description: str,
        fields: Optional[list[dict]] = None,
        ping_role: bool = True,
    ) -> None:
        if not self.admin_enabled or not self.admin_webhook:
            return

        content = None
        allowed_roles: list[str] = []

        if ping_role and self.admin_role_id:
            content = f"<@&{self.admin_role_id}>"
            allowed_roles = [self.admin_role_id]

        payload = {
            "content": content,
            "allowed_mentions": {
                "parse": [],
                "roles": allowed_roles,
            },
            "embeds": [
                {
                    "title": title,
                    "description": description,
                    "fields": fields or [],
                    "footer": {"text": "JTWP.org"},
                    "timestamp": self._utc_iso(),
                }
            ],
        }

        self.post(
            self.admin_webhook,
            payload,
            "admin",
        )

    def create_admin_alert(
        self,
        server_id: str,
        alert_type: str,
        player: Optional[dict],
        details: dict,
    ) -> dict:
        import uuid

        alert = {
            "alert_id": (
                f"{server_id}-{alert_type}-"
                f"{uuid.uuid4().hex[:10]}"
            ),
            "created_at": self._utc_iso(),
            "server_id": server_id,
            "type": alert_type,
            "player": player,
            "details": details,
            "response_window_seconds": self.response_window,
            "admin_joined_within_window": False,
            "responding_admin": None,
            "responded_at": None,
            "response_seconds": None,
            "expired": False,
        }

        self.admin_state["open_alerts"].append(alert)
        append_jsonl(self.admin_alerts_path, alert)
        self.save_admin_state()
        return alert

    def respond_to_admin_alerts(
        self,
        server_id: str,
        admin: dict,
    ) -> None:
        now = datetime.now(timezone.utc)

        for alert in self.admin_state.get(
            "open_alerts",
            [],
        ):
            if (
                alert.get("server_id") != server_id
                or alert.get("responded_at")
                or alert.get("expired")
            ):
                continue

            try:
                created = datetime.fromisoformat(
                    alert["created_at"].replace(
                        "Z",
                        "+00:00",
                    )
                )
            except Exception:
                continue

            seconds = int(
                (now - created).total_seconds()
            )

            if seconds > self.response_window:
                continue

            alert.update(
                {
                    "admin_joined_within_window": True,
                    "responding_admin": admin,
                    "responded_at": self._utc_iso(),
                    "response_seconds": seconds,
                }
            )

            append_jsonl(
                self.admin_events_path,
                {
                    "timestamp": self._utc_iso(),
                    "event": "admin_alert_response",
                    "alert_id": alert.get("alert_id"),
                    "alert_type": alert.get("type"),
                    "server_id": server_id,
                    "admin": admin,
                    "response_seconds": seconds,
                    "within_15_minutes": seconds <= 900,
                },
            )

        self.save_admin_state()

    def expire_admin_alerts(self) -> None:
        if not self.admin_enabled:
            return

        now = datetime.now(timezone.utc)
        changed = False

        for alert in self.admin_state.get(
            "open_alerts",
            [],
        ):
            if alert.get("responded_at") or alert.get("expired"):
                continue

            try:
                created = datetime.fromisoformat(
                    alert["created_at"].replace(
                        "Z",
                        "+00:00",
                    )
                )
            except Exception:
                continue

            if (
                now - created
            ).total_seconds() <= self.response_window:
                continue

            alert["expired"] = True
            changed = True

            append_jsonl(
                self.admin_events_path,
                {
                    "timestamp": self._utc_iso(),
                    "event": "admin_alert_expired",
                    "alert_id": alert.get("alert_id"),
                    "alert_type": alert.get("type"),
                    "server_id": alert.get("server_id"),
                    "admin_joined_within_window": False,
                },
            )

        if changed:
            self.save_admin_state()

    def handle_admin_player_join(
        self,
        entry: dict,
    ) -> None:
        if not self.admin_enabled:
            return

        sid = entry.get("server_id")
        product_id = entry.get("product_id")

        if not sid or not product_id:
            return

        server_state = self.admin_state[
            "servers"
        ].setdefault(
            sid,
            {
                "admins": {},
                "no_admin_since": None,
                "no_admin_alert_active": False,
                "players": {},
            },
        )

        player_state = server_state[
            "players"
        ].setdefault(
            product_id,
            {
                "negative_score_alert": False,
                "teamkill_alert": False,
            },
        )

        if entry.get("admin") is True:
            if product_id not in server_state["admins"]:
                admin = {
                    "product_id": product_id,
                    "player_name": entry.get(
                        "player_name"
                    ),
                    "joined_at": entry.get(
                        "joined_at"
                    ),
                    "connection_id": entry.get(
                        "connection_id"
                    ),
                }

                server_state["admins"][
                    product_id
                ] = admin

                append_jsonl(
                    self.admin_events_path,
                    {
                        "timestamp": self._utc_iso(),
                        "event": "admin_connected",
                        "server_id": sid,
                        "product_id": product_id,
                        "player_name": entry.get(
                            "player_name"
                        ),
                        "connection_id": entry.get(
                            "connection_id"
                        ),
                    },
                )

                self.respond_to_admin_alerts(
                    sid,
                    {
                        "product_id": product_id,
                        "player_name": entry.get(
                            "player_name"
                        ),
                    },
                )

        # Teamkills are available from the player stats database. This is
        # checked on join because connection logs do not contain live score.
        pdir = self.collector.players.player_dir(
            product_id
        )
        stats = load_json(
            pdir / "stats.json",
            {},
        )
        teamkills = int(
            (
                stats.get("combat")
                or {}
            ).get(
                "teamkills",
                0,
            )
            or 0
        )

        if (
            teamkills >= self.teamkill_threshold
            and not player_state.get(
                "teamkill_alert"
            )
        ):
            player_state["teamkill_alert"] = True

            self.create_admin_alert(
                sid,
                "multiple_teamkills",
                {
                    "product_id": product_id,
                    "player_name": entry.get(
                        "player_name"
                    ),
                },
                {
                    "teamkills": teamkills,
                },
            )

            self.send_admin_webhook(
                "🔴 Multiple Teamkills Detected",
                (
                    f"Player **{entry.get('player_name') or product_id}** "
                    f"has `{teamkills}` recorded teamkills."
                ),
                [
                    {
                        "name": "Server",
                        "value": f"`{sid}`",
                        "inline": True,
                    }
                ],
            )

        self.save_admin_state()
        self.evaluate_admin_state()

    def finish_admin_session(
        self,
        server_id: str,
        product_id: str,
        session: dict,
        leave_event: dict,
    ) -> None:
        joined = (
            session.get("joined_at")
            or leave_event.get("joined_at")
        )
        left = leave_event.get("disconnected_at")

        duration = calc_duration(joined, left)

        if duration is None:
            duration = leave_event.get(
                "joined_duration_seconds"
            )

        duration_int = max(
            0,
            int(duration or 0),
        )

        record = {
            "server_id": server_id,
            "product_id": product_id,
            "player_name": (
                session.get("player_name")
                or leave_event.get("player_name")
            ),
            "joined_at": joined,
            "left_at": left,
            "duration_seconds": duration_int,
            "disconnect_reason": leave_event.get(
                "disconnect_reason"
            ),
        }

        append_jsonl(
            self.admin_sessions_path,
            record,
        )

        stats = load_json(
            self.admin_stats_path,
            {},
        )

        entry = stats.setdefault(
            product_id,
            {
                "product_id": product_id,
                "total_admin_time_seconds": 0,
                "total_admin_sessions": 0,
                "servers": {},
            },
        )

        entry[
            "total_admin_time_seconds"
        ] += duration_int
        entry[
            "total_admin_sessions"
        ] += 1

        server_stats = entry[
            "servers"
        ].setdefault(
            server_id,
            {
                "time_seconds": 0,
                "sessions": 0,
            },
        )

        server_stats[
            "time_seconds"
        ] += duration_int
        server_stats[
            "sessions"
        ] += 1

        entry.setdefault(
            "first_admin_session",
            joined,
        )
        entry["last_admin_session"] = left

        atomic_write_json(
            self.admin_stats_path,
            stats,
        )

    def handle_admin_player_leave(
        self,
        event: dict,
    ) -> None:
        if not self.admin_enabled:
            return

        sid = event.get("server_id")
        product_id = event.get("product_id")

        if not sid or not product_id:
            return

        server_state = self.admin_state[
            "servers"
        ].setdefault(
            sid,
            {
                "admins": {},
                "no_admin_since": None,
                "no_admin_alert_active": False,
                "players": {},
            },
        )

        admin_session = server_state[
            "admins"
        ].pop(
            product_id,
            None,
        )

        if admin_session:
            self.finish_admin_session(
                sid,
                product_id,
                admin_session,
                event,
            )

            append_jsonl(
                self.admin_events_path,
                {
                    "timestamp": self._utc_iso(),
                    "event": "admin_disconnected",
                    "server_id": sid,
                    "product_id": product_id,
                    "player_name": event.get(
                        "player_name"
                    ),
                    "connection_id": event.get(
                        "connection_id"
                    ),
                    "duration_seconds": event.get(
                        "joined_duration_seconds"
                    ),
                    "disconnect_reason": event.get(
                        "disconnect_reason"
                    ),
                },
            )

        self.save_admin_state()
        self.evaluate_admin_state()

    def evaluate_admin_state(self) -> None:
        if not self.admin_enabled:
            return

        now = datetime.now(timezone.utc)
        changed = False

        for sid, sessions in self.online.items():
            players = [
                item
                for item in sessions.values()
                if item.get("product_id")
                and item.get("joined_at")
            ]

            admins = [
                item
                for item in players
                if item.get("admin") is True
            ]

            state = self.admin_state[
                "servers"
            ].setdefault(
                sid,
                {
                    "admins": {},
                    "no_admin_since": None,
                    "no_admin_alert_active": False,
                    "players": {},
                },
            )

            if players and not admins:
                if not state.get(
                    "no_admin_since"
                ):
                    state["no_admin_since"] = (
                        self._utc_iso()
                    )
                    changed = True

                try:
                    started = datetime.fromisoformat(
                        state[
                            "no_admin_since"
                        ].replace(
                            "Z",
                            "+00:00",
                        )
                    )
                except Exception:
                    state["no_admin_since"] = (
                        self._utc_iso()
                    )
                    started = now
                    changed = True

                elapsed = (
                    now - started
                ).total_seconds()

                if (
                    elapsed >= self.no_admin_delay
                    and not state.get(
                        "no_admin_alert_active"
                    )
                ):
                    state[
                        "no_admin_alert_active"
                    ] = True
                    changed = True

                    self.create_admin_alert(
                        sid,
                        "no_admin_online",
                        None,
                        {
                            "players_online": len(
                                players
                            )
                        },
                    )

                    self.send_admin_webhook(
                        "🚨 Players Online — No Admin Present",
                        (
                            f"`{len(players)}` players are online "
                            "and no known admin is present."
                        ),
                        [
                            {
                                "name": "Server",
                                "value": f"`{sid}`",
                                "inline": True,
                            }
                        ],
                    )
            else:
                if (
                    state.get("no_admin_since")
                    is not None
                    or state.get(
                        "no_admin_alert_active"
                    )
                ):
                    changed = True

                state["no_admin_since"] = None
                state[
                    "no_admin_alert_active"
                ] = False

        if changed:
            self.save_admin_state()

    def write_online_state(self) -> None:
        # Copy state before writing so the background InspectAll thread and the
        # log watcher never serialize a dict while the other is mutating it.
        lock = getattr(self, "state_lock", None)
        if lock is None:
            context = None
        if lock is not None:
            lock.acquire()
        try:
            servers = {}
            for sid, sessions in self.online.items():
                values = [dict(x) for x in sessions.values()]
                players = [x for x in values if x.get("product_id")]
                admins = [x for x in players if x.get("admin") is True]
                servers[sid] = {
                    "player_count": len(players),
                    "admin_count": len(admins),
                    "players": players,
                    "pending_connections": [x for x in values if not x.get("product_id")],
                }
        finally:
            if lock is not None:
                lock.release()
        atomic_write_json(
            self.online_path,
            {"updated_unix": time.time(), "servers": servers},
        )

    def post(self, url: str, payload: dict, label: str) -> None:
        if not url:
            return
        last = None
        for attempt in range(self.retries + 1):
            try:
                r = self.http.post(url, json=payload, timeout=self.timeout)
                if 200 <= r.status_code < 300:
                    return
                last = f"HTTP {r.status_code}: {r.text[:200]}"
            except requests.RequestException as exc:
                last = str(exc)
            if attempt < self.retries:
                time.sleep(attempt + 1)
        print(f"{label} webhook failed: {last}", file=sys.stderr)

    @staticmethod
    def yn(v: Any) -> str:
        return "Yes" if v is True else "No" if v is False else "Unknown"

    def _load_recent_rcon_security_events(self) -> None:
        if not self.rcon_security_events_path.exists():
            return
        now_epoch = time.time()
        cutoff = now_epoch - 86400
        minute_buckets = Counter()
        try:
            with self.rcon_security_events_path.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        item = json.loads(line)
                    except Exception:
                        continue
                    if item.get("type") != "rcon_auth_failed":
                        continue
                    raw_ts = item.get("timestamp")
                    dt = parse_pavlov_timestamp(raw_ts)
                    if not dt:
                        continue
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    epoch = dt.timestamp()
                    if epoch < cutoff:
                        continue
                    self.rcon_failure_times.append(epoch)
                    ih = str(item.get("ip_hash") or "")
                    if ih:
                        self.rcon_failure_times_by_hash.setdefault(ih, deque()).append(epoch)
                    minute_buckets[int(epoch // 60)] += 1
            if minute_buckets:
                self.rcon_security_state["peak_rate_per_minute"] = max(
                    int(self.rcon_security_state.get("peak_rate_per_minute", 0) or 0),
                    max(minute_buckets.values()),
                )
        except OSError:
            pass

    def _save_rcon_security_state(self) -> None:
        atomic_write_json(self.rcon_security_state_path, self.rcon_security_state)

    @staticmethod
    def _webhook_message_url(webhook_url: str, message_id: str) -> str:
        return webhook_url.rstrip("/") + f"/messages/{message_id}"

    def _trim_rcon_rates(self, now_epoch: float) -> None:
        cutoff_24h = now_epoch - 86400
        while self.rcon_failure_times and self.rcon_failure_times[0] < cutoff_24h:
            self.rcon_failure_times.popleft()
        for ih in list(self.rcon_failure_times_by_hash):
            q = self.rcon_failure_times_by_hash[ih]
            while q and q[0] < cutoff_24h:
                q.popleft()
            if not q:
                self.rcon_failure_times_by_hash.pop(ih, None)

    def _rate_count(self, seconds: int, now_epoch: float) -> int:
        cutoff = now_epoch - seconds
        return sum(1 for t in self.rcon_failure_times if t >= cutoff)

    def _rcon_status_label(self, rate: int) -> str:
        if rate >= self.rcon_attack_rate:
            return "🚨 ATTACK / FLOOD"
        if rate >= self.rcon_critical_rate:
            return "🔴 CRITICAL"
        if rate >= self.rcon_high_rate:
            return "🟠 HIGH"
        if rate >= self.rcon_elevated_rate:
            return "🟡 ELEVATED"
        return "🟢 NORMAL"

    def record_rcon_failure(
        self,
        server,
        ts: str,
        ip: str,
        ih: str,
        port: int,
        matches: list[dict],
    ) -> None:
        if not self.rcon_security_enabled:
            return

        now_epoch = time.time()
        self.rcon_failure_times.append(now_epoch)
        q = self.rcon_failure_times_by_hash.setdefault(ih, deque())
        q.append(now_epoch)
        self._trim_rcon_rates(now_epoch)

        current_rate = self._rate_count(60, now_epoch)
        self.rcon_security_state["peak_rate_per_minute"] = max(
            int(self.rcon_security_state.get("peak_rate_per_minute", 0) or 0),
            current_rate,
        )
        self.rcon_security_state["last_failure"] = {
            "timestamp": ts,
            "server_id": server.server_id,
            "ip_hash": ih,
            "source_port": port,
            "player_matches": matches,
        }

        event = {
            "timestamp": ts,
            "type": "rcon_auth_failed",
            "server_id": server.server_id,
            "ip_hash": ih,
            "source_port": port,
            "player_matches": matches,
        }
        append_jsonl(self.rcon_security_events_path, event)

        # IPS enforcement uses failures from this source in the rolling window,
        # not its lifetime counter.
        source_recent = sum(1 for t in q if t >= now_epoch - self.rcon_block_window)
        blocked = self.rcon_security_state.setdefault("blocked_hashes", {})
        if (
            self.rcon_auto_block_enabled
            and source_recent >= self.rcon_block_after
            and ih not in blocked
            and ip not in self.rcon_auto_block_whitelist
        ):
            cmd = [self.rcon_block_command, ip]
            if self.rcon_block_use_sudo:
                cmd = ["sudo", "-n"] + cmd
            try:
                result = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=10,
                    check=False,
                )
                if result.returncode == 0:
                    block_rec = {
                        "blocked_at": ts,
                        "server_id": server.server_id,
                        "ip_hash": ih,
                        "failures_in_window": source_recent,
                        "window_seconds": self.rcon_block_window,
                    }
                    blocked[ih] = block_rec
                    self.rcon_security_state.setdefault("blocks", []).append(block_rec)
                    self.rcon_security_state["last_block"] = block_rec
                    append_jsonl(self.rcon_security_events_path, {
                        "timestamp": ts,
                        "type": "rcon_ips_block",
                        **block_rec,
                    })
                    print(f"[RCON-IPS] blocked {ih[:12]}… after {source_recent} failures")
                else:
                    print(
                        f"[RCON-IPS] block failed for {ih[:12]}…: {result.stderr[:200]}",
                        file=sys.stderr,
                    )
            except Exception as exc:
                print(f"[RCON-IPS] block error: {exc}", file=sys.stderr)

        self._save_rcon_security_state()

    def _collect_rcon_host_stats(self):
        total = 0
        hosts = {}
        servers = Counter()
        player_matches = 0
        for server in self.collector.servers:
            sid = server.server_id
            path = self.collector.data_root / "servers" / sid / "rcon" / "failed_hosts.json"
            data = load_json(path, {})
            if not isinstance(data, dict):
                continue
            for ih, rec in data.items():
                if not isinstance(rec, dict):
                    continue
                n = int(rec.get("failed_attempts", 0) or 0)
                total += n
                servers[sid] += n
                h = hosts.setdefault(ih, {"attempts": 0, "players": 0, "last_seen": None})
                h["attempts"] += n
                h["players"] = max(h["players"], len(rec.get("players_seen_on_ip") or []))
                ls = rec.get("last_seen")
                if isinstance(ls, str) and (not h["last_seen"] or ls > h["last_seen"]):
                    h["last_seen"] = ls
        player_matches = sum(1 for h in hosts.values() if h["players"])
        return total, hosts, servers, player_matches

    def build_rcon_status_payload(self) -> dict:
        now_epoch = time.time()
        self._trim_rcon_rates(now_epoch)
        one = self._rate_count(60, now_epoch)
        five = self._rate_count(300, now_epoch)
        hour = self._rate_count(3600, now_epoch)
        day = self._rate_count(86400, now_epoch)
        peak = int(self.rcon_security_state.get("peak_rate_per_minute", 0) or 0)
        total, hosts, servers, player_matches = self._collect_rcon_host_stats()
        blocked = self.rcon_security_state.get("blocked_hashes") or {}
        blocks = self.rcon_security_state.get("blocks") or []
        today = datetime.now(timezone.utc).date().isoformat()
        blocks_today = sum(1 for x in blocks if str(x.get("blocked_at") or "").startswith(today))
        unique = len(hosts)
        blocked_pct = (len(blocked) / unique * 100.0) if unique else 0.0

        top_sources = sorted(hosts.items(), key=lambda kv: kv[1]["attempts"], reverse=True)[:5]
        source_lines = [f"__{ih[:12]}… —__ `{rec['attempts']:,}`" for ih, rec in top_sources]
        server_lines = [f"__{sid} —__ `{count:,}`" for sid, count in servers.most_common(5)]
        last = self.rcon_security_state.get("last_failure") or {}
        last_block = self.rcon_security_state.get("last_block") or {}

        description = (
            "-----------------------------------------------------------------\n"
            "🔥 **Most Active Source Hashes**\n" + ("\n".join(source_lines) if source_lines else "`None`") +
            "\n\n🖥️ **Most Targeted Servers**\n" + ("\n".join(server_lines) if server_lines else "`None`") +
            "\n-----------------------------------------------------------------"
        )

        fields = [
            {
                "name": ":computer: - RCON-focused IPS",
                "value": (
                    f":black_small_square: __Status:__ `{self._rcon_status_label(one)}`\n"
                    f":black_small_square: __Failed Auth Rate:__ `{one}/min`\n"
                    f":black_small_square: __Blocked IPs:__ `{len(blocked)}`\n"
                    f":black_small_square: __Blocks Today:__ `{blocks_today}`\n"
                    f":black_small_square: __Peak Rate:__ `{peak}/min`"
                ),
                "inline": True,
            },
            {
                "name": "📊 - Current Statistics",
                "value": (
                    f"__Failed Login Attempts:__ `{total:,}`\n"
                    f"__Unique Source Hashes:__ `{unique:,}`\n"
                    f"__Blocked Sources:__ `{len(blocked)} ({blocked_pct:.1f}%)`\n"
                    f"__Player IP Matches:__ `{player_matches}`"
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
            {
                "name": "🚨 - Recent Attempt",
                "value": (
                    f"__Server:__ `{last.get('server_id') or 'None'}`\n"
                    f"__Source Hash:__ `{str(last.get('ip_hash') or 'None')[:12]}…`\n"
                    f"__Source Port:__ `{last.get('source_port') or 'None'}`\n"
                    f"__Last Block:__ `{last_block.get('blocked_at') or 'None'}`"
                ),
                "inline": True,
            },
        ]

        return {
            "content": (
                "----------------------------------------------\n"
                "--  :octagonal_sign:    ** __RCON Server Status__ **  :octagonal_sign:    --\n"
                "----------------------------------------------\n"
                "*Continuously updated RCON authentication security summary.*"
            ),
            "embeds": [{
                "title": ":no_pedestrians:  __**Security Report**__ :exclamation:",
                "description": description,
                "color": 3618621,
                "fields": fields,
                "footer": {"text": f"JTWP • Updated {self._utc_iso()}"},
            }],
            "components": [],
        }

    def update_rcon_status_message(self) -> None:
        if not self.rcon_status_webhook:
            return
        payload = self.build_rcon_status_payload()
        state = load_json(self.rcon_status_state_path, {})
        message_id = str(state.get("message_id") or "").strip()
        if message_id:
            try:
                r = self.http.patch(
                    self._webhook_message_url(self.rcon_status_webhook, message_id),
                    json=payload,
                    timeout=self.timeout,
                )
                if r.status_code in (200, 204):
                    state["updated_at"] = self._utc_iso()
                    atomic_write_json(self.rcon_status_state_path, state)
                    return
                if r.status_code != 404:
                    print(f"RCON status PATCH failed: HTTP {r.status_code}: {r.text[:200]}", file=sys.stderr)
                    return
            except requests.RequestException as exc:
                print(f"RCON status PATCH failed: {exc}", file=sys.stderr)
                return

        sep = "&" if "?" in self.rcon_status_webhook else "?"
        create_url = self.rcon_status_webhook + sep + "wait=true"
        try:
            r = self.http.post(create_url, json=payload, timeout=self.timeout)
            if 200 <= r.status_code < 300:
                body = r.json()
                atomic_write_json(self.rcon_status_state_path, {
                    "message_id": str(body.get("id")),
                    "created_at": self._utc_iso(),
                    "updated_at": self._utc_iso(),
                })
            else:
                print(f"RCON status POST failed: HTTP {r.status_code}: {r.text[:200]}", file=sys.stderr)
        except requests.RequestException as exc:
            print(f"RCON status POST failed: {exc}", file=sys.stderr)

    def rcon_status_loop(self) -> None:
        while not self.rcon_status_stop.is_set():
            try:
                self.update_rcon_status_message()
            except Exception as exc:
                print(f"RCON status error: {exc}", file=sys.stderr)
            self.rcon_status_stop.wait(self.rcon_status_interval)

    def start_rcon_status_thread(self) -> None:
        if not self.rcon_status_webhook:
            return
        self.rcon_status_thread = threading.Thread(
            target=self.rcon_status_loop,
            name="jtwp-rcon-security-status",
            daemon=True,
        )
        self.rcon_status_thread.start()

    @staticmethod
    def redact_network_addresses(value: str) -> str:
        """Never expose raw IP addresses in Discord/audit-facing text."""
        value = str(value or "")

        # IPv4, optionally followed by :port
        value = re.sub(
            r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?::\d{1,5})?(?![\d.])",
            "[REDACTED-IP]",
            value,
        )

        # Bracketed/common IPv6 + optional port. Deliberately conservative:
        # this is Discord-facing redaction, not address validation.
        value = re.sub(
            r"\[[0-9A-Fa-f:]{2,}\](?::\d{1,5})?",
            "[REDACTED-IP]",
            value,
        )

        return value

    def get_verified_connection(self, ip_hash: Optional[str]) -> Optional[dict[str, Any]]:
        """Return the manual verified-connection record for an RCON IP hash."""
        if not ip_hash:
            return None
        data = load_json(
            self.verified_connections_path,
            {"version": 1, "verified_connections": {}},
        )
        if not isinstance(data, dict):
            return None
        records = data.get("verified_connections") or {}
        if not isinstance(records, dict):
            return None
        record = records.get(str(ip_hash))
        return record if isinstance(record, dict) else None


    def get_rcon_host_details(
        self,
        server_id: str,
        ip_hash: Optional[str],
    ) -> dict[str, Any]:
        """Build Discord-safe RCON connection details using only hashed/public data."""
        details: dict[str, Any] = {
            "successful_connections": 0,
            "failed_connections": 0,
            "background": {},
            "players": [],
        }
        if not ip_hash:
            return details

        rcon_root = self.collector.data_root / "servers" / server_id / "rcon"

        known = load_json(rcon_root / "known_hosts.json", {})
        if isinstance(known, dict):
            rec = known.get(ip_hash)
            if isinstance(rec, dict):
                details["successful_connections"] = int(
                    rec.get("successful_connections", 0) or 0
                )
                if isinstance(rec.get("players_seen_on_ip"), list):
                    details["players"] = rec.get("players_seen_on_ip") or []

        failed = load_json(rcon_root / "failed_hosts.json", {})
        if isinstance(failed, dict):
            rec = failed.get(ip_hash)
            if isinstance(rec, dict):
                details["failed_connections"] = int(
                    rec.get("failed_attempts", 0) or 0
                )
                if not details["players"] and isinstance(
                    rec.get("players_seen_on_ip"), list
                ):
                    details["players"] = rec.get("players_seen_on_ip") or []

        # Player IP records already contain the sanitized enrichment/background
        # associated with this hash. Never read or send raw IPs here.
        for player in self.collector.players.players_for_ip_hash(ip_hash):
            product_id = player.get("product_id")
            if not product_id:
                continue
            ips_doc = load_json(
                self.collector.players.player_dir(product_id) / "ips.json",
                {},
            )
            ips = ips_doc.get("ips") if isinstance(ips_doc, dict) else {}
            if not isinstance(ips, dict):
                continue
            rec = ips.get(ip_hash)
            if not isinstance(rec, dict):
                continue
            background = rec.get("background")
            if isinstance(background, dict) and background:
                details["background"] = background
                break

        return details

    def maybe_send_rcon_command_webhook(self, server, ts: str, body: str) -> None:
        if not self.rcon_command_webhook:
            return

        m = re.search(r"Rcon:\s*(.+)$", body, re.IGNORECASE)
        if not m:
            return

        command = m.group(1).strip()
        if not command:
            return

        low = command.casefold()

        # Authentication/connection lifecycle lines are not administrator commands.
        ignored_prefixes = (
            "user failed authentication",
            "user authenticated",
            "connection is blocked",
            "client connect",
            "client connected",
            "client disconnect",
            "client disconnected",
            "new connection",
            "closing connection",
            "authentication",
            "authenticated",
        )
        if low.startswith(ignored_prefixes):
            return

        command_name = command.split()[0] if command.split() else command
        if command_name.casefold() in self.rcon_command_exclude:
            return

        # collector.handle_rcon() runs first and maintains the authenticated RCON
        # sessions. Attribute the command to the only session when possible.
        sessions = list(self.active_rcon.get(server.server_id, {}).values())
        chosen = None
        attribution = "unknown"

        if len(sessions) == 1:
            chosen = sessions[0]
            attribution = "certain"
        elif sessions:
            chosen = max(
                sessions,
                key=lambda item: parse_pavlov_timestamp(
                    getattr(item, "authenticated_at", None)
                ) or datetime.min,
            )
            attribution = "inferred"

        ip_hash = getattr(chosen, "ip_hash", None) if chosen else None
        verified = self.get_verified_connection(ip_hash)
        host = self.get_rcon_host_details(server.server_id, ip_hash)
        bg = host.get("background") or {}

        verified_text = "✅ `true`" if verified else "❌ `false`"
        if verified and verified.get("label"):
            verified_text += f"\n**Label:** `{str(verified.get('label'))[:80]}`"

        organisation = (
            bg.get("organisation")
            or bg.get("provider")
            or "Unknown"
        )
        country = (
            bg.get("country_code")
            or bg.get("country_name")
            or "Unknown"
        )
        proxy = self.yn(bg.get("proxy"))
        vpn = self.yn(bg.get("vpn"))
        hosting = self.yn(bg.get("hosting"))
        tor = self.yn(bg.get("tor"))

        # Defense in depth: no raw network addresses ever go to Discord.
        command = self.redact_network_addresses(command)

        hash_text = f"`{ip_hash}`" if ip_hash else "`Unknown`"
        successful = int(host.get("successful_connections", 0) or 0)
        failed = int(host.get("failed_connections", 0) or 0)

        connection_value = (
            "---------------------------------------------------------------------\n"
            f"#️⃣  **ipHASH:**\n{hash_text}\n"
            "---------------------------------------------------------------------\n"
            f"🔴 | Failed Connections: `{failed}`\n"
            f"🟢 | Successful Connections: `{successful}`\n"
            "---------------------------------------------------------------------"
        )

        background_value = (
            f"* Organisation: `{organisation}`\n"
            f"* Country: `{country}`\n"
            f"* Proxy: `{proxy}`\n"
            f"* VPN: `{vpn}`\n"
            f"* Hosting: `{hosting}`\n"
            f"* Tor: `{tor}`"
        )

        verify_value = verified_text
        if verified and verified.get("notes"):
            verify_value += f"\n**Notes:** {str(verified.get('notes'))[:700]}"

        payload = {
            "content": (
                "------------------------------------------------------------------------------------\n"
                "--  :warning:  |  **RCON Command Detected**  | :warning:  --\n"
                "------------------------------------------------------------------------------------"
            ),
            "embeds": [{
                "title": (
                    "---------------------------------------------------------------------\n"
                    "- 🌐 -             Network Data -\n"
                    "---------------------------------------------------------------------"
                ),
                "description": (
                    f"* **Command Issued:** `{command[:1500]}`\n"
                    f"* **ServerID:** `{server.server_id}`\n"
                    f"* **Time:** `{ts}`\n"
                    f"* **Attribution:** `{attribution}`"
                ),
                "color": 263411,
                "fields": [
                    {
                        "name": "__**Connections**__",
                        "value": connection_value,
                        "inline": False,
                    },
                    {
                        "name": ":computer:  - __Connection Background__",
                        "value": background_value,
                        "inline": True,
                    },
                    {
                        "name": "🔒 - **__Verified Connection:?__**",
                        "value": verify_value,
                        "inline": True,
                    },
                ],
                "footer": {
                    "text": "---------------------------------------------------------------------\n-   JTWP.org   -"
                },
            }],
            "components": [],
        }

        self.post(
            self.rcon_command_webhook,
            payload,
            "RCON command",
        )

    def send_connection_alert(self, server, sess: NetSession, ts: str) -> None:
        pdir = self.collector.players.player_dir(sess.product_id)
        player = load_json(pdir / "player.json", {})
        stats = load_json(pdir / "stats.json", {})

        combat = stats.get("combat", {})
        activity = stats.get("activity", {})
        weapons = stats.get("weapons", {})
        bg = player.get("network", {}).get("current_background") or {}

        sid = server.server_id

        # Try to use the configured/collected Pavlov server name.
        server_state = load_json(
            self.collector.data_root / "servers" / sid / "server.json",
            {},
        )
        server_name = (
            server_state.get("server_name")
            or server_state.get("ServerName")
            or server_state.get("name")
            or sid
        )

        payload = {
            "content": (
                "----------------------------------------------\n"
                "--  :warning:    **A PLAYER CONNECTED**  :warning:    --\n"
                "----------------------------------------------"
            ),
            "components": [],
            "embeds": [
                {
                    "title": f"**{sess.player_name or 'Unknown'}**",
                    "color": 3618621,
                    "description": (
                        "   Joined\n"
                        f"{server_name}\n"
                        "----------------------------------------------"
                    ),
                    "fields": [
                        {
                            "name": "**Identity**",
                            "value": (
                                f"Product ID: `{sess.product_id}`\n"
                                f"Unique ID: `{sess.unique_id or 'Unknown'}`\n"
                                f"Platform: `{self.platforms[sid]}`"
                            ),
                            "inline": False,
                        },
                        {
                            "name": ":bookmark_tabs:  - Status",
                            "value": (
                                f"*Admin: `{self.yn(player.get('admin'))}`\n"
                                f"*Banned: `{self.yn(player.get('banned'))}`\n"
                                f"*Connections: `{activity.get('times_connected', 0)}`\n"
                                f"*Matches: `{activity.get('matches', 0)}`"
                            ),
                            "inline": True,
                        },
                        {
                            "name": ":military_helmet:  - Combat",
                            "value": (
                                f"*Kills: `{combat.get('kills', 0)}`\n"
                                f"*Deaths: `{combat.get('deaths', 0)}`\n"
                                f"*Headshots: `{combat.get('headshots', 0)}`\n"
                                f"*Favorite: `{weapons.get('favorite') or 'Unknown'}`"
                            ),
                            "inline": True,
                        },
                        {
                            "name": ":computer:  - Network",
                            "value": (
                                f"*Organisation: `{bg.get('organisation') or 'Unknown'}`\n"
                                f"*Country: `{bg.get('country_code') or 'Unknown'}`\n"
                                f"*Proxy: `{self.yn(bg.get('proxy'))}` | "
                                f"*VPN: `{self.yn(bg.get('vpn'))}` | "
                                f"*Hosting: `{self.yn(bg.get('hosting'))}`"
                            ),
                            "inline": False,
                        },
                    ],
                    "footer": {
                        "text": f"JTWP • {ts}"
                    },
                }
            ],
        }

        self.post(
            self.connection_webhook,
            payload,
            "connection",
        )


def main() -> None:
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
    LiveConnectionWatcher(merged).run()


if __name__ == "__main__":
    main()
