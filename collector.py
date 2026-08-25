#!/usr/bin/env python3
"""
JTWP Pavlov Log / Stats Collector

Python 3.10+

Major features:
- Multiple Pavlov servers from config.
- Derives server_id from .../{server_id}/Pavlov/Saved/Logs.
- Archives Pavlov-backup-*.log and Stats-*.log.
- Copies/truncates active Pavlov.log and Stats.log safely.
- Deduplicates processed archived files by SHA-256.
- Can recursively index one or more read-only historical log archive roots.
- Server, RCON, HTTP, runtime, custom gun/loot/mod, Game.ini, admins and bans.
- Stats.log JSON-block parsing and per-round JSON output.
- Kill/death combat tracking from StatManagerLog KillData blocks in Pavlov logs (not Stats files).
- productId-keyed player records and name/uniqueId indexes.
- Player connection/session data and preference change tracking.
- Raw player IPs isolated to private/player_ips.json.
- Stable HMAC-SHA256 IP hashes everywhere else.
- ProxyCheck v3 primary IP lookup with ip-api.com and FreeIPAPI fallbacks and caching.
- mod.io enrichment and caching for maps/mods.

Environment variables:
    JTWP_IP_HASH_SECRET    Required for stable private IP hashing.
    PROXYCHECK_API_KEY     Optional but recommended.
    MODIO_API_KEY          Optional; needed for mod.io enrichment.
    PAVLOV_API             Optional public server-list URL.
"""

from __future__ import annotations

import argparse
import configparser
import copy
import hashlib
import hmac
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import urlparse

import requests


# ----------------------------- utility ---------------------------------

TS_RE = re.compile(r"^\[(?P<ts>\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}:\d{3})\](?:\[\s*\d+\])?(?P<body>.*)$")
STATS_TS_RE = re.compile(r"^\[(?P<ts>\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2})\]\s*StatManagerLog:\s*(?P<body>.*)$")
UGC_RE = re.compile(r"^UGC(\d+)$", re.I)
IP_PORT_RE = re.compile(r"(?P<ip>(?:\d{1,3}\.){3}\d{1,3}):(?P<port>\d+)")
CONNECTION_NAME_RE = re.compile(r"\b(IpConnection_\d+)\b")
NETWORK_USER_RE = re.compile(r"\bUniqueId:\s*([^\s,\]]+)|\buserId:\s*([^\s]+)")
SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")

BADGE_DISCORD_LINK = "DISCORD BADGE #001"
BADGE_VPN_CONNECTION = "Vpn Connection #002"
BADGE_TEAMKILLER = "TeamKiller #003"
BADGE_1000_KILLS = "1000 Kills #004"
TEAMKILL_BADGE_THRESHOLD = 3
KILLS_BADGE_THRESHOLD = 1000


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def now_pavlov_name() -> str:
    return datetime.now().strftime("%Y.%m.%d-%H.%M.%S")


def parse_ts(ts: str) -> Optional[datetime]:
    for fmt in ("%Y.%m.%d-%H.%M.%S:%f", "%Y.%m.%d-%H.%M.%S"):
        try:
            return datetime.strptime(ts, fmt)
        except ValueError:
            pass
    return None


def duration_seconds(a: Optional[str], b: Optional[str]) -> Optional[int]:
    if not a or not b:
        return None
    da, db = parse_ts(a), parse_ts(b)
    if not da or not db:
        return None
    return max(0, int((db - da).total_seconds()))


def format_duration_seconds(total_seconds: int) -> str:
    total_seconds = max(0, int(total_seconds or 0))
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h {minutes}m {seconds}s"
    if hours:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"



