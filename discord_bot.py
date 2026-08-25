#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import re
import subprocess
import tempfile
import time
import requests
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

import discord
from discord import app_commands
from discord.ext import commands, tasks
from pavlov import PavlovRCON
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parent
ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


# Complete JTWP RCON + RCON Plus catalog used by /rcon autocomplete.
# Ban is intentionally excluded. Discord autocomplete shows at most 25 matching
# rows at once, but all commands remain searchable through this full list.
RCON_COMMANDS = ['AddMapRotation', 'AddMod', 'Banlist', 'ClearEmptyVehicles', 'Disconnect', 'EnableCompMode', 'EnableVerboseLogging', 'EnableWhitelist', 'Gag', 'GiveAll', 'GiveCash', 'GiveItem', 'GiveTeamCash', 'Help', 'InspectAll', 'InspectPlayer', 'InspectTeam', 'ItemList', 'Kick', 'Kill', 'MapList', 'ModeratorList', 'PauseMatch', 'RefreshList', 'RemoveMapRotation', 'RemoveMod', 'ResetSND', 'RotateMap', 'ServerInfo', 'SetBalanceTableURL', 'SetBotsEnabled', 'SetCash', 'SetLimitedAmmoType', 'SetMaxPlayers', 'SetPin', 'SetPlayerSkin', 'SetTimeLimit', 'ShowNametags', 'ShutdownServer', 'Slap', 'SwitchMap', 'SwitchTeam', 'Teleport', 'TTTAlwaysEnableSkinMenu', 'TTTEndRound', 'TTTFlushKarma', 'TTTGiveCredits', 'TTTPauseTimer', 'TTTSetKarma', 'TTTSetRole', 'Unban', 'UpdateServerName', 'UGCAddMod', 'UGCClearModList', 'UGCModList', 'UGCRemoveMod', 'Notify', 'DropItems', 'DisablePickup', 'MovementSpeed', 'CleanUp', 'Godmode', 'Warp', 'AddBot', 'RemoveBot', 'Ignite', 'DisableItems', 'Detonate', 'GameSpeed', 'SetGravity', 'EnableProne', 'FallDamage', 'EnableBuyMenu', 'NoClip', 'Supply', 'Visibility', 'Revive', 'DisableVoting', 'AttachmentMode', 'UtilityTrails', 'KillFeedback', 'SetTeamSkin', 'SpawnLootCrate', 'SpawnChickens', 'SpawnZombies', 'RemoveZombies', 'SetVitality', 'TeamSwitching']
RCON_BLOCKED_COMMANDS = {"ban"}


BADGE_DISCORD_LINK = "DISCORD BADGE #001"
BADGE_VPN_CONNECTION = "Vpn Connection #002"
BADGE_TEAMKILLER = "TeamKiller #003"
BADGE_1000_KILLS = "1000 Kills #004"
BADGE_5000_KILLS = "5000 Kills #005"
BADGE_10000_KILLS = "10000 Kills #006"
BADGE_100_HEADSHOTS = "100 Headshots #007"
BADGE_1000_HEADSHOTS = "1000 Headshots #008"
BADGE_100_CONNECTIONS = "100 Connections #009"
BADGE_1000_CONNECTIONS = "1000 Connections #010"
BADGE_VETERAN = "Veteran #011"
BADGE_CLEAN_PLAYER = "Clean Player #012"
BADGE_STAFF = "JTWP Staff #013"
BADGE_MANUAL_SPECIAL = "Special Recognition #014"
BADGE_015 = "Negative K/D #015"
BADGE_016 = "Network Traveler #016"
BADGE_017 = "Bot Slayer #017"
BADGE_018 = "Alias Collector #018"
BADGE_019 = "Ban History #019"
BADGE_020 = "SHACK Player #020"
BADGE_021 = "PCVR Player #021"
BADGE_022 = "Server Hopper #022"
BADGE_023 = "Snowball Fighter #023"
BADGE_024 = "Bayonet Veteran #024"
BADGE_025 = "C4 Expert #025"
BADGE_026 = "Tank Commander #026"
BADGE_027 = "Road Warrior #027"
BADGE_028 = "Knife Master #028"
BADGE_029 = "Flare Gunner #029"
BADGE_030 = "Bot Exterminator #030"
BADGE_031 = "Headshot Legend #031"
BADGE_032 = "Century Club #032"
BADGE_033 = "Day One Grinder #033"
BADGE_034 = "Arsenal Master #034"
BADGE_035 = "Multi-Weapon Veteran #035"
BADGE_036 = "Name Changer #036"
BADGE_037 = "Ancient Veteran #037"
BADGE_038 = "10K Connections #038"

DEFAULT_BADGES: dict[str, dict[str, Any]] = {
    BADGE_DISCORD_LINK: {
        "id": 1,
        "name": BADGE_DISCORD_LINK,
        "url": "",
        "description": "Discord account linked to a JTWP player account.",
        "automatic": True,
        "criteria": {"type": "discord_link"},
    },
    BADGE_VPN_CONNECTION: {
        "id": 2,
        "name": BADGE_VPN_CONNECTION,
        "url": "",
        "description": "Awarded when a VPN or proxy connection is detected for the player.",
        "automatic": True,
        "criteria": {"type": "vpn_or_proxy"},
    },
    BADGE_TEAMKILLER: {
        "id": 3,
        "name": BADGE_TEAMKILLER,
        "url": "",
        "description": "Awarded for getting 3 teamkills in a single match.",
        "automatic": False,
        "criteria": {"type": "single_match_teamkills", "threshold": 3},
    },
    BADGE_1000_KILLS: {
        "id": 4,
        "name": BADGE_1000_KILLS,
        "url": "",
        "description": "Awarded for reaching 1,000 lifetime kills.",
        "automatic": True,
        "criteria": {"type": "stat_gte", "stat": "kills", "threshold": 1000},
    },
    BADGE_5000_KILLS: {
        "id": 5,
        "name": BADGE_5000_KILLS,
        "url": "",
        "description": "Awarded for reaching 5,000 lifetime kills.",
        "automatic": True,
        "criteria": {"type": "stat_gte", "stat": "kills", "threshold": 5000},
    },
    BADGE_10000_KILLS: {
        "id": 6,
        "name": BADGE_10000_KILLS,
        "url": "",
        "description": "Awarded for reaching 10,000 lifetime kills.",
        "automatic": True,
        "criteria": {"type": "stat_gte", "stat": "kills", "threshold": 10000},
    },
    BADGE_100_HEADSHOTS: {
        "id": 7,
        "name": BADGE_100_HEADSHOTS,
        "url": "",
        "description": "Awarded for reaching 100 lifetime headshots.",
        "automatic": True,
        "criteria": {"type": "stat_gte", "stat": "headshots", "threshold": 100},
    },
    BADGE_1000_HEADSHOTS: {
        "id": 8,
        "name": BADGE_1000_HEADSHOTS,
        "url": "",
        "description": "Awarded for reaching 1,000 lifetime headshots.",
        "automatic": True,
        "criteria": {"type": "stat_gte", "stat": "headshots", "threshold": 1000},
    },
    BADGE_100_CONNECTIONS: {
        "id": 9,
        "name": BADGE_100_CONNECTIONS,
        "url": "",
        "description": "Awarded for connecting to JTWP servers 100 times.",
        "automatic": True,
        "criteria": {"type": "stat_gte", "stat": "times_connected", "threshold": 100},
    },
    BADGE_1000_CONNECTIONS: {
        "id": 10,
        "name": BADGE_1000_CONNECTIONS,
        "url": "",
        "description": "Awarded for connecting to JTWP servers 1,000 times.",
        "automatic": True,
        "criteria": {"type": "stat_gte", "stat": "times_connected", "threshold": 1000},
    },
    BADGE_VETERAN: {
        "id": 11,
        "name": BADGE_VETERAN,
        "url": "",
        "description": "Awarded to players first seen at least 365 days ago.",
        "automatic": True,
        "criteria": {"type": "account_age_days", "threshold": 365},
    },
    BADGE_CLEAN_PLAYER: {
        "id": 12,
        "name": BADGE_CLEAN_PLAYER,
        "url": "",
        "description": "Reserved for future clean-player/reputation criteria.",
        "automatic": False,
        "criteria": {"type": "manual"},
    },
    BADGE_STAFF: {
        "id": 13,
        "name": BADGE_STAFF,
        "url": "",
        "description": "Awarded to JTWP staff/admin player profiles.",
        "automatic": True,
        "criteria": {"type": "player_admin"},
    },
    BADGE_MANUAL_SPECIAL: {
        "id": 14,
        "name": BADGE_MANUAL_SPECIAL,
        "url": "",
        "description": "Manual badge for special recognition.",
        "automatic": False,
        "criteria": {"type": "manual"},
    },    BADGE_015: {
        "id": 15,
        "name": BADGE_015,
        "url": "",
        "description": "Awarded when lifetime deaths exceed lifetime kills.",
        "automatic": True,
        "criteria": {'type': 'negative_kd'},
    },
    BADGE_016: {
        "id": 16,
        "name": BADGE_016,
        "url": "",
        "description": "Awarded when more than 3 unique IP hashes have been recorded.",
        "automatic": True,
        "criteria": {'type': 'ip_hash_count_gt', 'threshold': 3},
    },
    BADGE_017: {
        "id": 17,
        "name": BADGE_017,
        "url": "",
        "description": "Awarded for reaching 1,000 lifetime bot kills.",
        "automatic": True,
        "criteria": {'type': 'stat_gte', 'stat': 'bot_kills', 'threshold': 1000},
    },
    BADGE_018: {
        "id": 18,
        "name": BADGE_018,
        "url": "",
        "description": "Awarded when more than one player name has been recorded.",
        "automatic": True,
        "criteria": {'type': 'name_count_gt', 'threshold': 1},
    },
    BADGE_019: {
        "id": 19,
        "name": BADGE_019,
        "url": "",
        "description": "Awarded if the player is currently banned or has a recorded JTWP ban history.",
        "automatic": True,
        "criteria": {'type': 'banned_history'},
    },
    BADGE_020: {
        "id": 20,
        "name": BADGE_020,
        "url": "",
        "description": "Awarded to players recorded on the SHACK platform.",
        "automatic": True,
        "criteria": {'type': 'platform_is', 'platform': 'SHACK'},
    },
    BADGE_021: {
        "id": 21,
        "name": BADGE_021,
        "url": "",
        "description": "Awarded to players recorded on the PCVR platform.",
        "automatic": True,
        "criteria": {'type': 'platform_is', 'platform': 'PCVR'},
    },
    BADGE_022: {
        "id": 22,
        "name": BADGE_022,
        "url": "",
        "description": "Awarded after connecting to every currently configured active JTWP server.",
        "automatic": True,
        "criteria": {'type': 'all_active_servers'},
    },
    BADGE_023: {
        "id": 23,
        "name": BADGE_023,
        "url": "",
        "description": "Awarded for 25 Snowball kills.",
        "automatic": True,
        "criteria": {'type': 'weapon_kills_sum_gte', 'weapons': ['snowball'], 'threshold': 25},
    },
    BADGE_024: {
        "id": 24,
        "name": BADGE_024,
        "url": "",
        "description": "Awarded for 100 combined bayonet kills.",
        "automatic": True,
        "criteria": {'type': 'weapon_kills_sum_gte', 'weapons': ['bayonet_held', 'bayonet_charge'], 'threshold': 100},
    },
    BADGE_025: {
        "id": 25,
        "name": BADGE_025,
        "url": "",
        "description": "Awarded for 100 TTT C4 kills.",
        "automatic": True,
        "criteria": {'type': 'weapon_kills_sum_gte', 'weapons': ['tttc4'], 'threshold': 100},
    },
    BADGE_026: {
        "id": 26,
        "name": BADGE_026,
        "url": "",
        "description": "Awarded for 100 combined tank turret and tank MG kills.",
        "automatic": True,
        "criteria": {'type': 'weapon_kills_sum_gte', 'weapons': ['tankturret', 'tankmg'], 'threshold': 100},
    },
    BADGE_027: {
        "id": 27,
        "name": BADGE_027,
        "url": "",
        "description": "Awarded for 50 roadkill/runover kills.",
        "automatic": True,
        "criteria": {'type': 'weapon_kills_sum_gte', 'weapons': ['runover'], 'threshold': 50},
    },
    BADGE_028: {
        "id": 28,
        "name": BADGE_028,
        "url": "",
        "description": "Awarded for 100 combined modern and WW2 knife kills.",
        "automatic": True,
        "criteria": {'type': 'weapon_kills_sum_gte', 'weapons': ['Knife', 'ww2knife'], 'threshold': 100},
    },
    BADGE_029: {
        "id": 29,
        "name": BADGE_029,
        "url": "",
        "description": "Awarded for 50 Flare Gun kills.",
        "automatic": True,
        "criteria": {'type': 'weapon_kills_sum_gte', 'weapons': ['flaregun'], 'threshold': 50},
    },
    BADGE_030: {
        "id": 30,
        "name": BADGE_030,
        "url": "",
        "description": "Awarded for reaching 5,000 lifetime bot kills.",
        "automatic": True,
        "criteria": {'type': 'stat_gte', 'stat': 'bot_kills', 'threshold': 5000},
    },
    BADGE_031: {
        "id": 31,
        "name": BADGE_031,
        "url": "",
        "description": "Awarded for reaching 5,000 lifetime headshots.",
        "automatic": True,
        "criteria": {'type': 'stat_gte', 'stat': 'headshots', 'threshold': 5000},
    },
    BADGE_032: {
        "id": 32,
        "name": BADGE_032,
        "url": "",
        "description": "Awarded for 100 hours of recorded JTWP playtime.",
        "automatic": True,
        "criteria": {'type': 'total_time_online_gte', 'seconds': 360000},
    },
    BADGE_033: {
        "id": 33,
        "name": BADGE_033,
        "url": "",
        "description": "Awarded for 24 hours of recorded JTWP playtime.",
        "automatic": True,
        "criteria": {'type': 'total_time_online_gte', 'seconds': 86400},
    },
    BADGE_034: {
        "id": 34,
        "name": BADGE_034,
        "url": "",
        "description": "Awarded for recording at least one kill with 20 different weapons.",
        "automatic": True,
        "criteria": {'type': 'weapon_types_gte', 'threshold': 20, 'minimum_kills_each': 1},
    },
    BADGE_035: {
        "id": 35,
        "name": BADGE_035,
        "url": "",
        "description": "Awarded for 100+ kills with at least 5 different weapons.",
        "automatic": True,
        "criteria": {'type': 'weapon_types_gte', 'threshold': 5, 'minimum_kills_each': 100},
    },
    BADGE_036: {
        "id": 36,
        "name": BADGE_036,
        "url": "",
        "description": "Awarded when 5 or more names have been recorded.",
        "automatic": True,
        "criteria": {'type': 'name_count_gte', 'threshold': 5},
    },
    BADGE_037: {
        "id": 37,
        "name": BADGE_037,
        "url": "",
        "description": "Awarded to players first seen at least 1,000 days ago.",
        "automatic": True,
        "criteria": {'type': 'account_age_days', 'threshold': 1000},
    },
    BADGE_038: {
        "id": 38,
        "name": BADGE_038,
        "url": "",
        "description": "Awarded for 10,000 recorded JTWP connections.",
        "automatic": True,
        "criteria": {'type': 'stat_gte', 'stat': 'times_connected', 'threshold': 10000},
    },

}



# ============================================================
# Generic helpers
# ============================================================

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return utc_now().isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def strip_ansi(value: str | None) -> str:
    return ANSI_RE.sub("", value or "")


def clip(value: Any, maximum: int = 1000) -> str:
    text = str(value if value is not None else "").strip()
    if not text:
        return "None"
    return text if len(text) <= maximum else text[: maximum - 1] + "…"


def load_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        if isinstance(default, dict):
            return dict(default)
        if isinstance(default, list):
            return list(default)
        return default


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


# ============================================================
# JSONL -> Discord webhook tailer
# ============================================================

class JsonlWebhookTailer:
    def __init__(
        self,
        *,
        bot: commands.Bot,
        source_path: Path,
        state_path: Path,
        webhook_url: str,
        title: str,
    ):
        self.bot = bot
        self.source_path = source_path
        self.state_path = state_path
        self.webhook_url = webhook_url
        self.title = title

    def load_offset(self) -> int:
        state = load_json(self.state_path, {})
        try:
            return max(0, int(state.get("offset", 0)))
        except Exception:
            return 0

    def save_offset(self, offset: int) -> None:
        atomic_write_json(self.state_path, {
            "source": str(self.source_path),
            "offset": int(offset),
            "updated_at": now_iso(),
        })

    @staticmethod
    def _field_value(value: Any) -> str:
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, default=str)
        text = str(value)
        return text if len(text) <= 1000 else text[:997] + "..."

    def payload(self, entry: dict[str, Any]) -> dict[str, Any]:
        success = bool(entry.get("success", True))
        event = entry.get("type") or entry.get("event") or "unknown"
        fields = []
        username = entry.get("discord_username")
        user_id = entry.get("discord_user_id")
        if username or user_id:
            fields.append({
                "name": "👤 User",
                "value": f"**{username or 'Unknown'}**\n`{user_id or 'Unknown'}`",
                "inline": True,
            })
        if entry.get("permission") is not None:
            fields.append({"name": "🔐 Permission", "value": f"`{entry.get('permission')}`", "inline": True})
        fields.append({
            "name": "📌 Result",
            "value": "✅ **Success**" if success else "❌ **Failed**",
            "inline": True,
        })
        ignored = {"timestamp", "discord_user_id", "discord_username", "permission", "type", "event", "success", "error"}
        for key, value in entry.items():
            if key in ignored or value is None:
                continue
            fields.append({
                "name": key.replace("_", " ").title()[:256],
                "value": f"`{self._field_value(value)}`",
                "inline": True,
            })
            if len(fields) >= 24:
                break
        if entry.get("error"):
            fields.append({
                "name": "⚠️ Error",
                "value": f"```text\n{self._field_value(entry['error'])}\n```",
                "inline": False,
            })
        return {
            "embeds": [{
                "title": self.title,
                "description": f"### `{event}`",
                "color": 5763719 if success else 15548997,
                "fields": fields[:25],
                "footer": {"text": f"JTWP • {entry.get('timestamp', 'Unknown time')}"},
            }]
        }

    def post(self, entry: dict[str, Any]) -> None:
        payload = self.payload(entry)
        for attempt in range(5):
            r = requests.post(self.webhook_url, json=payload, timeout=10)
            if r.status_code in {200, 204}:
                return
            if r.status_code == 429:
                try:
                    retry_after = float(r.json().get("retry_after", 1.0))
                except Exception:
                    retry_after = 1.0
                time.sleep(max(0.25, min(retry_after, 30.0)))
                continue
            raise RuntimeError(f"Webhook HTTP {r.status_code}: {r.text[:300]}")
        raise RuntimeError("Webhook remained rate limited after 5 retries")

    async def process_once(self) -> None:
        if not self.webhook_url or not self.source_path.is_file():
            return
        offset = self.load_offset()
        size = self.source_path.stat().st_size
        # File was truncated/replaced. Start at the beginning of the new file.
        if offset > size:
            offset = 0
        with self.source_path.open("rb") as handle:
            handle.seek(offset)
            while True:
                start = handle.tell()
                raw = handle.readline()
                if not raw:
                    break
                # Do not consume a partial line while another process is writing it.
                if not raw.endswith(b"\n"):
                    break
                try:
                    entry = json.loads(raw.decode("utf-8", errors="replace"))
                except json.JSONDecodeError:
                    # Preserve progress over malformed complete lines.
                    self.save_offset(handle.tell())
                    continue
                try:
                    await asyncio.to_thread(self.post, entry)
                except Exception as exc:
                    print(f"Webhook tailer error for {self.source_path}: {type(exc).__name__}: {exc}", flush=True)
                    handle.seek(start)
                    break
                self.save_offset(handle.tell())

    @tasks.loop(seconds=2)
    async def loop(self) -> None:
        await self.process_once()

    @loop.before_loop
    async def before_loop(self) -> None:
        await self.bot.wait_until_ready()


# ============================================================
# Bot
# ============================================================

