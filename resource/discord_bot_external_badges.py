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

BADGES_INDEX_PATH = PROJECT_ROOT / "resource" / "badges.json"


def load_badge_index(path: Path = BADGES_INDEX_PATH) -> dict[str, dict[str, Any]]:
    """Load badge definitions from resource/badges.json."""
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Badge index not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Invalid badge JSON in {path}: line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc

    if not isinstance(data, dict):
        raise RuntimeError(f"Badge index root must be an object: {path}")

    badges = data.get("badges")
    if not isinstance(badges, dict):
        raise RuntimeError(f"Badge index must contain a 'badges' object: {path}")

    loaded: dict[str, dict[str, Any]] = {}
    for badge_key, definition in badges.items():
        if not isinstance(badge_key, str) or not isinstance(definition, dict):
            raise RuntimeError(f"Invalid badge entry in {path}: {badge_key!r}")
        loaded[badge_key] = dict(definition)

    if not loaded:
        raise RuntimeError(f"Badge index is empty: {path}")

    return loaded


DEFAULT_BADGES: dict[str, dict[str, Any]] = load_badge_index()



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

        # Slash-command bot: message content is not required.
        intents.message_content = False

        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
        )

        self.cfg = cfg
        self.cfg_path = cfg_path
        self.bot_cfg = cfg.get("discord_bot", {})
        self.data_root = Path(cfg["data_path"])

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

    async def setup_hook(self) -> None:
        register_slash_commands(self)

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
        # Backfill badge #001 for players who linked Discord before badges
        # existed.
        bot.ensure_discord_link_badge(product_id, player_doc)

        registry = bot.load_badge_registry()
        definitions = registry.get("badges", {})
        if not isinstance(definitions, dict):
            definitions = {}

        owned_doc = bot.load_player_badges(product_id)
        owned = owned_doc.get("badges", {})
        if not isinstance(owned, dict):
            owned = {}

        player_name = (
            player_doc.get("current_name")
            or player_doc.get("name")
            or product_id
        )

        if not owned:
            embed = discord.Embed(
                title=f"🏆 Badges — {clip(player_name, 150)}",
                description="This player has not earned any badges yet.",
                color=3618621,
            )
            embed.set_footer(text=f"JTWP Badges • {product_id}")
            await respond(interaction, embed=embed, ephemeral=False)
            return

        embeds: list[discord.Embed] = []

        for badge_name, award in sorted(
            owned.items(),
            key=lambda kv: str(kv[0]).casefold(),
        ):
            definition = definitions.get(badge_name, {})
            if not isinstance(definition, dict):
                definition = {}
            if not isinstance(award, dict):
                award = {}

            display_name = str(
                definition.get("name")
                or badge_name
            )
            description = str(
                definition.get("description")
                or "JTWP achievement badge."
            )

            embed = discord.Embed(
                title=f"🏆 {clip(display_name, 240)}",
                description=clip(description, 3900),
                color=3618621,
            )
            embed.add_field(
                name="Player",
                value=(
                    f"**{clip(player_name, 200)}**\n"
                    f"`{product_id}`"
                ),
                inline=False,
            )
            embed.add_field(
                name="Awarded",
                value=f"`{award.get('awarded_at') or 'Unknown'}`",
                inline=True,
            )

            url = str(definition.get("url") or "").strip()
            if url:
                # Use thumbnail so the badge stays compact instead of being
                # expanded into a large full-width embed image.
                embed.set_thumbnail(url=url)

            embed.set_footer(
                text=f"JTWP Badges • {badge_name}"
            )
            embeds.append(embed)

        # Discord permits up to 10 embeds per message.
        for offset in range(0, len(embeds), 10):
            chunk = embeds[offset:offset + 10]

            if offset == 0:
                content = (
                    f"🏆 **{clip(player_name, 150)}** has "
                    f"`{len(embeds)}` badge(s)."
                )
                if interaction.response.is_done():
                    await interaction.followup.send(
                        content=content,
                        embeds=chunk,
                        ephemeral=False,
                    )
                else:
                    await interaction.response.send_message(
                        content=content,
                        embeds=chunk,
                        ephemeral=False,
                    )
            else:
                await interaction.followup.send(
                    embeds=chunk,
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

    @bot.event
    async def on_ready():
        print(
            f"JTWP slash bot online as {bot.user}",
            flush=True,
        )
        print(
            "Servers: "
            + ", ".join(bot.servers),
            flush=True,
        )

    await bot.start(token)


if __name__ == "__main__":
    asyncio.run(async_main())