def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE entries without overriding existing variables."""
    if not path.is_file():
        return

    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        os.environ.setdefault(key, value)


def atomic_write_json(
    path: Path,
    data: Any,
) -> None:
    import tempfile

    path = Path(path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )

    tmp_path = Path(tmp_name)

    try:
        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(
                data,
                f,
                indent=2,
                ensure_ascii=False,
            )

            f.write("\n")
            f.flush()
            os.fsync(
                f.fileno()
            )

        os.replace(
            tmp_path,
            path,
        )

    finally:
        try:
            tmp_path.unlink(
                missing_ok=True
            )
        except OSError:
            pass


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return copy.deepcopy(default)
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return copy.deepcopy(default)


def append_jsonl(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n")


def append_human_log(path: Path, ts: str, msg: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] JTWP log event /{msg}\n")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_name(value: str) -> str:
    out = SAFE_FILENAME_RE.sub("_", value.strip())
    return out[:180] or "unknown"


def country_flag(country_code: Optional[str]) -> Optional[str]:
    if not country_code:
        return None
    code = str(country_code).strip().lower()
    if len(code) != 2 or not code.isalpha():
        return None
    return f":flag_{code}:"


def normalize_bool(v: Any) -> Optional[bool]:
    if isinstance(v, bool):
        return v
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in {"1", "true", "yes", "on"}:
        return True
    if s in {"0", "false", "no", "off"}:
        return False
    return None


def unique_append(lst: list, value: Any) -> bool:
    if value not in lst:
        lst.append(value)
        return True
    return False


def json_get(d: dict, *keys: str, default=None):
    cur: Any = d
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


# ----------------------------- configuration ----------------------------

DEFAULT_CONFIG = {
    "data_path": "/home/steam/jtwp-collector-data",
    "archive_path": "/home/steam/jtwp-log-archive",
    "old_archive_paths": [],
    "request_timeout_seconds": 8,
    "modio_game_id": 3959,
    "modio_cache_ttl_hours": 24,
    "ip_lookup_cache_ttl_days": 30,
    "pavlov_api_enabled": True,
    "pavlov_api_host_cache_ttl_days": 30,
    "rotate_active_logs": True,
    "count_unverified_player_kills": True,

    # Player lookup indexes are derived/cache data. The per-player records under
    # players/records are the source of truth. Rebuild them at the beginning of
    # a normal collector run so a missing/truncated index cannot permanently
    # hide historical players that are already marked processed.
    "rebuild_player_indexes_on_start": True,

    "servers": [
        {
            "log_path": "/home/steam/pavlovserver/Pavlov/Saved/Logs/",
            "platform": "auto"
        }
    ]
}


@dataclass
class ServerCfg:
    log_path: Path
    server_id: str
    platform_override: str = "auto"
    stats_path: Optional[Path] = None
    game_ini_path: Optional[Path] = None

    @classmethod
    def from_dict(cls, d: dict) -> "ServerCfg":
        log_path = Path(d["log_path"]).expanduser().resolve()
        # /home/steam/{server}/Pavlov/Saved/Logs
        try:
            idx = list(log_path.parts).index("Pavlov")
            server_id = log_path.parts[idx - 1]
        except Exception:
            server_id = d.get("server_id") or log_path.parent.parent.parent.name

        stats = Path(d["stats_path"]).expanduser() if d.get("stats_path") else log_path.parent / "Stats"

        if d.get("game_ini_path"):
            game_ini = Path(d["game_ini_path"]).expanduser()
        else:
            candidates = [
                log_path.parent / "Config" / "LinuxServer" / "Game.ini",
                log_path.parent / "Config" / "Game.ini",
            ]
            game_ini = next((p for p in candidates if p.exists()), candidates[0])

        return cls(
            log_path=log_path,
            server_id=server_id,
            platform_override=str(d.get("platform", "auto")).upper(),
            stats_path=stats,
            game_ini_path=game_ini,
        )

    @property
    def server_root(self) -> Path:
        # .../{server_id}/Pavlov/Saved/Logs
        return self.log_path.parents[2]

    @property
    def config_dir(self) -> Path:
        return self.log_path.parent / "Config"

    @property
    def mods_txt(self) -> Path:
        return self.config_dir / "mods.txt"

    @property
    def rconplus_admins(self) -> Path:
        return self.config_dir / "ModSave" / "RconPlus" / "MenuAccesscfg.txt"

    @property
    def blacklist(self) -> Path:
        return self.config_dir / "blacklist.txt"


# ----------------------------- external APIs ----------------------------

class Enricher:
    def __init__(self, cfg: dict, data_root: Path):
        self.timeout = int(cfg.get("request_timeout_seconds", 8))
        self.modio_game_id = int(cfg.get("modio_game_id", 3959))
        self.modio_ttl = int(cfg.get("modio_cache_ttl_hours", 24)) * 3600
        self.ip_ttl = int(cfg.get("ip_lookup_cache_ttl_days", 30)) * 86400
        self.failed_ip_ttl = max(
            0,
            int(cfg.get("ip_lookup_failed_cache_ttl_minutes", 60)) * 60,
        )
        self.retry_failed_per_run = max(
            0,
            int(cfg.get("ip_lookup_retry_failed_per_run", 10)),
        )
        self.proxy_key = os.getenv("PROXYCHECK_API_KEY", "")
        self.modio_key = os.getenv("MODIO_API_KEY", "")
        self.private_dir = data_root / "private"
        self.private_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.private_dir, 0o700)
        except OSError:
            pass
        self.ip_cache_path = self.private_dir / "ip_lookup_cache.json"
        self.modio_cache_path = data_root / "global" / "modio" / "mods.json"
        self.server_host_cache_path = data_root / "global" / "pavlov_api" / "network_hosts_cache.json"
        self.server_host_ttl = int(cfg.get("pavlov_api_host_cache_ttl_days", 30)) * 86400
        self.ip_cache = load_json(self.ip_cache_path, {})
        self.modio_cache = load_json(self.modio_cache_path, {})
        self.server_host_cache = load_json(self.server_host_cache_path, {})
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "JTWP-Pavlov-Collector/1.0"})

    def _cache_fresh(self, entry: dict, ttl_seconds: int) -> bool:
        t = entry.get("_cached_unix")
        if not isinstance(t, (int, float)):
            return False

        # Successful lookups use the normal long cache TTL. Failed lookups use
        # a much shorter configurable TTL so a temporary provider outage does
        # not poison the cache for days.
        if entry.get("lookup_status") == "failed":
            ttl_seconds = min(
                ttl_seconds,
                self.failed_ip_ttl,
            )

        return (time.time() - t) < ttl_seconds

    def _safe_error(self, exc: Exception) -> str:
        """Return an error string that never exposes API keys or webhook tokens."""
        if isinstance(exc, requests.HTTPError):
            response = getattr(exc, "response", None)
            if response is not None:
                status = getattr(response, "status_code", None)
                reason = str(getattr(response, "reason", "") or "").strip()
                if status is not None:
                    return f"HTTPError: HTTP {status}" + (f" {reason}" if reason else "")

        text = f"{type(exc).__name__}: {exc}"

        # Redact common query-string credentials.
        text = re.sub(
            r"([?&](?:key|api_key|apikey|token|access_token|auth|authorization)=)[^&\\s\"']+",
            r"\\1REDACTED",
            text,
            flags=re.IGNORECASE,
        )

        # Redact Discord webhook URLs if one ever reaches an exception.
        text = re.sub(
            r"https://(?:discordapp\\.com|discord\\.com)/api/webhooks/\\d+/[A-Za-z0-9._-]+",
            "DISCORD_WEBHOOK_REDACTED",
            text,
            flags=re.IGNORECASE,
        )

        # Defense in depth: redact the exact secrets currently loaded in the process.
        for secret in (self.proxy_key, self.modio_key):
            if secret:
                text = text.replace(secret, "REDACTED")

        return text

    def lookup_ip(self, ip: str) -> dict:
        cached = self.ip_cache.get(ip)
        if isinstance(cached, dict) and self._cache_fresh(cached, self.ip_ttl):
            return {k: v for k, v in cached.items() if not k.startswith("_")}

        result = None
        for func in (self._proxycheck, self._ip_api, self._freeipapi):
            try:
                result = func(ip)
                break
            except Exception:
                continue

        if result is None:
            result = {
                "lookup_status": "failed",
                "source": None,
                "fallback": True,
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

        cache_entry = dict(result)
        cache_entry["_cached_unix"] = time.time()
        cache_entry["looked_up_at"] = now_iso()
        self.ip_cache[ip] = cache_entry
        atomic_write_json(self.ip_cache_path, self.ip_cache)
        try:
            os.chmod(self.ip_cache_path, 0o600)
        except OSError:
            pass
        return result

    def retry_failed_ip_lookups(
        self,
        limit: Optional[int] = None,
    ) -> dict[str, int]:
        """Retry a bounded batch of failed private-IP cache entries.

        This deliberately removes each selected failed entry from the in-memory
        cache before calling lookup_ip(), which forces a real provider request
        through ProxyCheck -> ip-api.com -> FreeIPAPI instead of returning the
        cached failure.
        """

        if limit is None:
            limit = self.retry_failed_per_run

        try:
            limit = max(0, int(limit))
        except (TypeError, ValueError):
            limit = 0

        failed_ips = [
            ip
            for ip, entry in self.ip_cache.items()
            if (
                isinstance(entry, dict)
                and entry.get("lookup_status") == "failed"
            )
        ]

        # Work oldest failures first.
        failed_ips.sort(
            key=lambda ip: (
                self.ip_cache[ip].get("_cached_unix", 0)
                if isinstance(self.ip_cache.get(ip), dict)
                else 0
            )
        )

        selected = failed_ips[:limit]
        success = 0
        failed = 0

        for ip in selected:
            old_entry = self.ip_cache.pop(ip, None)

            try:
                result = self.lookup_ip(ip)
            except Exception:
                # lookup_ip() normally converts provider failures into a failed
                # cache entry. If an unexpected exception escapes, preserve the
                # previous entry rather than losing it.
                if old_entry is not None:
                    self.ip_cache[ip] = old_entry
                failed += 1
                continue

            if (
                isinstance(result, dict)
                and result.get("lookup_status") == "success"
            ):
                success += 1
            else:
                failed += 1

        if selected:
            atomic_write_json(
                self.ip_cache_path,
                self.ip_cache,
            )
            try:
                os.chmod(
                    self.ip_cache_path,
                    0o600,
                )
            except OSError:
                pass

        remaining = sum(
            1
            for entry in self.ip_cache.values()
            if (
                isinstance(entry, dict)
                and entry.get("lookup_status") == "failed"
            )
        )

        return {
            "selected": len(selected),
            "successful": success,
            "failed": failed,
            "remaining": remaining,
        }

    def _proxycheck(self, ip: str) -> dict:
        params = {}
        if self.proxy_key:
            params["key"] = self.proxy_key
        r = self.session.get(f"https://proxycheck.io/v3/{ip}", params=params, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        if data.get("status") not in {"ok", "warning"} or ip not in data:
            raise ValueError(f"ProxyCheck invalid response status={data.get('status')!r}")
        item = data[ip]
        return {
            "lookup_status": "success",
            "source": "proxycheck",
            "fallback": False,
            "organisation": json_get(item, "network", "organisation"),
            "country_code": json_get(item, "location", "country_code"),
            "network_type": json_get(item, "network", "type"),
            "hosting": json_get(item, "detections", "hosting"),
            "proxy": json_get(item, "detections", "proxy"),
            "vpn": json_get(item, "detections", "vpn"),
            "tor": json_get(item, "detections", "tor"),
            "risk": json_get(item, "detections", "risk"),
            "confidence": json_get(item, "detections", "confidence"),
        }

    def _ip_api(self, ip: str) -> dict:
        # Free ip-api.com endpoint. No API key. HTTP is required on the free tier.
        r = self.session.get(
            f"http://ip-api.com/json/{ip}",
            params={"fields": "17032966"},
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("status") == "fail":
            raise ValueError(f"ip-api lookup failed: {data.get('message', 'unknown error')}")
        if data.get("query") and data.get("query") != ip:
            raise ValueError("ip-api returned a different IP")
        return {
            "lookup_status": "success",
            "source": "ip-api",
            "fallback": True,
            "organisation": data.get("org") or data.get("isp") or data.get("asname") or data.get("as"),
            "country_code": data.get("countryCode"),
            "network_type": None,
            "hosting": data.get("hosting"),
            "proxy": data.get("proxy"),
            "vpn": None,
            "tor": None,
            "risk": None,
            "confidence": None,
        }

    def _freeipapi(self, ip: str) -> dict:
        r = self.session.get(
            f"https://free.freeipapi.com/api/json/{ip}",
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("ipAddress") and data.get("ipAddress") != ip:
            raise ValueError("FreeIPAPI returned a different IP")
        if not data.get("countryCode") and not data.get("asn"):
            raise ValueError("FreeIPAPI returned an incomplete response")
        return {
            "lookup_status": "success",
            "source": "freeipapi",
            "fallback": True,
            "organisation": data.get("asnOrganization"),
            "country_code": data.get("countryCode"),
            "network_type": None,
            "hosting": None,
            "proxy": data.get("isProxy"),
            "vpn": None,
            "tor": None,
            "risk": None,
            "confidence": None,
        }

    def lookup_server_host(self, ip: str) -> dict:
        """Richer public-host enrichment for Pavlov server-list IPs."""
        cached = self.server_host_cache.get(ip)
        if isinstance(cached, dict) and self._cache_fresh(cached, self.server_host_ttl):
            return {k: v for k, v in cached.items() if not k.startswith("_")}

        result = None
        for func in (self._proxycheck_server, self._ip_api_server, self._freeipapi_server):
            try:
                result = func(ip)
                break
            except Exception:
                continue

        if result is None:
            result = {
                "lookup_status": "failed",
                "source": None,
                "fallback": True,
                "provider": None,
                "organisation": None,
                "type": None,
                "continent_code": None,
                "country_name": None,
                "country_code": None,
                "region_name": None,
                "region_code": None,
                "city_name": None,
                "risk": None,
                "confidence": None,
                "hosting": None,
                "proxy": None,
                "vpn": None,
            }

        result["looked_up_at"] = now_iso()
        cache_entry = dict(result)
        cache_entry["_cached_unix"] = time.time()
        self.server_host_cache[ip] = cache_entry
        atomic_write_json(self.server_host_cache_path, self.server_host_cache)
        return result

    def _proxycheck_server(self, ip: str) -> dict:
        params = {}
        if self.proxy_key:
            params["key"] = self.proxy_key
        r = self.session.get(f"https://proxycheck.io/v3/{ip}", params=params, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        if data.get("status") not in {"ok", "warning"} or ip not in data:
            raise ValueError(f"ProxyCheck invalid response status={data.get('status')!r}")
        item = data[ip]
        return {
            "lookup_status": "success",
            "source": "proxycheck",
            "fallback": False,
            "provider": json_get(item, "network", "provider"),
            "organisation": json_get(item, "network", "organisation"),
            "type": json_get(item, "network", "type"),
            "continent_code": json_get(item, "location", "continent_code"),
            "country_name": json_get(item, "location", "country_name"),
            "country_code": json_get(item, "location", "country_code"),
            "region_name": json_get(item, "location", "region_name"),
            "region_code": json_get(item, "location", "region_code"),
            "city_name": json_get(item, "location", "city_name"),
            "risk": json_get(item, "detections", "risk"),
            "confidence": json_get(item, "detections", "confidence"),
            "hosting": json_get(item, "detections", "hosting"),
            "proxy": json_get(item, "detections", "proxy"),
            "vpn": json_get(item, "detections", "vpn"),
        }

    def _ip_api_server(self, ip: str) -> dict:
        r = self.session.get(
            f"http://ip-api.com/json/{ip}",
            params={"fields": "17032966"},
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("status") == "fail":
            raise ValueError(f"ip-api lookup failed: {data.get('message', 'unknown error')}")
        return {
            "lookup_status": "success",
            "source": "ip-api",
            "fallback": True,
            "provider": data.get("isp"),
            "organisation": data.get("org") or data.get("isp") or data.get("asname") or data.get("as"),
            "type": "Hosting" if data.get("hosting") is True else None,
            "continent_code": data.get("continentCode"),
            "country_name": data.get("country"),
            "country_code": data.get("countryCode"),
            "region_name": data.get("regionName"),
            "region_code": data.get("region"),
            "city_name": data.get("city"),
            "risk": None,
            "confidence": None,
            "hosting": data.get("hosting"),
            "proxy": data.get("proxy"),
            "vpn": None,
        }

    def _freeipapi_server(self, ip: str) -> dict:
        r = self.session.get(
            f"https://free.freeipapi.com/api/json/{ip}",
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("ipAddress") and data.get("ipAddress") != ip:
            raise ValueError("FreeIPAPI returned a different IP")
        return {
            "lookup_status": "success",
            "source": "freeipapi",
            "fallback": True,
            "provider": data.get("asnOrganization"),
            "organisation": data.get("asnOrganization"),
            "type": None,
            "continent_code": data.get("continentCode"),
            "country_name": data.get("countryName"),
            "country_code": data.get("countryCode"),
            "region_name": data.get("regionName"),
            "region_code": data.get("regionCode"),
            "city_name": data.get("cityName"),
            "risk": None,
            "confidence": None,
            "hosting": None,
            "proxy": data.get("isProxy"),
            "vpn": None,
        }

    def modio(self, ugc_or_id: str | int) -> Optional[dict]:
        sid = str(ugc_or_id)
        m = re.search(r"(\d+)", sid)
        if not m:
            return None
        mod_id = m.group(1)

        cached = self.modio_cache.get(mod_id)
        if isinstance(cached, dict) and self._cache_fresh(cached, self.modio_ttl):
            return {k: v for k, v in cached.items() if not k.startswith("_")}

        if not self.modio_key:
            return cached if isinstance(cached, dict) else None

        r = self.session.get(
            f"https://api.mod.io/v1/games/{self.modio_game_id}/mods/{mod_id}",
            params={"api_key": self.modio_key},
            timeout=self.timeout,
        )
        r.raise_for_status()
        d = r.json()
        result = {
            "id": d.get("id"),
            "ugc_id": f"UGC{mod_id}",
            "name": d.get("name"),
            "thumb_320x180": json_get(d, "logo", "thumb_320x180"),
            "downloads_today": json_get(d, "stats", "downloads_today"),
            "downloads_total": json_get(d, "stats", "downloads_total"),
            "summary": d.get("summary"),
            "last_updated": now_iso(),
        }
        store = dict(result)
        store["_cached_unix"] = time.time()
        self.modio_cache[mod_id] = store
        atomic_write_json(self.modio_cache_path, self.modio_cache)
        return result


# ----------------------------- player database ---------------------------

class PlayerDB:
    def __init__(self, root: Path, ip_secret: str, enricher: Enricher):
        self.root = root
        self.records = root / "players" / "records"
        self.index_dir = root / "players" / "index"
        self.private_dir = root / "private"
        self.records.mkdir(parents=True, exist_ok=True)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.private_dir.mkdir(parents=True, exist_ok=True)

        self.ip_secret = ip_secret.encode("utf-8")
        self.enricher = enricher

        self.by_name_path = self.index_dir / "by_name.json"
        self.by_uid_path = self.index_dir / "by_unique_id.json"
        self.by_pid_path = self.index_dir / "by_product_id.json"
        self.by_ip_hash_path = self.index_dir / "by_ip_hash.json"
        self.by_discord_id_path = self.index_dir / "by_discord_id.json"
        self.by_steam_id_path = self.index_dir / "by_steam_id.json"
        self.by_name = load_json(self.by_name_path, {})
        self.by_uid = load_json(self.by_uid_path, {})
        self.by_pid = load_json(self.by_pid_path, {})
        self.by_ip_hash = load_json(self.by_ip_hash_path, {})
        self.by_discord_id = load_json(self.by_discord_id_path, {})
        self.by_steam_id = load_json(self.by_steam_id_path, {})

        self.private_ips_path = self.private_dir / "player_ips.json"
        self.private_ips = load_json(self.private_ips_path, {})
        try:
            os.chmod(self.private_dir, 0o700)
        except OSError:
            pass

    def flush_indexes(self):
        atomic_write_json(self.by_name_path, self.by_name)
        atomic_write_json(self.by_uid_path, self.by_uid)
        atomic_write_json(self.by_pid_path, self.by_pid)
        atomic_write_json(self.by_ip_hash_path, self.by_ip_hash)
        atomic_write_json(self.by_discord_id_path, self.by_discord_id)
        atomic_write_json(self.by_steam_id_path, self.by_steam_id)
        atomic_write_json(self.private_ips_path, self.private_ips)
        try:
            os.chmod(self.private_ips_path, 0o600)
        except OSError:
            pass

    def rebuild_indexes_from_records(self) -> dict[str, int]:
        """
        Rebuild all public player lookup indexes from the durable per-player
        records on disk.

        Source of truth:
          players/records/{product_id}/player.json
          players/records/{product_id}/names.json
          players/records/{product_id}/ips.json
          players/records/{product_id}/changes.jsonl

        Derived indexes:
          players/index/by_name.json
          players/index/by_unique_id.json
          players/index/by_product_id.json
          players/index/by_ip_hash.json

        This intentionally does not rebuild private/player_ips.json because that
        file contains isolated raw IP data and is not derivable from the public
        player records.
        """
        by_name: dict[str, list[str]] = {}
        by_uid: dict[str, list[str]] = {}
        by_pid: dict[str, dict[str, Any]] = {}
        by_ip_hash: dict[str, list[str]] = {}
        by_discord_id: dict[str, str] = {}
        by_steam_id: dict[str, str] = {}

        scanned_player_files = 0
        valid_players = 0
        invalid_players = 0
        name_relationships = 0
        uid_relationships = 0
        ip_relationships = 0

        print(
            f"Rebuilding player indexes from {self.records} ...",
            flush=True,
        )

        # Only directories containing player.json are valid durable player
        # records. This avoids treating the many partially-created/empty record
        # directories as complete players.
        for player_path in self.records.glob("*/player.json"):
            if not player_path.is_file():
                continue

            scanned_player_files += 1
            pdir = player_path.parent

            player = load_json(player_path, None)
            if not isinstance(player, dict):
                invalid_players += 1
                continue

            product_id = str(
                player.get("product_id") or pdir.name
            ).strip()
            if not product_id:
                invalid_players += 1
                continue

            valid_players += 1

            current_name = player.get("current_name")
            unique_id = player.get("unique_id")
            platform = player.get("platform")

            linked = player.get("linked_accounts", {})
            if isinstance(linked, dict):
                discord_link = linked.get("discord", {})
                if isinstance(discord_link, dict) and discord_link.get("user_id"):
                    by_discord_id[str(discord_link["user_id"])] = product_id
                steam_link = linked.get("steam", {})
                if isinstance(steam_link, dict) and steam_link.get("steam_id"):
                    by_steam_id[str(steam_link["steam_id"])] = product_id

            by_pid[product_id] = {
                "current_name": current_name,
                "unique_id": unique_id,
                "platform": platform,
            }

            # Current name.
            if current_name:
                vals = by_name.setdefault(
                    str(current_name).casefold(),
                    [],
                )
                if unique_append(vals, product_id):
                    name_relationships += 1

            # Historical names.
            names_doc = load_json(pdir / "names.json", {})
            if isinstance(names_doc, dict):
                historical_names = names_doc.get("names", {})
                if isinstance(historical_names, dict):
                    for historical_name in historical_names:
                        if not historical_name:
                            continue
                        vals = by_name.setdefault(
                            str(historical_name).casefold(),
                            [],
                        )
                        if unique_append(vals, product_id):
                            name_relationships += 1

            # Current UniqueID.
            if unique_id:
                vals = by_uid.setdefault(str(unique_id), [])
                if unique_append(vals, product_id):
                    uid_relationships += 1

            # Preserve historical UniqueIDs. learn_identity() intentionally
            # leaves old UniqueID mappings valid, so a rebuild must recover them
            # from the durable change log as well.
            changes_path = pdir / "changes.jsonl"
            if changes_path.is_file():
                try:
                    with changes_path.open(
                        "r",
                        encoding="utf-8",
                        errors="replace",
                    ) as changes_file:
                        for raw in changes_file:
                            raw = raw.strip()
                            if not raw:
                                continue
                            try:
                                change = json.loads(raw)
                            except json.JSONDecodeError:
                                continue
                            if not isinstance(change, dict):
                                continue
                            if change.get("type") != "unique_id_changed":
                                continue
                            for uid_value in (
                                change.get("old_value"),
                                change.get("new_value"),
                            ):
                                if not uid_value:
                                    continue
                                vals = by_uid.setdefault(
                                    str(uid_value),
                                    [],
                                )
                                if unique_append(vals, product_id):
                                    uid_relationships += 1
                except OSError:
                    pass

            # Every previously observed public IP hash.
            ips_doc = load_json(pdir / "ips.json", {})
            if isinstance(ips_doc, dict):
                ips = ips_doc.get("ips", {})
                if isinstance(ips, dict):
                    for ip_hash in ips:
                        if not ip_hash:
                            continue
                        vals = by_ip_hash.setdefault(
                            str(ip_hash),
                            [],
                        )
                        if unique_append(vals, product_id):
                            ip_relationships += 1

            if valid_players % 5000 == 0:
                print(
                    f"  indexed {valid_players:,} valid players ...",
                    flush=True,
                )

        # Replace in-memory indexes only after the complete scan succeeds. This
        # prevents a partially built index from being flushed if the scan fails
        # part-way through.
        self.by_name = dict(sorted(by_name.items()))
        self.by_uid = dict(sorted(by_uid.items()))
        self.by_pid = dict(sorted(by_pid.items()))
        self.by_ip_hash = dict(sorted(by_ip_hash.items()))
        self.by_discord_id = dict(sorted(by_discord_id.items()))
        self.by_steam_id = dict(sorted(by_steam_id.items()))

        self.flush_indexes()

        result = {
            "player_files_scanned": scanned_player_files,
            "valid_players": valid_players,
            "invalid_player_files": invalid_players,
            "name_entries": len(self.by_name),
            "name_relationships": name_relationships,
            "unique_id_entries": len(self.by_uid),
            "unique_id_relationships": uid_relationships,
            "product_id_entries": len(self.by_pid),
            "ip_hash_entries": len(self.by_ip_hash),
            "ip_hash_relationships": ip_relationships,
            "discord_id_entries": len(self.by_discord_id),
            "steam_id_entries": len(self.by_steam_id),
        }

        atomic_write_json(
            self.index_dir / "rebuild_status.json",
            {
                "rebuilt_at": now_iso(),
                **result,
            },
        )

        print(
            "Player index rebuild complete: "
            f"{valid_players:,} players, "
            f"{len(self.by_name):,} names, "
            f"{len(self.by_uid):,} unique IDs, "
            f"{len(self.by_ip_hash):,} IP hashes.",
            flush=True,
        )

        return result

    def ip_hash(self, ip: str) -> str:
        return hmac.new(self.ip_secret, ip.encode(), hashlib.sha256).hexdigest()

    def player_dir(self, product_id: str) -> Path:
        p = self.records / safe_name(product_id)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def resolve(self, name: Optional[str] = None, unique_id: Optional[str] = None) -> Optional[str]:
        candidates: list[str] = []
        if unique_id:
            candidates.extend(self.by_uid.get(unique_id, []))
        if name:
            candidates.extend(self.by_name.get(name.casefold(), []))
        u = list(dict.fromkeys(candidates))
        return u[0] if len(u) == 1 else None

    def identity_candidates(self, name: Optional[str]) -> list[str]:
        if not name:
            return []
        return list(self.by_name.get(name.casefold(), []))

    def learn_identity(self, product_id: str, unique_id: Optional[str], name: Optional[str],
                       platform: Optional[str], ts: str, server_id: str) -> None:
        pdir = self.player_dir(product_id)
        player_path = pdir / "player.json"
        names_path = pdir / "names.json"
        player = load_json(player_path, {
            "product_id": product_id,
            "platform": platform,
            "unique_id": unique_id,
            "current_name": name,
            "admin": False,
            "banned": False,
            "banned_servers": [],
            "first_seen": ts,
            "last_seen": ts,
            "servers_seen": [],
            "preferences": {
                "player_height": None,
                "right_handed": None,
                "vstock": None,
                "client_platform": None
            },
            "network": {
                "current_ip_hash": None,
                "known_ip_count": 0,
                "current_background": None
            },
            "linked_accounts": {
                "discord": None,
                "steam": None,
                "profile_link": None
            }
        })
        player["last_seen"] = ts
        player["first_seen"] = min(player.get("first_seen") or ts, ts)
        if platform:
            player["platform"] = platform
        if unique_id:
            old_uid = player.get("unique_id")
            if old_uid and old_uid != unique_id:
                self._change(product_id, ts, "unique_id_changed", old_uid, unique_id, server_id)
            player["unique_id"] = unique_id
            vals = self.by_uid.setdefault(unique_id, [])
            unique_append(vals, product_id)
        # On PCVR, Pavlov's pid/uniqueId is normally SteamID64. Keep the
        # explicit Steam -> EOS ProductID relationship so combat resolution does
        # not have to depend on player names.
        if str(platform or "").upper() == "PCVR" and unique_id:
            uid_text = str(unique_id).strip()
            if re.fullmatch(r"7656119\d{10}", uid_text):
                linked = player.setdefault("linked_accounts", {})
                steam = linked.get("steam")
                if not isinstance(steam, dict):
                    steam = {}
                steam["steam_id"] = uid_text
                linked["steam"] = steam
                self.by_steam_id[uid_text] = product_id

        if name:
            old_name = player.get("current_name")
            if old_name and old_name != name:
                self._change(product_id, ts, "player_name_changed", old_name, name, server_id)
            player["current_name"] = name
            vals = self.by_name.setdefault(name.casefold(), [])
            unique_append(vals, product_id)
        unique_append(player["servers_seen"], server_id)

        names = load_json(names_path, {"product_id": product_id, "current_name": name, "names": {}})
        if name:
            names["current_name"] = name
            ent = names["names"].setdefault(name, {"first_seen": ts, "last_seen": ts, "times_seen": 0})
            ent["first_seen"] = min(ent.get("first_seen") or ts, ts)
            ent["last_seen"] = max(ent.get("last_seen") or ts, ts)
            ent["times_seen"] = int(ent.get("times_seen", 0)) + 1

        self.by_pid[product_id] = {
            "current_name": player.get("current_name"),
            "unique_id": player.get("unique_id"),
            "platform": player.get("platform")
        }
        atomic_write_json(player_path, player)
        atomic_write_json(names_path, names)

    def _change(self, product_id: str, ts: str, ctype: str, old: Any, new: Any, server_id: str):
        append_jsonl(self.player_dir(product_id) / "changes.jsonl", {
            "timestamp": ts,
            "type": ctype,
            "old_value": old,
            "new_value": new,
            "server_id": server_id,
        })

    def set_admin(self, product_id: str, value: bool):
        p = self.player_dir(product_id) / "player.json"
        d = load_json(p, {"product_id": product_id})
        d["admin"] = bool(value)
        atomic_write_json(p, d)

    def set_ban_state(self, product_id: str, server_id: str, banned: bool):
        p = self.player_dir(product_id) / "player.json"
        d = load_json(p, {"product_id": product_id, "banned_servers": []})
        servers = d.setdefault("banned_servers", [])
        if banned:
            unique_append(servers, server_id)
        elif server_id in servers:
            servers.remove(server_id)
        d["banned"] = bool(servers)
        atomic_write_json(p, d)

    def update_preferences(self, product_id: str, ts: str, server_id: str,
                           height: Optional[float], right_handed: Optional[bool],
                           vstock: Optional[bool], client_platform: Optional[str]) -> None:
        p = self.player_dir(product_id) / "player.json"
        d = load_json(p, {"product_id": product_id, "preferences": {}})
        pref = d.setdefault("preferences", {})
        newvals = {
            "player_height": round(height, 1) if height is not None else None,
            "right_handed": right_handed,
            "vstock": vstock,
            "client_platform": client_platform,
        }
        for field, new in newvals.items():
            if new is None:
                continue
            old = pref.get(field)
            if old is not None and old != new:
                self._change(product_id, ts, f"{field}_changed", old, new, server_id)
            pref[field] = new
        d["last_seen"] = ts
        atomic_write_json(p, d)

    def observe_player_ip(self, product_id: str, ip: str, ts: str, server_id: str) -> tuple[str, dict]:
        # Validate before any storage / API request.
        ipaddress.ip_address(ip)
        ih = self.ip_hash(ip)
        background = self.enricher.lookup_ip(ip)

        pdir = self.player_dir(product_id)
        safe_path = pdir / "ips.json"
        safe = load_json(safe_path, {"product_id": product_id, "current_ip_hash": None, "ips": {}})
        old_hash = safe.get("current_ip_hash")
        ent = safe["ips"].setdefault(ih, {
            "first_seen": ts,
            "last_seen": ts,
            "connections": 0,
            "background": background
        })
        ent["first_seen"] = min(ent.get("first_seen") or ts, ts)
        ent["last_seen"] = max(ent.get("last_seen") or ts, ts)
        ent["connections"] = int(ent.get("connections", 0)) + 1
        ent["background"] = background
        safe["current_ip_hash"] = ih
        atomic_write_json(safe_path, safe)

        # Fast global correlation index: IP hash -> productIds.
        ip_players = self.by_ip_hash.setdefault(ih, [])
        unique_append(ip_players, product_id)

        # Private raw IP storage, keyed by productId.
        ppriv = self.private_ips.setdefault(product_id, {})
        ipent = ppriv.setdefault(ip, {"hash": ih, "first_seen": ts, "last_seen": ts, "connections": 0})
        ipent["first_seen"] = min(ipent.get("first_seen") or ts, ts)
        ipent["last_seen"] = max(ipent.get("last_seen") or ts, ts)
        ipent["connections"] = int(ipent.get("connections", 0)) + 1
        ipent["hash"] = ih

        # Update player current network, but change log stores no raw IP.
        player_path = pdir / "player.json"
        player = load_json(player_path, {"product_id": product_id, "network": {}})
        net = player.setdefault("network", {})
        old_bg = net.get("current_background") or {}
        if old_hash and old_hash != ih:
            self._change(product_id, ts, "ip_hash_changed", old_hash, ih, server_id)
        for key in ("organisation", "country_code", "proxy", "vpn", "hosting", "tor"):
            old, new = old_bg.get(key), background.get(key)
            if old is not None and new is not None and old != new:
                self._change(product_id, ts, f"network_{key}_changed", old, new, server_id)

        net["current_ip_hash"] = ih
        net["known_ip_count"] = len(safe["ips"])
        net["current_background"] = background
        atomic_write_json(player_path, player)

        if background.get("vpn") is True or background.get("proxy") is True:
            self.award_badge(
                product_id,
                BADGE_VPN_CONNECTION,
                ts,
                awarded_by="collector",
                reason="VPN or proxy connection detected.",
                metadata={
                    "server_id": server_id,
                    "ip_hash": ih,
                    "source": background.get("source"),
                    "vpn": background.get("vpn"),
                    "proxy": background.get("proxy"),
                },
            )

        return ih, background

    def players_for_ip_hash(self, ip_hash: str) -> list[dict[str, Any]]:
        """Return known player identities that have used this stable IP hash."""
        out: list[dict[str, Any]] = []
        for product_id in self.by_ip_hash.get(ip_hash, []):
            p = load_json(self.player_dir(product_id) / "player.json", {})
            out.append({
                "product_id": product_id,
                "unique_id": p.get("unique_id"),
                "player_name": p.get("current_name"),
                "admin": bool(p.get("admin", False)),
                "banned": bool(p.get("banned", False)),
            })
        return out

    def award_badge(
        self,
        product_id: str,
        badge_name: str,
        ts: str,
        awarded_by: str = "collector",
        reason: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Idempotently award a badge in players/records/{product_id}/badges.json."""
        path = self.player_dir(product_id) / "badges.json"
        doc = load_json(path, {
            "version": 1,
            "product_id": product_id,
            "badges": {},
        })
        doc["version"] = 1
        doc["product_id"] = product_id
        badges = doc.setdefault("badges", {})
        if badge_name in badges:
            return False

        entry: dict[str, Any] = {
            "name": badge_name,
            "awarded_at": ts,
            "awarded_by": awarded_by,
            "reason": reason,
        }
        if metadata:
            entry["metadata"] = metadata
        badges[badge_name] = entry
        atomic_write_json(path, doc)
        return True

    def increment_connection(self, product_id: str):
        self._inc_activity(product_id, "times_connected", 1)

    def increment_match(self, product_id: str):
        self._inc_activity(product_id, "matches", 1)

    def _inc_activity(self, product_id: str, field: str, n: int):
        p = self.player_dir(product_id) / "stats.json"
        d = load_json(p, {
            "product_id": product_id,
            "combat": {
                "kills": 0, "deaths": 0, "headshots": 0,
                "suicides": 0, "teamkills": 0, "bot_kills": 0,
                "kills_unverified_team_relation": 0
            },
            "activity": {"times_connected": 0, "matches": 0, "total_time_online_seconds": 0, "total_time_online_formatted": "0s"},
            "weapons": {"favorite": None, "favorite_kills": 0},
        })
        d.setdefault("activity", {})[field] = int(d["activity"].get(field, 0)) + n
        atomic_write_json(p, d)

    def rebuild_total_time_online(self) -> dict[str, int]:
        """Recompute lifetime online time from each player's completed sessions.

        connections.jsonl is the durable source, so this is safe to run repeatedly
        and also backfills players whose sessions were collected before this stat
        existed. Incomplete sessions without a duration are ignored.
        """
        records_root = self.data_root / "players" / "records"
        players_scanned = 0
        sessions_counted = 0

        if not records_root.is_dir():
            return {"players_scanned": 0, "sessions_counted": 0}

        for player_dir in records_root.iterdir():
            if not player_dir.is_dir():
                continue
            connections_path = player_dir / "connections.jsonl"
            if not connections_path.is_file():
                continue

            total = 0
            counted = 0
            with connections_path.open("r", encoding="utf-8", errors="replace") as handle:
                for raw in handle:
                    try:
                        entry = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    duration = entry.get("duration_seconds")
                    if duration is None:
                        continue
                    try:
                        duration = max(0, int(duration))
                    except (TypeError, ValueError):
                        continue
                    total += duration
                    counted += 1

            stats_path = player_dir / "stats.json"
            stats = load_json(stats_path, {"product_id": player_dir.name})
            activity = stats.setdefault("activity", {})
            activity.setdefault("times_connected", 0)
            activity.setdefault("matches", 0)
            activity["total_time_online_seconds"] = total
            activity["total_time_online_formatted"] = format_duration_seconds(total)
            atomic_write_json(stats_path, stats)

            players_scanned += 1
            sessions_counted += counted

        return {"players_scanned": players_scanned, "sessions_counted": sessions_counted}

    def combat(self, product_id: str, field: str, n: int = 1):
        p = self.player_dir(product_id) / "stats.json"
        d = load_json(p, {
            "product_id": product_id,
            "combat": {},
            "activity": {"times_connected": 0, "matches": 0, "total_time_online_seconds": 0, "total_time_online_formatted": "0s"},
            "weapons": {"favorite": None, "favorite_kills": 0}
        })
        combat = d.setdefault("combat", {})
        combat[field] = int(combat.get(field, 0)) + n
        d["combat_source"] = "pavlov_log"
        atomic_write_json(p, d)

        # Automatic badge #004: award once lifetime normal player kills
        # reach 1,000. This uses the collector's existing "kills" counter,
        # so bot kills/teamkills/suicides do not qualify unless they are
        # already counted as normal kills by the collector.
        if field == "kills" and int(combat.get("kills", 0)) >= KILLS_BADGE_THRESHOLD:
            self.award_badge(
                product_id,
                BADGE_1000_KILLS,
                now_iso(),
                awarded_by="collector",
                reason=f"Reached {KILLS_BADGE_THRESHOLD:,} lifetime kills.",
                metadata={
                    "kills": int(combat.get("kills", 0)),
                    "source": "pavlov_log",
                },
            )

    def weapon_kill(self, product_id: str, weapon: str, headshot: bool, source: str):
        if not weapon or weapon.casefold() == "none":
            return
        pdir = self.player_dir(product_id)
        path = pdir / "weapons.json"
        d = load_json(path, {
            "product_id": product_id,
            "favorite_weapon": None,
            "total_weapon_kills": 0,
            "weapons": {}
        })
        e = d["weapons"].setdefault(weapon, {"kills": 0, "headshots": 0, "source": source})
        e["kills"] += 1
        if headshot:
            e["headshots"] += 1
        e["source"] = source
        d["total_weapon_kills"] += 1
        fav, favdata = max(d["weapons"].items(), key=lambda kv: kv[1].get("kills", 0))
        d["favorite_weapon"] = fav
        atomic_write_json(path, d)

        sp = pdir / "stats.json"
        stats = load_json(sp, {"product_id": product_id, "combat": {}, "activity": {}, "weapons": {}})
        stats.setdefault("weapons", {})["favorite"] = fav
        stats["weapons"]["favorite_kills"] = favdata.get("kills", 0)
        atomic_write_json(sp, stats)