class JTWPBot(commands.Bot):
    def __init__(self, cfg: dict[str, Any], cfg_path: Path):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True

        # Needed for the simple text trigger: a linked user can type
        # exactly "badges" and the bot will reply with their badge row.
        intents.message_content = True

        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
        )

        self.cfg = cfg
        self.cfg_path = cfg_path
        self.bot_cfg = cfg.get("discord_bot", {})
        self.data_root = Path(cfg["data_path"])

        # Public leaderboard cache. Scanning 100k+ player records on every
        # slash-command invocation would be expensive, so rankings are cached.
        self.leaderboard_cache_ttl = int(
            cfg.get("leaderboard_cache_ttl_seconds", 300)
        )
        self._leaderboard_cache: dict[str, Any] = {
            "built_at": 0.0,
            "players": [],
            "guns": [],
            "weapon_players": {},
        }
        self.leaderboard_channel_id = int(
            cfg.get("leaderboard_channel_id", 1541562906892836986)
        )

        # Permanent JTWP public dashboard.
        self.dashboard_channel_id = int(
            cfg.get("dashboard_channel_id", 1541663723922399274)
        )
        self.dashboard_state_path = (
            self.data_root
            / "global"
            / "discord"
            / "dashboard_message.json"
        )
        self._dashboard_ready_done = False

        # Admin dashboard. Defaults to the same dashboard channel; change
        # admin_dashboard_channel_id in config.json if you want it elsewhere.
        self.admin_dashboard_channel_id = int(
            cfg.get("admin_dashboard_channel_id", 1541665529935429652)
        )
        self.admin_dashboard_state_path = (
            self.data_root
            / "global"
            / "discord"
            / "admin_dashboard_message.json"
        )
        self._admin_dashboard_ready_done = False
        self.leaderboard_update_hour_utc = int(
            cfg.get("leaderboard_update_hour_utc", 8)
        ) % 24
        self.leaderboard_messages_path = (
            self.data_root
            / "global"
            / "discord"
            / "leaderboard_messages.json"
        )
        self._last_daily_leaderboard_date: str | None = None

        # Badge image display settings.
        badge_display = cfg.get("badge_display", {})
        if not isinstance(badge_display, dict):
            badge_display = {}

        self.badges_per_image = max(
            1,
            min(10, int(badge_display.get("badges_per_image", 8))),
        )
        self.badge_image_size = max(
            32,
            min(256, int(badge_display.get("badge_size", 75))),
        )
        self.badge_image_gap = max(
            0,
            min(64, int(badge_display.get("gap", 4))),
        )
        self.badge_image_padding = max(
            0,
            min(64, int(badge_display.get("padding", 4))),
        )

        # Global badge definitions. Player-owned badges live in
        # players/records/<product_id>/badges.json.
        self.badges_registry_path = self.data_root / "global" / "badges.json"
        self.ensure_badge_registry()

        self.control_channel_id = int(
            self.bot_cfg.get("control_channel_id") or 0
        )

        roles = self.bot_cfg.get("roles", {})
        self.admin_role_id = int(roles.get("admin") or 0)
        self.owner_role_id = int(roles.get("owner") or 0)
        self.senior_admin_role_id = int(roles.get("senior_admin") or 0)

        self.admin_rcon = {
            str(x).casefold()
            for x in self.bot_cfg.get("admin_allowed_rcon_commands", [])
        }

        self.systemctl_actions = {
            str(x).casefold()
            for x in self.bot_cfg.get(
                "systemctl_actions",
                ["status", "start", "stop", "restart", "enable", "disable"],
            )
        }

        self.output_limit = int(
            self.bot_cfg.get("command_output_limit", 3500)
        )
        self.rcon_timeout = float(
            self.bot_cfg.get("rcon_timeout_seconds", 15)
        )

        self.audit_path = (
            self.data_root / "global" / "discord" / "commands.jsonl"
        )
        self.account_audit_path = (
            self.data_root / "global" / "discord" / "account_links.jsonl"
        )

        # Manually approved RCON/network connection hashes.  This is separate
        # from Discord/Steam account verification: a connection is verified
        # only when an administrator explicitly adds its stable IP hash here.
        self.verified_connections_path = (
            self.data_root / "global" / "rcon_security" / "verified_connections.json"
        )
        if not self.verified_connections_path.is_file():
            atomic_write_json(
                self.verified_connections_path,
                {
                    "version": 1,
                    "verified_connections": {},
                },
            )

        self.command_log_webhook_url = os.getenv("JTWP_COMMAND_LOG_WEBHOOK_URL", "").strip()
        self.moderation_log_webhook_url = os.getenv("JTWP_MODERATION_LOG_WEBHOOK_URL", "").strip()

        # Account-link approval alerts use the existing admin webhook by default.
        # Optional config overrides:
        #
        # "account_linking": {
        #   "pending_alert_enabled": true,
        #   "webhook_env": "JTWP_ADMIN_WEBHOOK_URL",
        #   "admin_role_id": "1540851171588177991"
        # }
        #
        # If account_linking is omitted, fall back to admin_notifications and
        # finally the Discord bot's configured admin role.
        self.account_link_cfg = cfg.get("account_linking", {})
        if not isinstance(self.account_link_cfg, dict):
            self.account_link_cfg = {}

        admin_notifications_cfg = cfg.get("admin_notifications", {})
        if not isinstance(admin_notifications_cfg, dict):
            admin_notifications_cfg = {}

        self.account_link_pending_alert_enabled = bool(
            self.account_link_cfg.get("pending_alert_enabled", True)
        )

        account_link_webhook_env = str(
            self.account_link_cfg.get("webhook_env")
            or admin_notifications_cfg.get("webhook_env")
            or "JTWP_ADMIN_WEBHOOK_URL"
        ).strip()
        self.account_link_webhook_env = account_link_webhook_env
        self.account_link_webhook_url = os.getenv(
            account_link_webhook_env,
            "",
        ).strip()

        try:
            self.account_link_admin_role_id = int(
                self.account_link_cfg.get("admin_role_id")
                or admin_notifications_cfg.get("admin_role_id")
                or self.admin_role_id
                or 0
            )
        except (TypeError, ValueError):
            self.account_link_admin_role_id = self.admin_role_id or 0

        self.steam_api_key = os.getenv("STEAM_WEB_API_KEY", "").strip()
        self.command_log_tailer = JsonlWebhookTailer(
            bot=self,
            source_path=self.audit_path,
            state_path=self.audit_path.with_name("commands_webhook_state.json"),
            webhook_url=self.command_log_webhook_url,
            title="🛡️ JTWP Command Log",
        )

        # Persistent DDoS/network dashboard.
        self.ddos_status_channel_id = int(
            self.bot_cfg.get("ddos_status_channel_id")
            or self.bot_cfg.get("network_ddos_channel_id")
            or self.control_channel_id
            or 0
        )
        self.ddos_status_state_path = (
            self.data_root / "global" / "network" / "ddos" / "discord_status.json"
        )
        self.ddos_refresh_seconds = max(
            15,
            int(self.bot_cfg.get("ddos_status_refresh_seconds", 30)),
        )
        self._last_ddos_refresh = 0.0

        self.servers: dict[str, dict[str, Any]] = {}
        for raw in cfg.get("servers", []):
            log_path = Path(raw["log_path"])
            server_root = log_path.parents[2]
            server_id = server_root.name
            self.servers[server_id] = {
                "server_id": server_id,
                "server_root": server_root,
                "rcon": raw.get("rcon", {}),
            }

        self.moderation = ModerationSystem(self)


    @tasks.loop(minutes=15)
    async def daily_leaderboard_loop(self):
        """Check periodically; update once on the configured UTC day/hour."""
        now = datetime.now(timezone.utc)
        today = now.date().isoformat()

        if now.hour < self.leaderboard_update_hour_utc:
            return
        if self._last_daily_leaderboard_date == today:
            return

        await self.update_daily_leaderboards()
        self._last_daily_leaderboard_date = today

    @daily_leaderboard_loop.before_loop
    async def before_daily_leaderboard_loop(self):
        await self.wait_until_ready()

    async def setup_hook(self) -> None:
        if not self.daily_leaderboard_loop.is_running():
            self.daily_leaderboard_loop.start()
        register_slash_commands(self)

        # Register the permanent dashboard buttons before Discord interactions
        # can arrive. custom_id values make the view persistent across restarts.
        self.add_view(JTWPDashboardView(self))
        self.add_view(JTWPAdminDashboardView(self))

        guild_id = (
            os.getenv("JTWP_DISCORD_GUILD_ID", "").strip()
            or str(self.bot_cfg.get("guild_id") or "").strip()
        )

        if guild_id:
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            print(
                f"Synced {len(synced)} slash command roots to guild {guild_id}.",
                flush=True,
            )
        else:
            synced = await self.tree.sync()
            print(
                f"Synced {len(synced)} global slash command roots.",
                flush=True,
            )

        if not self.moderation.expiry_loop.is_running():
            self.moderation.expiry_loop.start()
        if self.command_log_webhook_url and not self.command_log_tailer.loop.is_running():
            self.command_log_tailer.loop.start()
        if self.moderation_log_webhook_url and not self.moderation.webhook_tailer.loop.is_running():
            self.moderation.webhook_tailer.loop.start()
        if self.ddos_status_channel_id and not self.ddos_status_loop.is_running():
            self.ddos_status_loop.start()

    async def close(self) -> None:
        if self.moderation.expiry_loop.is_running():
            self.moderation.expiry_loop.cancel()
        if self.command_log_tailer.loop.is_running():
            self.command_log_tailer.loop.cancel()
        if self.moderation.webhook_tailer.loop.is_running():
            self.moderation.webhook_tailer.loop.cancel()
        if self.ddos_status_loop.is_running():
            self.ddos_status_loop.cancel()
        await super().close()

    def role_ids(self, member: discord.Member) -> set[int]:
        return {role.id for role in getattr(member, "roles", [])}

    def permission_level(self, member: discord.Member | discord.User) -> str:
        if not isinstance(member, discord.Member):
            return "NONE"

        ids = self.role_ids(member)

        if self.owner_role_id and self.owner_role_id in ids:
            return "OWNER"

        if self.admin_role_id and self.admin_role_id in ids:
            return "ADMIN"

        return "NONE"

    def is_senior(self, member: discord.Member | discord.User) -> bool:
        if not isinstance(member, discord.Member):
            return False
        if self.permission_level(member) == "OWNER":
            return True
        return bool(
            self.senior_admin_role_id
            and self.senior_admin_role_id in self.role_ids(member)
        )

    def audit(
        self,
        interaction: discord.Interaction | None,
        event: str,
        success: bool,
        **extra: Any,
    ) -> None:
        actor = interaction.user if interaction else None
        append_jsonl(
            self.audit_path,
            {
                "timestamp": now_iso(),
                "type": event,
                "success": success,
                "discord_user_id": str(actor.id) if actor else None,
                "discord_username": str(actor) if actor else None,
                "permission": (
                    self.permission_level(actor)
                    if isinstance(actor, discord.Member)
                    else "SYSTEM"
                ),
                **extra,
            },
        )

    async def require(
        self,
        interaction: discord.Interaction,
        *,
        admin: bool = True,
        owner: bool = False,
        senior: bool = False,
        control_channel: bool = True,
    ) -> bool:
        if interaction.guild is None:
            await respond(
                interaction,
                "⛔ This command must be used in the JTWP Discord server.",
                ephemeral=True,
            )
            return False

        if (
            control_channel
            and self.control_channel_id
            and interaction.channel_id != self.control_channel_id
        ):
            await respond(
                interaction,
                f"⛔ Use this command in <#{self.control_channel_id}>.",
                ephemeral=True,
            )
            return False

        member = interaction.user
        level = self.permission_level(member)

        allowed = True

        if owner:
            allowed = level == "OWNER"
        elif senior:
            allowed = self.is_senior(member)
        elif admin:
            allowed = level in {"ADMIN", "OWNER"}

        if not allowed:
            await respond(
                interaction,
                "⛔ You do not have permission to use this command.",
                ephemeral=True,
            )
            return False

        return True

    async def rcon_send(self, server_id: str, command: str) -> Any:
        if server_id not in self.servers:
            raise ValueError(f"Unknown server: {server_id}")

        rcon = self.servers[server_id]["rcon"]

        if not rcon.get("enabled", False):
            raise RuntimeError(f"RCON is disabled for {server_id}")

        password_env = str(rcon.get("password_env") or "")
        password = os.getenv(password_env, "").strip()

        if not password:
            raise RuntimeError(
                f"Missing environment variable: {password_env}"
            )

        client = PavlovRCON(
            str(rcon.get("host", "127.0.0.1")),
            int(rcon["port"]),
            password,
        )

        return await asyncio.wait_for(
            client.send(command),
            timeout=self.rcon_timeout,
        )

    async def read_ddos_stats(self) -> dict[str, Any]:
        result = await asyncio.to_thread(
            subprocess.run,
            ["sudo", "-n", "/usr/local/bin/jtwp-read-ddos-stats"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Failed to read network stats")
        data = json.loads(result.stdout)
        if not isinstance(data, dict):
            raise RuntimeError("DDoS stats helper returned invalid JSON")
        return data

    def ddos_status_embed(self, data: dict[str, Any]) -> discord.Embed:
        ports = data.get("destination_ports", {})
        top_ports = (
            sorted(ports.items(), key=lambda kv: int(kv[1]), reverse=True)[:10]
            if isinstance(ports, dict)
            else []
        )
        port_text = "\n".join(f"{port:<6} {count}" for port, count in top_ports) or "None"

        reasons = data.get("trigger_reasons", [])
        triggered = bool(reasons) or bool(
            data.get("attack_detected")
            or data.get("triggered")
            or data.get("under_attack")
        )

        status = "🔴 ATTACK / TRIGGERED" if triggered else "🟢 NORMAL"
        trigger_text = "\n".join(map(str, reasons)) if reasons else "✅ No trigger reasons"

        embed = discord.Embed(
            title="🛡️ JTWP Network / DDoS Status",
            description=(
                "----------------------------------------------\n"
                f"### {status}\n"
                "Continuously updated network security summary.\n"
                "----------------------------------------------"
            ),
            color=15548997 if triggered else 3618621,
            timestamp=utc_now(),
        )
        embed.add_field(
            name="📊 Current Traffic",
            value=(
                f"Window: `{int(data.get('window_seconds', 0)):,}s`\n"
                f"Packets: `{int(data.get('packets', 0)):,}`\n"
                f"Sources: `{int(data.get('unique_sources', 0)):,}`\n"
                f"Total Bytes: `{int(data.get('bytes', 0)):,}`"
            ),
            inline=True,
        )
        embed.add_field(
            name="📈 Rates",
            value=(
                f"Packets/sec: `{float(data.get('packets_per_second', 0)):,.2f}`\n"
                f"Bytes/sec: `{float(data.get('bytes_per_second', 0)):,.2f}`\n"
                f"Highest Source PPS: "
                f"`{float(data.get('highest_source_packets_per_second', 0)):,.2f}`"
            ),
            inline=True,
        )
        embed.add_field(
            name="🚪 Top Destination Ports",
            value=f"```text\n{port_text}\n```",
            inline=False,
        )
        embed.add_field(
            name="🚨 Detection",
            value=clip(trigger_text, 1000),
            inline=False,
        )
        embed.set_footer(
            text=(
                f"JTWP Network Security • Stats: "
                f"{data.get('timestamp', 'Unknown')} • No raw source IPs displayed"
            )
        )
        return embed

    async def refresh_ddos_status(self, *, create_if_missing: bool = True) -> discord.Message | None:
        if not self.ddos_status_channel_id:
            return None

        data = await self.read_ddos_stats()
        embed = self.ddos_status_embed(data)
        state = load_json(self.ddos_status_state_path, {})
        if not isinstance(state, dict):
            state = {}

        channel = self.get_channel(self.ddos_status_channel_id)
        if channel is None:
            channel = await self.fetch_channel(self.ddos_status_channel_id)

        message_id = 0
        try:
            message_id = int(state.get("message_id") or 0)
        except (TypeError, ValueError):
            message_id = 0

        message = None
        if message_id:
            try:
                message = await channel.fetch_message(message_id)
                await message.edit(embed=embed)
            except discord.NotFound:
                message = None
            except discord.Forbidden:
                raise RuntimeError("Bot cannot edit the configured DDoS status message")

        if message is None and create_if_missing:
            message = await channel.send(embed=embed)

        if message is not None:
            atomic_write_json(
                self.ddos_status_state_path,
                {
                    "channel_id": str(message.channel.id),
                    "message_id": str(message.id),
                    "updated_at": now_iso(),
                },
            )
        return message

    @tasks.loop(seconds=15)
    async def ddos_status_loop(self) -> None:
        now = time.monotonic()
        if now - self._last_ddos_refresh < self.ddos_refresh_seconds:
            return
        self._last_ddos_refresh = now
        try:
            await self.refresh_ddos_status(create_if_missing=True)
        except Exception as exc:
            print(
                f"DDoS status update error: {type(exc).__name__}: {exc}",
                flush=True,
            )

    @ddos_status_loop.before_loop
    async def before_ddos_status_loop(self) -> None:
        await self.wait_until_ready()

    def player_path(self, product_id: str) -> Path:
        return self.data_root / "players" / "records" / product_id / "player.json"

    def save_player(self, product_id: str, player: dict[str, Any]) -> None:
        atomic_write_json(self.player_path(product_id), player)

    def rebuild_link_indexes(self) -> None:
        records = self.data_root / "players" / "records"
        by_discord: dict[str, str] = {}
        by_steam: dict[str, str] = {}
        for path in records.glob("*/player.json"):
            player = load_json(path, {})
            if not isinstance(player, dict):
                continue
            pid = str(player.get("product_id") or path.parent.name)
            linked = player.get("linked_accounts", {})
            if not isinstance(linked, dict):
                continue
            d = linked.get("discord")
            s = linked.get("steam")
            if isinstance(d, dict) and d.get("user_id"):
                by_discord[str(d["user_id"])] = pid
            if isinstance(s, dict) and s.get("steam_id"):
                by_steam[str(s["steam_id"])] = pid
        index = self.data_root / "players" / "index"
        atomic_write_json(index / "by_discord_id.json", dict(sorted(by_discord.items())))
        atomic_write_json(index / "by_steam_id.json", dict(sorted(by_steam.items())))

    def steam_summary(self, steam_id: str) -> dict[str, Any]:
        if not self.steam_api_key:
            raise RuntimeError("STEAM_WEB_API_KEY is not set")
        steam_id = str(steam_id).strip()
        if not steam_id.isdigit() or len(steam_id) != 17:
            raise ValueError("Steam ID must be a 17-digit SteamID64")
        r = requests.get(
            "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/",
            params={"key": self.steam_api_key, "steamids": steam_id},
            headers={"User-Agent": "JTWP-Discord-Bot/1.0"},
            timeout=10,
        )
        r.raise_for_status()
        players = r.json().get("response", {}).get("players", [])
        if not players:
            raise ValueError("Steam profile was not returned by Steam Web API")
        p = players[0]
        return {
            "steam_id": str(p.get("steamid") or steam_id),
            "username": p.get("personaname"),
            "profile_url": p.get("profileurl"),
            "avatar_url": p.get("avatarfull") or p.get("avatarmedium") or p.get("avatar"),
            "visibility": p.get("communityvisibilitystate"),
            "last_logoff": p.get("lastlogoff"),
            "last_updated": now_iso(),
            "verified_by_api": True,
        }

    def log_account_event(self, event: str, product_id: str, actor: discord.abc.User, **extra: Any) -> None:
        append_jsonl(self.account_audit_path, {
            "timestamp": now_iso(),
            "event": event,
            "product_id": product_id,
            "discord_user_id": str(actor.id),
            "discord_username": str(actor),
            **extra,
        })

    def post_account_link_pending_webhook(
        self,
        *,
        request_id: str,
        product_id: str,
        player_doc: dict[str, Any],
        requester: discord.abc.User,
        steam_id: str | None = None,
        steam_error: str | None = None,
    ) -> bool:
        """Notify admins that an account-link request is awaiting approval.

        A webhook failure does not roll back the player's pending request. The
        request remains recorded in player.json and account_links.jsonl.
        """
        if not self.account_link_pending_alert_enabled:
            return False

        if not self.account_link_webhook_url:
            print(
                "Account-link pending alert skipped: "
                f"{self.account_link_webhook_env} is not configured.",
                flush=True,
            )
            return False

        linked = player_doc.get("linked_accounts", {})
        if not isinstance(linked, dict):
            linked = {}
        steam = linked.get("steam", {})
        if not isinstance(steam, dict):
            steam = {}

        player_name = player_doc.get("current_name") or player_doc.get("name") or "Unknown"
        platform = str(player_doc.get("platform") or "Unknown")
        unique_id = str(player_doc.get("unique_id") or "Unknown")
        requester_name = str(requester)
        requester_display = getattr(requester, "display_name", requester_name)
        role_id = int(self.account_link_admin_role_id or 0)

        content = f"<@&{role_id}>\n" if role_id else ""
        content += (
            "----------------------------------------------\n"
            "--  🔗  **Account Link Pending Approval**  🔗  --\n"
            "----------------------------------------------"
        )

        fields: list[dict[str, Any]] = [
            {"name": "👤 Discord User", "value": f"<@{requester.id}>\n`{clip(requester_name, 180)}`\nID: `{requester.id}`", "inline": True},
            {"name": "🎮 Player", "value": f"Name: `{clip(player_name, 180)}`\nPlatform: `{clip(platform, 80)}`", "inline": True},
            {"name": "🆔 Product ID", "value": f"`{clip(product_id, 200)}`", "inline": False},
            {"name": "🔑 Unique ID", "value": f"`{clip(unique_id, 300)}`", "inline": False},
            {"name": "📋 Request ID", "value": f"`{request_id}`", "inline": True},
            {"name": "⏳ Status", "value": "`Pending Admin Review`", "inline": True},
            {"name": "✅ Admin Action", "value": f"`/account approve product_id:{product_id}`", "inline": False},
        ]

        resolved_steam_id = str(steam.get("steam_id") or steam_id or "").strip()
        steam_username = str(steam.get("username") or "").strip()
        steam_profile_url = str(steam.get("profile_url") or "").strip()
        if resolved_steam_id or steam_username:
            steam_lines = []
            if steam_username:
                steam_lines.append(f"Name: `{clip(steam_username, 180)}`")
            if resolved_steam_id:
                steam_lines.append(f"SteamID64: `{clip(resolved_steam_id, 40)}`")
            if steam_profile_url:
                steam_lines.append(f"[Open Steam Profile]({steam_profile_url})")
            fields.append({"name": "🖥️ Steam", "value": "\n".join(steam_lines), "inline": False})

        if steam_error:
            fields.append({"name": "⚠️ Steam Lookup", "value": f"`{clip(steam_error, 900)}`", "inline": False})

        embed: dict[str, Any] = {
            "title": "🔗 Account Link Pending Approval",
            "description": "A player has requested to link their Discord account to a JTWP player profile. An admin must review and approve the link.",
            "color": 3618621,
            "fields": fields[:25],
            "footer": {"text": f"JTWP Account Linking • {request_id} • Requested by {requester_display}"},
            "timestamp": now_iso(),
        }
        avatar = getattr(getattr(requester, "display_avatar", None), "url", None)
        if avatar:
            embed["thumbnail"] = {"url": str(avatar)}

        payload: dict[str, Any] = {"content": content, "embeds": [embed]}
        payload["allowed_mentions"] = {
            "parse": [],
            "roles": [str(role_id)] if role_id else [],
            "users": [str(requester.id)],
        }

        last_error = None
        for attempt in range(3):
            try:
                response = requests.post(self.account_link_webhook_url, json=payload, timeout=10)
                if response.status_code in {200, 204}:
                    return True
                if response.status_code == 429:
                    try:
                        retry_after = float(response.json().get("retry_after", 1.0))
                    except Exception:
                        retry_after = 1.0
                    time.sleep(max(0.25, min(retry_after, 10.0)))
                    continue
                last_error = f"HTTP {response.status_code}: {response.text[:300]}"
            except requests.RequestException as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            if attempt < 2:
                time.sleep(attempt + 1)

        print(f"Account-link pending webhook failed: {last_error or 'unknown error'}", flush=True)
        return False


    def ensure_badge_registry(self) -> None:
        """Create/merge the global badge registry without removing custom badges."""
        data = load_json(
            self.badges_registry_path,
            {"version": 1, "badges": {}},
        )
        if not isinstance(data, dict):
            data = {"version": 1, "badges": {}}

        badges = data.get("badges")
        if not isinstance(badges, dict):
            badges = {}
            data["badges"] = badges

        changed = False
        for name, definition in DEFAULT_BADGES.items():
            current = badges.get(name)
            if not isinstance(current, dict):
                badges[name] = dict(definition)
                changed = True
                continue
            for key, value in definition.items():
                if key not in current:
                    current[key] = value
                    changed = True

        data["version"] = 1
        if changed or not self.badges_registry_path.is_file():
            atomic_write_json(self.badges_registry_path, data)

    def load_badge_registry(self) -> dict[str, Any]:
        self.ensure_badge_registry()
        data = load_json(
            self.badges_registry_path,
            {"version": 1, "badges": {}},
        )
        if not isinstance(data, dict):
            return {"version": 1, "badges": {}}
        if not isinstance(data.get("badges"), dict):
            data["badges"] = {}
        return data

    def player_badges_path(self, product_id: str) -> Path:
        return (
            self.data_root
            / "players"
            / "records"
            / str(product_id)
            / "badges.json"
        )

    def load_player_badges(self, product_id: str) -> dict[str, Any]:
        data = load_json(
            self.player_badges_path(product_id),
            {
                "version": 1,
                "product_id": str(product_id),
                "badges": {},
            },
        )
        if not isinstance(data, dict):
            data = {
                "version": 1,
                "product_id": str(product_id),
                "badges": {},
            }
        if not isinstance(data.get("badges"), dict):
            data["badges"] = {}
        data["version"] = 1
        data["product_id"] = str(product_id)
        return data

    def award_badge(
        self,
        product_id: str,
        badge_name: str,
        *,
        awarded_by: str,
        awarded_by_discord_id: str | None = None,
        reason: str | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        """Award a registered badge once. Returns (newly_awarded, record)."""
        product_id = str(product_id).strip()

        registry = self.load_badge_registry()
        available = registry.get("badges", {})
        if not isinstance(available, dict):
            available = {}

        canonical_name = next(
            (
                str(name)
                for name in available.keys()
                if str(name).casefold() == str(badge_name).strip().casefold()
            ),
            None,
        )
        if canonical_name is None:
            raise ValueError(f"Unknown badge: {badge_name}")

        if not self.player_path(product_id).is_file():
            raise ValueError(f"Player record not found: {product_id}")

        data = self.load_player_badges(product_id)
        owned = data.setdefault("badges", {})

        existing = owned.get(canonical_name)
        if isinstance(existing, dict):
            return False, existing

        record = {
            "name": canonical_name,
            "awarded_at": now_iso(),
            "awarded_by": str(awarded_by),
            "awarded_by_discord_id": (
                str(awarded_by_discord_id)
                if awarded_by_discord_id
                else None
            ),
            "reason": str(reason).strip() if reason else None,
        }

        owned[canonical_name] = record
        atomic_write_json(self.player_badges_path(product_id), data)
        return True, record

    def ensure_discord_link_badge(
        self,
        product_id: str,
        player_doc: dict[str, Any] | None = None,
    ) -> bool:
        """Award badge #001 to any profile with a linked Discord account."""
        if player_doc is None:
            player_doc = load_json(self.player_path(product_id), {})

        if not isinstance(player_doc, dict):
            return False

        linked = player_doc.get("linked_accounts", {})
        if not isinstance(linked, dict):
            return False

        discord_link = linked.get("discord")
        if not isinstance(discord_link, dict) or not discord_link.get("user_id"):
            return False

        try:
            newly_awarded, _ = self.award_badge(
                product_id,
                BADGE_DISCORD_LINK,
                awarded_by="system:discord_link",
                awarded_by_discord_id=str(discord_link.get("user_id")),
                reason="Discord account linked to JTWP player profile.",
            )
            return newly_awarded
        except ValueError:
            return False


    def build_badge_strip_images(
        self,
        badge_rows: list[tuple[str, dict[str, Any], dict[str, Any]]],
    ) -> list[io.BytesIO]:
        """Build multiple transparent badge strips.

        Each image contains at most self.badges_per_image visible badge icons.
        Badges with blank/broken image URLs are skipped visually but remain
        owned in the player's badge data.
        """
        badge_size = self.badge_image_size
        gap = self.badge_image_gap
        padding = self.badge_image_padding
        per_image = self.badges_per_image

        tiles: list[Image.Image] = []

        for _badge_name, definition, _award in badge_rows:
            url = str(definition.get("url") or "").strip()
            if not url:
                continue

            try:
                response = requests.get(
                    url,
                    timeout=10,
                    headers={"User-Agent": "JTWP-Discord-Bot/1.0"},
                )
                response.raise_for_status()

                with Image.open(io.BytesIO(response.content)) as source:
                    source = source.convert("RGBA")
                    source.thumbnail(
                        (badge_size, badge_size),
                        Image.Resampling.LANCZOS,
                    )

                    tile = Image.new(
                        "RGBA",
                        (badge_size, badge_size),
                        (0, 0, 0, 0),
                    )
                    x = (badge_size - source.width) // 2
                    y = (badge_size - source.height) // 2
                    tile.alpha_composite(source, (x, y))
                    tiles.append(tile)

            except Exception as exc:
                print(
                    "Badge image download failed: "
                    f"{type(exc).__name__}: {exc} • {url}",
                    flush=True,
                )

        outputs: list[io.BytesIO] = []

        for offset in range(0, len(tiles), per_image):
            group = tiles[offset:offset + per_image]
            if not group:
                continue

            width = (
                padding * 2
                + len(group) * badge_size
                + max(0, len(group) - 1) * gap
            )
            height = badge_size + padding * 2

            strip = Image.new(
                "RGBA",
                (width, height),
                (0, 0, 0, 0),
            )

            x = padding
            for tile in group:
                strip.alpha_composite(tile, (x, padding))
                x += badge_size + gap

            output = io.BytesIO()
            strip.save(output, format="PNG", optimize=True)
            output.seek(0)
            outputs.append(output)

        return outputs

    def revoke_badge(
        self,
        product_id: str,
        badge_name: str,
    ) -> tuple[bool, str | None]:
        """Remove an owned badge. Returns (removed, canonical_name)."""
        product_id = str(product_id).strip()
        data = self.load_player_badges(product_id)
        owned = data.get("badges", {})
        if not isinstance(owned, dict):
            return False, None

        canonical_name = next(
            (
                str(name)
                for name in owned.keys()
                if str(name).casefold() == str(badge_name).strip().casefold()
            ),
            None,
        )
        if canonical_name is None:
            return False, None

        owned.pop(canonical_name, None)
        atomic_write_json(self.player_badges_path(product_id), data)
        return True, canonical_name

    @staticmethod
    def _badge_number(value: Any) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    def _badge_stat_value(
        self,
        stats: dict[str, Any],
        stat_name: str,
    ) -> float:
        """Read common collector stat layouts without assuming one exact schema."""
        aliases = {
            "kills": ("kills", "total_kills", "lifetime_kills"),
            "headshots": ("headshots", "total_headshots", "lifetime_headshots"),
            "times_connected": ("times_connected", "connections", "total_connections"),
            "teamkills": ("teamkills", "team_kills", "total_teamkills"),
            "deaths": ("deaths", "total_deaths"),
            "suicides": ("suicides", "total_suicides"),
            "bot_kills": ("bot_kills", "total_bot_kills"),
            "bot_headshots": ("bot_headshots", "total_bot_headshots"),
            "matches": ("matches", "total_matches"),
        }
        keys = aliases.get(stat_name, (stat_name,))

        containers: list[dict[str, Any]] = [stats]
        for key in ("lifetime", "totals", "stats", "career", "combat", "activity"):
            nested = stats.get(key)
            if isinstance(nested, dict):
                containers.append(nested)

        for container in containers:
            for key in keys:
                if key in container:
                    return self._badge_number(container.get(key))
        return 0.0

    def _badge_player_age_days(self, player_doc: dict[str, Any]) -> int:
        value = str(player_doc.get("first_seen") or "").strip()
        if not value:
            return 0

        parsed = None
        for fmt in (
            "%Y.%m.%d-%H.%M.%S:%f",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S%z",
        ):
            try:
                parsed = datetime.strptime(value, fmt)
                break
            except ValueError:
                pass

        if parsed is None:
            return 0
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0, (utc_now() - parsed.astimezone(timezone.utc)).days)

    def _badge_weapon_doc(self, product_id: str) -> dict[str, Any]:
        data = load_json(
            self.data_root / "players" / "records" / product_id / "weapons.json",
            {},
        )
        return data if isinstance(data, dict) else {}

    def _badge_weapon_kills(
        self,
        product_id: str,
        names: list[str],
    ) -> int:
        doc = self._badge_weapon_doc(product_id)
        weapons = doc.get("weapons", {})
        if not isinstance(weapons, dict):
            return 0

        wanted = {str(x).casefold() for x in names}
        total = 0
        for weapon_name, rec in weapons.items():
            if str(weapon_name).casefold() not in wanted:
                continue
            if isinstance(rec, dict):
                total += int(rec.get("kills", 0) or 0)
        return total

    def _badge_weapon_type_count(
        self,
        product_id: str,
        minimum_kills_each: int,
    ) -> int:
        doc = self._badge_weapon_doc(product_id)
        weapons = doc.get("weapons", {})
        if not isinstance(weapons, dict):
            return 0
        return sum(
            1
            for rec in weapons.values()
            if isinstance(rec, dict)
            and int(rec.get("kills", 0) or 0) >= minimum_kills_each
        )

    def _badge_name_count(self, product_id: str) -> int:
        doc = load_json(
            self.data_root / "players" / "records" / product_id / "names.json",
            {},
        )
        if not isinstance(doc, dict):
            return 0
        names = doc.get("names", {})
        if isinstance(names, dict):
            return len(names)
        if isinstance(names, list):
            return len(names)
        return 0

    def _badge_ip_hash_count(
        self,
        product_id: str,
        player_doc: dict[str, Any],
    ) -> int:
        network = player_doc.get("network", {})
        if isinstance(network, dict):
            try:
                count = int(network.get("known_ip_count", 0) or 0)
                if count:
                    return count
            except (TypeError, ValueError):
                pass

        doc = load_json(
            self.data_root / "players" / "records" / product_id / "ips.json",
            {},
        )
        if not isinstance(doc, dict):
            return 0

        ips = doc.get("ips")
        if isinstance(ips, dict):
            return len(ips)
        if isinstance(ips, list):
            return len(ips)

        hashes = doc.get("ip_hashes")
        if isinstance(hashes, dict):
            return len(hashes)
        if isinstance(hashes, list):
            return len(hashes)

        return 0

    def _badge_has_ban_history(
        self,
        product_id: str,
        player_doc: dict[str, Any],
    ) -> bool:
        if bool(player_doc.get("banned")):
            return True
        banned_servers = player_doc.get("banned_servers", [])
        if isinstance(banned_servers, (list, dict, set, tuple)) and len(banned_servers) > 0:
            return True

        history = (
            self.data_root
            / "players"
            / "records"
            / product_id
            / "moderation"
            / "bans.jsonl"
        )
        if history.is_file():
            try:
                return any(line.strip() for line in history.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines())
            except OSError:
                pass
        return False

    def evaluate_automatic_badges(
        self,
        product_id: str,
        *,
        player_doc: dict[str, Any] | None = None,
        stats_doc: dict[str, Any] | None = None,
    ) -> list[str]:
        """Evaluate registry criteria and award every automatic badge earned."""
        product_id = str(product_id).strip()
        if player_doc is None:
            player_doc = load_json(self.player_path(product_id), {})
        if not isinstance(player_doc, dict):
            player_doc = {}

        if stats_doc is None:
            stats_doc = load_json(
                self.data_root / "players" / "records" / product_id / "stats.json",
                {},
            )
        if not isinstance(stats_doc, dict):
            stats_doc = {}

        registry = self.load_badge_registry()
        definitions = registry.get("badges", {})
        if not isinstance(definitions, dict):
            return []

        awarded: list[str] = []

        for badge_name, definition in definitions.items():
            if not isinstance(definition, dict):
                continue
            if definition.get("automatic") is not True:
                continue

            criteria = definition.get("criteria")
            if not isinstance(criteria, dict):
                continue

            kind = str(criteria.get("type") or "").strip().casefold()
            earned = False
            reason = None

            if kind == "discord_link":
                linked = player_doc.get("linked_accounts", {})
                discord_link = linked.get("discord") if isinstance(linked, dict) else None
                earned = isinstance(discord_link, dict) and bool(discord_link.get("user_id"))
                reason = "Discord account linked to JTWP player profile."

            elif kind == "stat_gte":
                stat_name = str(criteria.get("stat") or "").strip()
                threshold = self._badge_number(criteria.get("threshold"))
                current = self._badge_stat_value(stats_doc, stat_name)
                earned = current >= threshold
                reason = f"Automatic badge: {stat_name} {current:g} >= {threshold:g}."

            elif kind == "account_age_days":
                threshold = int(self._badge_number(criteria.get("threshold")))
                current = self._badge_player_age_days(player_doc)
                earned = current >= threshold
                reason = f"Automatic badge: player age {current} days >= {threshold} days."

            elif kind == "player_admin":
                earned = bool(player_doc.get("admin"))
                reason = "Automatic badge: JTWP player profile is marked as staff/admin."

            elif kind == "vpn_or_proxy":
                network = player_doc.get("network", {})
                background = (
                    network.get("current_background")
                    if isinstance(network, dict)
                    else None
                )
                if isinstance(background, dict):
                    earned = any(
                        background.get(key) is True
                        for key in ("vpn", "proxy")
                    )
                reason = "Automatic badge: VPN/proxy flag detected in player network background."

            elif kind == "negative_kd":
                kills = self._badge_stat_value(stats_doc, "kills")
                deaths = self._badge_stat_value(stats_doc, "deaths")
                earned = deaths > kills
                reason = f"Automatic badge: negative K/D ({kills:g} K / {deaths:g} D)."

            elif kind in {"ip_hash_count_gt", "ip_hash_count_gte"}:
                current = self._badge_ip_hash_count(product_id, player_doc)
                threshold = int(self._badge_number(criteria.get("threshold")))
                earned = (
                    current > threshold
                    if kind.endswith("_gt")
                    else current >= threshold
                )
                reason = f"Automatic badge: {current} unique IP hashes."

            elif kind in {"name_count_gt", "name_count_gte"}:
                current = self._badge_name_count(product_id)
                threshold = int(self._badge_number(criteria.get("threshold")))
                earned = (
                    current > threshold
                    if kind.endswith("_gt")
                    else current >= threshold
                )
                reason = f"Automatic badge: {current} recorded names."

            elif kind == "banned_history":
                earned = self._badge_has_ban_history(product_id, player_doc)
                reason = "Automatic badge: current or historical JTWP ban record exists."

            elif kind == "platform_is":
                wanted = str(criteria.get("platform") or "").casefold()
                current = str(player_doc.get("platform") or "").casefold()
                earned = bool(wanted and current == wanted)
                reason = f"Automatic badge: platform is {criteria.get('platform')}."

            elif kind == "all_active_servers":
                seen = player_doc.get("servers_seen", [])
                seen_set = {
                    str(x)
                    for x in seen
                } if isinstance(seen, list) else set()
                active = {
                    str(server_id)
                    for server_id, rec in self.servers.items()
                    if not isinstance(rec, dict)
                    or rec.get("enabled", True) is not False
                }
                earned = bool(active) and active.issubset(seen_set)
                reason = (
                    f"Automatic badge: connected to all {len(active)} active JTWP servers."
                )

            elif kind == "weapon_kills_sum_gte":
                weapon_names = criteria.get("weapons", [])
                if not isinstance(weapon_names, list):
                    weapon_names = []
                threshold = int(self._badge_number(criteria.get("threshold")))
                current = self._badge_weapon_kills(product_id, weapon_names)
                earned = current >= threshold
                reason = (
                    f"Automatic badge: {current} combined kills with "
                    f"{', '.join(map(str, weapon_names))}."
                )

            elif kind == "weapon_types_gte":
                threshold = int(self._badge_number(criteria.get("threshold")))
                minimum_each = int(
                    self._badge_number(criteria.get("minimum_kills_each"))
                )
                current = self._badge_weapon_type_count(product_id, minimum_each)
                earned = current >= threshold
                reason = (
                    f"Automatic badge: {current} weapons with at least "
                    f"{minimum_each} kill(s) each."
                )

            elif kind == "total_time_online_gte":
                activity = stats_doc.get("activity", {})
                seconds = (
                    int(activity.get("total_time_online_seconds", 0) or 0)
                    if isinstance(activity, dict)
                    else 0
                )
                threshold = int(self._badge_number(criteria.get("seconds")))
                earned = seconds >= threshold
                reason = f"Automatic badge: {seconds:,} recorded online seconds."

            if not earned:
                continue

            try:
                newly_awarded, _record = self.award_badge(
                    product_id,
                    str(badge_name),
                    awarded_by="system:auto_badges",
                    reason=reason,
                )
                if newly_awarded:
                    awarded.append(str(badge_name))
            except ValueError:
                continue

        return awarded

    def backfill_automatic_badges(
        self,
        *,
        limit: int | None = None,
    ) -> dict[str, int]:
        """Evaluate automatic badges for existing player records."""
        records_dir = self.data_root / "players" / "records"
        checked = 0
        awarded = 0
        players_awarded = 0

        if not records_dir.is_dir():
            return {"checked": 0, "awarded": 0, "players_awarded": 0}

        for player_dir in records_dir.iterdir():
            if not player_dir.is_dir():
                continue
            product_id = player_dir.name
            if not self.player_path(product_id).is_file():
                continue

            new_badges = self.evaluate_automatic_badges(product_id)
            checked += 1
            if new_badges:
                awarded += len(new_badges)
                players_awarded += 1

            if limit is not None and checked >= int(limit):
                break

        return {
            "checked": checked,
            "awarded": awarded,
            "players_awarded": players_awarded,
        }


    def build_leaderboard_cache(
        self,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        """Build cached public rankings from durable player stats.

        Sources:
          players/index/by_product_id.json
          players/records/<pid>/stats.json
          players/records/<pid>/weapons.json

        No private/network information is included.
        """
        now = time.time()
        cached_at = float(
            self._leaderboard_cache.get("built_at", 0.0) or 0.0
        )
        if (
            not force
            and cached_at > 0
            and (now - cached_at) < self.leaderboard_cache_ttl
        ):
            return self._leaderboard_cache

        index_path = (
            self.data_root
            / "players"
            / "index"
            / "by_product_id.json"
        )
        player_index = load_json(index_path, {})
        if not isinstance(player_index, dict):
            player_index = {}

        records_root = (
            self.data_root
            / "players"
            / "records"
        )

        rows: list[dict[str, Any]] = []
        gun_totals: dict[str, int] = {}
        weapon_players: dict[str, list[dict[str, Any]]] = {}

        for stats_path in records_root.glob("*/stats.json"):
            product_id = stats_path.parent.name
            stats = load_json(stats_path, {})
            if not isinstance(stats, dict):
                continue

            combat = stats.get("combat", {})
            activity = stats.get("activity", {})
            if not isinstance(combat, dict):
                combat = {}
            if not isinstance(activity, dict):
                activity = {}

            index_entry = player_index.get(product_id, {})
            if not isinstance(index_entry, dict):
                index_entry = {}

            name = str(
                index_entry.get("current_name")
                or product_id
            )

            kills = int(combat.get("kills", 0) or 0)
            deaths = int(combat.get("deaths", 0) or 0)

            row = {
                "product_id": product_id,
                "name": name,
                "kills": kills,
                "deaths": deaths,
                "headshots": int(
                    combat.get("headshots", 0) or 0
                ),
                "bot_kills": int(
                    combat.get("bot_kills", 0) or 0
                ),
                "bot_headshots": int(
                    combat.get("bot_headshots", 0) or 0
                ),
                "teamkills": int(
                    combat.get("teamkills", 0) or 0
                ),
                "suicides": int(
                    combat.get("suicides", 0) or 0
                ),
                "deaths_by_bots": int(
                    combat.get("deaths_by_bots", 0) or 0
                ),
                "times_connected": int(
                    activity.get("times_connected", 0) or 0
                ),
                "matches": int(
                    activity.get("matches", 0) or 0
                ),
                "kd": (
                    round(kills / deaths, 2)
                    if deaths > 0
                    else float(kills)
                ),
            }
            rows.append(row)

            weapons_path = stats_path.parent / "weapons.json"
            weapons_doc = load_json(weapons_path, {})
            if not isinstance(weapons_doc, dict):
                continue

            weapons = weapons_doc.get("weapons", {})
            if not isinstance(weapons, dict):
                continue

            for weapon_name, weapon_stats in weapons.items():
                if not isinstance(weapon_stats, dict):
                    continue

                weapon_kills = int(
                    weapon_stats.get("kills", 0) or 0
                )
                if weapon_kills <= 0:
                    continue

                display_weapon = str(weapon_name)
                key = display_weapon.casefold()

                gun_totals[key] = (
                    int(gun_totals.get(key, 0))
                    + weapon_kills
                )

                weapon_players.setdefault(key, []).append({
                    "product_id": product_id,
                    "name": name,
                    "weapon": display_weapon,
                    "kills": weapon_kills,
                    "headshots": int(
                        weapon_stats.get("headshots", 0) or 0
                    ),
                })

        # Sort per-weapon player rankings once while the cache is built.
        for key, values in weapon_players.items():
            values.sort(
                key=lambda row: (
                    int(row.get("kills", 0)),
                    int(row.get("headshots", 0)),
                ),
                reverse=True,
            )

        # Preserve a nice display name for global weapon totals.
        gun_display_names: dict[str, str] = {}
        for values in weapon_players.values():
            for row in values:
                key = str(row.get("weapon", "")).casefold()
                if key and key not in gun_display_names:
                    gun_display_names[key] = str(
                        row.get("weapon")
                    )

        guns = [
            {
                "weapon": gun_display_names.get(key, key),
                "kills": total,
            }
            for key, total in gun_totals.items()
        ]
        guns.sort(
            key=lambda row: int(row.get("kills", 0)),
            reverse=True,
        )

        self._leaderboard_cache = {
            "built_at": now,
            "players": rows,
            "guns": guns,
            "weapon_players": weapon_players,
        }
        return self._leaderboard_cache

    @staticmethod
    def leaderboard_medal(rank: int) -> str:
        if rank == 1:
            return "🥇"
        if rank == 2:
            return "🥈"
        if rank == 3:
            return "🥉"
        return f"`#{rank}`"

    async def send_player_leaderboard(
        self,
        interaction: discord.Interaction,
        *,
        field: str,
        title: str,
        label: str,
        emoji: str,
        limit: int = 10,
        minimum: int = 1,
        format_value=None,
    ) -> None:
        cache = await asyncio.to_thread(
            self.build_leaderboard_cache
        )
        rows = list(cache.get("players", []))
        rows = [
            row for row in rows
            if (
                isinstance(row, dict)
                and float(row.get(field, 0) or 0) >= minimum
            )
        ]
        rows.sort(
            key=lambda row: float(
                row.get(field, 0) or 0
            ),
            reverse=True,
        )
        rows = rows[:max(1, min(int(limit), 25))]

        embed = discord.Embed(
            title=f"{emoji} {title}",
            description=(
                f"Top `{len(rows)}` JTWP players by **{label}**.\n"
                f"Leaderboard cache refreshes every "
                f"`{self.leaderboard_cache_ttl}` seconds."
            ),
            color=3618621,
        )

        if not rows:
            embed.add_field(
                name="No data",
                value="No qualifying player stats are available yet.",
                inline=False,
            )
        else:
            lines = []
            for rank, row in enumerate(rows, start=1):
                value = row.get(field, 0)
                if callable(format_value):
                    value_text = str(format_value(value, row))
                else:
                    if isinstance(value, float):
                        value_text = f"{value:,.2f}"
                    else:
                        value_text = f"{int(value):,}"

                lines.append(
                    f"{self.leaderboard_medal(rank)} "
                    f"**{clip(str(row.get('name') or 'Unknown'), 80)}** "
                    f"— `{value_text}`"
                )

            embed.add_field(
                name=label,
                value="\n".join(lines),
                inline=False,
            )

        embed.set_footer(text="JTWP.org • Player Leaderboards")
        await respond(
            interaction,
            embed=embed,
            ephemeral=False,
        )


    def leaderboard_embed(
        self,
        cache: dict[str, Any],
        *,
        kind: str,
        limit: int = 10,
    ) -> discord.Embed:
        """Build one of the persistent daily leaderboard embeds."""
        specs = {
            "kills": ("💀 Most Kills", "kills", "Kills"),
            "headshots": ("🎯 Most Headshots", "headshots", "Headshots"),
            "botkills": ("🤖 Most Bot Kills", "bot_kills", "Bot Kills"),
            "deaths": ("☠️ Most Deaths", "deaths", "Deaths"),
            "teamkills": ("⚠️ Most Teamkills", "teamkills", "Teamkills"),
            "suicides": ("💥 Most Suicides", "suicides", "Suicides"),
            "connections": ("🔌 Most Connections", "times_connected", "Connections"),
            "matches": ("🎮 Most Matches", "matches", "Matches"),
        }

        if kind == "guns":
            embed = discord.Embed(
                title="🔫 Most Kills By Gun",
                description="Top weapons/items by total recorded player kills.",
                color=3618621,
            )
            rows = list(cache.get("guns", []))[:limit]
            lines = [
                f"{self.leaderboard_medal(rank)} "
                f"**{clip(str(row.get('weapon') or 'Unknown'), 80)}** "
                f"— `{int(row.get('kills', 0) or 0):,}` kills"
                for rank, row in enumerate(rows, start=1)
            ]
            embed.add_field(
                name="Weapon Kills",
                value="\n".join(lines) if lines else "No weapon kill data yet.",
                inline=False,
            )
        elif kind == "kd":
            rows = [
                row for row in cache.get("players", [])
                if isinstance(row, dict)
                and int(row.get("kills", 0) or 0) >= 100
            ]
            rows.sort(
                key=lambda row: float(row.get("kd", 0) or 0),
                reverse=True,
            )
            rows = rows[:limit]
            embed = discord.Embed(
                title="📈 Highest K/D",
                description="Minimum `100` recorded kills required.",
                color=3618621,
            )
            lines = [
                f"{self.leaderboard_medal(rank)} "
                f"**{clip(str(row.get('name') or 'Unknown'), 80)}** "
                f"— `{float(row.get('kd', 0) or 0):,.2f}` "
                f"(`{int(row.get('kills', 0) or 0):,}` K / "
                f"`{int(row.get('deaths', 0) or 0):,}` D)"
                for rank, row in enumerate(rows, start=1)
            ]
            embed.add_field(
                name="K/D",
                value="\n".join(lines) if lines else "No qualifying data yet.",
                inline=False,
            )
        else:
            title, field, label = specs[kind]
            rows = [
                row for row in cache.get("players", [])
                if isinstance(row, dict)
                and int(row.get(field, 0) or 0) > 0
            ]
            rows.sort(
                key=lambda row: int(row.get(field, 0) or 0),
                reverse=True,
            )
            rows = rows[:limit]
            embed = discord.Embed(
                title=title,
                description=f"Top JTWP players by **{label}**.",
                color=3618621,
            )
            lines = [
                f"{self.leaderboard_medal(rank)} "
                f"**{clip(str(row.get('name') or 'Unknown'), 80)}** "
                f"— `{int(row.get(field, 0) or 0):,}`"
                for rank, row in enumerate(rows, start=1)
            ]
            embed.add_field(
                name=label,
                value="\n".join(lines) if lines else "No qualifying data yet.",
                inline=False,
            )

        embed.set_footer(
            text="JTWP.org • Updated daily"
        )
        return embed

    async def update_daily_leaderboards(self) -> None:
        """Create each leaderboard message once, then edit it every day."""
        channel = self.get_channel(self.leaderboard_channel_id)
        if channel is None:
            try:
                channel = await self.fetch_channel(
                    self.leaderboard_channel_id
                )
            except Exception as exc:
                print(
                    f"WARNING: cannot access leaderboard channel "
                    f"{self.leaderboard_channel_id}: {exc}",
                    file=sys.stderr,
                )
                return

        cache = await asyncio.to_thread(
            self.build_leaderboard_cache,
            force=True,
        )

        state = load_json(
            self.leaderboard_messages_path,
            {"version": 1, "channel_id": self.leaderboard_channel_id, "messages": {}},
        )
        if not isinstance(state, dict):
            state = {
                "version": 1,
                "channel_id": self.leaderboard_channel_id,
                "messages": {},
            }

        messages = state.get("messages")
        if not isinstance(messages, dict):
            messages = {}
            state["messages"] = messages

        # These are persistent messages. We edit the same Discord message IDs
        # every day rather than posting a new set and filling the channel.
        kinds = [
            "kills",
            "headshots",
            "botkills",
            "guns",
            "kd",
            "deaths",
            "teamkills",
            "suicides",
            "connections",
            "matches",
        ]

        for kind in kinds:
            embed = self.leaderboard_embed(
                cache,
                kind=kind,
                limit=10,
            )
            message_id = messages.get(kind)
            message = None

            if message_id:
                try:
                    message = await channel.fetch_message(
                        int(message_id)
                    )
                except Exception:
                    message = None

            try:
                if message is None:
                    message = await channel.send(embed=embed)
                    messages[kind] = str(message.id)
                else:
                    await message.edit(
                        content=None,
                        embed=embed,
                    )
            except Exception as exc:
                print(
                    f"WARNING: failed to update leaderboard {kind}: "
                    f"{type(exc).__name__}: {exc}",
                    file=sys.stderr,
                )

        state["channel_id"] = self.leaderboard_channel_id
        state["last_updated"] = now_iso()
        atomic_write_json(
            self.leaderboard_messages_path,
            state,
        )

    @staticmethod
    def normalize_ip_hash(value: str) -> str:
        value = str(value or "").strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("IP hash must be exactly 64 hexadecimal characters")
        return value

    def load_verified_connections(self) -> dict[str, Any]:
        data = load_json(
            self.verified_connections_path,
            {"version": 1, "verified_connections": {}},
        )
        if not isinstance(data, dict):
            data = {"version": 1, "verified_connections": {}}
        entries = data.get("verified_connections")
        if not isinstance(entries, dict):
            entries = {}
            data["verified_connections"] = entries
        data.setdefault("version", 1)
        return data

    def verified_connection(self, ip_hash: str) -> dict[str, Any] | None:
        try:
            key = self.normalize_ip_hash(ip_hash)
        except ValueError:
            return None
        data = self.load_verified_connections()
        rec = data.get("verified_connections", {}).get(key)
        if isinstance(rec, dict) and bool(rec.get("verified", True)):
            return rec
        return None

    def set_verified_connection(
        self,
        ip_hash: str,
        *,
        label: str,
        actor: discord.abc.User,
        notes: str | None = None,
    ) -> dict[str, Any]:
        key = self.normalize_ip_hash(ip_hash)
        data = self.load_verified_connections()
        entries = data.setdefault("verified_connections", {})
        old = entries.get(key) if isinstance(entries.get(key), dict) else {}
        rec = {
            "verified": True,
            "label": str(label or "Known connection").strip()[:200],
            "notes": (str(notes).strip()[:1000] if notes else None),
            "added_at": old.get("added_at") or now_iso(),
            "updated_at": now_iso(),
            "added_by_discord_id": old.get("added_by_discord_id") or str(actor.id),
            "added_by": old.get("added_by") or str(actor),
            "updated_by_discord_id": str(actor.id),
            "updated_by": str(actor),
        }
        entries[key] = rec
        atomic_write_json(self.verified_connections_path, data)
        return {"ip_hash": key, **rec}

    def remove_verified_connection(self, ip_hash: str) -> dict[str, Any] | None:
        key = self.normalize_ip_hash(ip_hash)
        data = self.load_verified_connections()
        entries = data.setdefault("verified_connections", {})
        old = entries.pop(key, None)
        if old is None:
            return None
        atomic_write_json(self.verified_connections_path, data)
        return {"ip_hash": key, **(old if isinstance(old, dict) else {})}

    async def send_json(
        self,
        interaction: discord.Interaction,
        title: str,
        value: Any,
        filename: str,
        *,
        ephemeral: bool = True,
    ) -> None:
        raw = json.dumps(
            value,
            indent=2,
            ensure_ascii=False,
            default=str,
        )

        if len(raw) <= self.output_limit:
            embed = discord.Embed(
                title=title,
                description=f"```json\n{raw}\n```",
            )
            await respond(
                interaction,
                embed=embed,
                ephemeral=ephemeral,
            )
            return

        file = discord.File(
            io.BytesIO(raw.encode("utf-8")),
            filename=filename,
        )
        await respond(
            interaction,
            content=title,
            file=file,
            ephemeral=ephemeral,
        )

    def linked_product_id_for_discord(
        self,
        discord_user_id: int | str,
    ) -> str | None:
        """Resolve a Discord user to the linked JTWP ProductID."""
        by_discord = load_json(
            self.data_root
            / "players"
            / "index"
            / "by_discord_id.json",
            {},
        )
        if not isinstance(by_discord, dict):
            return None

        value = by_discord.get(str(discord_user_id))
        if isinstance(value, dict):
            value = value.get("product_id") or value.get("id")

        if not value:
            return None

        product_id = str(value)
        if not (
            self.data_root
            / "players"
            / "records"
            / product_id
        ).is_dir():
            return None

        return product_id

    def dashboard_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🎮 JTWP Player Dashboard",
            description=(
                "Use the buttons below to access your JTWP player data.\n\n"
                "🏆 **My Badges** — Show your earned badge row\n"
                "📊 **My Stats** — Show your recorded player stats\n"
                "🔗 **Link Account** — Instructions to link Discord\n"
                "🏅 **Leaderboards** — Open the leaderboard channel"
            ),
            color=3618621,
        )
        embed.set_footer(
            text="JTWP.org • Player tools"
        )
        return embed

    async def ensure_dashboard_message(self) -> None:
        """Create the dashboard once, or edit the previously-created message."""
        if not self.dashboard_channel_id:
            return

        try:
            channel = self.get_channel(self.dashboard_channel_id)
            if channel is None:
                channel = await self.fetch_channel(
                    self.dashboard_channel_id
                )

            if not isinstance(
                channel,
                (
                    discord.TextChannel,
                    discord.Thread,
                ),
            ):
                print(
                    "Dashboard channel is not a text channel/thread: "
                    f"{self.dashboard_channel_id}",
                    flush=True,
                )
                return

            state = load_json(self.dashboard_state_path, {})
            if not isinstance(state, dict):
                state = {}

            message = None
            message_id = state.get("message_id")
            if message_id:
                try:
                    message = await channel.fetch_message(
                        int(message_id)
                    )
                except (
                    discord.NotFound,
                    discord.Forbidden,
                    discord.HTTPException,
                    ValueError,
                    TypeError,
                ):
                    message = None

            view = JTWPDashboardView(self)

            if message is None:
                message = await channel.send(
                    embed=self.dashboard_embed(),
                    view=view,
                )
                atomic_write_json(
                    self.dashboard_state_path,
                    {
                        "channel_id": str(channel.id),
                        "message_id": str(message.id),
                        "updated_at": now_iso(),
                    },
                )
                print(
                    "JTWP dashboard posted: "
                    f"channel={channel.id} message={message.id}",
                    flush=True,
                )
            else:
                await message.edit(
                    embed=self.dashboard_embed(),
                    view=view,
                )
                atomic_write_json(
                    self.dashboard_state_path,
                    {
                        "channel_id": str(channel.id),
                        "message_id": str(message.id),
                        "updated_at": now_iso(),
                    },
                )
                print(
                    "JTWP dashboard updated: "
                    f"channel={channel.id} message={message.id}",
                    flush=True,
                )

        except Exception as exc:
            print(
                "JTWP dashboard setup failed: "
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )

    def admin_dashboard_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🛡️ JTWP Admin Dashboard",
            description=(
                "Admin-only JTWP command center.\n\n"
                "Use **Admin Commands** for the complete command sheet, or the "
                "category buttons for a shorter list."
            ),
            color=15158332,
        )
        embed.add_field(
            name="🔎 Player / Network",
            value="Player records, IP hashes, connection verification and DDoS status.",
            inline=False,
        )
        embed.add_field(
            name="⚖️ Moderation",
            value="Cases, votes, categories, rules, temp/permanent bans and warnings.",
            inline=False,
        )
        embed.add_field(
            name="🖥️ Server / RCON",
            value="RCON, server data, URL controls, loop controls and leaderboard refresh.",
            inline=False,
        )
        embed.set_footer(
            text="JTWP.org • Admin access required"
        )
        return embed

    async def ensure_admin_dashboard_message(self) -> None:
        if not self.admin_dashboard_channel_id:
            return

        try:
            channel = self.get_channel(self.admin_dashboard_channel_id)
            if channel is None:
                channel = await self.fetch_channel(
                    self.admin_dashboard_channel_id
                )

            if not isinstance(channel, (discord.TextChannel, discord.Thread)):
                print(
                    "Admin dashboard channel is not a text channel/thread: "
                    f"{self.admin_dashboard_channel_id}",
                    flush=True,
                )
                return

            state = load_json(self.admin_dashboard_state_path, {})
            if not isinstance(state, dict):
                state = {}

            message = None
            message_id = state.get("message_id")
            if message_id:
                try:
                    message = await channel.fetch_message(int(message_id))
                except (
                    discord.NotFound,
                    discord.Forbidden,
                    discord.HTTPException,
                    ValueError,
                    TypeError,
                ):
                    message = None

            view = JTWPAdminDashboardView(self)

            if message is None:
                message = await channel.send(
                    embed=self.admin_dashboard_embed(),
                    view=view,
                )
                action = "posted"
            else:
                await message.edit(
                    embed=self.admin_dashboard_embed(),
                    view=view,
                )
                action = "updated"

            atomic_write_json(
                self.admin_dashboard_state_path,
                {
                    "channel_id": str(channel.id),
                    "message_id": str(message.id),
                    "updated_at": now_iso(),
                },
            )
            print(
                f"JTWP admin dashboard {action}: "
                f"channel={channel.id} message={message.id}",
                flush=True,
            )

        except Exception as exc:
            print(
                "JTWP admin dashboard setup failed: "
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )

    def resolve_player(self, query: str) -> dict[str, Any]:
        raw = str(query or "").strip()
        if not raw:
            return {
                "resolved": False,
                "query": raw,
                "candidates": [],
            }

        records = self.data_root / "players" / "records"
        by_name = load_json(
            self.data_root / "players" / "index" / "by_name.json",
            {},
        )
        by_uid = load_json(
            self.data_root / "players" / "index" / "by_unique_id.json",
            {},
        )
        by_pid = load_json(
            self.data_root / "players" / "index" / "by_product_id.json",
            {},
        )

        candidates: list[str] = []

        if (records / raw).is_dir():
            candidates.append(raw)

        folded = raw.casefold()

        for index, key in (
            (by_name, folded),
            (by_uid, raw),
            (by_pid, raw),
        ):
            value = index.get(key)

            if isinstance(value, list):
                candidates.extend(str(x) for x in value)
            elif isinstance(value, dict):
                pid = (
                    value.get("product_id")
                    or value.get("id")
                    or raw
                )
                candidates.append(str(pid))
            elif value:
                candidates.append(str(value))

        candidates = list(dict.fromkeys(candidates))

        valid = [
            pid
            for pid in candidates
            if (records / pid).is_dir()
        ]

        if len(valid) != 1:
            return {
                "resolved": False,
                "query": raw,
                "candidates": valid or candidates,
            }

        product_id = valid[0]
        player_dir = records / product_id

        player = load_json(
            player_dir / "player.json",
            load_json(player_dir / "profile.json", {}),
        )

        return {
            "resolved": True,
            "query": raw,
            "product_id": product_id,
            "unique_id": player.get("unique_id"),
            "name": (
                player.get("current_name")
                or player.get("name")
                or raw
            ),
            "platform": player.get("platform"),
            "discord_id": player.get("discord_id"),
            "record": player,
        }


class JTWPAdminDashboardView(discord.ui.View):
    """Persistent admin-only command dashboard."""

    def __init__(self, bot: JTWPBot):
        super().__init__(timeout=None)
        self.bot = bot

    async def require_admin(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if self.bot.permission_level(interaction.user) not in {"ADMIN", "OWNER"}:
            await interaction.response.send_message(
                "⛔ This dashboard is restricted to JTWP admins.",
                ephemeral=True,
            )
            return False
        return True

    async def send_pages(
        self,
        interaction: discord.Interaction,
        title: str,
        sections: list[tuple[str, str]],
    ) -> None:
        if not await self.require_admin(interaction):
            return

        embeds: list[discord.Embed] = []
        for section_name, body in sections:
            embed = discord.Embed(
                title=title,
                color=15158332,
            )
            embed.add_field(
                name=section_name,
                value=body,
                inline=False,
            )
            embed.set_footer(text="JTWP.org • Admin Commands")
            embeds.append(embed)

        await interaction.response.send_message(
            embeds=embeds[:10],
            ephemeral=True,
        )

    @discord.ui.button(
        label="Admin Commands",
        emoji="🛡️",
        style=discord.ButtonStyle.danger,
        custom_id="jtwp:admin:all",
        row=0,
    )
    async def all_commands(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self.send_pages(
            interaction,
            "🛡️ JTWP Admin Commands",
            [
                (
                    "🔎 Player",
                    (
                        "`/player lookup <query>`\n"
                        "`/player productid <player>`\n"
                        "`/player network <product_id>`\n"
                        "`/player names <product_id>`\n"
                        "`/player stats <product_id>`\n"
                        "`/player profile <product_id>`"
                    ),
                ),
                (
                    "🌐 Network / Index",
                    (
                        "`/network verify-connection ...`\n"
                        "`/network unverify-connection ...`\n"
                        "`/network verified-connections`\n"
                        "`/network ddos`\n"
                        "`/index names`\n"
                        "`/index iphashes`\n"
                        "`/index productids`\n"
                        "`/index uniqueids`"
                    ),
                ),
                (
                    "⚖️ Moderation",
                    (
                        "`/moderation case ...`\n"
                        "`/moderation vote ...`\n"
                        "`/moderation category ...`\n"
                        "`/moderation rule ...`\n"
                        "`/moderation tempban ...`\n"
                        "`/moderation tempban-player ...`\n"
                        "`/moderation permban ...`\n"
                        "`/moderation reject ...`\n"
                        "`/moderation active-bans`\n"
                        "`/warn ...`\n"
                        "`/banlog ...`"
                    ),
                ),
                (
                    "🖥️ RCON / Server / Loop",
                    (
                        "`/rcon <server_id> <command>`\n"
                        "`/server set-url ...`\n"
                        "`/server data <server_id>`\n"
                        "`/loop start ...`\n"
                        "`/loop stop`\n"
                        "`/loop status`\n"
                        "`/leaderboard refresh`"
                    ),
                ),
                (
                    "🎖️ Badges / Accounts / Data",
                    (
                        "`/badge add ...`\n"
                        "`/account approve <product_id>`\n"
                        "`/data indexstats ...`"
                    ),
                ),
                (
                    "👑 Owner-only",
                    (
                        "`/data export`\n"
                        "`/data backup`\n"
                        "`/jtwp restart`\n"
                        "`/jtwp runcollector`\n"
                        "`/jtwp runpavlovapi`\n"
                        "`/server service ...`\n"
                        "`/server clear-mods ...`"
                    ),
                ),
            ],
        )

    @discord.ui.button(
        label="Player Tools",
        emoji="🔎",
        style=discord.ButtonStyle.secondary,
        custom_id="jtwp:admin:players",
        row=0,
    )
    async def player_tools(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if not await self.require_admin(interaction):
            return

        embed = discord.Embed(
            title="🔎 JTWP Player Tools",
            description=(
                "Search players and inspect their stored JTWP records.\n\n"
                "These controls perform the lookup directly; they do not just "
                "display slash-command names."
            ),
            color=15158332,
        )
        await interaction.response.send_message(
            embed=embed,
            view=JTWPPlayerAdminView(self.bot),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Moderation",
        emoji="⚖️",
        style=discord.ButtonStyle.secondary,
        custom_id="jtwp:admin:moderation",
        row=0,
    )
    async def moderation_tools(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if not await self.require_admin(interaction):
            return

        embed = discord.Embed(
            title="⚖️ JTWP Moderation Control",
            description=(
                "Create warnings/ban cases, review cases, view active bans, "
                "and perform senior-admin ban actions."
            ),
            color=15158332,
        )
        await interaction.response.send_message(
            embed=embed,
            view=JTWPModerationAdminView(self.bot),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Server / RCON",
        emoji="🖥️",
        style=discord.ButtonStyle.secondary,
        custom_id="jtwp:admin:server",
        row=0,
    )
    async def server_tools(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if not await self.require_admin(interaction):
            return

        embed = discord.Embed(
            title="🖥️ JTWP Server Control",
            description=(
                "Choose an admin tool.\n\n"
                "**RCON** opens a nested server → category → command menu."
            ),
            color=15158332,
        )
        embed.set_footer(text="JTWP.org • Admin Server Control")

        await interaction.response.send_message(
            embed=embed,
            view=JTWPServerControlView(self.bot),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Owner Tools",
        emoji="👑",
        style=discord.ButtonStyle.secondary,
        custom_id="jtwp:admin:owner",
        row=1,
    )
    async def owner_tools(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if self.bot.permission_level(interaction.user) != "OWNER":
            await interaction.response.send_message(
                "⛔ Owner access required.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=discord.Embed(
                title="👑 JTWP Owner Commands",
                description=(
                    "`/data export`\n"
                    "`/data backup`\n"
                    "`/jtwp restart`\n"
                    "`/jtwp runcollector`\n"
                    "`/jtwp runpavlovapi`\n"
                    "`/server service ...`\n"
                    "`/server clear-mods ...`"
                ),
                color=15844367,
            ),
            ephemeral=True,
        )




# ============================================================
# Functional admin player tools
# ============================================================

def admin_player_summary_embed(
    bot: JTWPBot,
    product_id: str,
) -> discord.Embed:
    pdir = bot.data_root / "players" / "records" / product_id
    player = load_json(
        pdir / "player.json",
        load_json(pdir / "profile.json", {}),
    )
    stats = load_json(pdir / "stats.json", {})
    ips = load_json(pdir / "ips.json", {})

    if not isinstance(player, dict):
        player = {}
    if not isinstance(stats, dict):
        stats = {}
    if not isinstance(ips, dict):
        ips = {}

    combat = stats.get("combat", {})
    activity = stats.get("activity", {})
    if not isinstance(combat, dict):
        combat = {}
    if not isinstance(activity, dict):
        activity = {}

    name = str(
        player.get("current_name")
        or player.get("name")
        or product_id
    )
    uid = player.get("unique_id")
    platform = player.get("platform")
    known_ips = len(ips.get("ips", {})) if isinstance(ips.get("ips"), dict) else 0

    embed = discord.Embed(
        title=f"👤 {clip(name, 180)}",
        description=f"**ProductID:** `{product_id}`",
        color=3447003,
    )
    embed.add_field(
        name="Identity",
        value=(
            f"Platform: `{platform or 'Unknown'}`\n"
            f"UniqueID: `{uid or 'Unknown'}`"
        ),
        inline=False,
    )
    embed.add_field(
        name="Combat",
        value=(
            f"Kills: `{int(combat.get('kills', 0) or 0):,}`\n"
            f"Deaths: `{int(combat.get('deaths', 0) or 0):,}`\n"
            f"Headshots: `{int(combat.get('headshots', 0) or 0):,}`"
        ),
        inline=True,
    )
    embed.add_field(
        name="Activity",
        value=(
            f"Connections: `{int(activity.get('times_connected', 0) or 0):,}`\n"
            f"Known IP hashes: `{known_ips:,}`"
        ),
        inline=True,
    )
    embed.set_footer(text="JTWP Admin • Player Record")
    return embed


class PlayerLookupModal(discord.ui.Modal):
    def __init__(self, bot: JTWPBot):
        super().__init__(title="JTWP Player Lookup", timeout=300)
        self.bot = bot
        self.query = discord.ui.TextInput(
            label="Name / ProductID / UniqueID",
            placeholder="Salted Cracker Jack or 0002...",
            required=True,
            max_length=200,
        )
        self.add_item(self.query)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if self.bot.permission_level(interaction.user) not in {"ADMIN", "OWNER"}:
            await interaction.response.send_message(
                "⛔ Admin access required.",
                ephemeral=True,
            )
            return

        result = self.bot.resolve_player(str(self.query.value))
        if not result.get("resolved"):
            candidates = result.get("candidates") or []
            await interaction.response.send_message(
                "❌ Could not resolve exactly one player.\n"
                + (
                    "**Candidates:**\n"
                    + "\n".join(f"`{x}`" for x in candidates[:20])
                    if candidates
                    else "No candidates found."
                ),
                ephemeral=True,
            )
            return

        product_id = str(result["product_id"])
        await interaction.response.send_message(
            embed=admin_player_summary_embed(self.bot, product_id),
            view=JTWPPlayerRecordView(self.bot, product_id),
            ephemeral=True,
        )


class IPHashLookupModal(discord.ui.Modal):
    def __init__(self, bot: JTWPBot):
        super().__init__(title="JTWP IP Hash Lookup", timeout=300)
        self.bot = bot
        self.ip_hash = discord.ui.TextInput(
            label="IP hash",
            placeholder="64-character SHA/HMAC hash",
            required=True,
            min_length=32,
            max_length=128,
        )
        self.add_item(self.ip_hash)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if self.bot.permission_level(interaction.user) not in {"ADMIN", "OWNER"}:
            await interaction.response.send_message(
                "⛔ Admin access required.",
                ephemeral=True,
            )
            return

        value = str(self.ip_hash.value).strip()
        index = load_json(
            self.bot.data_root / "players" / "index" / "by_ip_hash.json",
            {},
        )
        matches = index.get(value, []) if isinstance(index, dict) else []
        if isinstance(matches, str):
            matches = [matches]
        elif isinstance(matches, dict):
            matches = list(matches.values())
        if not isinstance(matches, list):
            matches = []

        rows = []
        for pid in matches[:25]:
            pid = str(pid)
            player = load_json(
                self.bot.data_root / "players" / "records" / pid / "player.json",
                {},
            )
            name = (
                player.get("current_name")
                if isinstance(player, dict)
                else None
            )
            rows.append(f"**{clip(str(name or 'Unknown'), 80)}** — `{pid}`")

        await interaction.response.send_message(
            embed=discord.Embed(
                title="🌐 IP Hash Results",
                description=(
                    "\n".join(rows)
                    if rows
                    else "No player records currently reference that IP hash."
                ),
                color=3447003,
            ),
            ephemeral=True,
        )


class JTWPPlayerRecordView(discord.ui.View):
    def __init__(self, bot: JTWPBot, product_id: str):
        super().__init__(timeout=300)
        self.bot = bot
        self.product_id = product_id

    async def send_file(
        self,
        interaction: discord.Interaction,
        filename: str,
        title: str,
    ) -> None:
        path = (
            self.bot.data_root
            / "players"
            / "records"
            / self.product_id
            / filename
        )
        if not path.is_file():
            await interaction.response.send_message(
                f"❌ `{filename}` does not exist for this player.",
                ephemeral=True,
            )
            return

        data = load_json(path, {})
        await self.bot.send_json(
            interaction,
            title,
            data,
            filename,
            ephemeral=True,
        )

    @discord.ui.button(label="Profile", emoji="👤", style=discord.ButtonStyle.secondary)
    async def profile(self, interaction, button):
        await self.send_file(interaction, "player.json", "👤 Player Profile")

    @discord.ui.button(label="Stats", emoji="📊", style=discord.ButtonStyle.secondary)
    async def stats(self, interaction, button):
        await self.send_file(interaction, "stats.json", "📊 Player Stats")

    @discord.ui.button(label="Names", emoji="📝", style=discord.ButtonStyle.secondary)
    async def names(self, interaction, button):
        await self.send_file(interaction, "names.json", "📝 Name History")

    @discord.ui.button(label="Network", emoji="🌐", style=discord.ButtonStyle.secondary)
    async def network(self, interaction, button):
        await self.send_file(interaction, "ips.json", "🌐 Network Record")

    @discord.ui.button(label="Weapons", emoji="🔫", style=discord.ButtonStyle.secondary)
    async def weapons(self, interaction, button):
        await self.send_file(interaction, "weapons.json", "🔫 Weapon Stats")


class JTWPPlayerAdminView(discord.ui.View):
    def __init__(self, bot: JTWPBot):
        super().__init__(timeout=300)
        self.bot = bot

    @discord.ui.button(label="Lookup Player", emoji="🔎", style=discord.ButtonStyle.primary)
    async def lookup(self, interaction, button):
        await interaction.response.send_modal(PlayerLookupModal(self.bot))

    @discord.ui.button(label="IP Hash Lookup", emoji="🌐", style=discord.ButtonStyle.secondary)
    async def iphash(self, interaction, button):
        await interaction.response.send_modal(IPHashLookupModal(self.bot))


# ============================================================
# Functional admin moderation tools
# ============================================================

class ModerationCreateCaseModal(discord.ui.Modal):
    def __init__(
        self,
        bot: JTWPBot,
        case_type: str,
        *,
        category: str | None = None,
        rule_id: str | None = None,
    ):
        title = "Create Warning" if case_type == "warning" else "Create Ban Case"
        super().__init__(title=title, timeout=300)
        self.bot = bot
        self.case_type = case_type
        self.category = category
        self.rule_id = rule_id

        self.player = discord.ui.TextInput(
            label="Player / ProductID",
            placeholder="Use exact ProductID when possible",
            required=True,
            max_length=200,
        )
        self.server_id = discord.ui.TextInput(
            label="Server ID",
            placeholder="pavlovserver",
            required=True,
            max_length=100,
        )
        self.reason = discord.ui.TextInput(
            label="Reason",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000,
        )
        self.evidence = discord.ui.TextInput(
            label="Evidence / notes (optional)",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=1000,
        )

        for item in (
            self.player,
            self.server_id,
            self.reason,
            self.evidence,
        ):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if self.bot.permission_level(interaction.user) not in {"ADMIN", "OWNER"}:
            await interaction.response.send_message(
                "⛔ Admin access required.",
                ephemeral=True,
            )
            return

        target = self.bot.resolve_player(str(self.player.value))
        if not target.get("resolved"):
            await interaction.response.send_message(
                "❌ Could not resolve exactly one player. Use the exact ProductID.",
                ephemeral=True,
            )
            return

        server_id = str(self.server_id.value).strip()
        if server_id not in self.bot.servers:
            await interaction.response.send_message(
                "❌ Unknown/current server ID.",
                ephemeral=True,
            )
            return

        # Re-validate the selected rule at submit time.
        rule_id = self.rule_id
        if rule_id:
            rec = self.bot.moderation.rule_record(rule_id)
            if not rec:
                await interaction.response.send_message(
                    f"❌ The selected rule `{rule_id}` no longer exists.",
                    ephemeral=True,
                )
                return
            if (
                self.category
                and str(rec.get("category") or "").casefold()
                != str(self.category).casefold()
            ):
                await interaction.response.send_message(
                    "❌ The selected rule no longer belongs to that category.",
                    ephemeral=True,
                )
                return

        case = self.bot.moderation.create_case(
            case_type=self.case_type,
            target=target,
            server_id=server_id,
            incident_summary=str(self.reason.value).strip(),
            evidence=str(self.evidence.value).strip() or None,
            submitted_by=interaction.user,
            category=self.category,
            rule_id=rule_id,
        )

        await self.bot.moderation.post_case(case)

        rule_display = self.bot.moderation.rule_display(rule_id)
        await interaction.response.send_message(
            (
                f"✅ {self.case_type.title()} case created: `{case['case_id']}`\n"
                f"**Category:** `{self.category or 'Unclassified'}`\n"
                f"**Rule:** `{rule_display}`"
            ),
            ephemeral=True,
        )


class ModerationRuleSelect(discord.ui.Select):
    def __init__(
        self,
        bot: JTWPBot,
        case_type: str,
        category: str | None,
    ):
        self.bot = bot
        self.case_type = case_type
        self.category = category

        options: list[discord.SelectOption] = [
            discord.SelectOption(
                label="None / No Rule",
                value="__NONE__",
                description="Create the case without assigning a specific rule.",
                emoji="➖",
            )
        ]

        if category:
            for rule_id, rec in bot.moderation.selectable_rules(category)[:24]:
                title = str(rec.get("title") or rule_id)
                description = str(
                    rec.get("description")
                    or rec.get("summary")
                    or ""
                ).replace("\n", " ").strip()

                options.append(
                    discord.SelectOption(
                        label=f"{rule_id} — {title}"[:100],
                        value=rule_id[:100],
                        description=(
                            description[:100]
                            if description
                            else f"Category: {category}"[:100]
                        ),
                        emoji="📜",
                    )
                )

        super().__init__(
            placeholder="Choose a rule",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        selected = self.values[0]
        rule_id = None if selected == "__NONE__" else selected

        await interaction.response.send_modal(
            ModerationCreateCaseModal(
                self.bot,
                self.case_type,
                category=self.category,
                rule_id=rule_id,
            )
        )


class ModerationRuleSelectView(discord.ui.View):
    def __init__(
        self,
        bot: JTWPBot,
        case_type: str,
        category: str | None,
    ):
        super().__init__(timeout=300)
        self.add_item(
            ModerationRuleSelect(
                bot,
                case_type,
                category,
            )
        )


class ModerationCategorySelect(discord.ui.Select):
    def __init__(self, bot: JTWPBot, case_type: str):
        self.bot = bot
        self.case_type = case_type

        options: list[discord.SelectOption] = [
            discord.SelectOption(
                label="Unclassified",
                value="__NONE__",
                description="Create the case without a category.",
                emoji="❔",
            )
        ]

        for category in bot.moderation.categories[:24]:
            category = str(category)
            rule_count = len(
                bot.moderation.selectable_rules(category)
            )
            options.append(
                discord.SelectOption(
                    label=category[:100],
                    value=category[:100],
                    description=f"{rule_count} selectable rule(s)"[:100],
                    emoji="📁",
                )
            )

        super().__init__(
            placeholder="Choose a moderation category",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        value = self.values[0]
        category = None if value == "__NONE__" else value

        if category:
            rules = self.bot.moderation.selectable_rules(category)
            lines = []
            for rule_id, rec in rules:
                title = str(rec.get("title") or rule_id)
                lines.append(f"**{rule_id} — {title}**")

            description = (
                f"**Category:** {category}\n\n"
                "**Available Rules**\n"
                + (
                    "\n".join(lines[:20])
                    if lines
                    else "No selectable rules are configured for this category."
                )
            )
        else:
            description = (
                "**Category:** Unclassified\n\n"
                "Choose **None / No Rule** to continue."
            )

        embed = discord.Embed(
            title="📜 Select Moderation Rule",
            description=clip(description, 3900),
            color=15158332,
        )
        embed.set_footer(
            text="After choosing a rule, the case details form will open."
        )

        await interaction.response.edit_message(
            embed=embed,
            view=ModerationRuleSelectView(
                self.bot,
                self.case_type,
                category,
            ),
        )


class ModerationCategorySelectView(discord.ui.View):
    def __init__(self, bot: JTWPBot, case_type: str):
        super().__init__(timeout=300)
        self.add_item(
            ModerationCategorySelect(
                bot,
                case_type,
            )
        )


def moderation_catalog_embed(bot: JTWPBot) -> discord.Embed:
    """Build a readable category + rule catalog from the configured rules file."""
    embed = discord.Embed(
        title="📚 JTWP Moderation Categories & Rules",
        description=(
            "These are loaded from the moderation rules configuration. "
            "Disabled/non-admin-selectable rules are omitted."
        ),
        color=15158332,
    )

    categories = [str(x) for x in bot.moderation.categories]

    if not categories:
        embed.description = (
            (embed.description or "")
            + "\n\nNo moderation categories are currently configured."
        )
        return embed

    for category in categories[:25]:
        rules = bot.moderation.selectable_rules(category)
        if rules:
            value = "\n".join(
                f"`{rule_id}` — {clip(str(rec.get('title') or rule_id), 70)}"
                for rule_id, rec in rules
            )
        else:
            value = "No selectable rules."

        embed.add_field(
            name=f"📁 {category}"[:256],
            value=clip(value, 1024),
            inline=False,
        )

    embed.set_footer(
        text="JTWP.org • Moderation rule catalog"
    )
    return embed


class TempBanPlayerModal(discord.ui.Modal):
    def __init__(self, bot: JTWPBot):
        super().__init__(title="Temporary Ban Player", timeout=300)
        self.bot = bot
        self.player = discord.ui.TextInput(
            label="Player / ProductID",
            required=True,
            max_length=200,
        )
        self.server_id = discord.ui.TextInput(
            label="Server ID",
            required=True,
            max_length=100,
        )
        self.days = discord.ui.TextInput(
            label="Days",
            placeholder="1 - 3650",
            required=True,
            max_length=4,
        )
        self.reason = discord.ui.TextInput(
            label="Reason",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000,
        )
        for item in (self.player, self.server_id, self.days, self.reason):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not self.bot.is_senior(interaction.user):
            await interaction.response.send_message(
                "⛔ Senior admin or owner access required.",
                ephemeral=True,
            )
            return

        target = self.bot.resolve_player(str(self.player.value))
        if not target.get("resolved"):
            await interaction.response.send_message(
                "❌ Could not resolve exactly one player.",
                ephemeral=True,
            )
            return

        server_id = str(self.server_id.value).strip()
        if server_id not in self.bot.servers:
            await interaction.response.send_message("❌ Unknown server.", ephemeral=True)
            return

        try:
            days = int(str(self.days.value).strip())
        except ValueError:
            days = 0
        if not 1 <= days <= 3650:
            await interaction.response.send_message(
                "❌ Days must be between 1 and 3650.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            case = self.bot.moderation.create_case(
                case_type="ban",
                target=target,
                server_id=server_id,
                incident_summary=str(self.reason.value).strip(),
                evidence=None,
                submitted_by=interaction.user,
                target_discord_id=None,
                status="pending_tempban",
            )
            await self.bot.moderation.post_case(case)
            ban = await self.bot.moderation.apply_temp_ban(
                case,
                days,
                interaction.user,
            )
            await interaction.followup.send(
                "✅ Temporary ban applied.\n"
                f"Case: `{case['case_id']}`\n"
                f"Player: **{target.get('name')}**\n"
                f"Expires: `{ban.get('expires_at')}`",
                ephemeral=True,
            )
        except Exception as exc:
            await interaction.followup.send(
                f"❌ Temp-ban failed: `{type(exc).__name__}: {exc}`",
                ephemeral=True,
            )


class CaseLookupModal(discord.ui.Modal):
    def __init__(self, bot: JTWPBot):
        super().__init__(title="Moderation Case Lookup", timeout=300)
        self.bot = bot
        self.case_id = discord.ui.TextInput(
            label="Case ID",
            required=True,
            max_length=100,
        )
        self.add_item(self.case_id)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if self.bot.permission_level(interaction.user) not in {"ADMIN", "OWNER"}:
            await interaction.response.send_message("⛔ Admin access required.", ephemeral=True)
            return

        case = self.bot.moderation.load_case(str(self.case_id.value).strip())
        if not case:
            await interaction.response.send_message("❌ Case not found.", ephemeral=True)
            return

        raw = json.dumps(case, indent=2, ensure_ascii=False, default=str)
        if len(raw) > 3500:
            raw = raw[-3500:]

        await interaction.response.send_message(
            embed=discord.Embed(
                title=f"⚖️ Case {case.get('case_id')}",
                description=f"```json\n{raw}\n```",
                color=15158332,
            ),
            view=ModerationCaseActionView(
                self.bot,
                str(case.get("case_id")),
            ),
            ephemeral=True,
        )


class RejectCaseModal(discord.ui.Modal):
    def __init__(self, bot: JTWPBot, case_id: str):
        super().__init__(title="Reject Moderation Case", timeout=300)
        self.bot = bot
        self.case_id = case_id
        self.reason = discord.ui.TextInput(
            label="Reason",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000,
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not self.bot.is_senior(interaction.user):
            await interaction.response.send_message(
                "⛔ Senior admin or owner access required.",
                ephemeral=True,
            )
            return

        case = self.bot.moderation.load_case(self.case_id)
        if not case:
            await interaction.response.send_message("❌ Case not found.", ephemeral=True)
            return

        await self.bot.moderation.reject_case(
            case,
            interaction.user,
            str(self.reason.value).strip(),
        )
        await interaction.response.send_message(
            f"✅ `{self.case_id}` rejected and closed.",
            ephemeral=True,
        )


class ModerationCaseActionView(discord.ui.View):
    def __init__(self, bot: JTWPBot, case_id: str):
        super().__init__(timeout=300)
        self.bot = bot
        self.case_id = case_id

    @discord.ui.button(label="Permanent Ban", emoji="🔨", style=discord.ButtonStyle.danger)
    async def permban(self, interaction, button):
        if not self.bot.is_senior(interaction.user):
            await interaction.response.send_message(
                "⛔ Senior admin or owner access required.",
                ephemeral=True,
            )
            return

        case = self.bot.moderation.load_case(self.case_id)
        if not case:
            await interaction.response.send_message("❌ Case not found.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await self.bot.moderation.apply_permanent_ban(case, interaction.user)
            await interaction.followup.send(
                f"✅ Permanent ban applied for `{self.case_id}`.",
                ephemeral=True,
            )
        except Exception as exc:
            await interaction.followup.send(
                f"❌ Permanent ban failed: `{type(exc).__name__}: {exc}`",
                ephemeral=True,
            )

    @discord.ui.button(label="Reject Case", emoji="❌", style=discord.ButtonStyle.secondary)
    async def reject(self, interaction, button):
        if not self.bot.is_senior(interaction.user):
            await interaction.response.send_message(
                "⛔ Senior admin or owner access required.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(
            RejectCaseModal(self.bot, self.case_id)
        )


class JTWPModerationAdminView(discord.ui.View):
    def __init__(self, bot: JTWPBot):
        super().__init__(timeout=300)
        self.bot = bot

    @discord.ui.button(label="Warning", emoji="⚠️", style=discord.ButtonStyle.secondary, row=0)
    async def warning(self, interaction, button):
        embed = discord.Embed(
            title="⚠️ Create Warning — Select Category",
            description=(
                "Choose the category for this warning. "
                "You will choose a rule next."
            ),
            color=15158332,
        )
        await interaction.response.send_message(
            embed=embed,
            view=ModerationCategorySelectView(self.bot, "warning"),
            ephemeral=True,
        )

    @discord.ui.button(label="Ban Case", emoji="📋", style=discord.ButtonStyle.secondary, row=0)
    async def ban_case(self, interaction, button):
        embed = discord.Embed(
            title="📋 Create Ban Case — Select Category",
            description=(
                "Choose the category for this ban case. "
                "You will choose a rule next."
            ),
            color=15158332,
        )
        await interaction.response.send_message(
            embed=embed,
            view=ModerationCategorySelectView(self.bot, "ban"),
            ephemeral=True,
        )

    @discord.ui.button(label="Temp Ban", emoji="⏳", style=discord.ButtonStyle.danger, row=0)
    async def tempban(self, interaction, button):
        if not self.bot.is_senior(interaction.user):
            await interaction.response.send_message(
                "⛔ Senior admin or owner access required.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(TempBanPlayerModal(self.bot))

    @discord.ui.button(label="Case Lookup", emoji="🔎", style=discord.ButtonStyle.primary, row=1)
    async def case_lookup(self, interaction, button):
        await interaction.response.send_modal(CaseLookupModal(self.bot))

    @discord.ui.button(label="Categories / Rules", emoji="📚", style=discord.ButtonStyle.secondary, row=1)
    async def catalog(self, interaction, button):
        if self.bot.permission_level(interaction.user) not in {"ADMIN", "OWNER"}:
            await interaction.response.send_message(
                "⛔ Admin access required.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=moderation_catalog_embed(self.bot),
            ephemeral=True,
        )

    @discord.ui.button(label="Active Bans", emoji="🔨", style=discord.ButtonStyle.secondary, row=1)
    async def active_bans(self, interaction, button):
        if self.bot.permission_level(interaction.user) not in {"ADMIN", "OWNER"}:
            await interaction.response.send_message("⛔ Admin access required.", ephemeral=True)
            return
        data = load_json(self.bot.moderation.active_bans_path, {})
        await self.bot.send_json(
            interaction,
            "🔨 Active JTWP Bans",
            data,
            "active-bans.json",
            ephemeral=True,
        )


# ============================================================
# Nested admin RCON dashboard
# ============================================================

RCON_DASHBOARD_CATEGORIES: dict[str, list[tuple[str, str, bool]]] = {
    "info": [
        ("Server Info", "ServerInfo", False),
        ("Inspect All", "InspectAll", False),
        ("Map List", "MapList", False),
        ("Refresh List", "RefreshList", False),
        ("Ban List", "Banlist", False),
        ("Moderator List", "ModeratorList", False),
        ("Item List", "ItemList", False),
        ("UGC Mod List", "UGCModList", False),
    ],
    "player": [
        ("Inspect Player", "InspectPlayer", True),
        ("Kick", "Kick", True),
        ("Kill", "Kill", True),
        ("Slap", "Slap", True),
        ("Gag", "Gag", True),
        ("Give Item", "GiveItem", True),
        ("Give Cash", "GiveCash", True),
        ("Set Cash", "SetCash", True),
        ("Switch Team", "SwitchTeam", True),
        ("Teleport", "Teleport", True),
        ("Revive", "Revive", True),
        ("Godmode", "Godmode", True),
        ("NoClip", "NoClip", True),
    ],
    "match": [
        ("Rotate Map", "RotateMap", False),
        ("Pause Match", "PauseMatch", False),
        ("Reset SND", "ResetSND", False),
        ("TTT End Round", "TTTEndRound", False),
        ("Enable Comp Mode", "EnableCompMode", True),
        ("Game Speed", "GameSpeed", True),
        ("Set Gravity", "SetGravity", True),
        ("Fall Damage", "FallDamage", True),
        ("Team Switching", "TeamSwitching", True),
    ],
    "server": [
        ("Set Max Players", "SetMaxPlayers", True),
        ("Set Time Limit", "SetTimeLimit", True),
        ("Set Bots Enabled", "SetBotsEnabled", True),
        ("Update Server Name", "UpdateServerName", True),
        ("Switch Map", "SwitchMap", True),
        ("Add Mod", "AddMod", True),
        ("Remove Mod", "RemoveMod", True),
        ("UGC Add Mod", "UGCAddMod", True),
        ("UGC Remove Mod", "UGCRemoveMod", True),
        ("Notify", "Notify", True),
    ],
}


async def dashboard_rcon_execute(
    bot: JTWPBot,
    interaction: discord.Interaction,
    server_id: str,
    final_command: str,
) -> None:
    """Execute RCON using the exact same permission rules as /rcon."""
    if bot.permission_level(interaction.user) not in {"ADMIN", "OWNER"}:
        if interaction.response.is_done():
            await interaction.followup.send(
                "⛔ Admin access required.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "⛔ Admin access required.",
                ephemeral=True,
            )
        return

    final_command = str(final_command or "").strip()
    if not final_command:
        if interaction.response.is_done():
            await interaction.followup.send(
                "❌ Empty RCON command.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "❌ Empty RCON command.",
                ephemeral=True,
            )
        return

    parts = final_command.split()
    command_key = parts[0].casefold() if parts else ""

    if command_key in RCON_BLOCKED_COMMANDS:
        message = (
            "⛔ `Ban` is not available through RCON. "
            "Use the moderation ban workflow instead."
        )
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
        return

    level = bot.permission_level(interaction.user)
    if level == "ADMIN" and command_key not in bot.admin_rcon:
        message = f"⛔ ADMIN cannot use RCON command `{command_key}`."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
        return

    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True, thinking=True)

    try:
        response = await bot.rcon_send(server_id, final_command)

        bot.audit(
            interaction,
            "dashboard_rcon",
            True,
            server_id=server_id,
            command=final_command,
        )

        raw = json.dumps(
            response,
            indent=2,
            ensure_ascii=False,
            default=str,
        )
        if len(raw) > 3600:
            raw = raw[-3600:]

        embed = discord.Embed(
            title=f"✅ RCON — {server_id}",
            description=(
                f"**Command:** `{clip(final_command, 500)}`\n"
                f"```json\n{raw}\n```"
            ),
            color=5763719,
        )
        embed.set_footer(text="JTWP Admin Dashboard • RCON")

        await interaction.followup.send(
            embed=embed,
            ephemeral=True,
        )

    except Exception as exc:
        bot.audit(
            interaction,
            "dashboard_rcon",
            False,
            server_id=server_id,
            command=final_command,
            error=f"{type(exc).__name__}: {exc}",
        )

        await interaction.followup.send(
            "❌ RCON failed:\n"
            f"`{type(exc).__name__}: {exc}`",
            ephemeral=True,
        )


class RCONArgumentsModal(discord.ui.Modal):
    def __init__(
        self,
        bot: JTWPBot,
        server_id: str,
        command: str,
        label: str | None = None,
    ):
        super().__init__(
            title=f"RCON • {command}"[:45],
            timeout=300,
        )
        self.bot = bot
        self.server_id = server_id
        self.command = command

        self.arguments = discord.ui.TextInput(
            label=label or f"Arguments for {command}",
            placeholder=(
                "Enter the arguments exactly as Pavlov RCON expects. "
                "Example: PlayerName 5000"
            ),
            required=True,
            max_length=1000,
        )
        self.add_item(self.arguments)

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        args = str(self.arguments.value or "").strip()
        await dashboard_rcon_execute(
            self.bot,
            interaction,
            self.server_id,
            f"{self.command} {args}".strip(),
        )


class RCONCustomModal(discord.ui.Modal):
    def __init__(self, bot: JTWPBot, server_id: str):
        super().__init__(
            title=f"Custom RCON • {server_id}"[:45],
            timeout=300,
        )
        self.bot = bot
        self.server_id = server_id

        self.command = discord.ui.TextInput(
            label="Full RCON command",
            placeholder="Example: ServerInfo",
            required=True,
            max_length=1000,
        )
        self.add_item(self.command)

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await dashboard_rcon_execute(
            self.bot,
            interaction,
            self.server_id,
            str(self.command.value or "").strip(),
        )


class RCONCommandButton(discord.ui.Button):
    def __init__(
        self,
        bot: JTWPBot,
        server_id: str,
        display_name: str,
        command: str,
        needs_arguments: bool,
        row: int,
    ):
        style = (
            discord.ButtonStyle.primary
            if not needs_arguments
            else discord.ButtonStyle.secondary
        )
        super().__init__(
            label=display_name[:80],
            style=style,
            row=row,
        )
        self.bot = bot
        self.server_id = server_id
        self.rcon_command = command
        self.needs_arguments = needs_arguments

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if self.needs_arguments:
            await interaction.response.send_modal(
                RCONArgumentsModal(
                    self.bot,
                    self.server_id,
                    self.rcon_command,
                )
            )
            return

        await dashboard_rcon_execute(
            self.bot,
            interaction,
            self.server_id,
            self.rcon_command,
        )


class RCONCommandCategoryView(discord.ui.View):
    def __init__(
        self,
        bot: JTWPBot,
        server_id: str,
        category: str,
    ):
        super().__init__(timeout=300)
        self.bot = bot
        self.server_id = server_id
        self.category = category

        rows = RCON_DASHBOARD_CATEGORIES.get(category, [])

        for index, (display_name, command, needs_arguments) in enumerate(rows):
            self.add_item(
                RCONCommandButton(
                    bot,
                    server_id,
                    display_name,
                    command,
                    needs_arguments,
                    row=min(index // 5, 3),
                )
            )

        self.add_item(
            RCONBackToCategoriesButton(
                bot,
                server_id,
                row=4,
            )
        )


class RCONBackToCategoriesButton(discord.ui.Button):
    def __init__(
        self,
        bot: JTWPBot,
        server_id: str,
        row: int = 4,
    ):
        super().__init__(
            label="Back",
            emoji="↩️",
            style=discord.ButtonStyle.secondary,
            row=row,
        )
        self.bot = bot
        self.server_id = server_id

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await interaction.response.edit_message(
            embed=RCONCategoryView.make_embed(self.server_id),
            view=RCONCategoryView(
                self.bot,
                self.server_id,
            ),
        )


class RCONCategoryButton(discord.ui.Button):
    def __init__(
        self,
        bot: JTWPBot,
        server_id: str,
        category: str,
        label: str,
        emoji: str,
        row: int,
    ):
        super().__init__(
            label=label,
            emoji=emoji,
            style=discord.ButtonStyle.secondary,
            row=row,
        )
        self.bot = bot
        self.server_id = server_id
        self.category = category

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        embed = discord.Embed(
            title=f"🎛️ {self.server_id} — {self.label}",
            description=(
                "Choose a command. "
                "Buttons requiring arguments will open a modal."
            ),
            color=15158332,
        )
        await interaction.response.edit_message(
            embed=embed,
            view=RCONCommandCategoryView(
                self.bot,
                self.server_id,
                self.category,
            ),
        )


class RCONCustomButton(discord.ui.Button):
    def __init__(
        self,
        bot: JTWPBot,
        server_id: str,
    ):
        super().__init__(
            label="Custom",
            emoji="⌨️",
            style=discord.ButtonStyle.danger,
            row=1,
        )
        self.bot = bot
        self.server_id = server_id

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await interaction.response.send_modal(
            RCONCustomModal(
                self.bot,
                self.server_id,
            )
        )


class RCONCategoryView(discord.ui.View):
    def __init__(
        self,
        bot: JTWPBot,
        server_id: str,
    ):
        super().__init__(timeout=300)
        self.bot = bot
        self.server_id = server_id

        self.add_item(
            RCONCategoryButton(
                bot, server_id, "info", "Info", "ℹ️", 0
            )
        )
        self.add_item(
            RCONCategoryButton(
                bot, server_id, "player", "Player", "👤", 0
            )
        )
        self.add_item(
            RCONCategoryButton(
                bot, server_id, "match", "Match", "🎮", 0
            )
        )
        self.add_item(
            RCONCategoryButton(
                bot, server_id, "server", "Server", "🖥️", 0
            )
        )
        self.add_item(
            RCONCustomButton(
                bot,
                server_id,
            )
        )

    @staticmethod
    def make_embed(server_id: str) -> discord.Embed:
        embed = discord.Embed(
            title=f"🎛️ RCON — {server_id}",
            description=(
                "Choose a command category.\n\n"
                "ℹ️ **Info** — server and player-list information\n"
                "👤 **Player** — inspect/control players\n"
                "🎮 **Match** — match/game controls\n"
                "🖥️ **Server** — server configuration\n"
                "⌨️ **Custom** — type any permitted RCON command"
            ),
            color=15158332,
        )
        embed.set_footer(text="JTWP Admin Dashboard • RCON")
        return embed


class RCONServerButton(discord.ui.Button):
    def __init__(
        self,
        bot: JTWPBot,
        server_id: str,
        row: int,
    ):
        super().__init__(
            label=server_id[:80],
            emoji="🟢",
            style=discord.ButtonStyle.primary,
            row=row,
        )
        self.bot = bot
        self.server_id = server_id

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if self.bot.permission_level(interaction.user) not in {"ADMIN", "OWNER"}:
            await interaction.response.send_message(
                "⛔ Admin access required.",
                ephemeral=True,
            )
            return

        await interaction.response.edit_message(
            embed=RCONCategoryView.make_embed(
                self.server_id
            ),
            view=RCONCategoryView(
                self.bot,
                self.server_id,
            ),
        )


class RCONServerSelectView(discord.ui.View):
    def __init__(self, bot: JTWPBot):
        super().__init__(timeout=300)
        self.bot = bot

        server_ids = sorted(bot.servers)
        for index, server_id in enumerate(server_ids[:20]):
            self.add_item(
                RCONServerButton(
                    bot,
                    server_id,
                    row=min(index // 5, 3),
                )
            )


class JTWPServerControlView(discord.ui.View):
    def __init__(self, bot: JTWPBot):
        super().__init__(timeout=300)
        self.bot = bot

    async def require_admin(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if self.bot.permission_level(interaction.user) not in {"ADMIN", "OWNER"}:
            await interaction.response.send_message(
                "⛔ Admin access required.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(
        label="RCON",
        emoji="🎛️",
        style=discord.ButtonStyle.primary,
        row=0,
    )
    async def rcon(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if not await self.require_admin(interaction):
            return

        embed = discord.Embed(
            title="🎛️ JTWP RCON",
            description="Choose the Pavlov server you want to control.",
            color=15158332,
        )
        embed.set_footer(text="JTWP Admin Dashboard • RCON")

        await interaction.response.edit_message(
            embed=embed,
            view=RCONServerSelectView(self.bot),
        )

    @discord.ui.button(
        label="DDoS Status",
        emoji="🛡️",
        style=discord.ButtonStyle.secondary,
        row=0,
    )
    async def ddos(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if not await self.require_admin(interaction):
            return

        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )
        try:
            data = await self.bot.read_ddos_stats()
            await interaction.followup.send(
                embed=self.bot.ddos_status_embed(data),
                ephemeral=True,
            )
        except Exception as exc:
            await interaction.followup.send(
                f"❌ DDoS status failed: `{type(exc).__name__}: {exc}`",
                ephemeral=True,
            )

class JTWPDashboardView(discord.ui.View):
    """Permanent JTWP dashboard shown in the configured dashboard channel."""

    def __init__(self, bot: JTWPBot):
        super().__init__(timeout=None)
        self.bot = bot

        # URL buttons do not need callbacks.
        guild_id = str(
            self.bot.bot_cfg.get("guild_id")
            or os.getenv("JTWP_DISCORD_GUILD_ID", "")
            or ""
        ).strip()

        if guild_id:
            self.add_item(
                discord.ui.Button(
                    label="Leaderboards",
                    emoji="🏅",
                    style=discord.ButtonStyle.link,
                    url=(
                        "https://discord.com/channels/"
                        f"{guild_id}/{self.bot.leaderboard_channel_id}"
                    ),
                    row=0,
                )
            )

    async def linked_player(
        self,
        interaction: discord.Interaction,
    ) -> tuple[str, dict[str, Any]] | None:
        product_id = self.bot.linked_product_id_for_discord(
            interaction.user.id
        )

        if not product_id:
            await interaction.response.send_message(
                "❌ Your Discord account is not linked to a JTWP player yet.\n"
                "Use `/account link` with your exact ProductID first.",
                ephemeral=True,
            )
            return None

        player_dir = (
            self.bot.data_root
            / "players"
            / "records"
            / product_id
        )
        player = load_json(
            player_dir / "player.json",
            load_json(player_dir / "profile.json", {}),
        )
        if not isinstance(player, dict):
            player = {}

        return product_id, player

    @discord.ui.button(
        label="My Badges",
        emoji="🏆",
        style=discord.ButtonStyle.primary,
        custom_id="jtwp:dashboard:badges",
        row=0,
    )
    async def my_badges(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        linked = await self.linked_player(interaction)
        if linked is None:
            return

        product_id, player_doc = linked

        self.bot.ensure_discord_link_badge(
            product_id,
            player_doc,
        )

        registry = self.bot.load_badge_registry()
        definitions = registry.get("badges", {})
        if not isinstance(definitions, dict):
            definitions = {}

        owned_doc = self.bot.load_player_badges(product_id)
        owned = owned_doc.get("badges", {})
        if not isinstance(owned, dict):
            owned = {}

        player_name = str(
            player_doc.get("current_name")
            or player_doc.get("name")
            or interaction.user.display_name
        )

        embed = discord.Embed(
            title=f"🏆 {clip(player_name, 180)} — Badges",
            description=f"**Badges Earned:** `{len(owned)}`",
            color=3618621,
        )
        embed.set_footer(text="JTWP Player Badges")

        if not owned:
            await interaction.response.send_message(
                embed=embed,
                ephemeral=True,
            )
            return

        badge_rows: list[
            tuple[str, dict[str, Any], dict[str, Any]]
        ] = []

        for badge_name, award in sorted(
            owned.items(),
            key=lambda kv: (
                int(
                    definitions.get(kv[0], {}).get("id", 999999)
                    if isinstance(definitions.get(kv[0]), dict)
                    else 999999
                ),
                str(kv[0]).casefold(),
            ),
        ):
            definition = definitions.get(badge_name, {})
            if not isinstance(definition, dict):
                definition = {}
            if not isinstance(award, dict):
                award = {}
            badge_rows.append(
                (str(badge_name), definition, award)
            )

        badge_images = await asyncio.to_thread(
            self.bot.build_badge_strip_images,
            badge_rows,
        )

        if not badge_images:
            await interaction.response.send_message(
                embed=embed,
                ephemeral=True,
            )
            return

        embeds: list[discord.Embed] = []
        files: list[discord.File] = []

        for index, image in enumerate(badge_images[:10]):
            first_badge = index * self.bot.badges_per_image + 1
            last_badge = min(
                first_badge + self.bot.badges_per_image - 1,
                len(owned),
            )
            filename = f"{product_id}-badges-{index + 1}.png"
            files.append(discord.File(image, filename=filename))

            if index == 0:
                row_embed = embed
            else:
                row_embed = discord.Embed(
                    title=f"🏆 Badges {first_badge}–{last_badge}",
                    color=3618621,
                )
                row_embed.set_footer(text="JTWP Player Badges")

            row_embed.set_image(
                url=f"attachment://{filename}"
            )
            embeds.append(row_embed)

        await interaction.response.send_message(
            embeds=embeds,
            files=files,
            ephemeral=True,
        )

    @discord.ui.button(
        label="My Stats",
        emoji="📊",
        style=discord.ButtonStyle.secondary,
        custom_id="jtwp:dashboard:stats",
        row=0,
    )
    async def my_stats(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        linked = await self.linked_player(interaction)
        if linked is None:
            return

        product_id, player_doc = linked
        stats = load_json(
            self.bot.data_root
            / "players"
            / "records"
            / product_id
            / "stats.json",
            {},
        )
        if not isinstance(stats, dict):
            stats = {}

        combat = stats.get("combat", {})
        activity = stats.get("activity", {})
        if not isinstance(combat, dict):
            combat = {}
        if not isinstance(activity, dict):
            activity = {}

        kills = int(combat.get("kills", 0) or 0)
        deaths = int(combat.get("deaths", 0) or 0)
        kd = (
            kills / deaths
            if deaths > 0
            else float(kills)
        )

        total_seconds = int(
            activity.get("total_time_online_seconds", 0)
            or 0
        )
        if total_seconds > 0:
            days, rem = divmod(total_seconds, 86400)
            hours, rem = divmod(rem, 3600)
            minutes, _ = divmod(rem, 60)
            playtime_parts = []
            if days:
                playtime_parts.append(f"{days}d")
            if hours or days:
                playtime_parts.append(f"{hours}h")
            playtime_parts.append(f"{minutes}m")
            playtime = " ".join(playtime_parts)
        else:
            playtime = str(
                activity.get("total_time_online_formatted")
                or "0m"
            )

        player_name = str(
            player_doc.get("current_name")
            or player_doc.get("name")
            or interaction.user.display_name
        )

        embed = discord.Embed(
            title=f"📊 {clip(player_name, 180)} — Player Stats",
            color=3618621,
        )
        embed.add_field(
            name="Kills",
            value=f"`{kills:,}`",
            inline=True,
        )
        embed.add_field(
            name="Deaths",
            value=f"`{deaths:,}`",
            inline=True,
        )
        embed.add_field(
            name="K/D",
            value=f"`{kd:.2f}`",
            inline=True,
        )
        embed.add_field(
            name="Headshots",
            value=f"`{int(combat.get('headshots', 0) or 0):,}`",
            inline=True,
        )
        embed.add_field(
            name="Connections",
            value=f"`{int(activity.get('times_connected', 0) or 0):,}`",
            inline=True,
        )
        embed.add_field(
            name="Time Online",
            value=f"`{playtime}`",
            inline=True,
        )
        embed.set_footer(
            text=f"JTWP.org • {product_id}"
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @discord.ui.button(
        label="Link Account",
        emoji="🔗",
        style=discord.ButtonStyle.success,
        custom_id="jtwp:dashboard:link",
        row=0,
    )
    async def link_account(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        existing = self.bot.linked_product_id_for_discord(
            interaction.user.id
        )

        if existing:
            player = load_json(
                self.bot.data_root
                / "players"
                / "records"
                / existing
                / "player.json",
                {},
            )
            name = (
                player.get("current_name")
                if isinstance(player, dict)
                else None
            )
            await interaction.response.send_message(
                "✅ Your Discord account is already linked.\n"
                f"**Player:** `{name or existing}`\n"
                f"**ProductID:** `{existing}`",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "🔗 **Link your JTWP player account**\n\n"
            "Run:\n"
            "`/account link player:<ProductID>`\n\n"
            "You can optionally provide your SteamID64 for PCVR.",
            ephemeral=True,
        )


async def respond(
    interaction: discord.Interaction,
    content: str | None = None,
    *,
    embed: discord.Embed | None = None,
    file: discord.File | None = None,
    ephemeral: bool = False,
) -> None:
    kwargs: dict[str, Any] = {"ephemeral": ephemeral}

    if content is not None:
        kwargs["content"] = content
    if embed is not None:
        kwargs["embed"] = embed
    if file is not None:
        kwargs["file"] = file

    if interaction.response.is_done():
        await interaction.followup.send(**kwargs)
    else:
        await interaction.response.send_message(**kwargs)


async def defer(
    interaction: discord.Interaction,
    *,
    ephemeral: bool = True,
) -> None:
    if not interaction.response.is_done():
        await interaction.response.defer(
            ephemeral=ephemeral,
            thinking=True,
        )


# ============================================================
# Moderation system - fresh implementation
# ============================================================

class ModerationSystem:
    """
    New moderation engine.

    Important design differences from the old bot:
    - reports use Discord modals instead of DM wait_for loops;
    - active bans are keyed by case_id, so a player can be banned
      independently on multiple JTWP servers;
    - a direct temp-ban action can create its own case;
    - scheduled unbans survive bot restarts;
    - all state writes are atomic;
    - RCON errors are recorded with exception type and message.
    """

    def __init__(self, bot: JTWPBot):
        self.bot = bot
        cfg = bot.cfg.get("moderation", {})
        self.cfg = cfg

        self.root = (
            bot.data_root / "global" / "moderation"
        )
        self.cases_dir = self.root / "cases"

        self.root.mkdir(parents=True, exist_ok=True)
        self.cases_dir.mkdir(parents=True, exist_ok=True)

        self.active_bans_path = (
            self.root / "active_bans.json"
        )
        self.audit_path = (
            self.root / "audit.jsonl"
        )
        self.webhook_tailer = JsonlWebhookTailer(
            bot=bot,
            source_path=self.audit_path,
            state_path=self.root / "moderation_webhook_state.json",
            webhook_url=bot.moderation_log_webhook_url,
            title="⚖️ JTWP Moderation Log",
        )
        self.reports_path = (
            self.root / "reports.jsonl"
        )
        self.bans_path = (
            self.root / "bans.jsonl"
        )
        self.warnings_path = (
            self.root / "warnings.jsonl"
        )
        self.offenders_path = (
            self.root / "offenders.json"
        )

        self.admin_channel_id = int(
            cfg.get("admin_channel_id")
            or bot.control_channel_id
            or 0
        )

        self.ban_check_interval = max(
            30,
            int(
                cfg.get(
                    "ban_check_interval_seconds",
                    60,
                )
            ),
        )

        rules_file = Path(
            cfg.get(
                "rules_file",
                "resource/Admin/rules_and_punishments_expanded.json",
            )
        )

        if not rules_file.is_absolute():
            rules_file = PROJECT_ROOT / rules_file

        self.rules_path = rules_file
        self.rules_doc = load_json(
            rules_file,
            {"rules": {}, "categories": []},
        )
        self.rules = self.rules_doc.get("rules", {})
        self.categories = self.rules_doc.get("categories", [])

        self._ban_lock = asyncio.Lock()

        # tasks.loop interval is fixed here, but the body handles
        # the configured minimum interval itself.
        self._last_expiry_check: datetime | None = None

    def new_case_id(self) -> str:
        return (
            "CASE-"
            + utc_now().strftime("%Y%m%d-%H%M%S")
            + "-"
            + uuid.uuid4().hex[:6].upper()
        )

    def case_path(self, case_id: str) -> Path:
        safe = case_id.upper().strip()
        return self.cases_dir / f"{safe}.json"

    def load_case(self, case_id: str) -> dict[str, Any] | None:
        path = self.case_path(case_id)
        if not path.is_file():
            return None
        value = load_json(path, None)
        return value if isinstance(value, dict) else None

    def save_case(self, case: dict[str, Any]) -> None:
        case["updated_at"] = now_iso()
        atomic_write_json(
            self.case_path(case["case_id"]),
            case,
        )

    def audit(
        self,
        event: str,
        *,
        case: dict[str, Any] | None = None,
        actor: discord.abc.User | None = None,
        **extra: Any,
    ) -> None:
        append_jsonl(
            self.audit_path,
            {
                "timestamp": now_iso(),
                "event": event,
                "case_id": (
                    case.get("case_id")
                    if case
                    else None
                ),
                "product_id": (
                    case.get("target", {}).get("product_id")
                    if case
                    else None
                ),
                "discord_user_id": (
                    str(actor.id)
                    if actor
                    else None
                ),
                "discord_username": (
                    str(actor)
                    if actor
                    else None
                ),
                "success": extra.pop(
                    "success",
                    not ("failed" in event.casefold() or "error" in event.casefold()),
                ),
                **extra,
            },
        )

    def player_history_dir(
        self,
        product_id: str,
    ) -> Path:
        return (
            self.bot.data_root
            / "players"
            / "records"
            / product_id
            / "moderation"
        )

    def append_player_history(
        self,
        case: dict[str, Any],
        event_type: str,
        **extra: Any,
    ) -> None:
        product_id = str(
            case.get("target", {}).get("product_id")
            or ""
        )

        if not product_id:
            return

        root = self.player_history_dir(product_id)
        root.mkdir(parents=True, exist_ok=True)

        event = {
            "timestamp": now_iso(),
            "event_type": event_type,
            "case_id": case["case_id"],
            "case_type": case["case_type"],
            "status": case.get("status"),
            "server_id": case.get("server_id"),
            "category": case.get("category"),
            "rule_id": case.get("rule_id"),
            **extra,
        }

        append_jsonl(
            root / "history.jsonl",
            event,
        )

        if event_type == "report_created":
            append_jsonl(
                root / "reports.jsonl",
                event,
            )
        elif event_type in {
            "ban_started",
            "ban_lifted",
            "permanent_ban_started",
        }:
            append_jsonl(
                root / "bans.jsonl",
                event,
            )
        elif event_type == "warning_created":
            append_jsonl(
                root / "warnings.jsonl",
                event,
            )

        self.rebuild_offender_entry(product_id)

    def history_counts(
        self,
        product_id: str,
    ) -> dict[str, int]:
        root = self.player_history_dir(product_id)
        result = {
            "reports": 0,
            "warnings": 0,
            "bans": 0,
        }

        for key, filename in (
            ("reports", "reports.jsonl"),
            ("warnings", "warnings.jsonl"),
            ("bans", "bans.jsonl"),
        ):
            path = root / filename
            if not path.is_file():
                continue
            try:
                result[key] = sum(
                    1
                    for line in path.read_text(
                        encoding="utf-8"
                    ).splitlines()
                    if line.strip()
                )
            except OSError:
                pass

        return result

    def rebuild_offender_entry(
        self,
        product_id: str,
    ) -> None:
        offenders = load_json(
            self.offenders_path,
            {},
        )

        if not isinstance(offenders, dict):
            offenders = {}

        player = self.bot.resolve_player(product_id)
        active = load_json(
            self.active_bans_path,
            {},
        )

        active_for_player = []

        if isinstance(active, dict):
            for ban in active.values():
                if (
                    isinstance(ban, dict)
                    and str(ban.get("product_id"))
                    == product_id
                ):
                    active_for_player.append(ban)

        offenders[product_id] = {
            "product_id": product_id,
            "current_name": (
                player.get("name")
                if player.get("resolved")
                else None
            ),
            **self.history_counts(product_id),
            "active_bans": active_for_player,
            "last_updated": now_iso(),
        }

        atomic_write_json(
            self.offenders_path,
            offenders,
        )

    def create_case(
        self,
        *,
        case_type: Literal["report", "ban", "warning"],
        target: dict[str, Any],
        server_id: str,
        incident_summary: str,
        evidence: str | None,
        submitted_by: discord.abc.User,
        category: str | None = None,
        rule_id: str | None = None,
        target_discord_id: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:

        if server_id not in self.bot.servers:
            raise ValueError(
                f"Unknown JTWP server: {server_id}"
            )

        case = {
            "case_id": self.new_case_id(),
            "case_type": case_type,
            "status": status or {
                "report": "pending_admin_review",
                "warning": "warning_recorded",
                "ban": "pending_senior_review",
            }[case_type],
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "target": {
                "product_id": target["product_id"],
                "unique_id": target.get("unique_id"),
                "name": target.get("name"),
                "platform": target.get("platform"),
                "discord_id": (
                    target_discord_id
                    or target.get("discord_id")
                ),
            },
            "server_id": server_id,
            "incident_summary": incident_summary.strip(),
            "evidence": (
                evidence.strip()
                if evidence
                else None
            ),
            "category": category,
            "rule_id": rule_id,
            "submitted_by": {
                "discord_id": str(submitted_by.id),
                "discord_name": str(submitted_by),
            },
            "review": {
                "reviewed": False,
                "reviewed_by": None,
                "reviewed_by_name": None,
                "decision": None,
                "reviewed_at": None,
                "reason": None,
            },
            "votes": {
                "approve": [],
                "reject": [],
                "escalate": [],
            },
            "discord": {
                "channel_id": None,
                "message_id": None,
            },
        }

        self.save_case(case)

        if case_type == "report":
            append_jsonl(self.reports_path, case)
            self.append_player_history(
                case,
                "report_created",
            )
        elif case_type == "warning":
            append_jsonl(self.warnings_path, case)
            self.append_player_history(
                case,
                "warning_created",
            )
        else:
            append_jsonl(
                self.bans_path,
                {
                    "timestamp": now_iso(),
                    "event": "ban_case_created",
                    "case_id": case["case_id"],
                    "case": case,
                },
            )

        self.audit(
            "case_created",
            case=case,
            actor=submitted_by,
        )

        return case

    def case_embed(
        self,
        case: dict[str, Any],
    ) -> discord.Embed:
        target = case.get("target", {})
        counts = self.history_counts(
            str(target.get("product_id") or "")
        )

        case_type = case.get("case_type", "report")
        color = {
            "report": discord.Color.orange(),
            "warning": discord.Color.gold(),
            "ban": discord.Color.red(),
        }.get(
            case_type,
            discord.Color.blurple(),
        )

        embed = discord.Embed(
            title=(
                f"{case['case_id']} • "
                f"{str(case_type).upper()}"
            ),
            description=clip(
                case.get("incident_summary"),
                3900,
            ),
            color=color,
            timestamp=(
                parse_iso(case.get("created_at"))
                or utc_now()
            ),
        )

        embed.add_field(
            name="Player",
            value=(
                f"**{clip(target.get('name'), 200)}**\n"
                f"Product ID: `{clip(target.get('product_id'), 200)}`\n"
                f"Unique ID: `{clip(target.get('unique_id'), 200)}`\n"
                f"Platform: `{clip(target.get('platform'), 100)}`"
            ),
            inline=False,
        )

        embed.add_field(
            name="Server",
            value=f"`{clip(case.get('server_id'), 150)}`",
            inline=True,
        )

        embed.add_field(
            name="Status",
            value=f"`{clip(case.get('status'), 150)}`",
            inline=True,
        )

        if case.get("category"):
            embed.add_field(
                name="Category",
                value=clip(case.get("category"), 250),
                inline=True,
            )

        if case.get("rule_id"):
            rule_id = str(case["rule_id"])
            rule = self.rules.get(rule_id, {})
            embed.add_field(
                name="Rule",
                value=(
                    f"`{rule_id}` • "
                    f"{clip(rule.get('title', rule_id), 400)}"
                ),
                inline=False,
            )

        embed.add_field(
            name="Evidence",
            value=clip(
                case.get("evidence")
                or "No additional evidence supplied.",
                1000,
            ),
            inline=False,
        )

        embed.add_field(
            name="Player History",
            value=(
                f"Reports: **{counts['reports']}**\n"
                f"Warnings: **{counts['warnings']}**\n"
                f"Ban events: **{counts['bans']}**"
            ),
            inline=True,
        )

        votes = case.get("votes", {})
        embed.add_field(
            name="Admin Votes",
            value=(
                f"Approve: **{len(votes.get('approve', []))}**\n"
                f"Reject: **{len(votes.get('reject', []))}**\n"
                f"Escalate: **{len(votes.get('escalate', []))}**"
            ),
            inline=True,
        )

        if case.get("ban"):
            ban = case["ban"]
            embed.add_field(
                name="Ban",
                value=(
                    f"Type: `{ban.get('type')}`\n"
                    f"Started: `{ban.get('started_at')}`\n"
                    f"Expires: `{ban.get('expires_at') or 'Never'}`\n"
                    f"Unbanned: `{ban.get('unbanned_at') or 'No'}`"
                ),
                inline=False,
            )

        review = case.get("review", {})
        if review.get("reviewed"):
            embed.add_field(
                name="Review",
                value=(
                    f"Decision: `{review.get('decision')}`\n"
                    f"By: {clip(review.get('reviewed_by_name'), 200)}\n"
                    f"Reason: {clip(review.get('reason'), 500)}"
                ),
                inline=False,
            )

        submitter = case.get("submitted_by", {})
        embed.set_footer(
            text=(
                f"Submitted by "
                f"{submitter.get('discord_name')}"
            )
        )

        return embed

    async def admin_channel(
        self,
    ) -> discord.abc.Messageable | None:
        if not self.admin_channel_id:
            return None

        channel = self.bot.get_channel(
            self.admin_channel_id
        )

        if channel is None:
            try:
                channel = await self.bot.fetch_channel(
                    self.admin_channel_id
                )
            except Exception:
                return None

        return channel

    async def post_case(
        self,
        case: dict[str, Any],
    ) -> None:
        channel = await self.admin_channel()

        if channel is None:
            raise RuntimeError(
                "Moderation admin channel is not configured "
                "or cannot be accessed."
            )

        message = await channel.send(
            embed=self.case_embed(case)
        )

        case["discord"] = {
            "channel_id": str(message.channel.id),
            "message_id": str(message.id),
        }

        self.save_case(case)

    async def refresh_case(
        self,
        case: dict[str, Any],
    ) -> None:
        state = case.get("discord", {})

        try:
            channel_id = int(
                state.get("channel_id") or 0
            )
            message_id = int(
                state.get("message_id") or 0
            )
        except (TypeError, ValueError):
            return

        if not channel_id or not message_id:
            return

        channel = self.bot.get_channel(channel_id)

        if channel is None:
            try:
                channel = await self.bot.fetch_channel(
                    channel_id
                )
            except Exception:
                return

        try:
            message = await channel.fetch_message(
                message_id
            )
            await message.edit(
                embed=self.case_embed(case)
            )
        except Exception:
            pass

    def add_vote(
        self,
        case: dict[str, Any],
        choice: str,
        member: discord.Member,
    ) -> None:
        choice = choice.casefold()

        if choice not in {
            "approve",
            "reject",
            "escalate",
        }:
            raise ValueError(
                "Vote must be approve, reject, or escalate."
            )

        uid = str(member.id)
        votes = case.setdefault(
            "votes",
            {
                "approve": [],
                "reject": [],
                "escalate": [],
            },
        )

        for key in (
            "approve",
            "reject",
            "escalate",
        ):
            current = votes.setdefault(key, [])
            if uid in current:
                current.remove(uid)

        votes[choice].append(uid)
        self.save_case(case)

        self.audit(
            "vote_changed",
            case=case,
            actor=member,
            vote=choice,
        )

    async def apply_temp_ban(
        self,
        case: dict[str, Any],
        days: int,
        reviewer: discord.Member,
    ) -> dict[str, Any]:

        if days < 1 or days > 3650:
            raise ValueError(
                "Temporary ban must be between 1 and 3650 days."
            )

        unique_id = str(
            case.get("target", {}).get("unique_id")
            or ""
        ).strip()

        if not unique_id:
            raise ValueError(
                "Player has no UniqueID for the RCON Ban command."
            )

        server_id = str(
            case.get("server_id") or ""
        )

        if server_id not in self.bot.servers:
            raise ValueError(
                f"Unknown server: {server_id}"
            )

        async with self._ban_lock:
            active = load_json(
                self.active_bans_path,
                {},
            )

            if not isinstance(active, dict):
                active = {}

            for existing in active.values():
                if not isinstance(existing, dict):
                    continue
                if (
                    existing.get("product_id")
                    == case["target"]["product_id"]
                    and existing.get("server_id")
                    == server_id
                ):
                    raise RuntimeError(
                        "This player already has an active ban "
                        f"on {server_id}."
                    )

            # Mark the case before network action.
            case["status"] = "tempban_starting"
            case["review"] = {
                "reviewed": True,
                "reviewed_by": str(reviewer.id),
                "reviewed_by_name": str(reviewer),
                "decision": "temporary_ban",
                "reviewed_at": now_iso(),
                "reason": case.get(
                    "review",
                    {},
                ).get("reason"),
            }
            self.save_case(case)

            try:
                response = await self.bot.rcon_send(
                    server_id,
                    f"Ban {unique_id}",
                )
            except Exception as exc:
                case["status"] = "tempban_failed"
                case["ban_error"] = (
                    f"{type(exc).__name__}: {exc}"
                )
                self.save_case(case)
                self.audit(
                    "temporary_ban_failed",
                    case=case,
                    actor=reviewer,
                    error=case["ban_error"],
                )
                raise

            started = utc_now()
            expires = started + timedelta(days=days)

            ban = {
                "case_id": case["case_id"],
                "type": "temporary",
                "product_id": (
                    case["target"]["product_id"]
                ),
                "player_name": (
                    case["target"].get("name")
                ),
                "unique_id": unique_id,
                "discord_id": (
                    case["target"].get("discord_id")
                ),
                "server_id": server_id,
                "days": days,
                "started_at": (
                    started.isoformat(
                        timespec="seconds"
                    ).replace("+00:00", "Z")
                ),
                "expires_at": (
                    expires.isoformat(
                        timespec="seconds"
                    ).replace("+00:00", "Z")
                ),
                "unbanned_at": None,
                "rcon_response": response,
            }

            case["status"] = "temporary_ban_active"
            case["ban"] = ban
            self.save_case(case)

            # Key by case ID instead of product ID.
            active[case["case_id"]] = ban
            atomic_write_json(
                self.active_bans_path,
                active,
            )

            append_jsonl(
                self.bans_path,
                {
                    "timestamp": now_iso(),
                    "event": "ban_started",
                    **ban,
                },
            )

            self.append_player_history(
                case,
                "ban_started",
                ban_type="temporary",
                days=days,
                starts_at=ban["started_at"],
                expires_at=ban["expires_at"],
            )

            self.audit(
                "temporary_ban_started",
                case=case,
                actor=reviewer,
                days=days,
                server_id=server_id,
            )

        await self.refresh_case(case)
        await self.notify_target_ban(case)

        return ban

    async def apply_permanent_ban(
        self,
        case: dict[str, Any],
        reviewer: discord.Member,
    ) -> dict[str, Any]:

        unique_id = str(
            case.get("target", {}).get("unique_id")
            or ""
        ).strip()

        if not unique_id:
            raise ValueError(
                "Player has no UniqueID for the RCON Ban command."
            )

        server_id = str(case.get("server_id") or "")

        response = await self.bot.rcon_send(
            server_id,
            f"Ban {unique_id}",
        )

        ban = {
            "case_id": case["case_id"],
            "type": "permanent",
            "product_id": case["target"]["product_id"],
            "player_name": case["target"].get("name"),
            "unique_id": unique_id,
            "discord_id": case["target"].get("discord_id"),
            "server_id": server_id,
            "days": None,
            "started_at": now_iso(),
            "expires_at": None,
            "unbanned_at": None,
            "rcon_response": response,
        }

        case["status"] = "permanent_ban_active"
        case["ban"] = ban
        case["review"] = {
            "reviewed": True,
            "reviewed_by": str(reviewer.id),
            "reviewed_by_name": str(reviewer),
            "decision": "permanent_ban",
            "reviewed_at": now_iso(),
            "reason": case.get("review", {}).get("reason"),
        }

        self.save_case(case)

        active = load_json(
            self.active_bans_path,
            {},
        )

        if not isinstance(active, dict):
            active = {}

        active[case["case_id"]] = ban

        atomic_write_json(
            self.active_bans_path,
            active,
        )

        append_jsonl(
            self.bans_path,
            {
                "timestamp": now_iso(),
                "event": "permanent_ban_started",
                **ban,
            },
        )

        self.append_player_history(
            case,
            "permanent_ban_started",
            ban_type="permanent",
            starts_at=ban["started_at"],
        )

        self.audit(
            "permanent_ban_started",
            case=case,
            actor=reviewer,
        )

        await self.refresh_case(case)
        await self.notify_target_ban(case)

        return ban

    async def reject_case(
        self,
        case: dict[str, Any],
        reviewer: discord.Member,
        reason: str,
    ) -> None:
        case["status"] = "rejected"
        case["review"] = {
            "reviewed": True,
            "reviewed_by": str(reviewer.id),
            "reviewed_by_name": str(reviewer),
            "decision": "rejected",
            "reviewed_at": now_iso(),
            "reason": reason,
        }

        self.save_case(case)

        self.append_player_history(
            case,
            "case_rejected",
            reason=reason,
        )

        self.audit(
            "case_rejected",
            case=case,
            actor=reviewer,
            reason=reason,
        )

        await self.refresh_case(case)

    def server_display_info(self, server_id: str) -> dict[str, Any]:
        path = self.bot.data_root / "servers" / server_id / "server.json"
        doc = load_json(path, {})
        if not isinstance(doc, dict):
            doc = {}
        api = doc.get("pavlov_api")
        if not isinstance(api, dict):
            api = {}
        rcon = doc.get("rcon")
        if not isinstance(rcon, dict):
            rcon = {}
        return {
            "server_id": server_id,
            "name": api.get("name") or doc.get("server_name") or server_id,
            "url": doc.get("url"),
            "platform": doc.get("platform") or api.get("server_type"),
            "map_name": api.get("map_label"),
            "game_mode": api.get("game_mode"),
            "slots": api.get("slots"),
            "max_slots": api.get("max_slots"),
            "game_port": api.get("port"),
            "rcon_port": rcon.get("port"),
        }

    def rule_record(self, rule_id: str | None) -> dict[str, Any]:
        if not rule_id:
            return {}
        rules = self.rules
        if isinstance(rules, dict):
            rec = rules.get(rule_id, {})
            return rec if isinstance(rec, dict) else {}
        if isinstance(rules, list):
            for rec in rules:
                if isinstance(rec, dict) and str(rec.get("id") or rec.get("rule_id") or "").upper() == str(rule_id).upper():
                    return rec
        return {}

    def selectable_rules(self, category: str | None = None) -> list[tuple[str, dict[str, Any]]]:
        rows: list[tuple[str, dict[str, Any]]] = []
        if isinstance(self.rules, dict):
            iterable = self.rules.items()
        elif isinstance(self.rules, list):
            iterable = ((str(x.get("id") or x.get("rule_id") or ""), x) for x in self.rules if isinstance(x, dict))
        else:
            iterable = []
        for rid, rec in iterable:
            if not rid or not isinstance(rec, dict):
                continue
            if rec.get("enabled") is False or rec.get("admin_selectable") is False:
                continue
            if category and str(rec.get("category") or "").casefold() != category.casefold():
                continue
            rows.append((str(rid).upper(), rec))
        return rows

    def rule_display(self, rule_id: str | None) -> str:
        if not rule_id:
            return "None"
        rec = self.rule_record(rule_id)
        title = rec.get("title") if rec else None
        return f"{rule_id} — {title}" if title else str(rule_id)

    def closed_case_embed(self, case: dict[str, Any]) -> discord.Embed:
        server = self.server_display_info(str(case.get("server_id") or ""))
        target = case.get("target") if isinstance(case.get("target"), dict) else {}
        review = case.get("review") if isinstance(case.get("review"), dict) else {}
        votes = case.get("votes") if isinstance(case.get("votes"), dict) else {}
        ban = case.get("ban") if isinstance(case.get("ban"), dict) else {}
        product_id = str(target.get("product_id") or "Unknown")
        history = self.history_counts(product_id) if product_id != "Unknown" else {"reports": 0, "warnings": 0, "bans": 0}
        embed = discord.Embed(
            title=str(server.get("name") or case.get("server_id") or "JTWP Server"),
            url=server.get("url") or None,
            description=(
                f"`{case.get('case_id', 'Unknown')}`\n"
                "-----------------------------------------\n\n"
                "**This is an automated message to let you know your case has been closed. Here are the results.**\n\n"
                "-----------------------------------------"
            ),
            color=3618621,
        )
        embed.set_author(name="- Moderation Team -")
        embed.set_thumbnail(url="https://www.vankrupt.com/img/Jared_03a.png")
        embed.set_footer(text="JTWP.org")
        embed.add_field(name="Case Details", value=f"`{clip(case.get('incident_summary') or 'None', 1000)}`", inline=False)
        embed.add_field(
            name="Player",
            value=(
                f"Player: `{clip(target.get('name') or 'Unknown', 150)}`\n"
                f"Product ID: `{clip(product_id, 150)}`\n"
                f"Unique ID: `{clip(target.get('unique_id') or 'Unknown', 150)}`\n"
                f"Platform: `{clip(target.get('platform') or 'Unknown', 50)}`\n"
                f"Server: `{clip(server.get('name') or case.get('server_id') or 'Unknown', 150)}`"
            ), inline=False,
        )
        embed.add_field(
            name="Classification",
            value=(
                f"Category: `{case.get('category') or 'Unclassified'}`\n"
                f"Rule: `{clip(self.rule_display(case.get('rule_id')), 300)}`\n"
                f"Status: `{case.get('status') or 'Unknown'}`"
            ), inline=False,
        )
        embed.add_field(name="Evidence", value=f"`{clip(case.get('evidence') or 'None', 1000)}`", inline=False)
        embed.add_field(name="Player History", value=(f"Reports: `{history.get('reports', 0)}`\nWarnings: `{history.get('warnings', 0)}`\nBan events: `{history.get('bans', 0)}`"), inline=True)
        embed.add_field(name="Admin Votes", value=(f"Approve: `{len(votes.get('approve', []))}`\nReject: `{len(votes.get('reject', []))}`\nEscalate: `{len(votes.get('escalate', []))}`"), inline=True)
        embed.add_field(
            name="Ban",
            value=(
                f"Type: `{ban.get('type') or 'None'}`\n"
                f"Started: `{ban.get('started_at') or 'N/A'}`\n"
                f"Expires: `{ban.get('expires_at') or 'N/A'}`\n"
                f"Unbanned: `{ban.get('unbanned_at') or 'No'}`"
            ), inline=False,
        )
        embed.add_field(
            name="Review",
            value=(
                f"Decision: `{review.get('decision') or 'None'}`\n"
                f"By: `{clip(review.get('reviewed_by_name') or 'None', 150)}`\n"
                f"Reason: `{clip(review.get('reason') or 'None', 700)}`"
            ), inline=False,
        )
        return embed

    async def notify_target_ban(
        self,
        case: dict[str, Any],
    ) -> None:
        discord_id = case.get("target", {}).get("discord_id")
        if not discord_id:
            return
        try:
            user = self.bot.get_user(int(discord_id))
            if user is None:
                user = await self.bot.fetch_user(int(discord_id))
            await user.send(
                content="This is an automated message from a Discord bot",
                embed=self.closed_case_embed(case),
            )
        except Exception as exc:
            self.audit("target_dm_failed", case=case, error=f"{type(exc).__name__}: {exc}")

    async def notify_target_unban(
        self,
        case: dict[str, Any],
    ) -> None:
        discord_id = (
            case.get("target", {}).get("discord_id")
        )

        if not discord_id:
            return

        try:
            user = self.bot.get_user(
                int(discord_id)
            )

            if user is None:
                user = await self.bot.fetch_user(
                    int(discord_id)
                )

            await user.send(
                "✅ **JTWP Temporary Ban Ended**\n\n"
                f"Server: **{self.server_display_info(str(case.get('server_id') or ''))['name']}**\n"
                f"Case: `{case['case_id']}`\n"
                f"Lifted: `{case.get('ban', {}).get('unbanned_at')}`"
            )

        except Exception as exc:
            self.audit(
                "target_unban_dm_failed",
                case=case,
                error=f"{type(exc).__name__}: {exc}",
            )

    async def expire_bans_once(self) -> None:
        async with self._ban_lock:
            active = load_json(
                self.active_bans_path,
                {},
            )

            if not isinstance(active, dict):
                return

            changed = False
            now = utc_now()

            for case_id, ban in list(active.items()):
                if not isinstance(ban, dict):
                    continue

                if ban.get("type") != "temporary":
                    continue

                expires = parse_iso(
                    ban.get("expires_at")
                )

                if not expires or expires > now:
                    continue

                unique_id = str(
                    ban.get("unique_id")
                    or ""
                ).strip()

                server_id = str(
                    ban.get("server_id")
                    or ""
                )

                case = self.load_case(case_id)

                if case is None:
                    self.audit(
                        "automatic_unban_missing_case",
                        case=None,
                        case_id=case_id,
                        server_id=server_id,
                    )
                    continue

                try:
                    response = await self.bot.rcon_send(
                        server_id,
                        f"Unban {unique_id}",
                    )
                except Exception as exc:
                    error = (
                        f"{type(exc).__name__}: {exc}"
                    )

                    ban["last_unban_error"] = error
                    ban["last_unban_attempt_at"] = (
                        now_iso()
                    )

                    active[case_id] = ban

                    self.audit(
                        "automatic_unban_failed",
                        case=case,
                        error=error,
                    )
                    continue

                lifted = now_iso()

                case["status"] = (
                    "temporary_ban_completed"
                )
                case.setdefault(
                    "ban",
                    {},
                )["unbanned_at"] = lifted
                case["ban"]["unban_response"] = (
                    response
                )

                self.save_case(case)

                append_jsonl(
                    self.bans_path,
                    {
                        "timestamp": lifted,
                        "event": "ban_lifted",
                        "case_id": case_id,
                        "product_id": (
                            ban.get("product_id")
                        ),
                        "server_id": server_id,
                        "rcon_response": response,
                    },
                )

                self.append_player_history(
                    case,
                    "ban_lifted",
                    ban_type="temporary",
                    unbanned_at=lifted,
                )

                del active[case_id]
                changed = True

                self.audit(
                    "automatic_unban_success",
                    case=case,
                )

                await self.refresh_case(case)
                await self.notify_target_unban(
                    case
                )

            if changed:
                atomic_write_json(
                    self.active_bans_path,
                    active,
                )
            elif active:
                # Persist failed-attempt timestamps/errors too.
                atomic_write_json(
                    self.active_bans_path,
                    active,
                )

    @tasks.loop(seconds=30)
    async def expiry_loop(self) -> None:
        if (
            self._last_expiry_check is not None
            and (
                utc_now() - self._last_expiry_check
            ).total_seconds()
            < self.ban_check_interval
        ):
            return

        self._last_expiry_check = utc_now()

        try:
            await self.expire_bans_once()
        except Exception as exc:
            self.audit(
                "ban_expiry_loop_error",
                error=f"{type(exc).__name__}: {exc}",
            )

    @expiry_loop.before_loop
    async def before_expiry_loop(self) -> None:
        await self.bot.wait_until_ready()


# ============================================================
# Player report modal
# ============================================================

class PlayerReportModal(
    discord.ui.Modal,
    title="JTWP Player Report",
):
    player = discord.ui.TextInput(
        label="Player name / Product ID / UniqueID",
        placeholder="Enter the player to report",
        max_length=128,
        required=True,
    )

    incident = discord.ui.TextInput(
        label="What happened?",
        style=discord.TextStyle.paragraph,
        min_length=10,
        max_length=1800,
        required=True,
    )

    evidence = discord.ui.TextInput(
        label="Evidence (optional)",
        placeholder="Links, witnesses, log times, etc.",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=False,
    )

    target_discord_id = discord.ui.TextInput(
        label="Target Discord ID (optional)",
        placeholder="Numeric Discord user ID if known",
        max_length=32,
        required=False,
    )

    def __init__(self, bot: JTWPBot, server_id: str):
        super().__init__(timeout=900)
        self.bot = bot
        self.server_id = str(server_id)

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        target = self.bot.resolve_player(
            str(self.player)
        )

        if not target.get("resolved"):
            candidates = target.get(
                "candidates",
                [],
            )

            suffix = ""

            if candidates:
                suffix = (
                    "\nPossible Product IDs:\n"
                    + "\n".join(
                        f"`{x}`"
                        for x in candidates[:10]
                    )
                )

            await interaction.followup.send(
                "❌ I could not resolve exactly one player. "
                "Try the exact Product ID."
                + suffix,
                ephemeral=True,
            )
            return

        server_id = self.server_id

        if server_id not in self.bot.servers:
            await interaction.followup.send(
                "❌ Unknown server. Available servers:\n"
                + "\n".join(
                    f"`{x}`"
                    for x in self.bot.servers
                ),
                ephemeral=True,
            )
            return

        discord_id = str(
            self.target_discord_id
        ).strip()

        if discord_id and not discord_id.isdigit():
            await interaction.followup.send(
                "❌ Target Discord ID must be numeric.",
                ephemeral=True,
            )
            return

        try:
            case = self.bot.moderation.create_case(
                case_type="report",
                target=target,
                server_id=server_id,
                incident_summary=str(
                    self.incident
                ),
                evidence=(
                    str(self.evidence).strip()
                    or None
                ),
                submitted_by=interaction.user,
                target_discord_id=(
                    discord_id or None
                ),
            )

            await self.bot.moderation.post_case(
                case
            )

            await interaction.followup.send(
                "✅ Report submitted.\n"
                f"Case: `{case['case_id']}`",
                ephemeral=True,
            )

        except Exception as exc:
            await interaction.followup.send(
                "❌ Report could not be submitted:\n"
                f"`{type(exc).__name__}: {exc}`",
                ephemeral=True,
            )


# ============================================================
# Slash commands
# ============================================================

def register_slash_commands(
    bot: JTWPBot,
) -> None:

    configured_server_ids = set(bot.servers.keys())
    server_data_root = bot.data_root / "servers"
    historical_server_ids = set()

    if server_data_root.is_dir():
        historical_server_ids = {
            p.name for p in server_data_root.iterdir()
            if p.is_dir()
        }

    server_choices = [
        app_commands.Choice(
            name=(sid if sid in configured_server_ids else f"legacy-{sid}")[:100],
            value=sid,
        )
        for sid in sorted(configured_server_ids | historical_server_ids)[:25]
    ]
    rcon_server_choices = [
         app_commands.Choice(
            name=sid[:100],
            value=sid,
        )
        for sid in sorted(configured_server_ids)[:25]
    ]

    def linked_product_id(interaction: discord.Interaction) -> str | None:
        index = load_json(
            bot.data_root / "players" / "index" / "by_discord_id.json",
            {},
        )
        if not isinstance(index, dict):
            return None
        value = index.get(str(interaction.user.id))
        if isinstance(value, list):
            return str(value[0]) if value else None
        return str(value) if value else None

    # --------------------------------------------------------
    # /report
    # --------------------------------------------------------

    report = app_commands.Group(
        name="report",
        description="JTWP player reporting",
    )

    @report.command(
        name="player",
        description="Report a player to the JTWP moderation team",
    )
    @app_commands.choices(server_id=server_choices)
    async def report_player(
        interaction: discord.Interaction,
        server_id: str,
    ):
        if interaction.guild is None:
            await respond(
                interaction,
                "⛔ Use this command inside the JTWP Discord server.",
                ephemeral=True,
            )
            return

        if server_id not in bot.servers:
            await respond(
                interaction,
                "❌ Reports can only use a currently configured server.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            PlayerReportModal(bot, server_id)
        )

    bot.tree.add_command(report)

    # --------------------------------------------------------
    # /moderation
    # --------------------------------------------------------

    moderation = app_commands.Group(
        name="moderation",
        description="JTWP moderation actions",
    )

    @moderation.command(
        name="case",
        description="View a moderation case",
    )
    async def moderation_case(
        interaction: discord.Interaction,
        case_id: str,
    ):
        if not await bot.require(
            interaction,
            admin=True,
        ):
            return

        case = bot.moderation.load_case(
            case_id
        )

        if not case:
            await respond(
                interaction,
                "❌ Case not found.",
                ephemeral=True,
            )
            return

        await respond(
            interaction,
            embed=bot.moderation.case_embed(case),
            ephemeral=True,
        )

    @moderation.command(
        name="vote",
        description="Vote approve/reject/escalate on a case",
    )
    @app_commands.choices(
        choice=[
            app_commands.Choice(
                name="Approve",
                value="approve",
            ),
            app_commands.Choice(
                name="Reject",
                value="reject",
            ),
            app_commands.Choice(
                name="Escalate",
                value="escalate",
            ),
        ]
    )
    async def moderation_vote(
        interaction: discord.Interaction,
        case_id: str,
        choice: app_commands.Choice[str],
    ):
        if not await bot.require(
            interaction,
            admin=True,
        ):
            return

        case = bot.moderation.load_case(
            case_id
        )

        if not case:
            await respond(
                interaction,
                "❌ Case not found.",
                ephemeral=True,
            )
            return

        bot.moderation.add_vote(
            case,
            choice.value,
            interaction.user,
        )

        await bot.moderation.refresh_case(
            case
        )

        await respond(
            interaction,
            f"✅ Vote recorded: **{choice.name}** on `{case['case_id']}`.",
            ephemeral=True,
        )

    category_choices = [
        app_commands.Choice(name="Unclassified", value="__NONE__"),
        *[
            app_commands.Choice(name=str(name)[:100], value=str(name)[:100])
            for name in bot.moderation.categories[:24]
        ],
    ]

    @moderation.command(name="category", description="Set or clear a case category")
    @app_commands.choices(category=category_choices)
    async def moderation_category(
        interaction: discord.Interaction,
        case_id: str,
        category: app_commands.Choice[str],
    ):
        if not await bot.require(interaction, admin=True):
            return
        case = bot.moderation.load_case(case_id)
        if not case:
            await respond(interaction, "❌ Case not found.", ephemeral=True)
            return
        old_category = case.get("category")
        old_rule = case.get("rule_id")
        new_category = None if category.value == "__NONE__" else category.value
        case["category"] = new_category
        case["rule_id"] = None
        bot.moderation.save_case(case)
        bot.moderation.audit(
            "case_category_changed", case=case, actor=interaction.user,
            old_category=old_category, new_category=new_category,
            cleared_rule_id=old_rule,
        )
        await bot.moderation.refresh_case(case)
        if new_category:
            rows = bot.moderation.selectable_rules(new_category)
            lines = [
                f"**{rid} — {rec.get('title', rid)}**\n{clip(rec.get('description') or rec.get('summary') or '', 500)}"
                for rid, rec in rows
            ]
            rule_text = "\n\n".join(lines) or "No selectable rules are configured for this category."
        else:
            rule_text = "Set a category before selecting a rule."
        await respond(
            interaction,
            f"✅ Category: **{new_category or 'Unclassified'}**\nRule reset to **None**.\n\n**Available rules**\n{clip(rule_text, 1800)}",
            ephemeral=True,
        )

    async def rule_autocomplete(
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        case_id = str(getattr(interaction.namespace, "case_id", "") or "")
        case = bot.moderation.load_case(case_id) if case_id else None
        category = case.get("category") if isinstance(case, dict) else None
        choices = [app_commands.Choice(name="None / No Rule", value="__NONE__")]
        if not category:
            return choices
        needle = current.casefold().strip()
        for rid, rec in bot.moderation.selectable_rules(category):
            title = str(rec.get("title") or rid)
            label = f"{rid} — {title}"
            if needle and needle not in label.casefold():
                continue
            choices.append(app_commands.Choice(name=label[:100], value=rid[:100]))
            if len(choices) >= 25:
                break
        return choices

    @moderation.command(name="rule", description="Set or clear the rule for a categorized case")
    @app_commands.autocomplete(rule_id=rule_autocomplete)
    async def moderation_rule(
        interaction: discord.Interaction,
        case_id: str,
        rule_id: str,
    ):
        if not await bot.require(interaction, admin=True):
            return
        case = bot.moderation.load_case(case_id)
        if not case:
            await respond(interaction, "❌ Case not found.", ephemeral=True)
            return
        category = case.get("category")
        if not category:
            await respond(interaction, "❌ Set the case category first.", ephemeral=True)
            return
        old_rule = case.get("rule_id")
        normalized = None if rule_id == "__NONE__" else rule_id.strip().upper()
        if normalized:
            rec = bot.moderation.rule_record(normalized)
            if not rec:
                await respond(interaction, f"❌ Unknown rule: `{normalized}`", ephemeral=True)
                return
            if str(rec.get("category") or "").casefold() != str(category).casefold():
                await respond(interaction, "❌ That rule does not belong to the selected category.", ephemeral=True)
                return
            if rec.get("enabled") is False or rec.get("admin_selectable") is False:
                await respond(interaction, "❌ That rule is not selectable.", ephemeral=True)
                return
        case["rule_id"] = normalized
        if case.get("status") == "pending_admin_review":
            case["status"] = "admin_reviewed"
        bot.moderation.save_case(case)
        bot.moderation.audit(
            "case_rule_changed", case=case, actor=interaction.user,
            old_rule_id=old_rule, new_rule_id=normalized,
        )
        await bot.moderation.refresh_case(case)
        if normalized:
            rec = bot.moderation.rule_record(normalized)
            detail = (
                f"**{normalized} — {rec.get('title', normalized)}**\n"
                f"Category: **{rec.get('category') or category}**\n\n"
                f"{clip(rec.get('description') or rec.get('summary') or '', 1200)}"
            )
        else:
            detail = "**None / No Rule**"
        await respond(interaction, f"✅ Rule updated.\n\n{detail}", ephemeral=True)

    @moderation.command(
        name="tempban",
        description="Approve a case as a temporary ban",
    )
    async def moderation_tempban(
        interaction: discord.Interaction,
        case_id: str,
        days: app_commands.Range[int, 1, 3650],
    ):
        if not await bot.require(
            interaction,
            senior=True,
        ):
            return

        case = bot.moderation.load_case(
            case_id
        )

        if not case:
            await respond(
                interaction,
                "❌ Case not found.",
                ephemeral=True,
            )
            return

        await defer(
            interaction,
            ephemeral=True,
        )

        try:
            ban = await bot.moderation.apply_temp_ban(
                case,
                int(days),
                interaction.user,
            )

            await interaction.followup.send(
                "✅ Temporary ban applied.\n"
                f"Case: `{case['case_id']}`\n"
                f"Server: `{ban['server_id']}`\n"
                f"Expires: `{ban['expires_at']}`",
                ephemeral=True,
            )

        except Exception as exc:
            await interaction.followup.send(
                "❌ Temporary ban failed:\n"
                f"`{type(exc).__name__}: {exc}`",
                ephemeral=True,
            )

    @moderation.command(
        name="tempban-player",
        description="Create a case and immediately temp-ban a player",
    )
    @app_commands.choices(server_id=server_choices)
    async def moderation_tempban_player(
        interaction: discord.Interaction,
        player: str,
        server_id: str,
        days: app_commands.Range[int, 1, 3650],
        reason: str,
        target_discord_id: str | None = None,
    ):
        if not await bot.require(
            interaction,
            senior=True,
        ):
            return

        target = bot.resolve_player(player)

        if not target.get("resolved"):
            await respond(
                interaction,
                "❌ Could not resolve exactly one player. "
                "Use the exact Product ID.",
                ephemeral=True,
            )
            return

        if server_id not in bot.servers:
            await respond(
                interaction,
                "❌ Unknown server.",
                ephemeral=True,
            )
            return

        if (
            target_discord_id
            and not target_discord_id.isdigit()
        ):
            await respond(
                interaction,
                "❌ target_discord_id must be numeric.",
                ephemeral=True,
            )
            return

        await defer(
            interaction,
            ephemeral=True,
        )

        try:
            case = bot.moderation.create_case(
                case_type="ban",
                target=target,
                server_id=server_id,
                incident_summary=reason,
                evidence=None,
                submitted_by=interaction.user,
                target_discord_id=target_discord_id,
                status="pending_tempban",
            )

            await bot.moderation.post_case(
                case
            )

            ban = await bot.moderation.apply_temp_ban(
                case,
                int(days),
                interaction.user,
            )

            await interaction.followup.send(
                "✅ Case created and temporary ban applied.\n"
                f"Case: `{case['case_id']}`\n"
                f"Player: **{target.get('name')}**\n"
                f"Server: `{server_id}`\n"
                f"Expires: `{ban['expires_at']}`",
                ephemeral=True,
            )

        except Exception as exc:
            await interaction.followup.send(
                "❌ Temp-ban failed:\n"
                f"`{type(exc).__name__}: {exc}`",
                ephemeral=True,
            )

    @moderation.command(
        name="permban",
        description="Approve a case as a permanent ban",
    )
    async def moderation_permban(
        interaction: discord.Interaction,
        case_id: str,
    ):
        if not await bot.require(
            interaction,
            senior=True,
        ):
            return

        case = bot.moderation.load_case(
            case_id
        )

        if not case:
            await respond(
                interaction,
                "❌ Case not found.",
                ephemeral=True,
            )
            return

        await defer(
            interaction,
            ephemeral=True,
        )

        try:
            await bot.moderation.apply_permanent_ban(
                case,
                interaction.user,
            )

            await interaction.followup.send(
                f"✅ Permanent ban applied for `{case['case_id']}`.",
                ephemeral=True,
            )

        except Exception as exc:
            await interaction.followup.send(
                "❌ Permanent ban failed:\n"
                f"`{type(exc).__name__}: {exc}`",
                ephemeral=True,
            )

    @moderation.command(
        name="reject",
        description="Reject and close a moderation case",
    )
    async def moderation_reject(
        interaction: discord.Interaction,
        case_id: str,
        reason: str,
    ):
        if not await bot.require(
            interaction,
            senior=True,
        ):
            return

        case = bot.moderation.load_case(
            case_id
        )

        if not case:
            await respond(
                interaction,
                "❌ Case not found.",
                ephemeral=True,
            )
            return

        await bot.moderation.reject_case(
            case,
            interaction.user,
            reason,
        )

        await respond(
            interaction,
            f"✅ `{case['case_id']}` rejected and closed.",
            ephemeral=True,
        )

    @moderation.command(
        name="active-bans",
        description="Show active JTWP bans tracked by the bot",
    )
    async def moderation_active_bans(
        interaction: discord.Interaction,
    ):
        if not await bot.require(
            interaction,
            admin=True,
        ):
            return

        data = load_json(
            bot.moderation.active_bans_path,
            {},
        )

        await bot.send_json(
            interaction,
            "🔨 Active JTWP Bans",
            data,
            "active-bans.json",
            ephemeral=True,
        )

    bot.tree.add_command(moderation)

    # --------------------------------------------------------
    # /warn + /banlog
    # --------------------------------------------------------

    @bot.tree.command(name="warn", description="Create a formal JTWP warning")
    @app_commands.choices(server_id=server_choices)
    async def warn(
        interaction: discord.Interaction,
        player: str,
        server_id: str,
        reason: str,
        evidence: str | None = None,
    ):
        if not await bot.require(interaction, admin=True):
            return
        target = bot.resolve_player(player)
        if not target.get("resolved"):
            await respond(interaction, "❌ Could not resolve exactly one player. Use the exact Product ID.", ephemeral=True)
            return
        if server_id not in bot.servers:
            await respond(interaction, "❌ Select a current server.", ephemeral=True)
            return
        case = bot.moderation.create_case(
            case_type="warning",
            target=target,
            server_id=server_id,
            incident_summary=reason,
            evidence=evidence,
            submitted_by=interaction.user,
        )
        await bot.moderation.post_case(case)
        await respond(interaction, f"✅ Warning recorded as `{case['case_id']}`.", ephemeral=True)

    @bot.tree.command(name="banlog", description="Create a proposed JTWP ban case")
    @app_commands.choices(server_id=server_choices)
    async def banlog(
        interaction: discord.Interaction,
        player: str,
        server_id: str,
        reason: str,
        evidence: str | None = None,
    ):
        if not await bot.require(interaction, admin=True):
            return
        target = bot.resolve_player(player)
        if not target.get("resolved"):
            await respond(interaction, "❌ Could not resolve exactly one player. Use the exact Product ID.", ephemeral=True)
            return
        if server_id not in bot.servers:
            await respond(interaction, "❌ Select a current server.", ephemeral=True)
            return
        case = bot.moderation.create_case(
            case_type="ban",
            target=target,
            server_id=server_id,
            incident_summary=reason,
            evidence=evidence,
            submitted_by=interaction.user,
        )
        await bot.moderation.post_case(case)
        await respond(interaction, f"✅ Ban case `{case['case_id']}` created and sent for review.", ephemeral=True)

    # --------------------------------------------------------
    # /rcon
    # --------------------------------------------------------

    async def rcon_command_autocomplete(
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Search every configured RCON + RCON Plus command.

        Discord can display only 25 autocomplete suggestions at once. This
        callback searches the complete catalog, so typing a few letters lets
        admins reach any command without losing the Custom option.
        """
        query = str(current or "").strip().casefold()
        available = [
            name for name in RCON_COMMANDS
            if name.casefold() not in RCON_BLOCKED_COMMANDS
        ]

        if query:
            starts = [x for x in available if x.casefold().startswith(query)]
            contains = [
                x for x in available
                if query in x.casefold() and x not in starts
            ]
            available = starts + contains

        choices = [
            app_commands.Choice(
                name="✏️ Custom command...",
                value="__custom__",
            )
        ]
        for name in available:
            if len(choices) >= 25:
                break
            choices.append(app_commands.Choice(name=name, value=name))
        return choices

    @bot.tree.command(
        name="rcon",
        description="Send an RCON or RCON Plus command to a JTWP Pavlov server",
    )
    @app_commands.choices(server_id=rcon_server_choices)
    @app_commands.describe(
        command="Search/select a command, or choose Custom command",
        arguments="Arguments appended to the selected command",
        custom_command="Full manual command when Custom command is selected",
    )
    @app_commands.autocomplete(command=rcon_command_autocomplete)
    async def rcon(
        interaction: discord.Interaction,
        server_id: str,
        command: str,
        arguments: str | None = None,
        custom_command: str | None = None,
    ):
        if not await bot.require(interaction, admin=True):
            return

        selected = str(command or "").strip()
        arguments = str(arguments or "").strip()
        custom_command = str(custom_command or "").strip()

        if selected == "__custom__":
            if not custom_command:
                await respond(
                    interaction,
                    "❌ Select **Custom command** and enter the full command in `custom_command`.",
                    ephemeral=True,
                )
                return
            final_command = custom_command
        else:
            canonical = next(
                (x for x in RCON_COMMANDS if x.casefold() == selected.casefold()),
                None,
            )
            if canonical is None:
                await respond(
                    interaction,
                    "❌ Choose a command from the autocomplete list or select **Custom command**.",
                    ephemeral=True,
                )
                return
            final_command = canonical + (f" {arguments}" if arguments else "")

        parts = final_command.split()
        command_key = parts[0].casefold() if parts else ""

        # Ban is intentionally unavailable even through the Custom option.
        if command_key in RCON_BLOCKED_COMMANDS:
            await respond(
                interaction,
                "⛔ `Ban` is not available through `/rcon`. Use the moderation ban workflow instead.",
                ephemeral=True,
            )
            return

        level = bot.permission_level(interaction.user)
        if level == "ADMIN" and command_key not in bot.admin_rcon:
            await respond(
                interaction,
                f"⛔ ADMIN cannot use RCON command `{command_key}`.",
                ephemeral=True,
            )
            return

        await defer(interaction, ephemeral=True)

        try:
            response = await bot.rcon_send(server_id, final_command)
            bot.audit(
                interaction,
                "rcon",
                True,
                server_id=server_id,
                command=final_command,
                selected_command=selected,
                custom=(selected == "__custom__"),
            )

            raw = json.dumps(response, indent=2, ensure_ascii=False, default=str)
            if len(raw) > 3800:
                raw = raw[-3800:]

            await interaction.followup.send(
                f"**RCON:** `{clip(final_command, 500)}`\n```json\n{raw}\n```",
                ephemeral=True,
            )
        except Exception as exc:
            bot.audit(
                interaction,
                "rcon",
                False,
                server_id=server_id,
                command=final_command,
                selected_command=selected,
                custom=(selected == "__custom__"),
                error=f"{type(exc).__name__}: {exc}",
            )
            await interaction.followup.send(
                "❌ RCON failed:\n"
                f"`{type(exc).__name__}: {exc}`",
                ephemeral=True,
            )

    # --------------------------------------------------------
    # /leaderboard
    # --------------------------------------------------------

    leaderboard_group = app_commands.Group(
        name="leaderboard",
        description="Public JTWP player leaderboards",
    )

    @leaderboard_group.command(
        name="kills",
        description="Players with the most kills",
    )
    async def leaderboard_kills(
        interaction: discord.Interaction,
    ):
        await bot.send_player_leaderboard(
            interaction,
            field="kills",
            title="Most Kills",
            label="Kills",
            emoji="💀",
        )

    @leaderboard_group.command(
        name="headshots",
        description="Players with the most headshots",
    )
    async def leaderboard_headshots(
        interaction: discord.Interaction,
    ):
        await bot.send_player_leaderboard(
            interaction,
            field="headshots",
            title="Most Headshots",
            label="Headshots",
            emoji="🎯",
        )

    @leaderboard_group.command(
        name="botkills",
        description="Players with the most bot kills",
    )
    async def leaderboard_botkills(
        interaction: discord.Interaction,
    ):
        await bot.send_player_leaderboard(
            interaction,
            field="bot_kills",
            title="Most Bot Kills",
            label="Bot Kills",
            emoji="🤖",
        )

    @leaderboard_group.command(
        name="deaths",
        description="Players with the most deaths",
    )
    async def leaderboard_deaths(
        interaction: discord.Interaction,
    ):
        await bot.send_player_leaderboard(
            interaction,
            field="deaths",
            title="Most Deaths",
            label="Deaths",
            emoji="☠️",
        )

    @leaderboard_group.command(
        name="teamkills",
        description="Players with the most teamkills",
    )
    async def leaderboard_teamkills(
        interaction: discord.Interaction,
    ):
        await bot.send_player_leaderboard(
            interaction,
            field="teamkills",
            title="Most Teamkills",
            label="Teamkills",
            emoji="⚠️",
        )

    @leaderboard_group.command(
        name="suicides",
        description="Players with the most suicides",
    )
    async def leaderboard_suicides(
        interaction: discord.Interaction,
    ):
        await bot.send_player_leaderboard(
            interaction,
            field="suicides",
            title="Most Suicides",
            label="Suicides",
            emoji="💥",
        )

    @leaderboard_group.command(
        name="connections",
        description="Players with the most server connections",
    )
    async def leaderboard_connections(
        interaction: discord.Interaction,
    ):
        await bot.send_player_leaderboard(
            interaction,
            field="times_connected",
            title="Most Connections",
            label="Connections",
            emoji="🔌",
        )

    @leaderboard_group.command(
        name="matches",
        description="Players with the most recorded matches",
    )
    async def leaderboard_matches(
        interaction: discord.Interaction,
    ):
        await bot.send_player_leaderboard(
            interaction,
            field="matches",
            title="Most Matches",
            label="Matches",
            emoji="🎮",
        )

    @leaderboard_group.command(
        name="kd",
        description="Players with the highest K/D ratio",
    )
    async def leaderboard_kd(
        interaction: discord.Interaction,
    ):
        # Require at least 100 kills so a 1-0 player does not lead the board.
        cache = await asyncio.to_thread(
            bot.build_leaderboard_cache
        )
        rows = [
            row for row in cache.get("players", [])
            if (
                isinstance(row, dict)
                and int(row.get("kills", 0) or 0) >= 100
            )
        ]
        rows.sort(
            key=lambda row: float(row.get("kd", 0) or 0),
            reverse=True,
        )
        rows = rows[:10]

        embed = discord.Embed(
            title="📈 Highest K/D",
            description=(
                "Top JTWP players by K/D ratio. "
                "Requires at least `100` recorded kills."
            ),
            color=3618621,
        )

        lines = []
        for rank, row in enumerate(rows, start=1):
            lines.append(
                f"{bot.leaderboard_medal(rank)} "
                f"**{clip(str(row.get('name') or 'Unknown'), 80)}** "
                f"— `{float(row.get('kd', 0)):,.2f}` "
                f"(`{int(row.get('kills', 0)):,}` K / "
                f"`{int(row.get('deaths', 0)):,}` D)"
            )

        embed.add_field(
            name="K/D",
            value="\n".join(lines) if lines else "No qualifying data yet.",
            inline=False,
        )
        embed.set_footer(text="JTWP.org • Player Leaderboards")
        await respond(
            interaction,
            embed=embed,
            ephemeral=False,
        )

    @leaderboard_group.command(
        name="guns",
        description="Guns/items responsible for the most player kills",
    )
    async def leaderboard_guns(
        interaction: discord.Interaction,
    ):
        cache = await asyncio.to_thread(
            bot.build_leaderboard_cache
        )
        guns = list(cache.get("guns", []))[:10]

        embed = discord.Embed(
            title="🔫 Most Kills By Gun",
            description=(
                "Top weapons/items by total recorded player kills "
                "across all JTWP player weapon records."
            ),
            color=3618621,
        )

        lines = []
        for rank, row in enumerate(guns, start=1):
            lines.append(
                f"{bot.leaderboard_medal(rank)} "
                f"**{clip(str(row.get('weapon') or 'Unknown'), 80)}** "
                f"— `{int(row.get('kills', 0)):,}` kills"
            )

        embed.add_field(
            name="Weapon Kills",
            value="\n".join(lines) if lines else "No weapon kill data yet.",
            inline=False,
        )
        embed.set_footer(text="JTWP.org • Player Leaderboards")
        await respond(
            interaction,
            embed=embed,
            ephemeral=False,
        )

    async def leaderboard_weapon_autocomplete(
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        cache = await asyncio.to_thread(
            bot.build_leaderboard_cache
        )
        current_cf = str(current or "").casefold()
        names = [
            str(row.get("weapon"))
            for row in cache.get("guns", [])
            if isinstance(row, dict) and row.get("weapon")
        ]

        if current_cf:
            starts = [
                name for name in names
                if name.casefold().startswith(current_cf)
            ]
            contains = [
                name for name in names
                if current_cf in name.casefold()
                and name not in starts
            ]
            names = starts + contains

        return [
            app_commands.Choice(
                name=name[:100],
                value=name,
            )
            for name in names[:25]
        ]

    @leaderboard_group.command(
        name="weapon",
        description="Players with the most kills using a specific weapon",
    )
    @app_commands.autocomplete(weapon=leaderboard_weapon_autocomplete)
    async def leaderboard_weapon(
        interaction: discord.Interaction,
        weapon: str,
    ):
        cache = await asyncio.to_thread(
            bot.build_leaderboard_cache
        )
        key = str(weapon).casefold()
        rows = list(
            cache.get("weapon_players", {}).get(key, [])
        )[:10]

        embed = discord.Embed(
            title=f"🔫 {clip(weapon, 180)} Leaderboard",
            description=(
                f"Players with the most recorded kills using "
                f"**{clip(weapon, 100)}**."
            ),
            color=3618621,
        )

        lines = []
        for rank, row in enumerate(rows, start=1):
            lines.append(
                f"{bot.leaderboard_medal(rank)} "
                f"**{clip(str(row.get('name') or 'Unknown'), 80)}** "
                f"— `{int(row.get('kills', 0)):,}` kills "
                f"• `{int(row.get('headshots', 0)):,}` HS"
            )

        embed.add_field(
            name="Players",
            value="\n".join(lines) if lines else "No data for that weapon.",
            inline=False,
        )
        embed.set_footer(text="JTWP.org • Player Leaderboards")
        await respond(
            interaction,
            embed=embed,
            ephemeral=False,
        )

    @leaderboard_group.command(
        name="refresh",
        description="Refresh the leaderboard cache now",
    )
    async def leaderboard_refresh(
        interaction: discord.Interaction,
    ):
        if not await bot.require(
            interaction,
            admin=True,
        ):
            return

        await defer(
            interaction,
            ephemeral=True,
        )
        cache = await asyncio.to_thread(
            bot.build_leaderboard_cache,
            force=True,
        )
        await interaction.followup.send(
            "✅ Leaderboards refreshed. "
            f"Indexed `{len(cache.get('players', [])):,}` players "
            f"and `{len(cache.get('guns', [])):,}` weapons/items.",
            ephemeral=True,
        )

    bot.tree.add_command(leaderboard_group)

    # --------------------------------------------------------
    # /player
    # --------------------------------------------------------

    player_group = app_commands.Group(
        name="player",
        description="JTWP player database commands",
    )

    async def send_player_file(
        interaction: discord.Interaction,
        product_id: str,
        filename: str,
        title: str,
        *,
        require_admin_access: bool = True,
    ):
        if require_admin_access:
            if not await bot.require(interaction, admin=True):
                return

        path = (
            bot.data_root
            / "players"
            / "records"
            / product_id
            / filename
        )

        if not path.is_file():
            await respond(
                interaction,
                f"❌ `{filename}` not found for `{product_id}`.",
                ephemeral=True,
            )
            return

        await bot.send_json(
            interaction,
            title,
            load_json(path, {}),
            filename,
            ephemeral=True,
        )

    @player_group.command(
        name="productid",
        description="Resolve player name/UniqueID/ProductID",
    )
    async def player_productid(
        interaction: discord.Interaction,
        player: str,
    ):
        result = bot.resolve_player(player)

        await bot.send_json(
            interaction,
            "Player Resolution",
            result,
            "player-resolution.json",
            ephemeral=True,
        )

    @player_group.command(
        name="network",
        description="Show a player's network record",
    )
    async def player_network(
        interaction: discord.Interaction,
        product_id: str,
    ):
        await send_player_file(
            interaction,
            product_id,
            "ips.json",
            "🌐 Player Network",
        )

    @player_group.command(
        name="names",
        description="Show a player's name history",
    )
    async def player_names(
        interaction: discord.Interaction,
        product_id: str,
    ):
        await send_player_file(
            interaction,
            product_id,
            "names.json",
            "📝 Player Names",
        )

    @player_group.command(
        name="stats",
        description="Show a player's stats",
    )
    async def player_stats(
        interaction: discord.Interaction,
        product_id: str,
    ):
        await send_player_file(
            interaction,
            product_id,
            "stats.json",
            "📊 Player Stats",
        )

    @player_group.command(
        name="weapons",
        description="Show a player's weapon stats",
    )
    async def player_weapons(
        interaction: discord.Interaction,
        product_id: str,
    ):
        await send_player_file(
            interaction,
            product_id,
            "weapons.json",
            "🔫 Player Weapons",
            require_admin_access=False,
        )

    @player_group.command(
        name="profile",
        description="Show a player's main record",
    )
    async def player_profile(
        interaction: discord.Interaction,
        product_id: str,
    ):
        directory = (
            bot.data_root
            / "players"
            / "records"
            / product_id
        )

        filename = (
            "player.json"
            if (directory / "player.json").is_file()
            else "profile.json"
        )

        await send_player_file(
            interaction,
            product_id,
            filename,
            "👤 Player Record",
            require_admin_access=False,
        )

    @player_group.command(
        name="lookup",
        description="Find by partial name/ProductID/UniqueID and dump the player record",
    )
    async def player_lookup(interaction: discord.Interaction, query: str):
        if not await bot.require(interaction, admin=True):
            return

        result = bot.resolve_player(query)
        if not result.get("resolved"):
            await bot.send_json(
                interaction,
                "🔎 Player Lookup",
                {
                    "query": query,
                    "resolved": False,
                    "candidates": (result.get("candidates") or [])[:25],
                },
                "player-lookup.json",
                ephemeral=True,
            )
            return

        product_id = str(result.get("product_id"))
        directory = bot.data_root / "players" / "records" / product_id
        dump = {
            "query": query,
            "identity": {
                "product_id": product_id,
                "player_name": result.get("name"),
                "unique_id": result.get("unique_id"),
                "platform": result.get("platform"),
            },
            "files": {},
        }

        if directory.is_dir():
            for path in sorted(directory.glob("*.json")):
                dump["files"][path.name] = load_json(path, None)

        bot.audit(interaction, "player_lookup_dump", True, query=query, product_id=product_id)
        await bot.send_json(
            interaction,
            f"👤 Player Dump — {product_id}",
            dump,
            f"{product_id}-full-dump.json",
            ephemeral=True,
        )

    bot.tree.add_command(player_group)

    # --------------------------------------------------------
    # /badges + /badge
    # --------------------------------------------------------

    async def badge_name_autocomplete(
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        registry = bot.load_badge_registry()
        definitions = registry.get("badges", {})
        if not isinstance(definitions, dict):
            return []

        current_folded = str(current or "").strip().casefold()
        names = sorted(
            (str(name) for name in definitions.keys()),
            key=str.casefold,
        )
        if current_folded:
            names = [
                name for name in names
                if current_folded in name.casefold()
            ]

        return [
            app_commands.Choice(name=name[:100], value=name)
            for name in names[:25]
        ]

    async def send_badges_public(
        interaction: discord.Interaction,
        product_id: str,
        player_doc: dict[str, Any],
    ) -> None:
        """Post one public embed with all earned badge icons in a 75x75 row."""
        # Evaluate all automatic badge criteria before displaying.
        bot.evaluate_automatic_badges(
            product_id,
            player_doc=player_doc,
        )

        registry = bot.load_badge_registry()
        definitions = registry.get("badges", {})
        if not isinstance(definitions, dict):
            definitions = {}

        owned_doc = bot.load_player_badges(product_id)
        owned = owned_doc.get("badges", {})
        if not isinstance(owned, dict):
            owned = {}

        player_name = str(
            player_doc.get("current_name")
            or player_doc.get("name")
            or product_id
        )

        summary = discord.Embed(
            title=f"🏆 {clip(player_name, 180)} — Badges",
            description=(
                f"**Player:** `{product_id}`\n"
                f"**Badges Earned:** `{len(owned)}`"
            ),
            color=3618621,
        )

        if not owned:
            summary.add_field(
                name="Badges",
                value="This player has not earned any badges yet.",
                inline=False,
            )
            summary.set_footer(text="JTWP Player Badges")

            await respond(
                interaction,
                embed=summary,
                ephemeral=False,
            )
            return

        badge_rows: list[
            tuple[str, dict[str, Any], dict[str, Any]]
        ] = []

        for badge_name, award in sorted(
            owned.items(),
            key=lambda kv: (
                int(
                    definitions.get(kv[0], {}).get("id", 999999)
                    if isinstance(definitions.get(kv[0]), dict)
                    else 999999
                ),
                str(kv[0]).casefold(),
            ),
        ):
            definition = definitions.get(badge_name, {})
            if not isinstance(definition, dict):
                definition = {}

            if not isinstance(award, dict):
                award = {}

            badge_rows.append(
                (str(badge_name), definition, award)
            )

        # Keep the readable badge names/details in the same embed.
        badge_lines: list[str] = []

        for badge_name, definition, award in badge_rows:
            display_name = str(
                definition.get("name")
                or badge_name
            )
            badge_id = definition.get("id")
            awarded_at = str(
                award.get("awarded_at")
                or "Unknown"
            )

            if isinstance(badge_id, int):
                title = f"`#{badge_id:03d}` **{display_name}**"
            else:
                title = f"**{display_name}**"

            badge_lines.append(
                f"{title} — `{awarded_at}`"
            )

        # Stay safely inside Discord's embed description limit.
        details = "\n".join(badge_lines)
        if details:
            summary.add_field(
                name="Earned Badges",
                value=clip(details, 1024),
                inline=False,
            )

        # Image downloading/resizing is blocking work, so run it off the
        # bot event loop. The shared builder automatically splits badges into
        # multiple images when the configured per-image limit is reached.
        badge_images = await asyncio.to_thread(
            bot.build_badge_strip_images,
            badge_rows,
        )

        summary.set_footer(
            text=(
                f"JTWP Player Badges • {len(owned)} earned • "
                f"{bot.badges_per_image} per image"
            )
        )

        if not badge_images:
            if interaction.response.is_done():
                await interaction.followup.send(
                    embed=summary,
                    ephemeral=False,
                )
            else:
                await interaction.response.send_message(
                    embed=summary,
                    ephemeral=False,
                )
            return

        # Discord permits multiple embeds/files in one message. Each embed gets
        # one badge strip image. Current badge counts are well below the 10
        # embed/message limit, but batch defensively in groups of 10.
        for batch_start in range(0, len(badge_images), 10):
            batch = badge_images[batch_start:batch_start + 10]
            embeds: list[discord.Embed] = []
            files: list[discord.File] = []

            for local_index, image in enumerate(batch):
                global_index = batch_start + local_index
                first_badge = global_index * bot.badges_per_image + 1
                last_badge = min(
                    first_badge + bot.badges_per_image - 1,
                    len(owned),
                )

                filename = (
                    f"{product_id}-badges-{global_index + 1}.png"
                )
                files.append(
                    discord.File(image, filename=filename)
                )

                if global_index == 0:
                    row_embed = summary
                else:
                    row_embed = discord.Embed(
                        title=(
                            f"🏆 Badges {first_badge}–{last_badge}"
                        ),
                        color=3618621,
                    )
                    row_embed.set_footer(
                        text=f"JTWP Player Badges • {len(owned)} earned"
                    )

                row_embed.set_image(
                    url=f"attachment://{filename}"
                )
                embeds.append(row_embed)

            if not interaction.response.is_done():
                await interaction.response.send_message(
                    embeds=embeds,
                    files=files,
                    ephemeral=False,
                )
            else:
                await interaction.followup.send(
                    embeds=embeds,
                    files=files,
                    ephemeral=False,
                )

    @bot.tree.command(
        name="badges",
        description="Show badges earned by a JTWP player",
    )
    async def badges(
        interaction: discord.Interaction,
        player: str | None = None,
    ):
        if interaction.guild is None:
            await respond(
                interaction,
                "⛔ Use this command inside the JTWP Discord server.",
                ephemeral=True,
            )
            return

        if player:
            target = bot.resolve_player(player)
            if not target.get("resolved"):
                await respond(
                    interaction,
                    "❌ Could not resolve exactly one player. "
                    "Try the exact Product ID.",
                    ephemeral=True,
                )
                return
        else:
            index = load_json(
                bot.data_root
                / "players"
                / "index"
                / "by_discord_id.json",
                {},
            )
            pid = (
                index.get(str(interaction.user.id))
                if isinstance(index, dict)
                else None
            )
            if isinstance(pid, list):
                pid = pid[0] if pid else None

            if not pid:
                await respond(
                    interaction,
                    "❌ Your Discord account is not linked. "
                    "Provide a player name/Product ID or use `/account link`.",
                    ephemeral=True,
                )
                return

            target = bot.resolve_player(str(pid))

        product_id = str(target.get("product_id"))
        player_doc = load_json(
            bot.player_path(product_id),
            {},
        )
        if not isinstance(player_doc, dict):
            await respond(
                interaction,
                "❌ Player record not found.",
                ephemeral=True,
            )
            return

        await send_badges_public(
            interaction,
            product_id,
            player_doc,
        )

    badge_group = app_commands.Group(
        name="badge",
        description="JTWP badge administration",
    )

    @badge_group.command(
        name="add",
        description="Award a badge to a JTWP player",
    )
    @app_commands.autocomplete(badge=badge_name_autocomplete)
    async def badge_add(
        interaction: discord.Interaction,
        player: str,
        badge: str,
        reason: str | None = None,
    ):
        if not await bot.require(
            interaction,
            admin=True,
        ):
            return

        target = bot.resolve_player(player)
        if not target.get("resolved"):
            await respond(
                interaction,
                "❌ Could not resolve exactly one player. "
                "Use the exact Product ID if needed.",
                ephemeral=True,
            )
            return

        product_id = str(target["product_id"])

        try:
            newly_awarded, record = bot.award_badge(
                product_id,
                badge,
                awarded_by=str(interaction.user),
                awarded_by_discord_id=str(interaction.user.id),
                reason=reason or "Awarded by JTWP administrator.",
            )
        except ValueError as exc:
            await respond(
                interaction,
                f"❌ {exc}",
                ephemeral=True,
            )
            return

        bot.audit(
            interaction,
            "badge_added" if newly_awarded else "badge_already_owned",
            True,
            product_id=product_id,
            badge_name=record.get("name"),
            reason=reason,
        )

        if newly_awarded:
            await respond(
                interaction,
                f"✅ Awarded **{record.get('name')}** to `{product_id}`.",
                ephemeral=True,
            )
        else:
            await respond(
                interaction,
                f"ℹ️ `{product_id}` already has **{record.get('name')}**.",
                ephemeral=True,
            )


    @badge_group.command(
        name="remove",
        description="Remove a badge from a JTWP player",
    )
    @app_commands.autocomplete(badge=badge_name_autocomplete)
    async def badge_remove(
        interaction: discord.Interaction,
        player: str,
        badge: str,
    ):
        if not await bot.require(interaction, admin=True):
            return

        target = bot.resolve_player(player)
        if not target.get("resolved"):
            await respond(
                interaction,
                "❌ Could not resolve exactly one player. Use the exact Product ID if needed.",
                ephemeral=True,
            )
            return

        product_id = str(target["product_id"])
        removed, canonical_name = bot.revoke_badge(product_id, badge)
        if not removed:
            await respond(
                interaction,
                f"ℹ️ `{product_id}` does not currently own **{badge}**.",
                ephemeral=True,
            )
            return

        bot.audit(
            interaction,
            "badge_removed",
            True,
            product_id=product_id,
            badge_name=canonical_name,
        )
        await respond(
            interaction,
            f"✅ Removed **{canonical_name}** from `{product_id}`.",
            ephemeral=True,
        )

    @badge_group.command(
        name="list",
        description="List all configured JTWP badges",
    )
    async def badge_list(interaction: discord.Interaction):
        registry = bot.load_badge_registry()
        definitions = registry.get("badges", {})
        if not isinstance(definitions, dict):
            definitions = {}

        rows = []
        for name, definition in sorted(
            definitions.items(),
            key=lambda kv: int(kv[1].get("id", 999999)) if isinstance(kv[1], dict) else 999999,
        ):
            if not isinstance(definition, dict):
                definition = {}
            badge_id = definition.get("id")
            auto = "AUTO" if definition.get("automatic") else "MANUAL"
            rows.append(
                f"`#{int(badge_id):03d}` **{definition.get('name') or name}** — `{auto}`\\n"
                f"{definition.get('description') or 'No description.'}"
                if isinstance(badge_id, int)
                else f"**{definition.get('name') or name}** — `{auto}`"
            )

        embed = discord.Embed(
            title="🏆 JTWP Badge Registry",
            description=clip("\\n\\n".join(rows) or "No badges configured.", 4000),
            color=3618621,
        )
        embed.set_footer(text=f"JTWP Player Badges • {len(definitions)} configured")
        await respond(interaction, embed=embed, ephemeral=True)

    @badge_group.command(
        name="refresh",
        description="Re-check automatic badges for one player",
    )
    async def badge_refresh(
        interaction: discord.Interaction,
        player: str,
    ):
        if not await bot.require(interaction, admin=True):
            return

        target = bot.resolve_player(player)
        if not target.get("resolved"):
            await respond(
                interaction,
                "❌ Could not resolve exactly one player. Use the exact Product ID if needed.",
                ephemeral=True,
            )
            return

        product_id = str(target["product_id"])
        awarded = bot.evaluate_automatic_badges(product_id)
        await respond(
            interaction,
            (
                f"✅ Checked automatic badges for `{product_id}`.\\n"
                + (
                    "**New:** " + ", ".join(awarded)
                    if awarded
                    else "No new badges were earned."
                )
            ),
            ephemeral=True,
        )

    @badge_group.command(
        name="backfill",
        description="Backfill automatic badges for existing player records",
    )
    async def badge_backfill(
        interaction: discord.Interaction,
        limit: app_commands.Range[int, 1, 200000] | None = None,
    ):
        if not await bot.require(interaction, owner=True):
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        result = await asyncio.to_thread(
            bot.backfill_automatic_badges,
            limit=limit,
        )
        await interaction.followup.send(
            (
                "✅ Automatic badge backfill complete.\\n"
                f"**Players checked:** `{result['checked']:,}`\\n"
                f"**Players receiving new badges:** `{result['players_awarded']:,}`\\n"
                f"**Badges awarded:** `{result['awarded']:,}`"
            ),
            ephemeral=True,
        )

    bot.tree.add_command(badge_group)

    # --------------------------------------------------------
    # /index
    # --------------------------------------------------------

    index_group = app_commands.Group(
        name="index",
        description="JTWP player index lists",
    )

    async def send_index_keys(interaction: discord.Interaction, filename: str, title: str):
        if not await bot.require(interaction, admin=True):
            return
        path = bot.data_root / "players" / "index" / filename
        data = load_json(path, None)
        if not isinstance(data, dict):
            await respond(interaction, f"❌ `{filename}` is missing or invalid.", ephemeral=True)
            return
        keys = sorted((str(k) for k in data.keys()), key=str.casefold)
        body = "\n".join(keys) + ("\n" if keys else "")
        file = discord.File(io.BytesIO(body.encode("utf-8")), filename=filename.replace(".json", ".txt"))
        await respond(
            interaction,
            content=f"📋 **{title}** — `{len(keys):,}` entries — `{now_iso()}`",
            file=file,
            ephemeral=True,
        )
        bot.audit(interaction, f"index_{Path(filename).stem}", True, entries=len(keys))

    @index_group.command(name="names", description="Download every key from by_name.json")
    async def index_names(interaction: discord.Interaction):
        await send_index_keys(interaction, "by_name.json", "Player Name Index")

    @index_group.command(name="iphashes", description="Download every key from by_ip_hash.json")
    async def index_iphashes(interaction: discord.Interaction):
        await send_index_keys(interaction, "by_ip_hash.json", "IP Hash Index")

    @index_group.command(name="productids", description="Download every key from by_product_id.json")
    async def index_productids(interaction: discord.Interaction):
        await send_index_keys(interaction, "by_product_id.json", "Product ID Index")

    @index_group.command(name="uniqueids", description="Download every key from by_unique_id.json")
    async def index_uniqueids(interaction: discord.Interaction):
        await send_index_keys(interaction, "by_unique_id.json", "Unique ID Index")

    bot.tree.add_command(index_group)

    # --------------------------------------------------------
    # /account
    # --------------------------------------------------------

    account_group = app_commands.Group(
        name="account",
        description="Link Discord/Steam information to a JTWP player profile",
    )

    @account_group.command(name="link", description="Link your Discord account to a JTWP player profile")
    async def account_link(
        interaction: discord.Interaction,
        player: str,
        steam_id: str | None = None,
    ):
        if interaction.guild is None:
            await respond(interaction, "⛔ Use this inside the JTWP Discord server.", ephemeral=True)
            return
        target = bot.resolve_player(player)
        if not target.get("resolved"):
            await respond(interaction, "❌ Could not resolve exactly one player. Use the exact Product ID.", ephemeral=True)
            return
        pid = str(target["product_id"])
        by_discord = load_json(bot.data_root / "players" / "index" / "by_discord_id.json", {})
        existing = by_discord.get(str(interaction.user.id)) if isinstance(by_discord, dict) else None
        if existing and str(existing) != pid:
            await respond(interaction, f"❌ Your Discord account is already linked to `{existing}`.", ephemeral=True)
            return
        player_doc = load_json(bot.player_path(pid), {})
        linked = player_doc.setdefault("linked_accounts", {})
        linked["discord"] = {
            "user_id": str(interaction.user.id),
            "username": str(interaction.user),
            "display_name": getattr(interaction.user, "display_name", str(interaction.user)),
            "linked_at": now_iso(),
            "verified_discord_identity": True,
        }
        chosen_steam = (steam_id or "").strip()
        if not chosen_steam and str(player_doc.get("platform", "")).upper() == "PCVR":
            uid = str(player_doc.get("unique_id") or "")
            if uid.isdigit() and len(uid) == 17:
                chosen_steam = uid
        steam_error = None
        if chosen_steam:
            try:
                linked["steam"] = await asyncio.to_thread(bot.steam_summary, chosen_steam)
                linked["steam"]["linked_at"] = now_iso()
            except Exception as exc:
                steam_error = f"{type(exc).__name__}: {exc}"
        request_id = "LINK-" + uuid.uuid4().hex[:8].upper()
        linked["profile_link"] = {
            "request_id": request_id,
            "status": "pending_admin_review",
            "verified": False,
            "requested_at": now_iso(),
            "requested_by_discord_id": str(interaction.user.id),
            "requested_by": str(interaction.user),
        }
        bot.save_player(pid, player_doc)
        bot.rebuild_link_indexes()

        # Badge #001 is earned immediately when Discord is linked.
        # This is idempotent, so a repeated link cannot duplicate the badge.
        discord_badge_new = bot.ensure_discord_link_badge(pid, player_doc)

        bot.log_account_event(
            "account_link_requested",
            pid,
            interaction.user,
            request_id=request_id,
            steam_id=chosen_steam or None,
            steam_error=steam_error,
            discord_badge_awarded=discord_badge_new,
        )
        await asyncio.to_thread(
            bot.post_account_link_pending_webhook,
            request_id=request_id,
            product_id=pid,
            player_doc=player_doc,
            requester=interaction.user,
            steam_id=chosen_steam or None,
            steam_error=steam_error,
        )
        msg = (
            f"✅ Account information linked to `{pid}` and marked **pending admin review**.\n"
            f"Request ID: `{request_id}`"
        )
        if steam_error:
            msg += f"\n⚠️ Steam lookup: `{clip(steam_error, 500)}`"
        await respond(interaction, msg, ephemeral=True)

    @account_group.command(name="steam", description="Add or refresh Steam info on your linked JTWP profile")
    async def account_steam(interaction: discord.Interaction, steam_id: str):
        index = load_json(bot.data_root / "players" / "index" / "by_discord_id.json", {})
        pid = index.get(str(interaction.user.id)) if isinstance(index, dict) else None
        if not pid:
            await respond(interaction, "❌ Link your JTWP profile first with `/account link`.", ephemeral=True)
            return
        await defer(interaction, ephemeral=True)
        try:
            summary = await asyncio.to_thread(bot.steam_summary, steam_id)
            player_doc = load_json(bot.player_path(str(pid)), {})
            linked = player_doc.setdefault("linked_accounts", {})
            summary["linked_at"] = now_iso()
            linked["steam"] = summary
            bot.save_player(str(pid), player_doc)
            bot.rebuild_link_indexes()
            bot.log_account_event("steam_account_linked", str(pid), interaction.user, steam_id=steam_id, steam_username=summary.get("username"))
            await interaction.followup.send(f"✅ Steam profile **{summary.get('username') or steam_id}** linked to `{pid}`.", ephemeral=True)
        except Exception as exc:
            await interaction.followup.send(f"❌ Steam lookup failed: `{type(exc).__name__}: {exc}`", ephemeral=True)

    @account_group.command(name="info", description="Show your linked JTWP account information")
    async def account_info(interaction: discord.Interaction):
        index = load_json(bot.data_root / "players" / "index" / "by_discord_id.json", {})
        pid = index.get(str(interaction.user.id)) if isinstance(index, dict) else None
        if not pid:
            await respond(interaction, "❌ Your Discord account is not linked.", ephemeral=True)
            return
        player_doc = load_json(bot.player_path(str(pid)), {})
        await bot.send_json(interaction, "🔗 Linked Account", {"product_id": pid, "linked_accounts": player_doc.get("linked_accounts")}, "linked-account.json", ephemeral=True)

    @account_group.command(name="approve", description="Approve a pending player/account link")
    async def account_approve(interaction: discord.Interaction, product_id: str):
        if not await bot.require(interaction, admin=True):
            return
        player_doc = load_json(bot.player_path(product_id), None)
        if not isinstance(player_doc, dict):
            await respond(interaction, "❌ Player record not found.", ephemeral=True)
            return
        linked = player_doc.setdefault("linked_accounts", {})
        profile_link = linked.setdefault("profile_link", {})
        profile_link.update({
            "status": "verified",
            "verified": True,
            "verified_at": now_iso(),
            "verified_by_discord_id": str(interaction.user.id),
            "verified_by": str(interaction.user),
        })
        bot.save_player(product_id, player_doc)
        bot.rebuild_link_indexes()
        bot.log_account_event("account_link_approved", product_id, interaction.user)
        await respond(interaction, f"✅ Account link for `{product_id}` approved.", ephemeral=True)

    @account_group.command(name="unlink", description="Remove your Discord/Steam links from your JTWP profile")
    async def account_unlink(interaction: discord.Interaction):
        index = load_json(bot.data_root / "players" / "index" / "by_discord_id.json", {})
        pid = index.get(str(interaction.user.id)) if isinstance(index, dict) else None
        if not pid:
            await respond(interaction, "❌ Your Discord account is not linked.", ephemeral=True)
            return
        player_doc = load_json(bot.player_path(str(pid)), {})
        player_doc["linked_accounts"] = {"discord": None, "steam": None, "profile_link": None}
        bot.save_player(str(pid), player_doc)
        bot.rebuild_link_indexes()
        bot.log_account_event("account_unlinked", str(pid), interaction.user)
        await respond(interaction, f"✅ Account links removed from `{pid}`.", ephemeral=True)

    @account_group.command(name="data", description="Show your own JTWP lifetime player data")
    async def account_data(interaction: discord.Interaction):
        pid = linked_product_id(interaction)
        if not pid:
            await respond(interaction, "❌ Your Discord account is not linked.", ephemeral=True)
            return

        directory = bot.data_root / "players" / "records" / pid
        payload = {"product_id": pid, "data": {}}

        for filename in (
            "player.json",
            "profile.json",
            "stats.json",
            "weapons.json",
            "names.json",
            "awards.json",
            "flags.json",
        ):
            path = directory / filename
            if path.is_file():
                payload["data"][filename] = load_json(path, None)

        # ips.json and private/global network data are intentionally excluded.
        await bot.send_json(
            interaction,
            "📊 Your JTWP Data",
            payload,
            f"{pid}-account-data.json",
            ephemeral=True,
        )

    @account_group.command(name="sessions", description="Show your last 10 JTWP play sessions")
    async def account_sessions(interaction: discord.Interaction):
        pid = linked_product_id(interaction)
        if not pid:
            await respond(interaction, "❌ Your Discord account is not linked.", ephemeral=True)
            return

        events_path = bot.data_root / "global" / "connections" / "events.jsonl"
        sessions = []

        if events_path.is_file():
            with events_path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    try:
                        event = json.loads(line)
                    except Exception:
                        continue
                    if str(event.get("product_id") or "") != pid:
                        continue
                    if event.get("type") != "player_left":
                        continue
                    sessions.append({
                        key: event.get(key)
                        for key in (
                            "server_id",
                            "connected_at",
                            "joined_at",
                            "disconnected_at",
                            "duration_seconds",
                            "duration_formatted",
                            "disconnect_reason",
                            "player_name",
                            "platform",
                        )
                    })

        await bot.send_json(
            interaction,
            "🕒 Your Recent JTWP Sessions",
            {"product_id": pid, "sessions": sessions[-10:][::-1]},
            f"{pid}-recent-sessions.json",
            ephemeral=True,
        )

    bot.tree.add_command(account_group)

    # --------------------------------------------------------
    # /network
    # --------------------------------------------------------

    network_group = app_commands.Group(
        name="network",
        description="JTWP network monitoring commands",
    )

    @network_group.command(
        name="verify_connection",
        description="Mark a known IP hash as a verified connection",
    )
    async def network_verify_connection(
        interaction: discord.Interaction,
        ip_hash: str,
        label: str,
        notes: str | None = None,
    ):
        if not await bot.require(interaction, admin=True):
            return
        try:
            rec = bot.set_verified_connection(
                ip_hash,
                label=label,
                actor=interaction.user,
                notes=notes,
            )
        except ValueError as exc:
            await respond(interaction, f"❌ {exc}", ephemeral=True)
            return

        bot.audit(
            interaction,
            "verified_connection_added",
            True,
            ip_hash=rec["ip_hash"],
            label=rec.get("label"),
        )
        await respond(
            interaction,
            (
                "✅ **Verified Connection Added**\n"
                f"ipHASH: `{rec['ip_hash']}`\n"
                f"Label: `{clip(rec.get('label'), 200)}`"
            ),
            ephemeral=True,
        )

    @network_group.command(
        name="unverify_connection",
        description="Remove an IP hash from the verified connection list",
    )
    async def network_unverify_connection(
        interaction: discord.Interaction,
        ip_hash: str,
    ):
        if not await bot.require(interaction, admin=True):
            return
        try:
            rec = bot.remove_verified_connection(ip_hash)
        except ValueError as exc:
            await respond(interaction, f"❌ {exc}", ephemeral=True)
            return

        if rec is None:
            await respond(interaction, "❌ That ipHASH is not verified.", ephemeral=True)
            return

        bot.audit(
            interaction,
            "verified_connection_removed",
            True,
            ip_hash=rec["ip_hash"],
            label=rec.get("label"),
        )
        await respond(
            interaction,
            f"✅ Removed verified connection `{rec['ip_hash']}`.",
            ephemeral=True,
        )

    @network_group.command(
        name="verified_connections",
        description="Show manually verified connection hashes",
    )
    async def network_verified_connections(interaction: discord.Interaction):
        if not await bot.require(interaction, admin=True):
            return
        data = bot.load_verified_connections()
        entries = data.get("verified_connections", {})
        rows = []
        for ip_hash, rec in sorted(entries.items()):
            if not isinstance(rec, dict):
                rec = {}
            rows.append({
                "ip_hash": ip_hash,
                "verified": bool(rec.get("verified", True)),
                "label": rec.get("label"),
                "notes": rec.get("notes"),
                "added_at": rec.get("added_at"),
                "updated_at": rec.get("updated_at"),
                "added_by": rec.get("added_by"),
            })
        await bot.send_json(
            interaction,
            f"🔒 Verified Connections — {len(rows)}",
            {"verified_connections": rows},
            "verified-connections.json",
            ephemeral=True,
        )

    @network_group.command(name="ddos", description="Refresh the static JTWP network/DDoS status")
    async def network_ddos(interaction: discord.Interaction):
        if not await bot.require(interaction, admin=True):
            return
        await defer(interaction, ephemeral=True)
        try:
            message = await bot.refresh_ddos_status(create_if_missing=True)
            if message is None:
                raise RuntimeError(
                    "DDoS status channel is not configured. "
                    "Set discord_bot.ddos_status_channel_id in config.json."
                )
            bot.audit(
                interaction,
                "network_ddos",
                True,
                channel_id=str(message.channel.id),
                message_id=str(message.id),
            )
            await interaction.followup.send(
                f"✅ DDoS status dashboard refreshed: {message.jump_url}",
                ephemeral=True,
            )
        except Exception as exc:
            bot.audit(
                interaction,
                "network_ddos",
                False,
                error=f"{type(exc).__name__}: {exc}",
            )
            await interaction.followup.send(
                f"❌ Failed to refresh DDoS status: `{type(exc).__name__}: {exc}`",
                ephemeral=True,
            )

    bot.tree.add_command(network_group)

    # --------------------------------------------------------
    # /data
    # --------------------------------------------------------

    data_group = app_commands.Group(
        name="data",
        description="JTWP collector data commands",
    )

    @data_group.command(
        name="indexstats",
        description="Show live and rebuild player index counts",
    )
    async def data_indexstats(
        interaction: discord.Interaction,
    ):
        index_dir = (
            bot.data_root
            / "players"
            / "index"
        )

        def count_file(path: Path) -> Any:
            value = load_json(path, None)
            if isinstance(value, (dict, list)):
                return len(value)
            return None

        current = {}

        for filename in (
            "by_ip_hash.json",
            "by_name.json",
            "by_product_id.json",
            "by_unique_id.json",
            "by_discord_id.json",
            "by_steam_id.json",
        ):
            path = index_dir / filename
            current[path.stem] = (
                count_file(path)
                if path.is_file()
                else "MISSING"
            )

        backups = {}

        for dirname in (
            "backup-before-rebuild",
            "backup-after-rebuild",
        ):
            directory = index_dir / dirname
            section = {}

            if directory.is_dir():
                for path in sorted(
                    directory.glob("*.json")
                ):
                    section[path.stem] = (
                        count_file(path)
                    )
            else:
                section["status"] = "MISSING"

            backups[dirname] = section

        report = {
            "timestamp": now_iso(),
            "current_indexes": current,
            "backups": backups,
            "rebuild_status": load_json(
                index_dir / "rebuild_status.json",
                None,
            ),
        }

        await bot.send_json(
            interaction,
            "📊 JTWP Player Index Stats",
            report,
            "index-stats.json",
            ephemeral=True,
        )

    async def owner_process(
        interaction: discord.Interaction,
        *,
        event: str,
        command: list[str],
        timeout: int,
        title: str,
    ) -> None:
        if not await bot.require(
            interaction,
            owner=True,
        ):
            return

        await defer(
            interaction,
            ephemeral=True,
        )

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout,
                check=False,
            )

            bot.audit(
                interaction,
                event,
                result.returncode == 0,
                returncode=result.returncode,
            )

            output = strip_ansi(
                result.stdout
                or "(no output)"
            )[-bot.output_limit:]

            await interaction.followup.send(
                embed=discord.Embed(
                    title=title,
                    description=f"```text\n{output}\n```",
                ),
                ephemeral=True,
            )

        except Exception as exc:
            bot.audit(
                interaction,
                event,
                False,
                error=f"{type(exc).__name__}: {exc}",
            )

            await interaction.followup.send(
                "❌ Command failed:\n"
                f"`{type(exc).__name__}: {exc}`",
                ephemeral=True,
            )

    @data_group.command(
        name="export",
        description="Export and compress JTWP collector data",
    )
    async def data_export(
        interaction: discord.Interaction,
    ):
        await owner_process(
            interaction,
            event="exportdata",
            command=[
                "/home/steam/jtwp-collector/venv/bin/python3",
                "-u",
                str(
                    PROJECT_ROOT
                    / "scripts"
                    / "export-data.py"
                ),
            ],
            timeout=1800,
            title="📦 JTWP Data Export",
        )

    @data_group.command(
        name="backup",
        description="Create a JTWP data backup",
    )
    async def data_backup(
        interaction: discord.Interaction,
    ):
        await owner_process(
            interaction,
            event="backupdata",
            command=[
                "/home/steam/jtwp-collector/venv/bin/python3",
                "-u",
                str(
                    PROJECT_ROOT
                    / "scripts"
                    / "backup-data.py"
                ),
            ],
            timeout=1800,
            title="📦 JTWP Data Backup",
        )

    bot.tree.add_command(data_group)

    # --------------------------------------------------------
    # /jtwp
    # --------------------------------------------------------

    jtwp = app_commands.Group(
        name="jtwp",
        description="JTWP service controls",
    )

    @jtwp.command(
        name="restart",
        description="Restart JTWP collector services",
    )
    async def jtwp_restart(
        interaction: discord.Interaction,
    ):
        if not await bot.require(
            interaction,
            owner=True,
        ):
            return

        await interaction.response.send_message(
            "🔄 Restarting JTWP services...",
            ephemeral=True,
        )

        process = await asyncio.create_subprocess_exec(
            "sudo",
            "-n",
            "/usr/local/bin/restart-jtwp",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

        bot.audit(
            interaction,
            "restartjtwp",
            True,
            pid=process.pid,
        )

    @jtwp.command(
        name="runcollector",
        description="Run the JTWP collector",
    )
    async def jtwp_runcollector(
        interaction: discord.Interaction,
    ):
        await owner_process(
            interaction,
            event="runcollector",
            command=[
                "/home/steam/jtwp-collector/venv/bin/python3",
                str(PROJECT_ROOT / "collector.py"),
                "-c",
                str(bot.cfg_path),
            ],
            timeout=3600,
            title="🚀 JTWP Collector",
        )

    @jtwp.command(
        name="runpavlovapi",
        description="Update Pavlov public API data",
    )
    async def jtwp_runpavlovapi(
        interaction: discord.Interaction,
    ):
        await owner_process(
            interaction,
            event="runpavlovapi",
            command=[
                "/home/steam/jtwp-collector/venv/bin/python3",
                str(
                    PROJECT_ROOT
                    / "update_pavlov_api.py"
                ),
                "-c",
                str(bot.cfg_path),
            ],
            timeout=600,
            title="🌐 Pavlov API Update",
        )

    bot.tree.add_command(jtwp)

    # --------------------------------------------------------
    # /server
    # --------------------------------------------------------

    server_group = app_commands.Group(
        name="server",
        description="Pavlov server controls",
    )

    @server_group.command(
        name="service",
        description="Run an allowed systemctl action",
    )
    @app_commands.choices(server_id=server_choices)
    async def server_service(
        interaction: discord.Interaction,
        server_id: str,
        action: str,
    ):
        if not await bot.require(
            interaction,
            owner=True,
        ):
            return

        action = action.casefold()

        if action not in bot.systemctl_actions:
            await respond(
                interaction,
                "❌ Invalid action. Allowed: "
                + ", ".join(
                    sorted(bot.systemctl_actions)
                ),
                ephemeral=True,
            )
            return

        if server_id not in bot.servers:
            await respond(
                interaction,
                "❌ Unknown server.",
                ephemeral=True,
            )
            return

        service = f"{server_id}.service"

        await owner_process(
            interaction,
            event="systemctl",
            command=[
                "sudo",
                "-n",
                "systemctl",
                action,
                service,
            ],
            timeout=120,
            title=f"⚙️ {service} {action}",
        )

    @server_group.command(
        name="clear-mods",
        description="Clear downloaded Pavlov mods for a server",
    )
    @app_commands.choices(server_id=server_choices)
    async def server_clear_mods(
        interaction: discord.Interaction,
        server_id: str,
    ):
        await owner_process(
            interaction,
            event="clearpavlovmods",
            command=[
                "sudo",
                "-n",
                "/usr/local/bin/clear-pavlov-mods",
                server_id,
            ],
            timeout=600,
            title="🧹 Clear Pavlov Mods",
        )

    @server_group.command(name="set-url", description="Set the public URL for a JTWP server")
    @app_commands.choices(server_id=server_choices)
    async def server_set_url(
        interaction: discord.Interaction,
        server_id: str,
        url: str,
    ):
        if not await bot.require(interaction, owner=True):
            return
        url = url.strip()
        if not (url.startswith("https://") or url.startswith("http://")):
            await respond(interaction, "❌ URL must start with http:// or https://", ephemeral=True)
            return
        if server_id not in bot.servers:
            await respond(interaction, "❌ Unknown server.", ephemeral=True)
            return
        path = bot.data_root / "servers" / server_id / "server.json"
        data = load_json(path, {"server_id": server_id})
        if not isinstance(data, dict):
            data = {"server_id": server_id}
        old_url = data.get("url")
        data["url"] = url
        data["url_updated_at"] = now_iso()
        data["url_updated_by"] = {
            "discord_user_id": str(interaction.user.id),
            "discord_username": str(interaction.user),
        }
        atomic_write_json(path, data)
        bot.audit(interaction, "server_url_changed", True, server_id=server_id, old_url=old_url, new_url=url)
        await respond(interaction, f"✅ Server URL updated.\nServer: `{server_id}`\nURL: <{url}>", ephemeral=True)

    @server_group.command(name="data", description="Dump non-private data/settings for a JTWP server")
    @app_commands.choices(server_id=server_choices)
    async def server_data(interaction: discord.Interaction, server_id: str):
        if not await bot.require(interaction, admin=True):
            return

        server_dir = bot.data_root / "servers" / server_id
        if not server_dir.is_dir():
            await respond(interaction, "❌ No stored data exists for that server.", ephemeral=True)
            return

        dump = {
            "server_id": server_id,
            "legacy": server_id not in bot.servers,
            "data": {},
        }

        # Only public/settings-oriented folders. Never dump RCON host files,
        # SSH/private IP data, or raw event streams.
        for child_name in ("server", "maps", "mods", "bans", "rounds"):
            child = server_dir / child_name
            if child.is_file() and child.suffix == ".json":
                dump["data"][child.name] = load_json(child, None)
            elif child.is_dir():
                section = {}
                for path in sorted(child.rglob("*.json")):
                    if path.name in {"known_hosts.json", "failed_hosts.json"}:
                        continue
                    section[str(path.relative_to(child))] = load_json(path, None)
                if section:
                    dump["data"][child_name] = section

        for path in sorted(server_dir.glob("*.json")):
            if path.name not in {"known_hosts.json", "failed_hosts.json"}:
                dump["data"][path.name] = load_json(path, None)

        await bot.send_json(
            interaction,
            f"🖥️ Server Data — {server_id}",
            dump,
            f"{server_id}-server-data.json",
            ephemeral=True,
        )

    bot.tree.add_command(server_group)

    # --------------------------------------------------------
    # /loop
    # --------------------------------------------------------

    loop_group = app_commands.Group(
        name="loop",
        description="JTWP RCON loop controls",
    )

    @loop_group.command(
        name="start",
        description="Start the RCON loop",
    )
    @app_commands.choices(server_id=server_choices)
    async def loop_start(
        interaction: discord.Interaction,
        server_id: str,
        seconds: app_commands.Range[int, 1, 3600],
    ):
        await owner_process(
            interaction,
            event="loop_start",
            command=[
                "/home/steam/jtwp-collector/venv/bin/python3",
                str(
                    PROJECT_ROOT
                    / "scripts"
                    / "set-rcon-loop.py"
                ),
                "-c",
                str(bot.cfg_path),
                "start",
                server_id,
                str(seconds),
            ],
            timeout=30,
            title="🔁 RCON Loop Start",
        )

    @loop_group.command(
        name="stop",
        description="Stop the RCON loop",
    )
    async def loop_stop(
        interaction: discord.Interaction,
    ):
        await owner_process(
            interaction,
            event="loop_stop",
            command=[
                "/home/steam/jtwp-collector/venv/bin/python3",
                str(
                    PROJECT_ROOT
                    / "scripts"
                    / "set-rcon-loop.py"
                ),
                "-c",
                str(bot.cfg_path),
                "stop",
            ],
            timeout=30,
            title="🔁 RCON Loop Stop",
        )

    @loop_group.command(
        name="status",
        description="Show the RCON loop state",
    )
    async def loop_status(
        interaction: discord.Interaction,
    ):
        if not await bot.require(
            interaction,
            admin=True,
        ):
            return

        cfg = bot.cfg.get(
            "rcon_loop",
            {},
        )

        report = {
            "control": load_json(
                Path(cfg.get("control_path", "")),
                None,
            ),
            "output": load_json(
                Path(cfg.get("output_path", "")),
                None,
            ),
        }

        await bot.send_json(
            interaction,
            "🔁 RCON Loop",
            report,
            "rcon-loop.json",
            ephemeral=True,
        )

    bot.tree.add_command(loop_group)


# ============================================================
# Main
# ============================================================

async def async_main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-c",
        "--config",
        default="config.json",
    )

    args = parser.parse_args()

    cfg_path = Path(
        args.config
    ).expanduser().resolve()

    if not cfg_path.is_file():
        raise SystemExit(
            f"Config not found: {cfg_path}"
        )

    load_env_file(
        cfg_path.parent / ".env"
    )

    cfg = json.loads(
        cfg_path.read_text(
            encoding="utf-8"
        )
    )

    bot_cfg = cfg.get(
        "discord_bot",
        {},
    )

    if not bot_cfg.get(
        "enabled",
        True,
    ):
        raise SystemExit(
            "Discord bot disabled in config.json"
        )

    token_env = bot_cfg.get(
        "token_env",
        "JTWP_DISCORD_BOT_TOKEN",
    )

    token = os.getenv(
        token_env,
        "",
    ).strip()

    if not token:
        raise SystemExit(
            f"Missing environment variable: {token_env}"
        )

    bot = JTWPBot(
        cfg,
        cfg_path,
    )

    # Per-user cooldown for the plain-text "badges" trigger.
    # This prevents accidental/repeated spam while keeping the trigger simple.
    badge_text_cooldowns: dict[int, float] = {}
    badge_text_cooldown_seconds = 10.0

    async def reply_with_member_badges(message: discord.Message) -> None:
        discord_id = str(message.author.id)

        by_discord = load_json(
            bot.data_root / "players" / "index" / "by_discord_id.json",
            {},
        )

        product_id = None
        if isinstance(by_discord, dict):
            value = by_discord.get(discord_id)
            if isinstance(value, dict):
                product_id = (
                    value.get("product_id")
                    or value.get("id")
                )
            elif value:
                product_id = value

        if not product_id:
            await message.reply(
                "❌ Your Discord account is not linked to a JTWP player.",
                mention_author=False,
            )
            return

        product_id = str(product_id)
        player_dir = (
            bot.data_root
            / "players"
            / "records"
            / product_id
        )

        player_doc = load_json(
            player_dir / "player.json",
            load_json(player_dir / "profile.json", {}),
        )
        if not isinstance(player_doc, dict):
            player_doc = {}

        # Ensure linked users receive Discord Badge #001 before display.
        bot.ensure_discord_link_badge(product_id, player_doc)

        registry = bot.load_badge_registry()
        definitions = registry.get("badges", {})
        if not isinstance(definitions, dict):
            definitions = {}

        owned_doc = bot.load_player_badges(product_id)
        owned = owned_doc.get("badges", {})
        if not isinstance(owned, dict):
            owned = {}

        player_name = str(
            player_doc.get("current_name")
            or player_doc.get("name")
            or message.author.display_name
        )

        if not owned:
            await message.reply(
                f"🏆 **{player_name}** has not earned any badges yet.",
                mention_author=False,
            )
            return

        badge_rows: list[
            tuple[str, dict[str, Any], dict[str, Any]]
        ] = []

        for badge_name, award in sorted(
            owned.items(),
            key=lambda kv: (
                int(
                    definitions.get(kv[0], {}).get("id", 999999)
                    if isinstance(definitions.get(kv[0]), dict)
                    else 999999
                ),
                str(kv[0]).casefold(),
            ),
        ):
            definition = definitions.get(badge_name, {})
            if not isinstance(definition, dict):
                definition = {}
            if not isinstance(award, dict):
                award = {}
            badge_rows.append(
                (str(badge_name), definition, award)
            )

        badge_images = await asyncio.to_thread(
            bot.build_badge_strip_images,
            badge_rows,
        )

        embed = discord.Embed(
            title=f"🏆 {clip(player_name, 180)} — Badges",
            description=(
                f"**Badges Earned:** `{len(owned)}`"
            ),
            color=3618621,
        )
        embed.set_footer(text="JTWP Player Badges")

        if not badge_images:
            await message.reply(
                embed=embed,
                mention_author=False,
            )
            return

        embeds: list[discord.Embed] = []
        files: list[discord.File] = []

        for index, image in enumerate(badge_images[:10]):
            first_badge = index * bot.badges_per_image + 1
            last_badge = min(
                first_badge + bot.badges_per_image - 1,
                len(owned),
            )
            filename = f"{product_id}-badges-{index + 1}.png"
            files.append(discord.File(image, filename=filename))

            if index == 0:
                row_embed = embed
            else:
                row_embed = discord.Embed(
                    title=f"🏆 Badges {first_badge}–{last_badge}",
                    color=3618621,
                )
                row_embed.set_footer(text="JTWP Player Badges")

            row_embed.set_image(
                url=f"attachment://{filename}"
            )
            embeds.append(row_embed)

        await message.reply(
            embeds=embeds,
            files=files,
            mention_author=False,
        )

    @bot.event
    async def on_message(message: discord.Message):
        if message.author.bot:
            return

        # Only the exact word "badges" triggers it, case-insensitive.
        if str(message.content or "").strip().casefold() == "badges":
            now = time.monotonic()
            last = badge_text_cooldowns.get(message.author.id, 0.0)

            if (now - last) >= badge_text_cooldown_seconds:
                badge_text_cooldowns[message.author.id] = now
                await reply_with_member_badges(message)

        # Preserve any traditional prefix commands / command processing.
        await bot.process_commands(message)

    @bot.event
    async def on_ready():
        print(
            f"JTWP slash bot online as {bot.user}",
            flush=True,
        )

        if not bot._dashboard_ready_done:
            bot._dashboard_ready_done = True
            await bot.ensure_dashboard_message()

        if not bot._admin_dashboard_ready_done:
            bot._admin_dashboard_ready_done = True
            await bot.ensure_admin_dashboard_message()
        print(
            "Servers: "
            + ", ".join(bot.servers),
            flush=True,
        )

    await bot.start(token)


if __name__ == "__main__":
    asyncio.run(async_main())