# ----------------------------- archive / state ---------------------------

class ProcessingState:
    def __init__(self, root: Path):
        self.path = root / "global" / "processing_state.json"
        self.data = load_json(self.path, {"processed_files": {}})

    def done(self, path: Path) -> bool:
        if not path.exists():
            return True
        h = sha256_file(path)
        return h in self.data["processed_files"]

    def mark(self, path: Path):
        h = sha256_file(path)
        self.data["processed_files"][h] = {
            "path": str(path),
            "size": path.stat().st_size,
            "processed_at": now_iso()
        }
        atomic_write_json(self.path, self.data)


def archive_logs(server: ServerCfg, archive_root: Path, rotate_active: bool) -> tuple[list[Path], list[Path]]:
    srv_arc = archive_root / server.server_id
    log_arc = srv_arc / "logs"
    stats_arc = srv_arc / "stats"
    log_arc.mkdir(parents=True, exist_ok=True)
    stats_arc.mkdir(parents=True, exist_ok=True)

    # Move Pavlov backups.
    if server.log_path.exists():
        for p in sorted(server.log_path.glob("Pavlov-backup-*.log")):
            dest = log_arc / p.name
            if dest.exists():
                # Content-safe duplicate name handling.
                if sha256_file(dest) == sha256_file(p):
                    p.unlink()
                    continue
                dest = log_arc / f"{p.stem}-{int(time.time())}{p.suffix}"
            shutil.move(str(p), str(dest))

        live = server.log_path / "Pavlov.log"
        if rotate_active and live.exists() and live.stat().st_size > 0:
            dest = log_arc / f"Pavlov-backup-{now_pavlov_name()}.log"
            shutil.copy2(live, dest)
            # Only truncate after copy completed.
            with live.open("r+b") as f:
                f.truncate(0)

    # Move Stats archives.
    if server.stats_path and server.stats_path.exists():
        for p in sorted(server.stats_path.glob("Stats-*.log")):
            dest = stats_arc / p.name
            if dest.exists():
                if sha256_file(dest) == sha256_file(p):
                    p.unlink()
                    continue
                dest = stats_arc / f"{p.stem}-{int(time.time())}{p.suffix}"
            shutil.move(str(p), str(dest))

        live = server.stats_path / "Stats.log"
        if rotate_active and live.exists() and live.stat().st_size > 0:
            dest = stats_arc / f"Stats-{now_pavlov_name()}.log"
            shutil.copy2(live, dest)
            with live.open("r+b") as f:
                f.truncate(0)

    return sorted(log_arc.glob("*.log")), sorted(stats_arc.glob("*.log"))


# ----------------------------- Stats parser ------------------------------

def iter_stats_records(path: Path) -> Iterable[tuple[str, dict]]:
    """
    Stats files are streams of timestamped JSON documents, not one JSON document.
    The first line contains '[timestamp] StatManagerLog:' and the following lines
    contain the remainder of the object.
    """
    current_ts: Optional[str] = None
    buf: list[str] = []
    depth = 0
    in_string = False
    escape = False
    started = False

    def feed_balance(s: str):
        nonlocal depth, in_string, escape, started
        for ch in s:
            if escape:
                escape = False
                continue
            if ch == "\\" and in_string:
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
                started = True
            elif ch == "}":
                depth -= 1

    with path.open("r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\n")
            m = STATS_TS_RE.match(line)
            if m:
                # Flush a prior complete record if necessary.
                current_ts = m.group("ts")
                body = m.group("body")
                buf = [body] if body else []
                depth = 0
                in_string = False
                escape = False
                started = False
                feed_balance(body)
            elif current_ts is not None:
                buf.append(line)
                feed_balance(line)

            if current_ts and started and depth == 0:
                text = "\n".join(buf).strip()
                try:
                    yield current_ts, json.loads(text)
                except json.JSONDecodeError:
                    pass
                current_ts = None
                buf = []
                started = False



def iter_pavlov_stat_records(path: Path) -> Iterable[tuple[str, dict]]:
    """Yield multiline ``StatManagerLog: { ... }`` objects from a Pavlov log.

    Pavlov.log / Pavlov-backup-*.log interleave ordinary timestamped log lines
    with multiline StatManagerLog JSON blocks.  This parser intentionally reads
    only those JSON blocks so combat can be rebuilt without replaying connection,
    RCON, HTTP, or other side effects from the same Pavlov log.
    """
    current_ts: Optional[str] = None
    buf: list[str] = []
    depth = 0
    in_string = False
    escape = False
    started = False

    def feed_balance(s: str) -> None:
        nonlocal depth, in_string, escape, started
        for ch in s:
            if escape:
                escape = False
                continue
            if ch == "\\" and in_string:
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
                started = True
            elif ch == "}":
                depth -= 1

    def reset() -> None:
        nonlocal current_ts, buf, depth, in_string, escape, started
        current_ts = None
        buf = []
        depth = 0
        in_string = False
        escape = False
        started = False

    with path.open("r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\n")
            m = TS_RE.match(line)

            if m:
                # A new timestamped line terminates any malformed/incomplete
                # StatManager block rather than accidentally swallowing the rest
                # of the Pavlov log.
                if current_ts is not None and (not started or depth != 0):
                    reset()

                body = m.group("body").strip()
                sm = re.match(r"StatManagerLog:\s*(.*)$", body)
                if not sm:
                    continue

                current_ts = m.group("ts")
                first = sm.group(1)
                buf = [first] if first else []
                depth = 0
                in_string = False
                escape = False
                started = False
                feed_balance(first)
            elif current_ts is not None:
                buf.append(line)
                feed_balance(line)
            else:
                continue

            if current_ts and started and depth == 0:
                payload = "\n".join(buf).strip()
                try:
                    obj = json.loads(payload)
                except json.JSONDecodeError:
                    reset()
                    continue
                if isinstance(obj, dict):
                    yield current_ts, obj
                reset()


# ----------------------------- server collector --------------------------

@dataclass
class RconSession:
    ip_hash: str
    port: int
    authenticated_at: str
    raw_ip_ephemeral: Optional[str] = None


@dataclass
class NetSession:
    endpoint: str
    ip: str
    port: int
    connection_name: Optional[str]
    started_at: str
    login_at: Optional[str] = None
    joined_at: Optional[str] = None
    disconnected_at: Optional[str] = None
    player_name: Optional[str] = None
    unique_id: Optional[str] = None
    network_user_id: Optional[str] = None
    player_height: Optional[float] = None
    right_handed: Optional[bool] = None
    vstock: Optional[bool] = None
    client_platform: Optional[str] = None
    team_id: Optional[int] = None
    product_id: Optional[str] = None
    counted_join: bool = False
    enriched_ip_hash: Optional[str] = None


class Collector:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.data_root = Path(cfg["data_path"]).expanduser()
        self.archive_root = Path(cfg["archive_path"]).expanduser()

        # Historical archives are READ ONLY.  They are scanned recursively and
        # fed through the same parsers / SHA-256 processing state as live archives.
        raw_old_archives = cfg.get("old_archive_paths", [])
        if isinstance(raw_old_archives, (str, Path)):
            raw_old_archives = [raw_old_archives]

        # Backwards-friendly singular spelling too.
        singular_old_archive = cfg.get("old_archive_path")
        if singular_old_archive:
            raw_old_archives = list(raw_old_archives) + [singular_old_archive]

        self.old_archive_roots: list[Path] = []
        for value in raw_old_archives:
            if not value:
                continue
            p = Path(str(value)).expanduser().resolve()
            if p not in self.old_archive_roots:
                self.old_archive_roots.append(p)

        self.data_root.mkdir(parents=True, exist_ok=True)
        self.archive_root.mkdir(parents=True, exist_ok=True)
        secret = os.getenv("JTWP_IP_HASH_SECRET")
        if not secret:
            raise SystemExit(
                "JTWP_IP_HASH_SECRET is required. Example:\n"
                "  export JTWP_IP_HASH_SECRET=\"$(openssl rand -hex 32)\""
            )
        self.enricher = Enricher(cfg, self.data_root)
        self.players = PlayerDB(self.data_root, secret, self.enricher)

        # server_id -> product_id -> teamkills in the current match.
        self.match_teamkills: dict[str, dict[str, int]] = defaultdict(dict)

        self.state = ProcessingState(self.data_root)
        self.servers = [ServerCfg.from_dict(x) for x in cfg["servers"]]
        items_path = Path(__file__).resolve().parent / "resource" / "items.json"
        items_data = load_json(items_path, {"items": []})
        self.base_items = set(items_data.get("items", []))
        self.global_admins: set[str] = set()
        self.platforms: dict[str, str] = {}

    @staticmethod
    def _unique_paths(paths: Iterable[Path]) -> list[Path]:
        """Return paths once, preserving deterministic sorted order."""
        seen: set[str] = set()
        out: list[Path] = []
        for path in sorted(paths, key=lambda p: str(p)):
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            out.append(path)
        return out

    def discover_old_archives(self) -> list[tuple[ServerCfg, list[Path], list[Path]]]:
        """
        Recursively discover historical Pavlov archives without modifying them.

        Expected layouts can be deeply nested, for example:
            /home/steam/logs/home/steam/pavlovserver005/Pavlov/Saved/Logs/*.log

        A directory is considered a Pavlov server source when a directory named
        "Pavlov" contains Saved/Logs and/or Saved/Stats.  The server_id is the
        directory immediately before "Pavlov".
        """
        discovered: dict[tuple[str, str], dict[str, Any]] = {}

        for root in self.old_archive_roots:
            if not root.exists():
                print(f"WARNING: old archive path does not exist: {root}", file=sys.stderr)
                continue
            if not root.is_dir():
                print(f"WARNING: old archive path is not a directory: {root}", file=sys.stderr)
                continue

            for pavlov_dir in root.rglob("Pavlov"):
                if not pavlov_dir.is_dir():
                    continue

                saved_dir = pavlov_dir / "Saved"
                log_dir = saved_dir / "Logs"
                stats_dir = saved_dir / "Stats"

                if not log_dir.is_dir() and not stats_dir.is_dir():
                    continue

                server_id = pavlov_dir.parent.name or "historical"
                source_key = (server_id, str(pavlov_dir.resolve()))

                log_files: list[Path] = []
                stat_files: list[Path] = []

                if log_dir.is_dir():
                    # Includes old Pavlov.log snapshots as well as backups.
                    log_files = [
                        p for p in log_dir.rglob("*.log")
                        if p.is_file() and (
                            p.name == "Pavlov.log"
                            or p.name.startswith("Pavlov-backup-")
                        )
                    ]

                if stats_dir.is_dir():
                    stat_files = [
                        p for p in stats_dir.rglob("*.log")
                        if p.is_file() and (
                            p.name == "Stats.log"
                            or p.name.startswith("Stats-")
                        )
                    ]

                server = ServerCfg(
                    log_path=log_dir,
                    server_id=server_id,
                    platform_override="auto",
                    stats_path=stats_dir,
                    game_ini_path=None,
                )

                discovered[source_key] = {
                    "server": server,
                    "logs": self._unique_paths(log_files),
                    "stats": self._unique_paths(stat_files),
                }

        result: list[tuple[ServerCfg, list[Path], list[Path]]] = []
        report_sources: list[dict[str, Any]] = []

        for (_, source_root), item in sorted(discovered.items()):
            server = item["server"]
            logs = item["logs"]
            stats = item["stats"]
            result.append((server, logs, stats))
            report_sources.append({
                "server_id": server.server_id,
                "source_root": source_root,
                "log_files": len(logs),
                "stats_files": len(stats),
            })

        atomic_write_json(
            self.data_root / "global" / "old_archive_index.json",
            {
                "indexed_at": now_iso(),
                "configured_roots": [str(p) for p in self.old_archive_roots],
                "sources_found": len(report_sources),
                "log_files_found": sum(x["log_files"] for x in report_sources),
                "stats_files_found": sum(x["stats_files"] for x in report_sources),
                "sources": report_sources,
                "read_only": True,
                "dedupe": "SHA-256 processing state",
            },
        )

        return result

    def backfill_badges(self) -> dict[str, int]:
        """Backfill automatic badges from durable player data already on disk.

        Safe/idempotent:
          #001 Discord link: player.json linked_accounts.discord.user_id exists.
          #002 VPN/proxy: any historical ips.json background has vpn/proxy == True.
          #004 1000 kills: stats.json combat.kills >= 1000.

        TeamKiller #003 is intentionally NOT backfilled from lifetime teamkill
        totals because the rule is 3 teamkills in one match, and a lifetime
        count cannot prove that condition.
        """
        results = {
            "players_scanned": 0,
            "discord_001_awarded": 0,
            "vpn_002_awarded": 0,
            "kills_004_awarded": 0,
            "already_owned_or_not_eligible": 0,
            "errors": 0,
        }

        records_root = self.data_root / "players" / "records"
        print(
            f"Badge backfill: scanning {records_root} ...",
            flush=True,
        )

        for player_path in records_root.glob("*/player.json"):
            if not player_path.is_file():
                continue

            results["players_scanned"] += 1
            pdir = player_path.parent
            product_id = pdir.name

            try:
                player = load_json(player_path, {})
                if not isinstance(player, dict):
                    results["errors"] += 1
                    continue

                product_id = str(
                    player.get("product_id")
                    or pdir.name
                ).strip()
                if not product_id:
                    results["errors"] += 1
                    continue

                awarded_any = False

                # #001 — Discord account already linked.
                linked = player.get("linked_accounts", {})
                if isinstance(linked, dict):
                    discord_link = linked.get("discord")
                    if (
                        isinstance(discord_link, dict)
                        and discord_link.get("user_id")
                    ):
                        if self.players.award_badge(
                            product_id,
                            BADGE_DISCORD_LINK,
                            now_iso(),
                            awarded_by="collector_backfill",
                            reason="Discord account already linked when badge backfill ran.",
                            metadata={
                                "backfilled": True,
                                "discord_user_id": str(
                                    discord_link.get("user_id")
                                ),
                            },
                        ):
                            results["discord_001_awarded"] += 1
                            awarded_any = True

                # #002 — any previously observed hashed IP positively detected
                # as VPN/proxy. No raw IP is copied into badges.json.
                ips_doc = load_json(pdir / "ips.json", {})
                ips = (
                    ips_doc.get("ips", {})
                    if isinstance(ips_doc, dict)
                    else {}
                )
                if isinstance(ips, dict):
                    for ip_hash, ip_entry in ips.items():
                        if not isinstance(ip_entry, dict):
                            continue
                        background = ip_entry.get("background", {})
                        if not isinstance(background, dict):
                            continue
                        if (
                            background.get("vpn") is True
                            or background.get("proxy") is True
                        ):
                            if self.players.award_badge(
                                product_id,
                                BADGE_VPN_CONNECTION,
                                now_iso(),
                                awarded_by="collector_backfill",
                                reason="Historical VPN or proxy connection detected.",
                                metadata={
                                    "backfilled": True,
                                    "ip_hash": str(ip_hash),
                                    "source": background.get("source"),
                                    "vpn": background.get("vpn"),
                                    "proxy": background.get("proxy"),
                                },
                            ):
                                results["vpn_002_awarded"] += 1
                                awarded_any = True
                            break

                # #004 — lifetime normal/player kills already at or above 1000.
                stats = load_json(pdir / "stats.json", {})
                combat = (
                    stats.get("combat", {})
                    if isinstance(stats, dict)
                    else {}
                )
                kills = (
                    int(combat.get("kills", 0) or 0)
                    if isinstance(combat, dict)
                    else 0
                )
                if kills >= KILLS_BADGE_THRESHOLD:
                    if self.players.award_badge(
                        product_id,
                        BADGE_1000_KILLS,
                        now_iso(),
                        awarded_by="collector_backfill",
                        reason=f"Already had {kills:,} lifetime kills when badge backfill ran.",
                        metadata={
                            "backfilled": True,
                            "kills": kills,
                            "threshold": KILLS_BADGE_THRESHOLD,
                            "source": (
                                stats.get("combat_source")
                                if isinstance(stats, dict)
                                else None
                            ),
                        },
                    ):
                        results["kills_004_awarded"] += 1
                        awarded_any = True

                if not awarded_any:
                    results["already_owned_or_not_eligible"] += 1

                if results["players_scanned"] % 5000 == 0:
                    print(
                        "  Badge backfill: "
                        f"{results['players_scanned']:,} players scanned, "
                        f"#001={results['discord_001_awarded']:,}, "
                        f"#002={results['vpn_002_awarded']:,}, "
                        f"#004={results['kills_004_awarded']:,}",
                        flush=True,
                    )

            except Exception as exc:
                results["errors"] += 1
                print(
                    f"WARNING: badge backfill failed for {product_id}: "
                    f"{type(exc).__name__}: {exc}",
                    file=sys.stderr,
                )

        report = {
            "backfilled_at": now_iso(),
            **results,
            "teamkiller_003_backfilled": False,
            "teamkiller_003_note": (
                "Not backfilled from lifetime totals because #003 requires "
                "3 teamkills in one match."
            ),
        }
        atomic_write_json(
            self.data_root / "global" / "badge_backfill_report.json",
            report,
        )

        print(
            "Badge backfill complete: "
            f"players={results['players_scanned']:,} "
            f"discord_001={results['discord_001_awarded']:,} "
            f"vpn_002={results['vpn_002_awarded']:,} "
            f"kills_004={results['kills_004_awarded']:,} "
            f"errors={results['errors']:,}",
            flush=True,
        )
        return results

    def run(self):
        # The durable per-player files are the source of truth. Rebuild the
        # derived lookup indexes before consulting processing_state, otherwise
        # previously processed logs cannot restore a lost/truncated index.
        if bool(self.cfg.get("rebuild_player_indexes_on_start", True)):
            self.players.rebuild_indexes_from_records()

        if bool(self.cfg.get("_backfill_badges", False)):
            self.backfill_badges()

        # Repair a small batch of old failed private-IP lookups every collector
        # run, even when those players do not reconnect. This uses the same
        # provider chain as normal player enrichment.
        if self.enricher.retry_failed_per_run > 0:
            retry = self.enricher.retry_failed_ip_lookups()
            if retry["selected"]:
                print(
                    "IP retry: "
                    f"selected={retry['selected']} "
                    f"successful={retry['successful']} "
                    f"failed={retry['failed']} "
                    f"remaining={retry['remaining']}"
                )

        # Public Pavlov server-list snapshot is independent of local log rotation.
        if bool(self.cfg.get("pavlov_api_enabled", True)):
            self.collect_pavlov_api()

        # Read config-side files first.
        self.load_global_admins()
        for server in self.servers:
            self.collect_game_ini(server)
            self.collect_bans(server)
            self.collect_systemd_service_metadata(server)

        # Build one combined processing view. Live archives are still rotated into
        # archive_root as before. Historical roots are read in-place and NEVER moved,
        # deleted, copied, or truncated.
        archives: dict[str, tuple[list[Path], list[Path]]] = {}
        processing_servers: dict[str, ServerCfg] = {}

        for server in self.servers:
            live_logs, live_stats = archive_logs(
                server, self.archive_root, bool(self.cfg.get("rotate_active_logs", True))
            )
            archives[server.server_id] = (
                self._unique_paths(live_logs),
                self._unique_paths(live_stats),
            )
            processing_servers[server.server_id] = server

        for old_server, old_logs, old_stats in self.discover_old_archives():
            sid = old_server.server_id
            current_logs, current_stats = archives.get(sid, ([], []))
            archives[sid] = (
                self._unique_paths(current_logs + old_logs),
                self._unique_paths(current_stats + old_stats),
            )
            # Prefer the live ServerCfg if this historical server_id still exists.
            processing_servers.setdefault(sid, old_server)

        all_processing_servers = list(processing_servers.values())

        if bool(self.cfg.get("_rebuild_identities", False)):
            print("Rebuilding player identities from Stats + explicit EOS login IDs ...", flush=True)
            identity = self.rebuild_identities_from_archives(archives, all_processing_servers)
            print(
                "Identity rebuild complete: "
                f"players_reset={identity['players_reset']:,} "
                f"stats_rows={identity['stats_identity_rows']:,} "
                f"login_rows={identity['login_identity_rows']:,} "
                f"players={identity['valid_players']:,} "
                f"names={identity['name_entries']:,} "
                f"unique_ids={identity['unique_id_entries']:,} "
                f"steam_ids={identity['steam_id_entries']:,}",
                flush=True,
            )

        if bool(self.cfg.get("_rebuild_connections", False)):
            print(
                "Rebuilding connections from authenticated network lifecycles "
                "(RemoteAddr + EOS ProductID on close/cleanup) ...",
                flush=True,
            )
            connection_result = self.rebuild_connections_from_archives(
                archives,
                all_processing_servers,
            )
            print(
                "Connection rebuild complete: "
                f"players_reset={connection_result['players_reset']:,} "
                f"connections={connection_result['authoritative_connections']:,} "
                f"ip_observations={connection_result['ip_observations']:,} "
                f"sessions={connection_result['sessions_written']:,} "
                f"close_only={connection_result['sessions_without_start']:,} "
                f"duplicate_close_lines="
                f"{connection_result['duplicate_close_lines_skipped']:,} "
                f"malformed_closes="
                f"{connection_result['malformed_authenticated_closes']:,} "
                f"ip_hashes={connection_result['ip_hash_entries']:,}",
                flush=True,
            )

        # First pass Stats across every live + historical server: learn productId
        # identity mappings before name-only KillData and connection lines.
        for server in all_processing_servers:
            log_files, stat_files = archives.get(server.server_id, ([], []))
            platform = self.detect_platform(server, log_files)
            self.platforms[server.server_id] = platform
            for p in stat_files:
                if not self.state.done(p):
                    self.process_stats_identity_and_rounds(server, platform, p)
                    self.state.mark(p)

        self.players.flush_indexes()
        self.apply_admin_flags()

        # Pavlov logs from both normal archives and configured historical archives.
        for server in all_processing_servers:
            log_files, _ = archives.get(server.server_id, ([], []))
            for p in log_files:
                if not self.state.done(p):
                    self.process_pavlov_log(
                        server,
                        self.platforms.get(server.server_id, "PCVR"),
                        p,
                    )
                    self.state.mark(p)

        # Combat comes from StatManagerLog KillData embedded in Pavlov logs, not
        # from Saved/Stats/Stats-*.log.  It has its own SHA state so already-
        # processed Pavlov logs can be combat-indexed without replaying connections.
        if bool(self.cfg.get("_rebuild_pavlov_combat", False)):
            self.reset_pavlov_combat_data()
        self.process_pavlov_combat_all(archives, all_processing_servers)

        self.players.flush_indexes()
        # Refresh enriched admins after log/stat processing so names/UniqueIDs that
        # became resolvable during this run appear in admins.json immediately.
        self.load_global_admins()
        self.apply_admin_flags()
        self.apply_ban_flags_from_snapshots()

        # Recompute lifetime online time from durable completed connection sessions.
        # This also backfills historical players and cannot double-count across runs.
        online = self.players.rebuild_total_time_online()
        if online["players_scanned"]:
            print(
                "Online-time stats: "
                f"players={online['players_scanned']:,} "
                f"sessions={online['sessions_counted']:,}",
                flush=True,
            )

        # Rebuild player links after ALL current and historical player IP hashes
        # have been learned.
        self.reconcile_rcon_player_links()

    def collect_pavlov_api(self) -> dict[str, Any]:
        """Fetch, enrich, index, and persist the public Pavlov server list."""
        api_url = os.getenv("PAVLOV_API", "").strip()
        outdir = self.data_root / "global" / "pavlov_api"
        indexdir = outdir / "index"
        outdir.mkdir(parents=True, exist_ok=True)
        indexdir.mkdir(parents=True, exist_ok=True)

        result = {
            "success": False,
            "collected_at": now_iso(),
            "api_url_configured": bool(api_url),
            "server_count": 0,
            "unique_host_count": 0,
        }

        if not api_url:
            result["error"] = "PAVLOV_API is not configured"
            atomic_write_json(outdir / "last_update.json", result)
            return result

        try:
            r = self.enricher.session.get(api_url, timeout=self.enricher.timeout)
            r.raise_for_status()
            raw = r.json()
            if not isinstance(raw, list):
                raise ValueError("PAVLOV_API response is not a JSON array")
        except Exception as e:
            result["error"] = self.enricher._safe_error(e)
            atomic_write_json(outdir / "last_update.json", result)
            return result

        # Enrich each unique host only once. Cache prevents repeat provider calls.
        host_data: dict[str, dict[str, Any]] = {}
        for row in raw:
            if not isinstance(row, dict):
                continue
            ip = str(row.get("ip") or "").strip()
            if not ip or ip in host_data:
                continue
            try:
                ipaddress.ip_address(ip)
            except ValueError:
                continue
            host_data[ip] = self.enricher.lookup_server_host(ip)

        servers: list[dict[str, Any]] = []
        by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
        by_ip: dict[str, list[str]] = defaultdict(list)
        by_map: dict[str, list[str]] = defaultdict(list)
        by_mode: dict[str, list[str]] = defaultdict(list)
        by_type: dict[str, list[str]] = defaultdict(list)

        total_players = 0
        total_slots = 0
        shack_servers = shack_players = 0
        pcvr_servers = pcvr_players = 0
        providers: dict[str, dict[str, int]] = defaultdict(lambda: {"servers": 0, "players": 0})
        countries: dict[str, dict[str, int]] = defaultdict(lambda: {"servers": 0, "players": 0})

        for row in raw:
            if not isinstance(row, dict):
                continue
            sid = str(row.get("_id") or row.get("hash") or row.get("pk") or "").strip()
            if not sid:
                continue
            ip = str(row.get("ip") or "").strip()
            name = str(row.get("name") or "").strip() or "Unnamed Server"
            slots = int(row.get("slots") or 0)
            max_slots = int(row.get("max_slots") or 0)
            server_type = str(row.get("server_type") or "")
            game_mode = str(row.get("game_mode") or "")
            map_id = str(row.get("map_id") or "")

            rec = {
                "id": sid,
                "name": name,
                "ip": ip or None,
                "port": row.get("port"),
                "server_type": server_type or None,
                "game_mode": game_mode or None,
                "map_id": map_id or None,
                "map_label": row.get("map_label"),
                "slots": slots,
                "max_slots": max_slots,
                "password_protected": normalize_bool(row.get("bPasswordProtected")),
                "secured": normalize_bool(row.get("bSecured")),
                "version": row.get("version"),
                "updated": row.get("updated"),
                "host": host_data.get(ip),
            }
            servers.append(rec)

            by_name[name.lower()].append({
                "name": name,
                "id": sid,
                "ip": ip or None,
                "port": row.get("port")
            })
            if ip:
                unique_append(by_ip[ip], sid)
            if map_id:
                unique_append(by_map[map_id], sid)
            if game_mode:
                unique_append(by_mode[game_mode], sid)
            if server_type:
                unique_append(by_type[server_type], sid)

            total_players += slots
            total_slots += max_slots
            st_lower = server_type.lower()
            if "shack" in st_lower:
                shack_servers += 1
                shack_players += slots
            else:
                pcvr_servers += 1
                pcvr_players += slots

            host = host_data.get(ip) or {}
            provider = host.get("provider") or host.get("organisation")
            if provider:
                providers[provider]["servers"] += 1
                providers[provider]["players"] += slots
            country = host.get("country_code")
            if country:
                countries[country]["servers"] += 1
                countries[country]["players"] += slots

        servers.sort(key=lambda x: (str(x.get("name") or "").lower(), str(x.get("id") or "")))
        clean_hosts = {ip: data for ip, data in sorted(host_data.items())}

        summary = {
            "collected_at": result["collected_at"],
            "total_servers": len(servers),
            "total_players": total_players,
            "total_slots": total_slots,
            "unique_hosts": len(clean_hosts),
            "shack": {"servers": shack_servers, "players": shack_players},
            "pcvr": {"servers": pcvr_servers, "players": pcvr_players},
            "hosting_providers": dict(sorted(providers.items(), key=lambda kv: (-kv[1]["servers"], kv[0].lower()))),
            "countries": dict(sorted(countries.items(), key=lambda kv: (-kv[1]["servers"], kv[0]))),
        }

        atomic_write_json(outdir / "servers.json", {
            "collected_at": result["collected_at"],
            "servers": servers,
        })
        atomic_write_json(outdir / "network_hosts.json", clean_hosts)
        atomic_write_json(outdir / "summary.json", summary)
        atomic_write_json(indexdir / "by_name.json", dict(sorted(by_name.items())))
        atomic_write_json(indexdir / "by_ip.json", dict(sorted(by_ip.items())))
        atomic_write_json(indexdir / "by_map.json", dict(sorted(by_map.items())))
        atomic_write_json(indexdir / "by_game_mode.json", dict(sorted(by_mode.items())))
        atomic_write_json(indexdir / "by_server_type.json", dict(sorted(by_type.items())))

        result.update({
            "success": True,
            "server_count": len(servers),
            "unique_host_count": len(clean_hosts),
        })
        atomic_write_json(outdir / "last_update.json", result)
        return result

    # --------------------- global admin / bans ---------------------------

    @staticmethod
    def _read_string_file(path: Path) -> list[str]:
        if not path.exists():
            return []
        vals = []
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                vals.append(s)
        return list(dict.fromkeys(vals))

    def load_global_admins(self):
        sources: dict[str, list[str]] = defaultdict(list)
        all_admins: set[str] = set()
        for s in self.servers:
            for path, label in (
                (s.mods_txt, "mods.txt"),
                (s.rconplus_admins, "RconPlus/MenuAccesscfg.txt"),
            ):
                for identifier in self._read_string_file(path):
                    all_admins.add(identifier)
                    sources[identifier].append(f"{s.server_id}/{label}")

        self.global_admins = all_admins
        output: dict[str, dict[str, Any]] = {}

        for identifier in sorted(all_admins, key=str.casefold):
            candidates: list[str] = []
            candidates.extend(self.players.by_uid.get(identifier, []))
            candidates.extend(self.players.by_name.get(identifier.casefold(), []))
            candidates = list(dict.fromkeys(candidates))

            item: dict[str, Any] = {
                "sources": sorted(set(sources[identifier])),
                "product_id": None,
                "platform": None,
                "unique_id": None,
                "current_name": identifier,
                "discord": None,
                "steam": None,
                "network": None,
            }

            if len(candidates) == 1:
                product_id = candidates[0]
                player = load_json(self.players.player_dir(product_id) / "player.json", {})
                linked = player.get("linked_accounts", {}) if isinstance(player, dict) else {}
                network = player.get("network", {}) if isinstance(player, dict) else {}
                bg = network.get("current_background", {}) if isinstance(network, dict) else {}
                country_code = bg.get("country_code") if isinstance(bg, dict) else None

                item.update({
                    "product_id": product_id,
                    "platform": player.get("platform"),
                    "unique_id": player.get("unique_id"),
                    "current_name": player.get("current_name") or identifier,
                    "discord": linked.get("discord") if isinstance(linked, dict) else None,
                    "steam": linked.get("steam") if isinstance(linked, dict) else None,
                    "network": {
                        "current_ip_hash": network.get("current_ip_hash") if isinstance(network, dict) else None,
                        "country_code": country_code,
                        "country_flag": country_flag(country_code),
                    },
                })
                self.players.set_admin(product_id, True)
            elif candidates:
                item["candidate_product_ids"] = candidates

            output[identifier] = item

        atomic_write_json(self.data_root / "global" / "admins.json", output)

    def apply_admin_flags(self):
        # load_global_admins resolves both names and UniqueIDs and sets the matching
        # durable player records. This method remains for backwards compatibility.
        for identifier in self.global_admins:
            pids = list(self.players.by_uid.get(identifier, []))
            pids.extend(self.players.by_name.get(identifier.casefold(), []))
            for pid in dict.fromkeys(pids):
                self.players.set_admin(pid, True)

    def collect_bans(self, server: ServerCfg):
        ids = self._read_string_file(server.blacklist)
        outdir = self.data_root / "servers" / server.server_id / "bans"
        cur_path = outdir / "current_bans.json"
        old = load_json(cur_path, {"banned_ids": []})
        oldset, newset = set(old.get("banned_ids", [])), set(ids)
        ts = now_iso()
        for uid in sorted(newset - oldset):
            append_jsonl(outdir / "changes.jsonl", {
                "timestamp": ts, "type": "ban_added",
                "server_id": server.server_id, "unique_id": uid
            })
        for uid in sorted(oldset - newset):
            append_jsonl(outdir / "changes.jsonl", {
                "timestamp": ts, "type": "ban_removed",
                "server_id": server.server_id, "unique_id": uid
            })
        atomic_write_json(cur_path, {
            "server_id": server.server_id,
            "updated_at": ts,
            "banned_ids": sorted(newset),
            "total_bans": len(newset)
        })

    def apply_ban_flags_from_snapshots(self):
        for s in self.servers:
            p = self.data_root / "servers" / s.server_id / "bans" / "current_bans.json"
            cur = load_json(p, {"banned_ids": []})
            banned = set(cur.get("banned_ids", []))
            for uid, pids in self.players.by_uid.items():
                for pid in pids:
                    self.players.set_ban_state(pid, s.server_id, uid in banned)


    def reconcile_rcon_player_links(self):
        """
        Link every RCON IP hash (successful OR failed, on every indexed server)
        to any player ever observed on that same stable IP hash.

        This is deliberately rebuilt after historical archives are processed so
        an older player connection can retroactively correlate with newer RCON data,
        and vice versa. Shared IP/hash correlation is evidence of association only;
        it is not proof that the player generated the RCON traffic.
        """
        hash_players = defaultdict(list)

        for pdir in self.players.records.iterdir() if self.players.records.exists() else []:
            if not pdir.is_dir():
                continue
            player = load_json(pdir / "player.json", {})
            pid = player.get("product_id")
            if not pid:
                continue

            ips = load_json(pdir / "ips.json", {"ips": {}}).get("ips", {})
            rec = {
                "product_id": pid,
                "unique_id": player.get("unique_id"),
                "player_name": player.get("current_name"),
            }
            for ih in ips:
                if rec not in hash_players[ih]:
                    hash_players[ih].append(rec)

        servers_root = self.data_root / "servers"
        if not servers_root.exists():
            return

        for rcon_dir in sorted(servers_root.glob("*/rcon")):
            if not rcon_dir.is_dir():
                continue

            for filename in ("known_hosts.json", "failed_hosts.json"):
                path = rcon_dir / filename
                hosts = load_json(path, {})
                if not isinstance(hosts, dict) or not hosts:
                    continue

                changed = False
                for ih, host in hosts.items():
                    if not isinstance(host, dict):
                        continue
                    arr = host.setdefault("players_seen_on_ip", [])
                    for rec in hash_players.get(ih, []):
                        if rec not in arr:
                            arr.append(rec)
                            changed = True

                if changed:
                    atomic_write_json(path, hosts)

    # --------------------- systemd service metadata ----------------------

    @staticmethod
    def _systemctl_value(unit: str, prop: str) -> str:
        try:
            p = subprocess.run(
                ["systemctl", "show", unit, "-p", prop, "--value", "--no-pager"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=5,
                check=False,
            )
            return p.stdout.strip()
        except Exception:
            return ""

    def collect_systemd_service_metadata(self, server: ServerCfg) -> None:
        """
        Discover the systemd service associated with this Pavlov server path.

        The mapping is informational and is safe for normal collector output:
        it stores local service/path information but no passwords or raw IPs.
        """
        server_root = server.server_root.resolve()
        out = self.data_root / "servers" / server.server_id / "server" / "service.json"
        out.parent.mkdir(parents=True, exist_ok=True)

        matches: list[dict[str, Any]] = []

        try:
            p = subprocess.run(
                [
                    "systemctl",
                    "list-unit-files",
                    "--type=service",
                    "--no-legend",
                    "--no-pager",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=15,
                check=False,
            )
            units = [
                line.split()[0]
                for line in p.stdout.splitlines()
                if line.strip() and line.split()
            ]
        except Exception as e:
            atomic_write_json(out, {
                "server_id": server.server_id,
                "server_path": str(server_root),
                "detected_at": now_iso(),
                "service": None,
                "matches": [],
                "error": f"systemctl discovery failed: {type(e).__name__}: {e}",
            })
            return

        target = str(server_root)

        for unit in units:
            try:
                q = subprocess.run(
                    [
                        "systemctl",
                        "show",
                        unit,
                        "-p", "WorkingDirectory",
                        "-p", "ExecStart",
                        "-p", "FragmentPath",
                        "--no-pager",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=3,
                    check=False,
                )
                info = q.stdout
            except Exception:
                continue

            if target not in info:
                continue

            working_directory = self._systemctl_value(unit, "WorkingDirectory")
            exec_start = self._systemctl_value(unit, "ExecStart")
            fragment_path = self._systemctl_value(unit, "FragmentPath")
            active_state = self._systemctl_value(unit, "ActiveState")
            unit_file_state = self._systemctl_value(unit, "UnitFileState")

            matches.append({
                "service": unit,
                "working_directory": working_directory or None,
                "exec_start": exec_start or None,
                "fragment_path": fragment_path or None,
                "active_state": active_state or None,
                "unit_file_state": unit_file_state or None,
            })

        service = matches[0]["service"] if len(matches) == 1 else None

        commands = {}
        if service:
            commands = {
                "status": f"sudo systemctl status {service} --no-pager",
                "start": f"sudo systemctl start {service}",
                "stop": f"sudo systemctl stop {service}",
                "restart": f"sudo systemctl restart {service}",
                "enable": f"sudo systemctl enable {service}",
                "disable": f"sudo systemctl disable {service}",
                "enable_now": f"sudo systemctl enable --now {service}",
                "disable_now": f"sudo systemctl disable --now {service}",
                "logs": f"sudo journalctl -u {service} -n 100 --no-pager",
                "logs_live": f"sudo journalctl -u {service} -f",
                "is_active": f"systemctl is-active {service}",
                "is_enabled": f"systemctl is-enabled {service}",
            }

        atomic_write_json(out, {
            "server_id": server.server_id,
            "server_path": str(server_root),
            "detected_at": now_iso(),
            "service": service,
            "match_count": len(matches),
            "matches": matches,
            "commands": commands,
            "note": (
                None
                if len(matches) == 1
                else "No unique service match; zero or multiple services reference the server path."
            ),
        })

    # --------------------- platform / Game.ini ---------------------------

    def detect_platform(
        self,
        server: ServerCfg,
        log_files: Optional[list[Path]] = None,
    ) -> str:
        if server.platform_override in {"SHACK", "PCVR"}:
            return server.platform_override

        if log_files is None:
            log_files = []
            try:
                if server.log_path.exists():
                    log_files = sorted(
                        server.log_path.glob("*.log"),
                        key=lambda p: p.stat().st_mtime,
                    )
            except OSError:
                log_files = []

        for p in reversed(log_files):
            try:
                with p.open("r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if "PavlovLog: SHACK SERVER BUILD" in line:
                            return "SHACK"
            except OSError:
                continue

        return "PCVR"

    @staticmethod
    def _parse_ini_scalar(value: str) -> Any:
        value = value.strip()
        low = value.casefold()
        if low == "true":
            return True
        if low == "false":
            return False
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            return value

    @staticmethod
    def _server_name_tokens(value: Any) -> set[str]:
        return set(re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).split())

    def _match_pavlov_api_server(self, server_name: str | None, rotations: list[dict], platform: str | None) -> dict[str, Any] | None:
        api_doc = load_json(self.data_root / "global" / "pavlov_api" / "servers.json", [])
        if isinstance(api_doc, dict):
            api_rows = api_doc.get("servers") if isinstance(api_doc.get("servers"), list) else list(api_doc.values())
        else:
            api_rows = api_doc if isinstance(api_doc, list) else []
        wanted_words = self._server_name_tokens(server_name)
        wanted_maps = {str(x.get("map_id") or "").casefold() for x in rotations if isinstance(x, dict)}
        best_score = 0
        best = None
        for row in api_rows:
            if not isinstance(row, dict):
                continue
            score = 0
            api_words = self._server_name_tokens(row.get("name"))
            if wanted_words and api_words:
                overlap = len(wanted_words & api_words)
                score += overlap * 10
                if wanted_words == api_words:
                    score += 100
            if str(row.get("map_id") or "").casefold() in wanted_maps:
                score += 35
            stype = str(row.get("server_type") or "").upper()
            p = str(platform or "").upper()
            if (p == "PCVR" and "PCVR" in stype) or (p == "SHACK" and "SHACK" in stype):
                score += 20
            if score > best_score:
                best_score, best = score, row
        return dict(best) if best is not None and best_score >= 35 else None

    def collect_rcon_settings(self, server: ServerCfg) -> dict[str, Any]:
        path = server.config_dir / "RconSettings.txt"
        result: dict[str, Any] = {"source": str(path), "port": None, "password_file": None, "settings": {}}
        if not path.exists():
            return result
        password = None
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith(";") or "=" not in line:
                continue
            key, value = (x.strip() for x in line.split("=", 1))
            low = key.casefold()
            if low in {"password", "rconpassword", "rcon_password"}:
                password = value
            elif low in {"port", "rconport", "rcon_port"}:
                try:
                    result["port"] = int(value)
                except ValueError:
                    pass
            else:
                result["settings"][key] = self._parse_ini_scalar(value)
        private_dir = self.data_root / "servers" / server.server_id / "private"
        private_dir.mkdir(parents=True, exist_ok=True)
        try:
            private_dir.chmod(0o700)
        except OSError:
            pass
        if password is not None:
            password_path = private_dir / "rconPassword.txt"
            password_path.write_text(password + "\n", encoding="utf-8")
            try:
                password_path.chmod(0o600)
            except OSError:
                pass
            result["password_file"] = "private/rconPassword.txt"
        return result

    def collect_game_ini(self, server: ServerCfg):
        path = server.game_ini_path
        if not path or not path.exists():
            return

        server_name = None
        verbose = None
        tick = None
        rotations: list[dict] = []
        mods: list[dict] = []
        settings: dict[str, Any] = {}
        repeated: dict[str, list[Any]] = defaultdict(list)
        secret_keys = {"apikey", "api_key", "password", "token", "secret", "rconpassword", "rcon_password"}

        with path.open("r", encoding="utf-8", errors="replace") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or line.startswith(";"):
                    continue
                if line.startswith("[") and line.endswith("]"):
                    continue
                if "=" not in line:
                    continue
                key, value = (x.strip() for x in line.split("=", 1))
                if key.casefold() in secret_keys:
                    continue
                if key == "ServerName":
                    server_name = value
                elif key == "bVerboseLogging":
                    verbose = normalize_bool(value)
                elif key == "TickRate":
                    try:
                        tick = int(value)
                    except ValueError:
                        pass
                if key == "MapRotation":
                    mm = re.search(r'MapId\s*=\s*"([^"]+)"', value, re.I)
                    gm = re.search(r'GameMode\s*=\s*"([^"]+)"', value, re.I)
                    if mm:
                        map_id = mm.group(1)
                        rec = {"map_id": map_id, "game_mode": gm.group(1) if gm else None}
                        ugc = UGC_RE.match(map_id)
                        if ugc:
                            rec["modio_id"] = int(ugc.group(1))
                            rec["modio"] = self.enricher.modio(map_id)
                        rotations.append(rec)
                    continue
                if key == "AdditionalMods":
                    m = UGC_RE.match(value)
                    rec = {"ugc_id": value}
                    if m:
                        rec["modio_id"] = int(m.group(1))
                        rec["modio"] = self.enricher.modio(value)
                    mods.append(rec)
                    continue
                parsed = self._parse_ini_scalar(value)
                if key in settings:
                    if not repeated[key]:
                        repeated[key].append(settings.pop(key))
                    repeated[key].append(parsed)
                elif repeated[key]:
                    repeated[key].append(parsed)
                else:
                    settings[key] = parsed
        for key, values in repeated.items():
            settings[key] = values
        settings["MapRotation"] = rotations
        if mods:
            settings["AdditionalMods"] = mods

        game_ini_doc = {
            "server_id": server.server_id,
            "source": str(path),
            "updated_at": now_iso(),
            "server_name": server_name,
            "verbose_logging": verbose,
            "tick_rate": tick,
            "map_rotation": rotations,
            "additional_mods": mods,
            "settings": settings,
        }
        outdir = self.data_root / "servers" / server.server_id
        outdir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(outdir / "game_ini.json", game_ini_doc)

        # Enrich server.json while preserving manually maintained fields such as URL.
        server_json_path = outdir / "server.json"
        server_doc = load_json(server_json_path, {})
        if not isinstance(server_doc, dict):
            server_doc = {}
        platform = self.detect_platform(server)
        server_doc.update({
            "server_id": server.server_id,
            "platform": platform,
            "server_name": server_name,
            "game_ini": settings,
            "game_ini_source": str(path),
            "rcon": self.collect_rcon_settings(server),
            "pavlov_api": self._match_pavlov_api_server(server_name, rotations, platform),
            "metadata_updated_at": now_iso(),
        })
        atomic_write_json(server_json_path, server_doc)

        map_catalog = {"server_id": server.server_id, "updated_at": now_iso(), "maps": {}}
        for rec in rotations:
            map_id = rec.get("map_id")
            if not map_id:
                continue
            map_catalog["maps"][map_id] = rec
        atomic_write_json(outdir / "maps.json", map_catalog)


    def reset_identity_data(self) -> dict[str, int]:
        """Clear derived identity/name data while preserving stats and moderation data."""
        players_reset = 0
        for pdir in self.players.records.iterdir() if self.players.records.is_dir() else []:
            if not pdir.is_dir():
                continue
            player_path = pdir / "player.json"
            player = load_json(player_path, {})
            if not isinstance(player, dict):
                continue
            player["current_name"] = None
            player["unique_id"] = None
            player["platform"] = None
            player["first_seen"] = None
            player["last_seen"] = None
            player["servers_seen"] = []

            # Steam links are identity-derived and are rebuilt from authoritative
            # PCVR records. Discord/profile links are intentionally preserved.
            linked = player.setdefault("linked_accounts", {})
            if isinstance(linked, dict):
                linked["steam"] = None

            atomic_write_json(player_path, player)
            try:
                (pdir / "names.json").unlink(missing_ok=True)
            except OSError:
                pass
            players_reset += 1

        self.players.by_name = {}
        self.players.by_uid = {}
        self.players.by_pid = {}
        self.players.by_steam_id = {}
        self.players.flush_indexes()
        return {"players_reset": players_reset}

    def process_stats_identity_only(self, server: ServerCfg, platform: str, path: Path) -> int:
        """Learn only authoritative identity mappings from Stats allStats."""
        learned = 0
        for ts, obj in iter_stats_records(path):
            for p in obj.get("allStats") or []:
                product_id = str(p.get("productId") or "").strip().lower()
                if not re.fullmatch(r"[0-9a-f]{32}", product_id):
                    continue
                unique_id = str(p.get("uniqueId") or "").strip() or None
                name = str(p.get("playerName") or "").strip() or unique_id
                self.players.learn_identity(
                    product_id, unique_id, name, platform, ts, server.server_id
                )
                learned += 1
        return learned

    def process_pavlov_identity_only(self, server: ServerCfg, platform: str, path: Path) -> int:
        """Learn identity from login lines without replaying connection side effects.

        A login line that contains userId gives us the EOS ProductID, pid gives us
        the PCVR SteamID/UniqueID, and Name is metadata for that exact session.
        No connection counters, IP counters, RCON events, HTTP events, or session
        files are changed by this pass.
        """
        learned = 0
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                m = TS_RE.match(raw.rstrip("\n"))
                if not m:
                    continue
                ts = m.group("ts")
                body = m.group("body").strip()
                if "LogNet: Login request:" not in body:
                    continue

                name = self.query_field(body, "Name") or self.query_field(body, "name")
                unique_id = self.query_field(body, "pid")
                um = re.search(r"\buserId:\s*([^\s]+)", body)
                network_user_id = um.group(1) if um else None
                product_id = self.product_id_from_network_user_id(network_user_id)
                if not product_id:
                    continue

                self.players.learn_identity(
                    product_id,
                    unique_id or name,
                    name,
                    platform,
                    ts,
                    server.server_id,
                )
                learned += 1
        return learned

    def rebuild_identities_from_archives(
        self,
        archives: dict[str, tuple[list[Path], list[Path]]],
        servers: list[ServerCfg],
    ) -> dict[str, int]:
        """Rebuild identity/name indexes from authoritative historical evidence.

        This intentionally ignores ProcessingState and does not mark files. It is
        an identity-only pass, so existing connection/combat/IP counts are not
        replayed or doubled.
        """
        reset = self.reset_identity_data()
        stats_rows = 0
        login_rows = 0

        # Stats productId mappings are explicit and safe to learn first.
        for server in servers:
            log_files, stat_files = archives.get(server.server_id, ([], []))
            platform = self.detect_platform(server, log_files)
            for path in stat_files:
                stats_rows += self.process_stats_identity_only(server, platform, path)

        # Then add exact-session login mappings where userId explicitly supplies
        # the EOS ProductID. Names never select the destination ProductID here.
        for server in servers:
            log_files, _ = archives.get(server.server_id, ([], []))
            platform = self.detect_platform(server, log_files)
            for path in log_files:
                login_rows += self.process_pavlov_identity_only(server, platform, path)

        self.players.flush_indexes()
        rebuilt = self.players.rebuild_indexes_from_records()
        return {
            **reset,
            "stats_identity_rows": stats_rows,
            "login_identity_rows": login_rows,
            "valid_players": int(rebuilt.get("valid_players", 0)),
            "name_entries": int(rebuilt.get("name_entries", 0)),
            "unique_id_entries": int(rebuilt.get("unique_id_entries", 0)),
            "steam_id_entries": int(rebuilt.get("steam_id_entries", 0)),
        }

    def reset_connection_data(self, servers: list[ServerCfg]) -> dict[str, int]:
        """Reset only derived player connection/IP activity.

        Combat, badges, bans, moderation data, Discord links, names, and identity
        mappings are preserved. The rebuilt connection pass repopulates only data
        that can be tied to explicit EOS login IDs and/or explicit anti-cheat
        SteamID+IP evidence.
        """
        players_reset = 0
        records_root = self.players.records

        if records_root.is_dir():
            for pdir in records_root.iterdir():
                if not pdir.is_dir():
                    continue

                for filename in ("ips.json", "connections.jsonl"):
                    try:
                        (pdir / filename).unlink(missing_ok=True)
                    except OSError:
                        pass

                player_path = pdir / "player.json"
                player = load_json(player_path, {})
                if isinstance(player, dict):
                    net = player.setdefault("network", {})
                    net["current_ip_hash"] = None
                    net["known_ip_count"] = 0
                    net["current_background"] = None
                    atomic_write_json(player_path, player)

                stats_path = pdir / "stats.json"
                stats = load_json(stats_path, {"product_id": pdir.name})
                if isinstance(stats, dict):
                    activity = stats.setdefault("activity", {})
                    activity["times_connected"] = 0
                    # Completed durations are rebuilt only from safely bound
                    # endpoint sessions. Until then, reset them rather than keep
                    # contaminated totals.
                    activity["total_time_online_seconds"] = 0
                    activity["total_time_online_formatted"] = "0s"
                    atomic_write_json(stats_path, stats)

                players_reset += 1

        self.players.by_ip_hash = {}
        self.players.private_ips = {}
        self.players.flush_indexes()

        unresolved_removed = 0
        for server in servers:
            p = (
                self.data_root
                / "servers"
                / server.server_id
                / "connections"
                / "unresolved.jsonl"
            )
            try:
                if p.exists():
                    p.unlink()
                    unresolved_removed += 1
            except OSError:
                pass

        return {
            "players_reset": players_reset,
            "unresolved_files_removed": unresolved_removed,
        }

    @staticmethod
    def extract_anticheat_steam_ip(body: str) -> Optional[tuple[str, str]]:
        """Extract an explicit SteamID64 + IPv4 pair from an anti-cheat line.

        Historical Pavlov logs have used several anti-cheat text formats, so the
        parser intentionally keys on the evidence itself rather than one exact
        prefix. A line must contain "Anti-cheat", one SteamID64-looking value,
        and one IPv4 address.
        """
        if "anti-cheat" not in body.casefold():
            return None

        steam = re.search(r"\b(7656119\d{10})\b", body)
        ip = re.search(r"\b((?:\d{1,3}\.){3}\d{1,3})\b", body)
        if not steam or not ip:
            return None

        try:
            ipaddress.ip_address(ip.group(1))
        except ValueError:
            return None

        return steam.group(1), ip.group(1)

    def build_explicit_steam_product_map(
        self,
        archives: dict[str, tuple[list[Path], list[Path]]],
        servers: list[ServerCfg],
    ) -> tuple[dict[str, str], set[str], int]:
        """Build SteamID64 -> EOS ProductID only from explicit login lines.

        If the same SteamID is explicitly observed with more than one EOS
        ProductID, it is considered ambiguous and excluded from IP attribution.
        """
        candidates: dict[str, set[str]] = defaultdict(set)
        login_rows = 0

        all_logs: list[tuple[ServerCfg, Path]] = []
        for server in servers:
            log_files, _ = archives.get(server.server_id, ([], []))
            for path in log_files:
                all_logs.append((server, path))

        total = len(all_logs)
        for idx, (server, path) in enumerate(all_logs, 1):
            print(
                f"\r[CONNECTION REBUILD][MAP] {idx:,}/{total:,} "
                f"{server.server_id}: {path.name[:80]}",
                end="",
                flush=True,
            )
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for raw in handle:
                    m = TS_RE.match(raw.rstrip("\n"))
                    if not m:
                        continue
                    body = m.group("body").strip()
                    if "LogNet: Login request:" not in body:
                        continue

                    um = re.search(r"\buserId:\s*([^\s]+)", body)
                    product_id = self.product_id_from_network_user_id(
                        um.group(1) if um else None
                    )
                    steam_id = self.query_field(body, "pid")
                    if (
                        product_id
                        and steam_id
                        and re.fullmatch(r"7656119\d{10}", steam_id)
                    ):
                        candidates[steam_id].add(product_id)
                        login_rows += 1

        if total:
            print(flush=True)

        ambiguous = {
            steam_id
            for steam_id, product_ids in candidates.items()
            if len(product_ids) != 1
        }
        resolved = {
            steam_id: next(iter(product_ids))
            for steam_id, product_ids in candidates.items()
            if len(product_ids) == 1
        }
        return resolved, ambiguous, login_rows

    @staticmethod
    def extract_authenticated_connection_identity(
        body: str,
    ) -> Optional[tuple[str, int, Optional[str], str]]:
        """Extract an authoritative IP/port/connection/ProductID close record.

        Pavlov writes the remote endpoint and authenticated EOS ProductID on the
        same UNetConnection/UChannel cleanup/close line, for example:

            RemoteAddr: 1.2.3.4:54321,
            Name: IpConnection_123,
            ...
            UniqueId: NULL:<32-char EOS ProductID>

        This is stronger evidence than name matching, pending-connection order,
        or Anti-cheat correlation because IP and ProductID are present together
        in the same connection record.
        """
        close_markers = (
            "UChannel::CleanUp:",
            "UChannel::Cleanup:",
            "UNetConnection::Cleanup:",
            "UNetConnection::Close:",
            "UChannel::Close:",
            "UNetConnection::PendingConnectionLost",
        )
        if not any(marker in body for marker in close_markers):
            return None
        if "RemoteAddr:" not in body or "UniqueId:" not in body:
            return None

        epm = IP_PORT_RE.search(body)
        if not epm:
            return None

        ip = epm.group("ip")
        port = int(epm.group("port"))
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            return None

        pm = re.search(
            r"\bUniqueId:\s*(?:NULL:)?([0-9a-fA-F]{32})\b",
            body,
        )
        if not pm:
            return None

        cm = CONNECTION_NAME_RE.search(body)
        connection_name = cm.group(1) if cm else None
        product_id = pm.group(1).lower()
        return ip, port, connection_name, product_id

    def rebuild_connections_from_archives(
        self,
        archives: dict[str, tuple[list[Path], list[Path]]],
        servers: list[ServerCfg],
    ) -> dict[str, int]:
        """Rebuild connection/IP data from authenticated connection lifecycles.

        Primary authoritative evidence is a cleanup/close line that contains,
        on the SAME log record:

          * RemoteAddr: IPv4:port
          * Name: IpConnection_N (when available)
          * UniqueId: NULL:<32-char EOS ProductID>

        This works with the old 2022 connection format and newer SHACK logs and
        does not require Anti-cheat output.

        Rules:
          * A connection is counted only once per authenticated connection
            lifecycle, even though Pavlov may emit CleanUp, Close,
            UChannel::Close, and PendingConnectionLost for the same disconnect.
          * IP -> ProductID attribution comes only from the same authenticated
            close/cleanup record.
          * Names NEVER select the ProductID.
          * Login request data is metadata only and does not increment the
            connection counter.
          * Duration is written only when the matching AddClientConnection start
            can be found in the same log stream.
          * Duplicate/overlapping archive copies are deduplicated globally by
            server + endpoint + connection name + ProductID + close time.

        Combat, badges, bans, moderation data, Discord links, and identity/name
        history are not reset by this rebuild.
        """
        reset = self.reset_connection_data(servers)

        authoritative_connections = 0
        ip_observations = 0
        sessions_written = 0
        sessions_without_start = 0
        duplicate_close_lines = 0
        malformed_authenticated_closes = 0
        login_metadata_rows = 0

        all_logs: list[tuple[ServerCfg, str, Path]] = []
        for server in servers:
            log_files, _ = archives.get(server.server_id, ([], []))
            platform = self.detect_platform(server, log_files)
            for path in log_files:
                all_logs.append((server, platform, path))

        total_files = len(all_logs)

        # Keep recent authoritative close events across files too, because old
        # archives can contain overlapping/copy-equivalent log material.
        # key -> datetime of most recent accepted close.
        last_close_seen: dict[
            tuple[str, str, str, str],
            datetime,
        ] = {}

        for file_index, (server, platform, path) in enumerate(all_logs, 1):
            print(
                f"\r[CONNECTION REBUILD][LIFECYCLE] "
                f"{file_index:,}/{total_files:,} "
                f"{server.server_id}: {path.name[:80]}",
                end="",
                flush=True,
            )

            by_endpoint: dict[str, NetSession] = {}
            by_conn: dict[str, NetSession] = {}

            # Login information is safe metadata because product_id is read
            # explicitly from userId. It is never used to redirect a connection
            # to a ProductID.
            login_meta_by_pid: dict[str, dict[str, Any]] = {}

            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for raw in handle:
                    m = TS_RE.match(raw.rstrip("\n"))
                    if not m:
                        continue

                    ts = m.group("ts")
                    body = m.group("body").strip()

                    # Track the beginning of the exact network lifecycle.
                    if "AddClientConnection: Added client connection:" in body:
                        epm = IP_PORT_RE.search(body)
                        if epm:
                            ip = epm.group("ip")
                            port = int(epm.group("port"))
                            endpoint = f"{ip}:{port}"
                            cm = CONNECTION_NAME_RE.search(body)
                            sess = NetSession(
                                endpoint=endpoint,
                                ip=ip,
                                port=port,
                                connection_name=(
                                    cm.group(1) if cm else None
                                ),
                                started_at=ts,
                            )
                            by_endpoint[endpoint] = sess
                            if sess.connection_name:
                                by_conn[sess.connection_name] = sess
                        continue

                    # Capture explicit identity metadata, but do NOT count a
                    # connection here. The authenticated network lifecycle close
                    # is what proves IP ownership and counts the connection.
                    if "LogNet: Login request:" in body:
                        um = re.search(r"\buserId:\s*([^\s]+)", body)
                        network_user_id = um.group(1) if um else None
                        product_id = self.product_id_from_network_user_id(
                            network_user_id
                        )
                        if product_id:
                            login_metadata_rows += 1
                            login_meta_by_pid[product_id] = {
                                "player_name": (
                                    self.query_field(body, "Name")
                                    or self.query_field(body, "name")
                                ),
                                "unique_id": self.query_field(body, "pid"),
                                "network_user_id": network_user_id,
                                "login_at": ts,
                                "player_height": self.float_or_none(
                                    self.query_field(body, "playerHeight")
                                ),
                                "right_handed": normalize_bool(
                                    self.query_field(body, "rightHanded")
                                ),
                                "vstock": normalize_bool(
                                    self.query_field(body, "vstock")
                                ),
                                "client_platform": self.query_field(
                                    body, "platform"
                                ),
                            }
                        continue

                    auth = self.extract_authenticated_connection_identity(body)
                    if not auth:
                        # Count lines that look authenticated but do not contain
                        # a normal EOS ProductID so they can be reviewed later.
                        if (
                            "RemoteAddr:" in body
                            and "UniqueId:" in body
                            and any(
                                x in body
                                for x in (
                                    "UChannel::CleanUp:",
                                    "UChannel::Cleanup:",
                                    "UNetConnection::Cleanup:",
                                    "UNetConnection::Close:",
                                    "UChannel::Close:",
                                    "UNetConnection::PendingConnectionLost",
                                )
                            )
                            and "UniqueId: INVALID" not in body
                        ):
                            malformed_authenticated_closes += 1
                        continue

                    ip, port, connection_name, product_id = auth
                    endpoint = f"{ip}:{port}"

                    # Pavlov emits several close records for one disconnect. The
                    # exact same lifecycle is accepted only once. A short
                    # two-second window also handles neighboring close records
                    # whose timestamps differ by a few milliseconds.
                    dedupe_key = (
                        server.server_id,
                        endpoint,
                        connection_name or "",
                        product_id,
                    )
                    close_dt = parse_ts(ts)
                    previous_dt = last_close_seen.get(dedupe_key)
                    if (
                        close_dt is not None
                        and previous_dt is not None
                        and abs((close_dt - previous_dt).total_seconds()) <= 2.0
                    ):
                        duplicate_close_lines += 1
                        continue

                    if close_dt is not None:
                        last_close_seen[dedupe_key] = close_dt

                    # Find the original AddClientConnection by the strongest
                    # available key: connection name first, then exact endpoint.
                    sess = (
                        by_conn.get(connection_name)
                        if connection_name
                        else None
                    )
                    if sess is None:
                        sess = by_endpoint.get(endpoint)

                    if sess is None:
                        # The archive may begin after the connection was
                        # accepted, or the start may live in another rotated
                        # file. We can still safely count/IP-attribute this
                        # authenticated close, but we cannot claim a duration.
                        sess = NetSession(
                            endpoint=endpoint,
                            ip=ip,
                            port=port,
                            connection_name=connection_name,
                            started_at=ts,
                        )
                        sessions_without_start += 1

                    sess.product_id = product_id
                    sess.disconnected_at = ts

                    meta = login_meta_by_pid.get(product_id)
                    if meta:
                        sess.player_name = meta.get("player_name")
                        sess.unique_id = meta.get("unique_id")
                        sess.network_user_id = meta.get("network_user_id")
                        sess.login_at = meta.get("login_at")
                        sess.player_height = meta.get("player_height")
                        sess.right_handed = meta.get("right_handed")
                        sess.vstock = meta.get("vstock")
                        sess.client_platform = meta.get("client_platform")

                    # Count exactly once here: the authenticated close is the
                    # authoritative connection event.
                    self.players.increment_connection(product_id)
                    authoritative_connections += 1

                    ih, _ = self.players.observe_player_ip(
                        product_id,
                        ip,
                        ts,
                        server.server_id,
                    )
                    sess.enriched_ip_hash = ih
                    ip_observations += 1

                    # Only write a timed session if an actual earlier connection
                    # start was found. A close-only record remains valid for
                    # connection count and IP attribution but contributes no
                    # fabricated online duration.
                    if sess.started_at != ts:
                        self.write_connection_session(
                            server.server_id,
                            platform,
                            sess,
                        )
                        sessions_written += 1

                    # Retire this open lifecycle so later cleanup/close records
                    # cannot accidentally match it again.
                    by_endpoint.pop(endpoint, None)
                    if connection_name:
                        by_conn.pop(connection_name, None)

        if total_files:
            print(flush=True)

        # Total time online is rebuilt only from safely paired start/end
        # connection sessions.
        time_result = self.players.rebuild_total_time_online()

        # Rebuild global IP correlation from the newly reconstructed ips.json
        # files while preserving all identity/name/Discord/Steam indexes.
        index_result = self.players.rebuild_indexes_from_records()

        return {
            **reset,
            "authoritative_connections": authoritative_connections,
            "login_metadata_rows": login_metadata_rows,
            "ip_observations": ip_observations,
            "sessions_written": sessions_written,
            "sessions_without_start": sessions_without_start,
            "duplicate_close_lines_skipped": duplicate_close_lines,
            "malformed_authenticated_closes": malformed_authenticated_closes,
            "time_sessions_counted": int(
                time_result.get("sessions_counted", 0)
            ),
            "ip_hash_entries": int(index_result.get("ip_hash_entries", 0)),
        }

    def process_stats_identity_and_rounds(self, server: ServerCfg, platform: str, path: Path):
        for ts, obj in iter_stats_records(path):
            if "allStats" not in obj:
                continue
            players = obj.get("allStats") or []
            round_doc = {
                "server_id": server.server_id,
                "timestamp": ts,
                "map": {"label": obj.get("MapLabel")},
                "game_mode": obj.get("GameMode"),
                "match_duration": obj.get("MatchDuration"),
                "player_count": obj.get("PlayerCount"),
                "teams_enabled": obj.get("bTeams"),
                "teams": {
                    "0": {"score": obj.get("Team0Score")},
                    "1": {"score": obj.get("Team1Score")}
                },
                "players": []
            }
            for p in players:
                pid = str(p.get("productId") or "").strip()
                if not pid:
                    continue
                uid = str(p.get("uniqueId") or "").strip() or None
                name = str(p.get("playerName") or "").strip() or uid
                self.players.learn_identity(pid, uid, name, platform, ts, server.server_id)
                self.players.increment_match(pid)
                statmap = {}
                for e in p.get("stats") or []:
                    if e.get("statType") is not None:
                        statmap[str(e["statType"])] = e.get("amount")
                pp = {
                    "unique_id": uid,
                    "product_id": pid,
                    "player_name": name,
                    "team_id": p.get("teamId"),
                    "stats": statmap
                }
                round_doc["players"].append(pp)
                append_jsonl(self.players.player_dir(pid) / "matches.jsonl", {
                    "timestamp": ts,
                    "server_id": server.server_id,
                    "map_label": obj.get("MapLabel"),
                    "game_mode": obj.get("GameMode"),
                    "match_duration": obj.get("MatchDuration"),
                    "player_count": obj.get("PlayerCount"),
                    "team_id": p.get("teamId"),
                    "team_score": obj.get(f"Team{p.get('teamId')}Score") if p.get("teamId") in (0, 1) else None,
                    "stats": statmap
                })

            fname = (
                f"{server.server_id}-{safe_name(ts)}-"
                f"{safe_name(str(obj.get('MapLabel') or 'unknown'))}-"
                f"{safe_name(str(obj.get('GameMode') or 'unknown'))}-"
                f"{obj.get('PlayerCount', len(players))}.json"
            )
            atomic_write_json(self.data_root / "servers" / server.server_id / "rounds" / fname, round_doc)

    def reset_pavlov_combat_data(self) -> None:
        """Reset only combat-derived data before an explicit full rebuild.

        Connection counts, matches, identities, names, IP history, preferences,
        admin state, bans, and other collector data are preserved.
        """
        print("Resetting combat-derived data for Pavlov-log rebuild ...", flush=True)
        players_reset = 0

        for pdir in self.players.records.iterdir():
            if not pdir.is_dir():
                continue

            for name in ("kills.jsonl", "deaths.jsonl", "weapons.json"):
                try:
                    (pdir / name).unlink(missing_ok=True)
                except OSError:
                    pass

            stats_path = pdir / "stats.json"
            if not stats_path.is_file():
                continue

            stats = load_json(stats_path, None)
            if not isinstance(stats, dict):
                continue

            stats["combat"] = {
                "kills": 0,
                "deaths": 0,
                "headshots": 0,
                "suicides": 0,
                "teamkills": 0,
                "deaths_from_teamkills": 0,
                "bot_kills": 0,
                "bot_headshots": 0,
                "deaths_by_bots": 0,
                "kills_unverified_team_relation": 0,
            }
            stats["weapons"] = {
                "favorite": None,
                "favorite_kills": 0,
            }
            stats["combat_source"] = "pavlov_log"
            atomic_write_json(stats_path, stats)
            players_reset += 1

        servers_root = self.data_root / "servers"
        if servers_root.exists():
            for p in servers_root.glob("*/stats/bots/events.jsonl"):
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    pass
            for p in servers_root.glob("*/stats/combat/*.jsonl"):
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    pass

        state_path = self.data_root / "global" / "pavlov_combat_state.json"
        try:
            state_path.unlink(missing_ok=True)
        except OSError:
            pass

        print(f"Combat reset complete: {players_reset:,} player stats files reset.", flush=True)

    def resolve_kill_identity(self, platform: str, raw_id: str) -> Optional[str]:
        """Resolve a KillData participant to the collector's product_id.

        PCVR KillData commonly carries SteamID64 / UniqueID values.
        SHACK KillData uses the player's name as its UniqueID, so the same raw
        value is checked against both the UniqueID and name indexes.
        """
        value = str(raw_id or "").strip()
        if not value:
            return None

        # A product_id can occasionally be emitted directly by custom tooling.
        if value in self.players.by_pid:
            return value
        lower_value = value.lower()
        if lower_value in self.players.by_pid:
            return lower_value

        p = str(platform or "").upper()

        if p == "PCVR":
            steam_pid = self.players.by_steam_id.get(value)
            if steam_pid:
                return steam_pid
            return (
                self.players.resolve(unique_id=value)
                or self.players.resolve(name=value)
            )

        if p == "SHACK":
            # On Shack the game-side UniqueID is the player's name.
            return self.players.resolve(name=value, unique_id=value)

        return (
            self.players.resolve(unique_id=value)
            or self.players.resolve(name=value)
        )

    def _kill_participant(self, platform: str, raw_id: str) -> dict[str, Any]:
        value = str(raw_id or "").strip()
        if not value:
            return {
                "raw_id": None,
                "product_id": None,
                "unique_id": None,
                "name": None,
                "type": "bot",
                "identity_status": "bot",
            }

        pid = self.resolve_kill_identity(platform, value)
        player = self.players.by_pid.get(pid, {}) if pid else {}
        if not isinstance(player, dict):
            player = {}

        p = str(platform or "").upper()
        if p == "SHACK":
            unique_id = value
            name = player.get("current_name") or value
        else:
            unique_id = player.get("unique_id") or value
            name = player.get("current_name")

        return {
            "raw_id": value,
            "product_id": pid,
            "unique_id": unique_id,
            "name": name,
            "type": "player" if pid else "unresolved",
            "identity_status": "resolved" if pid else "unresolved",
        }

    def process_pavlov_combat_all(
        self,
        archives: dict[str, tuple[list[Path], list[Path]]],
        servers: Optional[Iterable[ServerCfg]] = None,
    ) -> None:
        """Process KillData from Pavlov logs with a dedicated SHA-256 state.

        This state is intentionally separate from processing_state.json because
        existing Pavlov logs may already have been processed for connections/RCON
        before Pavlov-log combat tracking was introduced.
        """
        state_path = self.data_root / "global" / "pavlov_combat_state.json"
        state = load_json(state_path, {"processed": {}, "source": "pavlov_log"})
        if not isinstance(state, dict):
            state = {"processed": {}, "source": "pavlov_log"}
        processed = state.setdefault("processed", {})
        state["source"] = "pavlov_log"

        source_servers = list(servers) if servers is not None else self.servers
        files_seen = 0
        files_processed = 0
        events_processed = 0

        for server in source_servers:
            log_files, _ = archives.get(server.server_id, ([], []))
            platform = self.platforms.get(server.server_id) or self.detect_platform(server, log_files)

            for path in log_files:
                files_seen += 1
                h = sha256_file(path)
                if h in processed:
                    continue

                count = self.process_pavlov_combat(server, platform, path)
                events_processed += count
                files_processed += 1
                processed[h] = {
                    "path": str(path),
                    "processed_at": now_iso(),
                    "kill_events": count,
                }
                # Commit after every physical file.  A crash therefore cannot
                # cause that file's counters to be replayed on the next run.
                atomic_write_json(state_path, state)

        print(
            "Pavlov combat pass: "
            f"files_seen={files_seen:,} "
            f"files_processed={files_processed:,} "
            f"kill_events={events_processed:,}",
            flush=True,
        )

    def process_pavlov_combat(self, server: ServerCfg, platform: str, path: Path) -> int:
        count = 0
        for ts, obj in iter_pavlov_stat_records(path):
            kd = obj.get("KillData")
            if not isinstance(kd, dict):
                continue

            count += 1
            killer_raw = str(kd.get("Killer") or "").strip()
            victim_raw = str(kd.get("Killed") or "").strip()
            weapon = str(kd.get("KilledBy") or "None").strip() or "None"
            headshot = bool(kd.get("Headshot", False))
            killer_team = kd.get("KillerTeamID")
            victim_team = kd.get("KilledTeamID")

            killer = self._kill_participant(platform, killer_raw)
            victim = self._kill_participant(platform, victim_raw)
            killer_pid = killer.get("product_id")
            victim_pid = victim.get("product_id")
            killer_bot = killer.get("type") == "bot"
            victim_bot = victim.get("type") == "bot"
            killer_unresolved = killer.get("type") == "unresolved"
            victim_unresolved = victim.get("type") == "unresolved"

            suicide = bool(
                killer_raw
                and victim_raw
                and killer_raw == victim_raw
            )
            team_relation_known = (
                killer_team is not None
                and victim_team is not None
                and not suicide
                and not killer_bot
                and not victim_bot
            )
            teamkill = bool(team_relation_known and killer_team == victim_team)

            if killer_bot and victim_bot:
                classification = "bot_vs_bot"
            elif killer_bot and victim_pid:
                classification = "bot_killed_player"
            elif victim_bot and killer_pid:
                classification = "player_killed_bot"
            elif killer_unresolved or victim_unresolved:
                classification = "unresolved"
            elif suicide:
                classification = "suicide"
            elif teamkill:
                classification = "teamkill"
            elif team_relation_known:
                classification = "normal"
            else:
                classification = "normal_unverified_team_relation"

            killer["team_id"] = killer_team
            victim["team_id"] = victim_team

            event = {
                "timestamp": ts,
                "type": "kill",
                "source": "pavlov_log",
                "source_file": str(path),
                "server_id": server.server_id,
                "platform": platform,
                "killer": killer,
                "killed": victim,
                "weapon": weapon,
                "headshot": headshot,
                "classification": classification,
            }

            # Keep one server-wide event stream for auditing/rebuild verification.
            append_jsonl(
                self.data_root / "servers" / server.server_id / "stats" / "combat" / "events.jsonl",
                event,
            )

            if killer_bot or victim_bot:
                append_jsonl(
                    self.data_root / "servers" / server.server_id / "stats" / "bots" / "events.jsonl",
                    event,
                )

            if classification == "unresolved":
                append_jsonl(
                    self.data_root / "servers" / server.server_id / "stats" / "combat" / "unresolved.jsonl",
                    event,
                )

            if killer_pid:
                append_jsonl(self.players.player_dir(killer_pid) / "kills.jsonl", event)
            if victim_pid and victim_pid != killer_pid:
                append_jsonl(self.players.player_dir(victim_pid) / "deaths.jsonl", event)

            # Lifetime player counters.  PvP kills stay separate from bot kills.
            if suicide and killer_pid:
                self.players.combat(killer_pid, "suicides")
            elif teamkill and killer_pid:
                self.players.combat(killer_pid, "teamkills")

                server_tks = self.match_teamkills.setdefault(server.server_id, {})
                match_tks = int(server_tks.get(killer_pid, 0)) + 1
                server_tks[killer_pid] = match_tks

                if match_tks == TEAMKILL_BADGE_THRESHOLD:
                    self.players.award_badge(
                        killer_pid,
                        BADGE_TEAMKILLER,
                        ts,
                        awarded_by="collector",
                        reason=f"{TEAMKILL_BADGE_THRESHOLD} teamkills in a single match.",
                        metadata={
                            "server_id": server.server_id,
                            "teamkills_in_match": match_tks,
                            "source": "pavlov_log",
                        },
                    )

                if victim_pid:
                    self.players.combat(victim_pid, "deaths_from_teamkills")
            elif classification == "player_killed_bot" and killer_pid:
                self.players.combat(killer_pid, "bot_kills")
                if headshot:
                    self.players.combat(killer_pid, "bot_headshots")
            elif classification == "bot_killed_player" and victim_pid:
                self.players.combat(victim_pid, "deaths_by_bots")
            elif classification in {"normal", "normal_unverified_team_relation"}:
                if killer_pid:
                    if classification == "normal_unverified_team_relation":
                        self.players.combat(killer_pid, "kills_unverified_team_relation")
                        count_as_kill = bool(self.cfg.get("count_unverified_player_kills", True))
                    else:
                        count_as_kill = True

                    if count_as_kill:
                        self.players.combat(killer_pid, "kills")
                        if headshot:
                            self.players.combat(killer_pid, "headshots")
                        self.players.weapon_kill(
                            killer_pid,
                            weapon,
                            headshot,
                            self.weapon_source(server.server_id, weapon),
                        )
                if victim_pid:
                    self.players.combat(victim_pid, "deaths")

        return count

    # --------------------- Pavlov line parser ----------------------------

    def process_pavlov_log(self, server: ServerCfg, platform: str, path: Path):
        active_rcon: dict[tuple[str, int], RconSession] = {}
        net_by_endpoint: dict[str, NetSession] = {}
        net_by_conn: dict[str, NetSession] = {}
        latest_pending_by_name: dict[str, NetSession] = {}

        with path.open("r", encoding="utf-8", errors="replace") as f:
            for raw in f:
                m = TS_RE.match(raw.rstrip("\n"))
                if not m:
                    continue
                ts = m.group("ts")
                body = m.group("body").strip()

                # Platform.
                if "PavlovLog: SHACK SERVER BUILD" in body:
                    self.update_server_state(server.server_id, "platform", "SHACK")
                    self.server_event(server.server_id, ts, {
                        "type": "server_platform_detected", "platform": "SHACK"
                    }, "Server platform detected / Platform: SHACK")

                # RCON.
                if self.handle_rcon(server, ts, body, active_rcon):
                    continue

                # Connections.
                self.handle_connection_line(
                    server, platform, ts, body,
                    net_by_endpoint, net_by_conn, latest_pending_by_name
                )

                # HTTP / EOS.
                if self.handle_http(server, ts, body):
                    continue

                # General server / runtime / content.
                self.handle_server_line(server, ts, body)

    def handle_rcon(self, server: ServerCfg, ts: str, body: str,
                    active: dict[tuple[str, int], RconSession]) -> bool:
        if "Rcon:" not in body:
            return False

        ma = re.search(r"Rcon:\s*User authenticated\s+((?:\d{1,3}\.){3}\d{1,3}):(\d+)", body)
        if ma:
            ip, port = ma.group(1), int(ma.group(2))
            ih = self.players.ip_hash(ip)
            active[(ih, port)] = RconSession(ih, port, ts)
            self.rcon_event(server.server_id, ts, {
                "type": "rcon_authenticated", "ip_hash": ih, "port": port
            }, f"RCON authenticated / IP Hash: {ih} / Port: {port}")
            self.update_rcon_host(server.server_id, ih, ts, success=True)
            return True

        mf = re.search(r"Rcon:\s*User Failed authentication! Closing connection to client\s+((?:\d{1,3}\.){3}\d{1,3}):(\d+)", body)
        if mf:
            ip, port = mf.group(1), int(mf.group(2))
            ih = self.players.ip_hash(ip)
            matches = self.players.players_for_ip_hash(ih)
            self.rcon_event(server.server_id, ts, {
                "type": "rcon_authentication_failed",
                "ip_hash": ih,
                "port": port,
                "player_matches": matches
            }, f"RCON authentication failed / IP Hash: {ih} / Port: {port}"
               + (f" / Player Matches: {len(matches)}" if matches else ""))
            self.update_rcon_host(server.server_id, ih, ts, success=False)
            return True

        md = re.search(r"Rcon:\s*Client Disconnect\s+((?:\d{1,3}\.){3}\d{1,3}):(\d+)", body)
        if md:
            ip, port = md.group(1), int(md.group(2))
            ih = self.players.ip_hash(ip)
            active.pop((ih, port), None)
            self.rcon_event(server.server_id, ts, {
                "type": "rcon_disconnected", "ip_hash": ih, "port": port
            }, f"RCON disconnected / IP Hash: {ih} / Port: {port}")
            return True

        mc = re.search(r"Rcon:\s*(.+)$", body)
        if mc:
            command = mc.group(1).strip()
            if command.startswith(("User authenticated", "User Failed authentication", "Client Disconnect")):
                return True
            sessions = list(active.values())
            attrib = "unknown"
            chosen = None
            if len(sessions) == 1:
                chosen, attrib = sessions[0], "certain"
            elif sessions:
                chosen = max(sessions, key=lambda s: parse_ts(s.authenticated_at) or datetime.min)
                attrib = "inferred"
            ev = {
                "type": "rcon_command",
                "command": command,
                "command_name": command.split()[0] if command else None,
                "arguments": command.split()[1:] if command else [],
                "ip_hash": chosen.ip_hash if chosen else None,
                "port": chosen.port if chosen else None,
                "attribution": attrib,
            }
            human = f"RCON command / Command: {command}"
            if chosen:
                human += f" / IP Hash: {chosen.ip_hash} / Port: {chosen.port} / Attribution: {attrib}"
            self.rcon_event(server.server_id, ts, ev, human)
            return True
        return True

    def handle_connection_line(self, server: ServerCfg, platform: str, ts: str, body: str,
                               by_endpoint: dict[str, NetSession],
                               by_conn: dict[str, NetSession],
                               by_name: dict[str, NetSession]):
        # Initial IP connection.
        if "AddClientConnection: Added client connection:" in body:
            epm = IP_PORT_RE.search(body)
            if epm:
                ip, port = epm.group("ip"), int(epm.group("port"))
                endpoint = f"{ip}:{port}"
                cm = CONNECTION_NAME_RE.search(body)
                sess = NetSession(endpoint, ip, port, cm.group(1) if cm else None, ts)
                by_endpoint[endpoint] = sess
                if sess.connection_name:
                    by_conn[sess.connection_name] = sess
            return

        # Login request contains all preference fields + userId.
        if "LogNet: Login request:" in body:
            name = self.query_field(body, "Name") or self.query_field(body, "name")
            pid = self.query_field(body, "pid")
            sess = self.find_pending_session(by_endpoint, by_conn, name, by_name)
            if sess:
                sess.login_at = ts
                sess.player_name = name or sess.player_name
                sess.unique_id = pid or name or sess.unique_id
                sess.player_height = self.float_or_none(self.query_field(body, "playerHeight"))
                sess.right_handed = normalize_bool(self.query_field(body, "rightHanded"))
                sess.vstock = normalize_bool(self.query_field(body, "vstock"))
                sess.client_platform = self.query_field(body, "platform")
                um = re.search(r"\buserId:\s*([^\s]+)", body)
                if um:
                    sess.network_user_id = um.group(1)
                if name:
                    by_name[name] = sess
            return

        if "LogNet: Join request:" in body:
            name = self.query_field(body, "name") or self.query_field(body, "Name")
            pid = self.query_field(body, "pid")
            sess = by_name.get(name) if name else None
            if not sess:
                sess = self.find_pending_session(by_endpoint, by_conn, name, by_name)
            if sess:
                sess.player_name = name or sess.player_name
                sess.unique_id = pid or sess.unique_id
                for field, attr in (
                    ("playerHeight", "player_height"),
                    ("rightHanded", "right_handed"),
                    ("vstock", "vstock"),
                    ("platform", "client_platform")
                ):
                    val = self.query_field(body, field)
                    if val is None: continue
                    setattr(sess, attr, self.float_or_none(val) if field == "playerHeight"
                            else normalize_bool(val) if field in {"rightHanded", "vstock"} else val)
                if name:
                    by_name[name] = sess
            return

        jm = re.search(r"LogNet:\s*Join succeeded:\s*(.+)$", body)
        if jm:
            name = jm.group(1).strip()
            sess = by_name.get(name)
            if not sess:
                sess = self.find_pending_session(by_endpoint, by_conn, name, by_name)
            if sess:
                sess.joined_at = ts
                sess.player_name = name
                if not sess.unique_id:
                    sess.unique_id = name

                # The EOS ProductID in this exact login session is authoritative.
                # Never let a historical name mapping redirect an explicit EOS ID
                # to a different player record.
                explicit_product_id = self.product_id_from_network_user_id(
                    sess.network_user_id
                )
                if explicit_product_id:
                    sess.product_id = explicit_product_id
                else:
                    # Legacy/fallback path for log formats that do not expose an
                    # EOS ProductID. Prefer UniqueID; only use name when there is
                    # no stronger identifier available.
                    sess.product_id = self.players.resolve(unique_id=sess.unique_id)
                    if not sess.product_id and not sess.unique_id:
                        sess.product_id = self.players.resolve(name=name)
                if sess.product_id and not sess.counted_join:
                    sess.counted_join = True
                    self.players.increment_connection(sess.product_id)
                    self.players.learn_identity(
                        sess.product_id, sess.unique_id, sess.player_name,
                        platform, ts, server.server_id
                    )
                    self.players.update_preferences(
                        sess.product_id, ts, server.server_id,
                        sess.player_height, sess.right_handed,
                        sess.vstock, sess.client_platform
                    )
                    ih, bg = self.players.observe_player_ip(
                        sess.product_id, sess.ip, ts, server.server_id
                    )
                    sess.enriched_ip_hash = ih
                    self.link_rcon_player(server.server_id, ih, sess.product_id, sess.unique_id, sess.player_name, ts)
            return

        tm = re.search(r"TeamAssign:\s*Player\s+(.+?)\s+assigned to\s+(-?\d+)", body)
        if tm:
            name, team = tm.group(1), int(tm.group(2))
            sess = by_name.get(name)
            if sess:
                sess.team_id = team
            return

        # Close can be matched by exact endpoint / connection name.
        if "UChannel::Close:" in body and "RemoteAddr:" in body:
            epm = IP_PORT_RE.search(body)
            cm = CONNECTION_NAME_RE.search(body)
            sess = None
            if cm:
                sess = by_conn.get(cm.group(1))
            if not sess and epm:
                sess = by_endpoint.get(f"{epm.group('ip')}:{epm.group('port')}")
            if sess:
                sess.disconnected_at = ts
                if not sess.product_id:
                    explicit_product_id = self.product_id_from_network_user_id(
                        sess.network_user_id
                    )
                    if explicit_product_id:
                        sess.product_id = explicit_product_id
                    elif sess.unique_id:
                        sess.product_id = self.players.resolve(unique_id=sess.unique_id)
                    elif sess.player_name:
                        sess.product_id = self.players.resolve(name=sess.player_name)
                if sess.product_id:
                    self.write_connection_session(server.server_id, platform, sess)
                else:
                    append_jsonl(self.data_root / "servers" / server.server_id / "connections" / "unresolved.jsonl", {
                        "connected_at": sess.started_at,
                        "joined_at": sess.joined_at,
                        "disconnected_at": sess.disconnected_at,
                        "ip_hash": self.players.ip_hash(sess.ip),
                        "unique_id": sess.unique_id,
                        "player_name": sess.player_name,
                        "network_user_id": sess.network_user_id
                    })
                by_endpoint.pop(sess.endpoint, None)
                if sess.connection_name:
                    by_conn.pop(sess.connection_name, None)
                if sess.player_name and by_name.get(sess.player_name) is sess:
                    by_name.pop(sess.player_name, None)
            return

    @staticmethod
    def product_id_from_network_user_id(network_user_id: Optional[str]) -> Optional[str]:
        """Return the explicit 32-char EOS ProductID carried by Pavlov userId.

        This value comes from the same login session and is more authoritative
        than historical name/UniqueID indexes.
        """
        if not network_user_id:
            return None
        m = re.search(r"(?:NULL:)?([0-9a-fA-F]{32})$", str(network_user_id).strip())
        return m.group(1).lower() if m else None

    @staticmethod
    def query_field(body: str, name: str) -> Optional[str]:
        m = re.search(r"(?:\?|&)" + re.escape(name) + r"=([^?&\s]+)", body)
        return m.group(1) if m else None

    @staticmethod
    def float_or_none(s: Optional[str]) -> Optional[float]:
        try: return float(s) if s is not None else None
        except ValueError: return None

    @staticmethod
    def find_pending_session(by_endpoint, by_conn, name, by_name) -> Optional[NetSession]:
        if name and name in by_name:
            return by_name[name]
        # Most recent unjoined session is the best available correlation when
        # the login line itself lacks endpoint/connection name.
        candidates = [x for x in by_endpoint.values() if x.joined_at is None]
        if not candidates:
            return None
        return max(candidates, key=lambda x: parse_ts(x.started_at) or datetime.min)

    def write_connection_session(self, server_id: str, platform: str, s: NetSession):
        if not s.product_id:
            return
        if not s.enriched_ip_hash:
            # If Join succeeded was seen before identity became resolvable.
            ih, _ = self.players.observe_player_ip(s.product_id, s.ip, s.joined_at or s.started_at, server_id)
            s.enriched_ip_hash = ih
        append_jsonl(self.players.player_dir(s.product_id) / "connections.jsonl", {
            "connected_at": s.started_at,
            "login_at": s.login_at,
            "joined_at": s.joined_at,
            "disconnected_at": s.disconnected_at,
            "duration_seconds": duration_seconds(s.joined_at or s.started_at, s.disconnected_at),
            "server_id": server_id,
            "platform": platform,
            "ip_hash": s.enriched_ip_hash,
            "unique_id": s.unique_id,
            "player_name": s.player_name,
            "network_user_id": s.network_user_id,
            "player_height": round(s.player_height, 1) if s.player_height is not None else None,
            "right_handed": s.right_handed,
            "vstock": s.vstock,
            "client_platform": s.client_platform,
            "team_id": s.team_id,
        })

    # --------------------- HTTP -----------------------------------------

    def handle_http(self, server: ServerCfg, ts: str, body: str) -> bool:
        if "LogHttp:" not in body and "LogEOS" not in body:
            return False

        patterns = [
            (r"LogHttp: Warning: (0x[0-9a-fA-F]+): request failed, libcurl error: (\d+) \((.*?)\)",
             "http_request_failed"),
            (r"Connection timeout after (\d+) ms", "http_connection_timeout"),
            (r"Failed to connect to ([^\s]+) port (\d+) after (\d+) ms: (.*?)\)", "http_connection_failed"),
            (r"Retry exhausted on (https?://\S+)", "http_retry_exhausted"),
            (r"Failed to connect to the backend\. ServiceName=\[(.*?)\], OperationName=\[(.*?)\]", "eos_backend_failed"),
            (r"Unable to get the client auth token\. Last result:\s*([A-Za-z0-9_]+)", "eos_client_auth_token_failed"),
            (r"ConnectClientAuthTask Failure", "eos_client_auth_failure"),
            (r"ConnectClientAuthTask Success", "eos_client_auth_success"),
            (r"VerifyIdToken: Key not found in cache, fetching new public keys", "eos_id_key_fetch"),
        ]

        mi = re.search(
            r"(0x[0-9a-fA-F]+): invalid HTTP response code received\. URL: (https?://\S+), "
            r"HTTP code: (\d+), content length: (\d+), actual payload size: (\d+)", body)
        if mi:
            url = mi.group(2)
            u = urlparse(url)
            ev = {
                "type": "invalid_http_response",
                "request_id": mi.group(1),
                "host": u.hostname,
                "path": u.path,
                "http_code": int(mi.group(3)),
                "content_length": int(mi.group(4)),
                "payload_size": int(mi.group(5)),
            }
            self.http_event(server.server_id, ts, ev,
                            f"Invalid HTTP response / Host: {u.hostname} / HTTP Code: {mi.group(3)}")
            return True

        for pat, typ in patterns:
            m = re.search(pat, body)
            if not m:
                continue
            ev: dict[str, Any] = {"type": typ}
            human = typ.replace("_", " ").title()
            if typ == "http_request_failed":
                ev.update(request_id=m.group(1), curl_error=int(m.group(2)), error=m.group(3))
                human += f" / Curl Error: {m.group(2)} / Error: {m.group(3)}"
            elif typ == "http_connection_timeout":
                ev["timeout_ms"] = int(m.group(1))
                human += f" / Timeout: {m.group(1)} ms"
            elif typ == "http_connection_failed":
                ev.update(host=m.group(1), port=int(m.group(2)), after_ms=int(m.group(3)), error=m.group(4))
                human += f" / Host: {m.group(1)} / Port: {m.group(2)} / Error: {m.group(4)}"
            elif typ == "http_retry_exhausted":
                u = urlparse(m.group(1))
                ev.update(host=u.hostname, path=u.path)
                human += f" / Host: {u.hostname} / Path: {u.path}"
            elif typ == "eos_backend_failed":
                ev.update(service=m.group(1), operation=m.group(2))
                human += f" / Service: {m.group(1)} / Operation: {m.group(2)}"
            elif typ == "eos_client_auth_token_failed":
                ev["result"] = m.group(1)
                human += f" / Result: {m.group(1)}"
            self.http_event(server.server_id, ts, ev, human)
            return True

        # Diagnostic HTTP lines are retained in JSONL with sanitized text.
        if "LogHttp:" in body:
            append_jsonl(self.data_root / "servers" / server.server_id / "http" / "debug.jsonl", {
                "timestamp": ts,
                "type": "http_diagnostic",
                "message": re.sub(r"https?://\S+", lambda m: self.sanitize_url(m.group(0)), body)
            })
            return True
        return False

    @staticmethod
    def sanitize_url(url: str) -> str:
        u = urlparse(url.rstrip(","))
        return f"{u.scheme}://{u.netloc}{u.path}" if u.scheme and u.netloc else url

    # --------------------- General server lines -------------------------

    def handle_server_line(self, server: ServerCfg, ts: str, body: str):
        sid = server.server_id

        if "GameMode: Rotating map requested" in body:
            self.server_event(sid, ts, {"type": "map_rotation_requested"}, "Map rotation requested")
            return

        m = re.search(r"Successfully spawned mod initializer for mod (UGC\d+) Version (\d+)", body)
        if m:
            self.server_event(sid, ts, {
                "type": "mod_initializer_spawned", "ugc_id": m.group(1), "version": int(m.group(2))
            }, f"Mod initialized / Mod: {m.group(1)} / Version: {m.group(2)}")
            self.update_mod_catalog(sid, m.group(1), ts, loaded=True)
            return

        m = re.search(r"Match State Changed from (\S+) to (\S+)", body)
        if m:
            old_state = m.group(1)
            new_state = m.group(2)
            self.server_event(sid, ts, {
                "type": "match_state_changed", "from": old_state, "to": new_state
            }, f"Match state changed / From: {old_state} / To: {new_state}")
            self.update_server_state(sid, "match_state", new_state)

            # Reset only the per-match TK counters when a completed/waiting
            # match transitions into another state. Earned badges remain.
            old_cf = old_state.casefold()
            new_cf = new_state.casefold()
            if old_cf != new_cf and (
                "post" in old_cf
                or "end" in old_cf
                or "standby" in old_cf
                or "waiting" in old_cf
            ):
                self.match_teamkills[sid] = {}
            return

        m = re.search(r"Bringing World\s+(\S+)\s+up for play \(max tick rate (\d+)\)", body)
        if m:
            path, rate = m.group(1), int(m.group(2))
            ugc = re.search(r"/(UGC\d+)/", path)
            world = path.rsplit("/", 1)[-1].split(".", 1)[0]
            state = {
                "ugc": ugc.group(1) if ugc else None,
                "name": world,
                "path": path,
                "max_tick_rate": rate
            }
            self.update_server_state(sid, "current_world", state)
            self.server_event(sid, ts, {"type": "world_loaded", **state},
                              f"World loaded / Mod: {state['ugc']} / World: {world} / Max Tick Rate: {rate}")
            return

        m = re.search(r"IpNetDriver listening on port (\d+)", body)
        if m:
            port = int(m.group(1))
            self.update_server_state(sid, "game_port", port)
            self.server_event(sid, ts, {"type": "game_network_started", "port": port},
                              f"Game network started / Port: {port}")
            return

        m = re.search(r"Game class is '([^']+)'", body)
        if m:
            self.update_server_state(sid, "game_class", m.group(1))
            self.server_event(sid, ts, {"type": "game_class", "class": m.group(1)},
                              f"Game class / Class: {m.group(1)}")
            return

        m = re.search(r"Remote debugging available on port:\s*(\d+)", body)
        if m:
            port = int(m.group(1))
            self.update_server_state(sid, "debug_port", port)
            self.server_event(sid, ts, {"type": "remote_inspector_initialized", "port": port},
                              f"Remote inspector initialized / Port: {port}")
            return

        # Custom guns and loot.
        m = re.search(r"PavlovLog:\s*Added Gun\s+(.+)$", body)
        if m:
            item = m.group(1).strip()
            self.update_unique_catalog(sid, "custom_guns.json", item, ts)
            self.server_event(sid, ts, {"type": "custom_gun_loaded", "gun": item},
                              f"Custom gun loaded / Gun: {item}")
            return

        m = re.search(r"PavlovLog:\s*Added Loot Mesh\s+(.+)$", body)
        if m:
            item = m.group(1).strip()
            self.update_unique_catalog(sid, "custom_loot.json", item, ts)
            self.server_event(sid, ts, {"type": "custom_loot_loaded", "item": item},
                              f"Custom loot loaded / Item: {item}")
            return

        m = re.search(r"LogTemp: Error:\s*(\d+)Failed to add(.+)$", body)
        if m:
            ugc, item = f"UGC{m.group(1)}", m.group(2).strip()
            self.failed_item(sid, ts, item, "unknown", ugc)
            return

        m = re.search(r"PavlovLog: Error: Failed to add item\s+(.+?)\s+it already exists in the list", body)
        if m:
            self.failed_item(sid, ts, m.group(1).strip(), "already_exists", None)
            return

        m = re.search(r"ModInitializer Found (UGC\d+) path (\S+)", body)
        if m:
            ugc, path = m.group(1), m.group(2)
            initializer = path.rsplit("/", 1)[-1].split(".")[-1]
            self.update_mod_catalog(sid, ugc, ts, path=path, initializer=initializer, loaded=True)
            self.server_event(sid, ts, {
                "type": "mod_initializer_found",
                "ugc_id": ugc, "path": path, "initializer": initializer
            }, f"Mod initializer found / Mod: {ugc} / Initializer: {initializer}")
            return

        # Hardware / engine.
        runtime_patterns = [
            (r"Number of physical cores available for the process:\s*(\d+)", ("cpu", "physical_cores"), int),
            (r"Number of logical cores available for the process:\s*(\d+)", ("cpu", "logical_cores"), int),
            (r"Physical RAM available .*?:\s*(\d+)\s*GB \((\d+)\s*MB,\s*(\d+)\s*KB,\s*(\d+)\s*bytes\)",
             ("memory",), None),
            (r"LogInit:\s*Build:\s*(.+)$", ("unreal", "build"), str),
            (r"LogInit:\s*Engine Version:\s*(.+)$", ("unreal", "engine_version"), str),
            (r"LogInit:\s*Branch Name:\s*(.+)$", ("unreal", "branch"), str),
            (r"LogInit:\s*Command Line:\s*(.+)$", ("startup", "command_line"), str),
            (r"ICU TimeZone Detection - Raw Offset:\s*([^,]+)", ("timezone_offset",), str),
        ]
        for pat, keypath, conv in runtime_patterns:
            m = re.search(pat, body)
            if not m:
                continue
            if keypath == ("memory",):
                val = {
                    "physical_ram_gb": int(m.group(1)),
                    "physical_ram_mb": int(m.group(2)),
                    "physical_ram_kb": int(m.group(3)),
                    "physical_ram_bytes": int(m.group(4))
                }
            else:
                val = conv(m.group(1).strip()) if conv else m.group(1)
            self.update_runtime(sid, ts, keypath, val)
            if keypath == ("startup", "command_line"):
                pm = re.search(r"-PORT=(\d+)", str(val))
                if pm:
                    self.update_runtime(sid, ts, ("startup", "configured_port"), int(pm.group(1)))
            return

        m = re.search(
            r"LogNetVersion:\s*Pavlov\s+([^,]+),\s*NetCL:\s*(\d+),\s*EngineNetVer:\s*(\d+),\s*"
            r"GameNetVer:\s*(\d+)\s*\(Checksum:\s*(\d+)\)", body)
        if m:
            val = {
                "version": m.group(1).strip(),
                "net_cl": int(m.group(2)),
                "engine_net_version": int(m.group(3)),
                "game_net_version": int(m.group(4)),
                "network_checksum": int(m.group(5)),
            }
            self.update_runtime(sid, ts, ("pavlov",), val)
            self.server_event(sid, ts, {"type": "pavlov_network_version", **val},
                              f"Pavlov network version / Version: {val['version']} / Checksum: {val['network_checksum']}")
            return

        # Anti-cheat.
        m = re.search(r"\[BeginSession-\d+\] ServerName: '([^']+)' RegisterTimeout: (\d+) bEnableGameplayData: (\d+)", body)
        if m:
            ac = {
                "server_name": m.group(1),
                "register_timeout": int(m.group(2)),
                "gameplay_data": bool(int(m.group(3)))
            }
            self.update_server_state(sid, "anti_cheat", ac)
            self.server_event(sid, ts, {"type": "anti_cheat_session_started", **ac},
                              f"Anti-cheat session started / Server Name: {m.group(1)} / Register Timeout: {m.group(2)}")
            return

        m = re.search(r"PreviousKicksEnabledValue:\s*(\d+)\s+NewKicksEnabledValue:\s*(\d+)", body)
        if m:
            ev = {"type": "anti_cheat_kick_status_changed",
                  "previous": bool(int(m.group(1))), "new": bool(int(m.group(2)))}
            self.server_event(sid, ts, ev,
                              f"Anti-cheat kick status changed / Previous: {ev['previous']} / New: {ev['new']}")
            return

    # --------------------- helpers / output ------------------------------

    def server_event(self, sid: str, ts: str, ev: dict, human: str):
        append_jsonl(self.data_root / "servers" / sid / "server" / "events.jsonl",
                     {"timestamp": ts, **ev})
        append_human_log(self.data_root / "servers" / sid / "server" / "server.log", ts, human)

    def rcon_event(self, sid: str, ts: str, ev: dict, human: str):
        append_jsonl(self.data_root / "servers" / sid / "rcon" / "events.jsonl",
                     {"timestamp": ts, **ev})
        append_human_log(self.data_root / "servers" / sid / "rcon" / "rcon.log", ts, human)

    def http_event(self, sid: str, ts: str, ev: dict, human: str):
        append_jsonl(self.data_root / "servers" / sid / "http" / "events.jsonl",
                     {"timestamp": ts, **ev})
        append_human_log(self.data_root / "servers" / sid / "http" / "http.log", ts, human)

    def update_server_state(self, sid: str, key: str, value: Any):
        p = self.data_root / "servers" / sid / "server.json"
        d = load_json(p, {"server_id": sid})
        d[key] = value
        d["updated_at"] = now_iso()
        atomic_write_json(p, d)

    def update_runtime(self, sid: str, ts: str, keypath: tuple[str, ...], value: Any):
        p = self.data_root / "servers" / sid / "server.json"
        d = load_json(p, {"server_id": sid, "runtime": {}})
        runtime = d.setdefault("runtime", {})
        cur = runtime
        for k in keypath[:-1]:
            cur = cur.setdefault(k, {})
        key = keypath[-1]
        old = cur.get(key)
        if old is not None and old != value:
            self.server_event(sid, ts, {
                "type": "runtime_changed",
                "field": ".".join(keypath),
                "old_value": old,
                "new_value": value
            }, f"Runtime changed / Field: {'.'.join(keypath)} / Old: {old} / New: {value}")
        cur[key] = value
        d["updated_at"] = now_iso()
        atomic_write_json(p, d)

    def update_unique_catalog(self, sid: str, filename: str, item: str, ts: str):
        p = self.data_root / "servers" / sid / "server" / filename
        d = load_json(p, {})
        e = d.setdefault(item, {"first_seen": ts, "last_seen": ts, "times_loaded": 0})
        e["first_seen"] = min(e.get("first_seen") or ts, ts)
        e["last_seen"] = max(e.get("last_seen") or ts, ts)
        e["times_loaded"] = int(e.get("times_loaded", 0)) + 1
        atomic_write_json(p, d)

    def failed_item(self, sid: str, ts: str, item: str, reason: str, ugc: Optional[str]):
        p = self.data_root / "servers" / sid / "server" / "failed_items.json"
        d = load_json(p, {})
        e = d.setdefault(item, {
            "first_seen": ts, "last_seen": ts, "failures": 0,
            "ugc_ids": [], "reasons": []
        })
        e["first_seen"] = min(e.get("first_seen") or ts, ts)
        e["last_seen"] = max(e.get("last_seen") or ts, ts)
        e["failures"] += 1
        if ugc: unique_append(e["ugc_ids"], ugc)
        unique_append(e["reasons"], reason)
        atomic_write_json(p, d)
        self.server_event(sid, ts, {
            "type": "custom_item_load_failed",
            "item": item, "reason": reason, "ugc_id": ugc
        }, f"Custom item load failed / Mod: {ugc or 'Unknown'} / Item: {item} / Reason: {reason}")

    def update_mod_catalog(self, sid: str, ugc: str, ts: str, path: Optional[str] = None,
                           initializer: Optional[str] = None, loaded: bool = False):
        p = self.data_root / "servers" / sid / "server" / "mods.json"
        d = load_json(p, {})
        e = d.setdefault(ugc, {
            "first_seen": ts, "last_seen": ts, "times_loaded": 0,
            "initializer_paths": [], "initializers": [],
            "configured": False,
            "sources": [],
            "modio": None
        })
        if "ModInitializer" not in e.setdefault("sources", []):
            e["sources"].append("ModInitializer")
        e["first_seen"] = min(e.get("first_seen") or ts, ts)
        e["last_seen"] = max(e.get("last_seen") or ts, ts)
        if loaded: e["times_loaded"] += 1
        if path: unique_append(e["initializer_paths"], path)
        if initializer: unique_append(e["initializers"], initializer)
        if e.get("modio") is None:
            try: e["modio"] = self.enricher.modio(ugc)
            except Exception: pass
        atomic_write_json(p, d)

    def weapon_source(self, sid: str, weapon: str) -> str:
        if not weapon or weapon.casefold() == "none":
            return "unknown"
        custom = load_json(self.data_root / "servers" / sid / "server" / "custom_guns.json", {})
        if weapon.casefold() in {str(x).casefold() for x in custom.keys()}:
            return "custom"
        if weapon.casefold() in {str(x).casefold() for x in self.base_items}:
            return "base"
        # preserve unknowns globally.
        p = self.data_root / "global" / "reference" / "unknown_items.json"
        d = load_json(p, {})
        e = d.setdefault(weapon, {"times_seen": 0, "servers": []})
        e["times_seen"] += 1
        unique_append(e["servers"], sid)
        atomic_write_json(p, d)
        return "unknown"

    def update_rcon_host(self, sid: str, ih: str, ts: str, success: bool):
        fname = "known_hosts.json" if success else "failed_hosts.json"
        p = self.data_root / "servers" / sid / "rcon" / fname
        d = load_json(p, {})
        is_new = ih not in d
        e = d.setdefault(ih, {
            "first_seen": ts, "last_seen": ts,
            "successful_connections": 0, "failed_attempts": 0,
            "players_seen_on_ip": []
        })
        # Correlation only: shared IP does not prove the player made the RCON attempt.
        for rec in self.players.players_for_ip_hash(ih):
            simple = {
                "product_id": rec.get("product_id"),
                "unique_id": rec.get("unique_id"),
                "player_name": rec.get("player_name")
            }
            if simple not in e["players_seen_on_ip"]:
                e["players_seen_on_ip"].append(simple)
        e["first_seen"] = min(e.get("first_seen") or ts, ts)
        e["last_seen"] = max(e.get("last_seen") or ts, ts)
        if success: e["successful_connections"] += 1
        else: e["failed_attempts"] += 1
        atomic_write_json(p, d)
        if is_new:
            human_file = "known_hosts.log" if success else "failed_hosts.log"
            label = "Known RCON host" if success else "Failed RCON host"
            append_human_log(self.data_root / "servers" / sid / "rcon" / human_file, ts,
                             f"{label} / IP Hash: {ih}")

    def link_rcon_player(self, sid: str, ih: str, pid: str, uid: Optional[str],
                         name: Optional[str], ts: str):
        p = self.data_root / "servers" / sid / "rcon" / "known_hosts.json"
        d = load_json(p, {})
        if ih not in d:
            return
        host = d[ih]
        players = host.setdefault("players_seen_on_ip", [])
        rec = {"product_id": pid, "unique_id": uid, "player_name": name}
        if rec not in players:
            players.append(rec)
            atomic_write_json(p, d)
            append_human_log(
                self.data_root / "servers" / sid / "rcon" / "known_hosts.log",
                ts,
                f"RCON host linked to player / IP Hash: {ih} / Player: {name} / ProductID: {pid}"
            )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-c", "--config", default="config.json")
    ap.add_argument(
        "--old-archive",
        action="append",
        default=[],
        help=(
            "Read-only historical archive root to index recursively. "
            "May be supplied more than once. Values are added to old_archive_paths."
        ),
    )
    ap.add_argument(
        "--backfill-badges",
        action="store_true",
        help=(
            "Backfill automatic badges from existing player.json, ips.json, "
            "and stats.json records. Safe to run more than once."
        ),
    )
    ap.add_argument(
        "--rebuild-identities",
        action="store_true",
        help=(
            "Reset derived player name/UniqueID/Steam identity mappings and "
            "rebuild them from Stats productId records plus Pavlov login lines "
            "with explicit EOS userId ProductIDs. Does not replay connection, "
            "IP, RCON, HTTP, or combat counters."
        ),
    )
    ap.add_argument(
        "--rebuild-connections",
        action="store_true",
        help=(
            "Reset derived player connection/IP data and rebuild it from "
            "authenticated Pavlov connection lifecycle records containing both "
            "RemoteAddr and EOS ProductID (UniqueId: NULL:<ProductID>). "
            "Duplicate cleanup/close records are deduplicated. Names and "
            "Anti-cheat lines are not required for ownership. Combat, badges, "
            "bans, moderation data, Discord links, and names are preserved."
        ),
    )
    ap.add_argument(
        "--rebuild-combat",
        action="store_true",
        help=(
            "Reset combat-only counters/event files and rebuild kills from "
            "StatManagerLog KillData found in Pavlov.log/Pavlov-backup-*.log. "
            "Connection, match, identity, IP, admin, and ban data are preserved."
        ),
    )
    args = ap.parse_args()

    cfg_path = Path(args.config).expanduser().resolve()
    if not cfg_path.exists():
        print(f"Config not found: {cfg_path}", file=sys.stderr)
        print(json.dumps(DEFAULT_CONFIG, indent=2), file=sys.stderr)
        raise SystemExit(2)

    # Load .env beside config.json for manual runs; existing environment wins.
    load_env_file(cfg_path.parent / ".env")

    with cfg_path.open("r", encoding="utf-8") as f:
        cfg = json.load(f)

    # Merge top-level defaults without overwriting explicit config.
    merged = copy.deepcopy(DEFAULT_CONFIG)
    merged.update(cfg)
    if "servers" in cfg:
        merged["servers"] = cfg["servers"]

    if args.old_archive:
        configured_old = merged.get("old_archive_paths", [])
        if isinstance(configured_old, (str, Path)):
            configured_old = [configured_old]
        merged["old_archive_paths"] = list(configured_old) + list(args.old_archive)

    merged["_rebuild_identities"] = bool(args.rebuild_identities)
    merged["_rebuild_connections"] = bool(args.rebuild_connections)
    merged["_rebuild_pavlov_combat"] = bool(args.rebuild_combat)
    merged["_backfill_badges"] = bool(args.backfill_badges)

    Collector(merged).run()
    print("JTWP Pavlov collector completed successfully.")


if __name__ == "__main__":
    main()
