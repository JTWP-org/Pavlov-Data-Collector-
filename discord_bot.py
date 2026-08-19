#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import subprocess
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import discord
from discord.ext import commands
from pavlov import PavlovRCON

from active_config import ActiveConfig


def now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")



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


def load_json(
    path: Path,
    default: Any,
) -> Any:
    try:
        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return default


def append_jsonl(
    path: Path,
    data: dict,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "a",
        encoding="utf-8",
    ) as f:
        f.write(
            json.dumps(
                data,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n"
        )


ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def strip_ansi(value: str | None) -> str:
    """Remove terminal ANSI color/formatting escape sequences."""
    return ANSI_ESCAPE_RE.sub("", value or "")


class JTWPBot(commands.Bot):
    def __init__(
        self,
        cfg: dict,
        active_path: Path,
    ):
        intents = (
            discord.Intents.default()
        )

        intents.message_content = True
        intents.members = True
        intents.guilds = True

        bot_cfg = cfg.get(
            "discord_bot",
            {},
        )

        super().__init__(
            command_prefix=bot_cfg.get(
                "prefix",
                "!",
            ),
            intents=intents,
            help_command=None,
            case_insensitive=True,
        )

        self.cfg = cfg
        self.bot_cfg = bot_cfg
        self.active = ActiveConfig(
            active_path
        )

        self.data_root = Path(
            cfg["data_path"]
        )

        self.audit_path = (
            self.data_root
            / "global"
            / "discord"
            / "commands.jsonl"
        )

        self.control_channel_id = int(
            bot_cfg.get(
                "control_channel_id"
            )
            or 0
        )

        role_cfg = bot_cfg.get(
            "roles",
            {},
        )

        self.admin_role_id = int(
            role_cfg.get("admin")
            or 0
        )

        self.owner_role_id = int(
            role_cfg.get("owner")
            or 0
        )

        self.admin_rcon = {
            str(value).casefold()
            for value
            in bot_cfg.get(
                "admin_allowed_rcon_commands",
                [],
            )
        }

        self.output_limit = int(
            bot_cfg.get(
                "command_output_limit",
                3500,
            )
        )

        self.servers = {}

        for raw in cfg.get(
            "servers",
            [],
        ):
            log_path = Path(
                raw["log_path"]
            )

            server_id = (
                log_path.parents[2].name
            )

            self.servers[
                server_id
            ] = {
                "server_id": (
                    server_id
                ),
                "server_root": (
                    log_path.parents[2]
                ),
                "rcon": raw.get(
                    "rcon",
                    {},
                ),
            }

    def permission_level(
        self,
        member,
    ) -> str:
        role_ids = {
            role.id
            for role
            in getattr(
                member,
                "roles",
                [],
            )
        }

        if (
            self.owner_role_id
            and self.owner_role_id
            in role_ids
        ):
            return "OWNER"

        if (
            self.admin_role_id
            and self.admin_role_id
            in role_ids
        ):
            return "ADMIN"

        return "NONE"

    def feature(
        self,
        *keys: str,
    ) -> bool:
        self.active.reload()

        return self.active.enabled(
            "discord_bot",
            *keys,
        )

    async def guard(
        self,
        ctx,
        owner_only: bool = False,
    ) -> bool:
        if (
            self.control_channel_id
            and ctx.channel.id
            != self.control_channel_id
        ):
            return False

        level = self.permission_level(
            ctx.author
        )

        if (
            level == "NONE"
            or (
                owner_only
                and level != "OWNER"
            )
        ):
            await ctx.send(
                "⛔ You do not have permission "
                "to use this command."
            )

            return False

        return True

    def audit(
        self,
        ctx,
        command_type: str,
        success: bool,
        **extra,
    ) -> None:
        append_jsonl(
            self.audit_path,
            {
                "timestamp": now_iso(),
                "discord_user_id": str(
                    ctx.author.id
                ),
                "discord_username": str(
                    ctx.author
                ),
                "permission": (
                    self.permission_level(
                        ctx.author
                    )
                ),
                "type": command_type,
                "success": success,
                **extra,
            },
        )

    async def send_json(
        self,
        ctx,
        title: str,
        value: Any,
        filename: str,
    ) -> None:
        raw = json.dumps(
            value,
            indent=2,
            ensure_ascii=False,
        )

        if len(raw) <= self.output_limit:
            await ctx.send(
                embed=discord.Embed(
                    title=title,
                    description=(
                        "```json\n"
                        + raw
                        + "\n```"
                    ),
                )
            )
            return

        await ctx.send(
            title,
            file=discord.File(
                io.BytesIO(
                    raw.encode("utf-8")
                ),
                filename=filename,
            ),
        )

    def resolve_product_id(
        self,
        player_name: str,
    ) -> str | None:
        index = load_json(
            self.data_root
            / "players"
            / "index"
            / "by_name.json",
            {},
        )

        value = index.get(
            player_name.casefold()
        )

        if isinstance(value, list):
            return (
                str(value[0])
                if value
                else None
            )

        return (
            str(value)
            if value
            else None
        )

    async def rcon_send(
        self,
        server_id: str,
        command: str,
    ):
        if server_id not in self.servers:
            raise ValueError(
                f"Unknown server: {server_id}"
            )

        rcon = self.servers[
            server_id
        ]["rcon"]

        if not rcon.get(
            "enabled",
            False,
        ):
            raise ValueError(
                "RCON is disabled "
                "for that server"
            )

        password = os.getenv(
            rcon["password_env"],
            "",
        ).strip()

        if not password:
            raise RuntimeError(
                "Missing environment variable: "
                + rcon["password_env"]
            )

        client = PavlovRCON(
            rcon.get(
                "host",
                "127.0.0.1",
            ),
            int(rcon["port"]),
            password,
        )

        return await asyncio.wait_for(
            client.send(command),
            timeout=float(
                self.bot_cfg.get(
                    "rcon_timeout_seconds",
                    15,
                )
            ),
        )


def register_commands(
    bot: JTWPBot,
) -> None:

    @bot.command(name="exportdata")
    async def export_data(ctx):
        if not await bot.guard(
            ctx,
            owner_only=True,
        ):
           return

        await ctx.send(
            "📦 JTWP data export started..."
        )

        result = await asyncio.to_thread(
            subprocess.run,
            [
                "/home/steam/jtwp-collector/venv/bin/python3",
                "-u",
                "/home/steam/jtwp-collector/"
                "Pavlov-Data-Collector-/"
                "scripts/export-data.py",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=1800,
            check=False,
        )

        output = strip_ansi(
            result.stdout
            or "(no output)"
        )[-bot.output_limit:]

        bot.audit(
            ctx,
            "exportdata",
            result.returncode == 0,
            returncode=result.returncode,
        )

        await ctx.send(
            embed=discord.Embed(
                title=(
                    "✅ Export Complete"
                    if result.returncode == 0
                    else "❌ Export Failed"
                ),
                description=(
                    "```text\n"
                    + output
                   + "\n```"
                ),
            )
        )


    @bot.command(name="backupdata")
    async def backup_data(ctx):
        if not await bot.guard(
            ctx,
            owner_only=True,
        ):
            return

        await ctx.send(
            "📦 JTWP backup started..."
        )

        result = await asyncio.to_thread(
            subprocess.run,
            [
                "/home/steam/jtwp-collector/venv/bin/python3",
                "-u",
                "/home/steam/jtwp-collector/"
                "Pavlov-Data-Collector-/"
                "scripts/backup-data.py",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=1800,
            check=False,
        )

        output = strip_ansi(
            result.stdout
            or "(no output)"
        )[-bot.output_limit:]

        bot.audit(
            ctx,
            "backupdata",
            result.returncode == 0,
            returncode=result.returncode,
        )

        await ctx.send(
            embed=discord.Embed(
                title=(
                    "✅ Backup Complete"
                    if result.returncode == 0
                    else "❌ Backup Failed"
                ),
                description=(
                    "```text\n"
                    + output
                    + "\n```"
                ),
            )
        )


    @bot.command(name="cleardata")
    async def clear_data(
        ctx,
        confirmation: str = None,
    ):
        if not await bot.guard(
            ctx,
            owner_only=True,
        ):
            return

        if confirmation != "YES":
            await ctx.send(
                embed=discord.Embed(
                    title=(
                        "⚠️ ARE YOU SURE YOU WANT TO "
                        "REMOVE ALL THE DATA?"
                    ),
                    description=(
                        "This will permanently clear the "
                        "JTWP collector data.\n\n"
                        "To confirm, type:\n"
                        "```text\n"
                        "!cleardata YES\n"
                        "```"
                    ),
                )
            )
            return

        await ctx.send(
            "🧹 Clearing JTWP collector data..."
        )

        result = await asyncio.to_thread(
            subprocess.run,
            [
                "sudo",
                "-n",
                "/home/steam/jtwp-collector/"
                "Pavlov-Data-Collector-/"
                "scripts/clear-data.sh",
                "--yes",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=300,
            check=False,
        )

        output = strip_ansi(
            result.stdout
            or "(no output)"
        )[-bot.output_limit:]

        bot.audit(
            ctx,
            "cleardata",
            result.returncode == 0,
            returncode=result.returncode,
        )

        await ctx.send(
            embed=discord.Embed(
                title=(
                    "✅ Clear Data Complete"
                    if result.returncode == 0
                    else "❌ Clear Data Failed"
                ),
                description=(
                    "```text\n"
                    + output
                    + "\n```"
                ),
            )
        )

    @bot.command(name="restartjtwp")
    async def restart_jtwp(ctx):
        if not await bot.guard(
            ctx,
            owner_only=True,
        ):
            return

        await ctx.send(
            "🔄 Restarting JTWP services..."
        )

        process = await asyncio.create_subprocess_exec(
            "sudo",
            "-n",
            "/usr/local/bin/restart-jtwp",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

        bot.audit(
            ctx,
            "restartjtwp",
            True,
            pid=process.pid,
        )


    @bot.event
    async def on_ready():
        print(
            f"JTWP Discord bot online as "
            f"{bot.user}",
            flush=True,
        )

    @bot.command(
        name="rcon"
    )
    async def rcon_command(
        ctx,
        server_id: str = None,
        *,
        command: str = None,
    ):
        if not await bot.guard(ctx):
            return

        if not bot.feature("rcon"):
            return

        if (
            not server_id
            or not command
        ):
            await ctx.send(
                "Usage: "
                "`!rcon <server_id> <command>`"
            )
            return

        level = (
            bot.permission_level(
                ctx.author
            )
        )

        command_key = (
            command.split()[0]
            .casefold()
        )

        if (
            level == "ADMIN"
            and command_key
            not in bot.admin_rcon
        ):
            await ctx.send(
                "⛔ ADMIN cannot use "
                f"RCON command "
                f"`{command_key}`."
            )
            return

        try:
            response = await bot.rcon_send(
                server_id,
                command,
            )

            bot.audit(
                ctx,
                "rcon",
                True,
                server_id=server_id,
                command=command,
            )

            await bot.send_json(
                ctx,
                f"🎛️ RCON — {server_id}",
                response,
                "rcon-response.json",
            )

        except Exception as e:
            bot.audit(
                ctx,
                "rcon",
                False,
                server_id=server_id,
                command=command,
                error=str(e),
            )

            await ctx.send(
                f"❌ `{type(e).__name__}: "
                f"{e}`"
            )

    @bot.command(
        name="systemCtl"
    )
    async def systemctl_command(
        ctx,
        server_id: str = None,
        action: str = None,
    ):
        if not await bot.guard(
            ctx,
            owner_only=True,
        ):
            return

        if not bot.feature(
            "systemctl"
        ):
            return

        if (
            not server_id
            or not action
        ):
            await ctx.send(
                "Usage: "
                "`!systemCtl <server_id> "
                "<status|start|stop|restart|"
                "enable|disable>`"
            )
            return

        if server_id not in bot.servers:
            await ctx.send(
                "❌ Unknown server ID."
            )
            return

        action = action.casefold()

        allowed = {
            str(x).casefold()
            for x
            in bot.bot_cfg.get(
                "systemctl_actions",
                [],
            )
        }

        if action not in allowed:
            await ctx.send(
                "❌ Unsupported "
                "systemctl action."
            )
            return

        service_data = load_json(
            bot.data_root
            / "servers"
            / server_id
            / "server"
            / "service.json",
            {},
        )

        service = (
            service_data.get("service")
            or f"{server_id}.service"
        )

        command = [
            "sudo",
            "systemctl",
            action,
            service,
        ]

        if action == "status":
            command.append(
                "--no-pager"
            )

        result = await asyncio.to_thread(
            subprocess.run,
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=60,
            check=False,
        )

        bot.audit(
            ctx,
            "systemctl",
            result.returncode == 0,
            server_id=server_id,
            service=service,
            action=action,
            returncode=result.returncode,
        )

        output = strip_ansi(
            result.stdout
            or "(no output)"
        )[-bot.output_limit:]

        await ctx.send(
            embed=discord.Embed(
                title=(
                    f"⚙️ {service} — "
                    f"{action}"
                ),
                description=(
                    "```\n"
                    + output
                    + "\n```"
                ),
            )
        )

    @bot.command(
        name="getProductID"
    )
    async def get_product_id(
        ctx,
        *,
        player_name: str = None,
    ):
        if not await bot.guard(ctx):
            return

        if not player_name:
            await ctx.send(
                "Usage: "
                "`!getProductID <playername>`"
            )
            return

        product_id = (
            bot.resolve_product_id(
                player_name
            )
        )

        bot.audit(
            ctx,
            "get_product_id",
            bool(product_id),
            query=player_name,
            product_id=product_id,
        )

        if product_id:
            await ctx.send(
                f"🆔 **{player_name}** → "
                f"`{product_id}`"
            )
        else:
            await ctx.send(
                "❌ Player name not found."
            )

    async def send_player_file(
        ctx,
        product_id: str,
        filename: str,
        title: str,
    ):
        if not await bot.guard(ctx):
            return

        path = (
            bot.data_root
            / "players"
            / "records"
            / product_id
            / filename
        )

        if not path.exists():
            await ctx.send(
                f"❌ `{filename}` not found "
                f"for `{product_id}`."
            )
            return

        data = load_json(
            path,
            {},
        )

        bot.audit(
            ctx,
            "player_file_lookup",
            True,
            product_id=product_id,
            filename=filename,
        )

        await bot.send_json(
            ctx,
            title,
            data,
            filename,
        )

    @bot.command(name="getNETWORK")
    async def get_network(
        ctx,
        product_id: str = None,
    ):
        if product_id:
            await send_player_file(
                ctx,
                product_id,
                "ips.json",
                "🌐 Player Network",
            )

    @bot.command(name="getNAMES")
    async def get_names(
        ctx,
        product_id: str = None,
    ):
        if product_id:
            await send_player_file(
                ctx,
                product_id,
                "names.json",
                "📝 Player Names",
            )

    @bot.command(name="getSTATS")
    async def get_stats(
        ctx,
        product_id: str = None,
    ):
        if product_id:
            await send_player_file(
                ctx,
                product_id,
                "stats.json",
                "📊 Player Stats",
            )

    @bot.command(name="getGUNS")
    async def get_guns(
        ctx,
        product_id: str = None,
    ):
        if product_id:
            await send_player_file(
                ctx,
                product_id,
                "weapons.json",
                "🔫 Player Weapons",
            )

    @bot.command(name="getPLAYER")
    async def get_player(
        ctx,
        product_id: str = None,
    ):
        if product_id:
            await send_player_file(
                ctx,
                product_id,
                "player.json",
                "👤 Player Record",
            )

    @bot.command(name="getDUMP")
    async def get_dump(
        ctx,
        product_id: str = None,
    ):
        if not await bot.guard(ctx):
            return

        if not product_id:
            await ctx.send(
                "Usage: "
                "`!getDUMP <ProductID>`"
            )
            return

        directory = (
            bot.data_root
            / "players"
            / "records"
            / product_id
        )

        if not directory.is_dir():
            await ctx.send(
                "❌ Player record not found."
            )
            return

        dump = {
            path.stem: load_json(
                path,
                {},
            )
            for path
            in sorted(
                directory.glob("*.json")
            )
        }

        bot.audit(
            ctx,
            "get_dump",
            True,
            product_id=product_id,
        )

        await bot.send_json(
            ctx,
            "📦 Player JSON Dump",
            dump,
            f"{product_id}-dump.json",
        )

    @bot.command(name="checkCONS")
    async def check_connections(
        ctx,
        *,
        player_name: str = None,
    ):
        if not await bot.guard(ctx):
            return

        if not player_name:
            await ctx.send(
                "Usage: "
                "`!checkCONS <playername>`"
            )
            return

        product_id = (
            bot.resolve_product_id(
                player_name
            )
        )

        if not product_id:
            await ctx.send(
                "❌ Player not found."
            )
            return

        player_dir = (
            bot.data_root
            / "players"
            / "records"
            / product_id
        )

        ips = load_json(
            player_dir / "ips.json",
            {},
        )

        hashes = set()

        def collect_hashes(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if (
                        key in (
                            "ip_hash",
                            "hash",
                        )
                        and isinstance(
                            child,
                            str,
                        )
                    ):
                        hashes.add(child)

                    collect_hashes(child)

            elif isinstance(value, list):
                for child in value:
                    collect_hashes(child)

        collect_hashes(ips)

        by_ip_hash = load_json(
            bot.data_root
            / "players"
            / "index"
            / "by_ip_hash.json",
            {},
        )

        other_players = []
        rcon_matches = []
        ssh_matches = []
        ddos_matches = []

        for ip_hash in hashes:
            for other in by_ip_hash.get(
                ip_hash,
                [],
            ):
                if str(other) != product_id:
                    other_players.append(
                        {
                            "ip_hash": ip_hash,
                            "product_id": str(
                                other
                            ),
                        }
                    )

            servers_root = (
                bot.data_root
                / "servers"
            )

            if servers_root.exists():
                for server_dir in (
                    servers_root.iterdir()
                ):
                    if not server_dir.is_dir():
                        continue

                    for filename, kind in (
                        (
                            "known_hosts.json",
                            "known",
                        ),
                        (
                            "failed_hosts.json",
                            "failed",
                        ),
                    ):
                        host = load_json(
                            server_dir
                            / "rcon"
                            / filename,
                            {},
                        ).get(ip_hash)

                        if host:
                            rcon_matches.append(
                                {
                                    "ip_hash": (
                                        ip_hash
                                    ),
                                    "server_id": (
                                        server_dir.name
                                    ),
                                    "kind": kind,
                                    "record": host,
                                }
                            )

            ssh_host = load_json(
                bot.data_root
                / "global"
                / "ssh"
                / "failed_hosts.json",
                {},
            ).get(ip_hash)

            if ssh_host:
                ssh_matches.append(
                    {
                        "ip_hash": ip_hash,
                        "record": ssh_host,
                    }
                )

            ddos_host = load_json(
                bot.data_root
                / "global"
                / "network"
                / "ddos"
                / "hosts.json",
                {},
            ).get(ip_hash)

            if ddos_host:
                ddos_matches.append(
                    {
                        "ip_hash": ip_hash,
                        "record": ddos_host,
                    }
                )

        report = {
            "player_name": player_name,
            "product_id": product_id,
            "known_ip_hashes": sorted(
                hashes
            ),
            "rcon_matches": rcon_matches,
            "ssh_matches": ssh_matches,
            "ddos_matches": ddos_matches,
            "other_players_on_same_hash": (
                other_players
            ),
            "warning": (
                "Shared IP correlation does not "
                "prove the player performed the "
                "SSH/RCON/network activity."
            ),
        }

        bot.audit(
            ctx,
            "check_cons",
            True,
            query=player_name,
            product_id=product_id,
        )

        await bot.send_json(
            ctx,
            (
                "🔎 JTWP Player / SSH / "
                "RCON IP Correlation"
            ),
            report,
            (
                f"{product_id}-"
                f"correlation.json"
            ),
        )

    @bot.group(
        name="server",
        invoke_without_command=True,
    )
    async def server_group(ctx):
        if await bot.guard(ctx):
            await ctx.send(
                "Usage: "
                "`!server clear-pavlov-mods "
                "<server_id>`"
            )

    @server_group.command(
        name="clear-pavlov-mods"
    )
    async def clear_pavlov_mods(
        ctx,
        server_id: str = None,
    ):
        if not await bot.guard(
            ctx,
            owner_only=True,
        ):
            return

        if not server_id:
            await ctx.send(
                "Usage: "
                "`!server clear-pavlov-mods "
                "<server_id>`"
            )
            return

        result = await asyncio.to_thread(
            subprocess.run,
            [
                "sudo",
                "-n",
                "/usr/local/bin/clear-pavlov-mods",
                server_id,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=180,
            check=False,
        )

        bot.audit(
            ctx,
            "clear_pavlov_mods",
            result.returncode == 0,
            server_id=server_id,
            returncode=result.returncode,
        )

        output = strip_ansi(
            result.stdout
            or "(no output)"
        )[-bot.output_limit:]

        await ctx.send(
            embed=discord.Embed(
                title="🧹 Clear Pavlov Mods",
                description=(
                    "```\n"
                    + output
                    + "\n```"
                ),
            )
        )

    @bot.command(name="clearpavlovmods")
    async def clear_pavlov_mods_alias(
        ctx,
        server_id: str = None,
    ):
        """Top-level alias for !server clear-pavlov-mods."""
        await clear_pavlov_mods(
            ctx,
            server_id,
        )

    async def run_owner_process(
        ctx,
        name: str,
        command: list[str],
        timeout: int = 600,
    ):
        if not await bot.guard(
            ctx,
            owner_only=True,
        ):
            return

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
            ctx,
            name,
            result.returncode == 0,
            returncode=result.returncode,
        )

        output = strip_ansi(
            result.stdout
            or "(no output)"
        )[-bot.output_limit:]

        await ctx.send(
            embed=discord.Embed(
                title=f"👑 {name}",
                description=(
                    "```\n"
                    + output
                    + "\n```"
                ),
            )
        )

    @bot.command(name="RUNcollector")
    async def run_collector(ctx):

        if not await bot.guard(
            ctx,
            owner_only=True,
        ):
            return

        await ctx.send(
            "🚀 JTWP collector started."
        )

        process = await asyncio.create_subprocess_exec(
            "sudo",
            "-n",
            "/home/steam/jtwp-collector/"
            "Pavlov-Data-Collector-/"
            "scripts/run-collector.sh",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

        bot.audit(
            ctx,
            "RUNcollector",
            True,
            pid=process.pid,
        )

    @bot.command(name="RUNpavlovApi")
    async def run_pavlov_api(ctx):
        await run_owner_process(
            ctx,
            "RUNpavlovApi",
            [
                "/home/steam/jtwp-collector/"
                "venv/bin/python3",
                "/home/steam/jtwp-collector/"
                "Pavlov-Data-Collector-/"
                "update_pavlov_api.py",
                "-c",
                "/home/steam/jtwp-collector/"
                "Pavlov-Data-Collector-/"
                "config.json",
            ],
        )

    @bot.command(name="RUNssh")
    async def run_ssh_report(ctx):
        """
        Build a combined Player + SSH + RCON connection correlation report.

        Correlation is performed using the stable HMAC-SHA256 IP hash.
        A shared hash indicates association only; it does not prove that a
        player performed SSH or RCON activity.
        """
        if not await bot.guard(
            ctx,
            owner_only=True,
        ):
            return

        await ctx.send(
            "🔎 Building combined Player / SSH / RCON connection report..."
        )

        player_root = (
            bot.data_root
            / "players"
            / "records"
        )

        ssh_path = (
            bot.data_root
            / "global"
            / "ssh"
            / "failed_hosts.json"
        )

        servers_root = (
            bot.data_root
            / "servers"
        )

        players_by_hash: dict[str, list[dict[str, Any]]] = {}
        ssh_hosts: dict[str, Any] = {}
        rcon_by_hash: dict[str, list[dict[str, Any]]] = {}

        player_records_with_hash = 0
        total_player_hash_links = 0
        rcon_record_count = 0

        if player_root.exists():
            for player_dir in sorted(player_root.iterdir()):
                if not player_dir.is_dir():
                    continue

                player = load_json(
                    player_dir / "player.json",
                    {},
                )

                ips = load_json(
                    player_dir / "ips.json",
                    {},
                )

                product_id = str(
                    player.get("product_id")
                    or player_dir.name
                )

                player_name = str(
                    player.get("current_name")
                    or "Unknown"
                )

                hashes: set[str] = set()

                if isinstance(ips, dict):
                    current_hash = ips.get(
                        "current_ip_hash"
                    )

                    if (
                        isinstance(current_hash, str)
                        and current_hash
                    ):
                        hashes.add(current_hash)

                    known_ips = (
                        ips.get("ips")
                        or {}
                    )

                    if isinstance(known_ips, dict):
                        for ip_hash in known_ips.keys():
                            if (
                                isinstance(ip_hash, str)
                                and ip_hash
                            ):
                                hashes.add(ip_hash)

                network = (
                    player.get("network")
                    or {}
                )

                if isinstance(network, dict):
                    current_hash = network.get(
                        "current_ip_hash"
                    )

                    if (
                        isinstance(current_hash, str)
                        and current_hash
                    ):
                        hashes.add(current_hash)

                if hashes:
                    player_records_with_hash += 1

                for ip_hash in hashes:
                    players_by_hash.setdefault(
                        ip_hash,
                        [],
                    ).append(
                        {
                            "product_id": product_id,
                            "name": player_name,
                            "admin": bool(
                                player.get(
                                    "admin",
                                    False,
                                )
                            ),
                            "banned": bool(
                                player.get(
                                    "banned",
                                    False,
                                )
                            ),
                        }
                    )
                    total_player_hash_links += 1

        raw_ssh = load_json(
            ssh_path,
            {},
        )

        if isinstance(raw_ssh, dict):
            ssh_hosts = raw_ssh

        if servers_root.exists():
            for server_dir in sorted(servers_root.iterdir()):
                if not server_dir.is_dir():
                    continue

                rcon_dir = (
                    server_dir
                    / "rcon"
                )

                for filename, kind in (
                    (
                        "known_hosts.json",
                        "known",
                    ),
                    (
                        "failed_hosts.json",
                        "failed",
                    ),
                ):
                    data = load_json(
                        rcon_dir / filename,
                        {},
                    )

                    if not isinstance(data, dict):
                        continue

                    for ip_hash, record in data.items():
                        if not isinstance(ip_hash, str):
                            continue

                        rcon_by_hash.setdefault(
                            ip_hash,
                            [],
                        ).append(
                            {
                                "server_id": server_dir.name,
                                "kind": kind,
                                "record": (
                                    record
                                    if isinstance(record, dict)
                                    else {
                                        "value": record
                                    }
                                ),
                            }
                        )

                        rcon_record_count += 1

        all_hashes = (
            set(players_by_hash)
            | set(ssh_hosts)
            | set(rcon_by_hash)
        )

        shared: list[dict[str, Any]] = []

        player_ssh = 0
        player_rcon = 0
        ssh_rcon = 0
        all_three = 0

        for ip_hash in all_hashes:
            has_player = (
                ip_hash in players_by_hash
            )

            has_ssh = (
                ip_hash in ssh_hosts
            )

            has_rcon = (
                ip_hash in rcon_by_hash
            )

            systems = (
                int(has_player)
                + int(has_ssh)
                + int(has_rcon)
            )

            if systems < 2:
                continue

            if has_player and has_ssh:
                player_ssh += 1

            if has_player and has_rcon:
                player_rcon += 1

            if has_ssh and has_rcon:
                ssh_rcon += 1

            if has_player and has_ssh and has_rcon:
                all_three += 1

            ssh_record = (
                ssh_hosts.get(ip_hash)
                if has_ssh
                else None
            )

            ssh_attempts = 0
            ssh_blocked = False

            if isinstance(ssh_record, dict):
                try:
                    ssh_attempts = int(
                        ssh_record.get(
                            "failed_attempts",
                            0,
                        )
                        or 0
                    )
                except (TypeError, ValueError):
                    ssh_attempts = 0

                ssh_blocked = bool(
                    ssh_record.get(
                        "blocked",
                        False,
                    )
                )

            shared.append(
                {
                    "ip_hash": ip_hash,
                    "players": players_by_hash.get(
                        ip_hash,
                        [],
                    ),
                    "ssh": ssh_record,
                    "rcon": rcon_by_hash.get(
                        ip_hash,
                        [],
                    ),
                    "has_player": has_player,
                    "has_ssh": has_ssh,
                    "has_rcon": has_rcon,
                    "systems": systems,
                    "ssh_attempts": ssh_attempts,
                    "ssh_blocked": ssh_blocked,
                }
            )

        shared.sort(
            key=lambda item: (
                item["systems"],
                item["ssh_attempts"],
                len(item["players"]),
                len(item["rcon"]),
            ),
            reverse=True,
        )

        report_path = (
            bot.data_root
            / "global"
            / "ssh"
            / "connection_correlations.json"
        )

        report_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        report = {
            "generated_at": now_iso(),
            "summary": {
                "player_records_with_hash": (
                    player_records_with_hash
                ),
                "player_hash_links": (
                    total_player_hash_links
                ),
                "unique_player_hashes": (
                    len(players_by_hash)
                ),
                "ssh_hashes": len(ssh_hosts),
                "rcon_hashes": len(rcon_by_hash),
                "rcon_records": rcon_record_count,
                "shared_hashes": len(shared),
                "player_ssh": player_ssh,
                "player_rcon": player_rcon,
                "ssh_rcon": ssh_rcon,
                "all_three": all_three,
            },
            "correlations": shared,
            "warning": (
                "Shared IP-hash correlation indicates association only. "
                "It does not prove a player performed SSH or RCON activity."
            ),
        }

        report_path.write_text(
            json.dumps(
                report,
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        summary = discord.Embed(
            title=(
                "🔌 JTWP Combined Connection Report"
            ),
            description=(
                "Player, SSH, and RCON records correlated using "
                "the stable full IP hash."
            ),
            color=0xF39C12,
            timestamp=datetime.now(
                timezone.utc
            ),
        )

        summary.add_field(
            name="📊 Data Sources",
            value=(
                f"Players With Hashes: "
                f"**{player_records_with_hash:,}**\n"
                f"Unique Player Hashes: "
                f"**{len(players_by_hash):,}**\n"
                f"SSH Hashes: "
                f"**{len(ssh_hosts):,}**\n"
                f"RCON Hashes: "
                f"**{len(rcon_by_hash):,}**"
            ),
            inline=True,
        )

        summary.add_field(
            name="🔗 Correlations",
            value=(
                f"Shared Hashes: "
                f"**{len(shared):,}**\n"
                f"Player ↔ SSH: "
                f"**{player_ssh:,}**\n"
                f"Player ↔ RCON: "
                f"**{player_rcon:,}**\n"
                f"SSH ↔ RCON: "
                f"**{ssh_rcon:,}**\n"
                f"All Three: "
                f"**{all_three:,}**"
            ),
            inline=True,
        )

        summary.add_field(
            name="💾 Stored Report",
            value=(
                "`global/ssh/"
                "connection_correlations.json`"
            ),
            inline=False,
        )

        summary.set_footer(
            text=(
                "JTWP • Shared hashes are correlation evidence only, "
                "not proof of activity."
            )
        )

        await ctx.send(
            embed=summary
        )

        max_detail_embeds = int(
            bot.bot_cfg.get(
                "runssh_max_detail_embeds",
                10,
            )
        )

        for index, item in enumerate(
            shared[:max_detail_embeds],
            start=1,
        ):
            ip_hash = item["ip_hash"]

            systems = []

            if item["has_player"]:
                systems.append("👤 Player")

            if item["has_ssh"]:
                systems.append("🔐 SSH")

            if item["has_rcon"]:
                systems.append("🎛️ RCON")

            detail = discord.Embed(
                title=(
                    f"🔗 Correlation #{index}"
                ),
                description=(
                    "**Full IP Hash**\n"
                    f"```text\n{ip_hash}\n```\n"
                    f"Matched Systems: "
                    f"**{' + '.join(systems)}**"
                ),
                color=(
                    0xE74C3C
                    if item["ssh_blocked"]
                    else 0xF39C12
                ),
                timestamp=datetime.now(
                    timezone.utc
                ),
            )

            players = item["players"]

            if players:
                player_lines = []

                for player in players[:10]:
                    player_lines.append(
                        f"**{player['name']}**\n"
                        f"Product ID: "
                        f"`{player['product_id']}`\n"
                        f"Admin: "
                        f"`{player['admin']}` • "
                        f"Banned: "
                        f"`{player['banned']}`"
                    )

                if len(players) > 10:
                    player_lines.append(
                        f"…and **{len(players) - 10}** more."
                    )

                detail.add_field(
                    name="👤 Player Records",
                    value="\n\n".join(
                        player_lines
                    )[:1024],
                    inline=False,
                )

            ssh = item["ssh"]

            if isinstance(ssh, dict):
                usernames = (
                    ssh.get("usernames")
                    or {}
                )

                top_users = []

                if isinstance(usernames, dict):
                    sorted_users = sorted(
                        usernames.items(),
                        key=lambda kv: int(
                            kv[1]
                            or 0
                        ),
                        reverse=True,
                    )

                    for username, count in sorted_users[:8]:
                        top_users.append(
                            f"`{username}`: **{count}**"
                        )

                ssh_value = (
                    f"Failed Attempts: "
                    f"**{item['ssh_attempts']:,}**\n"
                    f"Blocked: "
                    f"**{bool(ssh.get('blocked', False))}**\n"
                    f"First Seen: "
                    f"`{ssh.get('first_seen') or 'Unknown'}`\n"
                    f"Last Seen: "
                    f"`{ssh.get('last_seen') or 'Unknown'}`"
                )

                if top_users:
                    ssh_value += (
                        "\n\n**Top Usernames**\n"
                        + "\n".join(top_users)
                    )

                detail.add_field(
                    name="🔐 SSH",
                    value=ssh_value[:1024],
                    inline=False,
                )

            rcon_entries = item["rcon"]

            if rcon_entries:
                rcon_lines = []

                for entry in rcon_entries[:10]:
                    record = (
                        entry.get("record")
                        or {}
                    )

                    if not isinstance(record, dict):
                        record = {}

                    count = (
                        record.get(
                            "failed_attempts"
                        )
                        or record.get(
                            "attempts"
                        )
                        or record.get(
                            "connections"
                        )
                        or record.get(
                            "count"
                        )
                        or "Unknown"
                    )

                    rcon_lines.append(
                        f"**{entry['server_id']}** "
                        f"• `{entry['kind']}`\n"
                        f"Attempts / Connections: "
                        f"`{count}`"
                    )

                if len(rcon_entries) > 10:
                    rcon_lines.append(
                        f"…and **{len(rcon_entries) - 10}** more."
                    )

                detail.add_field(
                    name="🎛️ RCON",
                    value="\n\n".join(
                        rcon_lines
                    )[:1024],
                    inline=False,
                )

            detail.set_footer(
                text=(
                    "JTWP • A shared IP hash does not prove the player "
                    "performed SSH/RCON activity."
                )
            )

            await ctx.send(
                embed=detail
            )

        if len(shared) > max_detail_embeds:
            await ctx.send(
                f"ℹ️ **{len(shared) - max_detail_embeds:,}** additional "
                "correlations were saved to "
                "`global/ssh/connection_correlations.json`."
            )

        if not shared:
            await ctx.send(
                "✅ No IP hashes were shared between two or more of "
                "Player, SSH, and RCON data."
            )

        bot.audit(
            ctx,
            "RUNssh",
            True,
            player_hashes=len(
                players_by_hash
            ),
            ssh_hashes=len(
                ssh_hosts
            ),
            rcon_hashes=len(
                rcon_by_hash
            ),
            shared_hashes=len(
                shared
            ),
            player_ssh=player_ssh,
            player_rcon=player_rcon,
            ssh_rcon=ssh_rcon,
            all_three=all_three,
        )

    @bot.group(
        name="loop",
        invoke_without_command=True,
    )
    async def loop_group(ctx):
        if await bot.guard(ctx):
            await ctx.send(
                "`!loop start <server> <seconds>` "
                "| `!loop stop` | `!loop status`"
            )

    @loop_group.command(name="start")
    async def loop_start(
        ctx,
        server_id: str = None,
        seconds: int = None,
    ):
        if not await bot.guard(
            ctx,
            owner_only=True,
        ):
            return

        if (
            not server_id
            or seconds is None
        ):
            await ctx.send(
                "Usage: "
                "`!loop start "
                "<server> <seconds>`"
            )
            return

        result = await asyncio.to_thread(
            subprocess.run,
            [
                "/home/steam/jtwp-collector/"
                "venv/bin/python3",
                "/home/steam/jtwp-collector/"
                "Pavlov-Data-Collector-/"
                "scripts/set-rcon-loop.py",
                "-c",
                "/home/steam/jtwp-collector/"
                "Pavlov-Data-Collector-/"
                "config.json",
                "start",
                server_id,
                str(seconds),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=20,
            check=False,
        )

        bot.audit(
            ctx,
            "loop_start",
            result.returncode == 0,
            server_id=server_id,
            seconds=seconds,
        )

        await ctx.send(
            "```\n"
            + strip_ansi(result.stdout)
            + "\n```"
        )

    @loop_group.command(name="stop")
    async def loop_stop(ctx):
        if not await bot.guard(
            ctx,
            owner_only=True,
        ):
            return

        result = await asyncio.to_thread(
            subprocess.run,
            [
                "/home/steam/jtwp-collector/"
                "venv/bin/python3",
                "/home/steam/jtwp-collector/"
                "Pavlov-Data-Collector-/"
                "scripts/set-rcon-loop.py",
                "-c",
                "/home/steam/jtwp-collector/"
                "Pavlov-Data-Collector-/"
                "config.json",
                "stop",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=20,
            check=False,
        )

        bot.audit(
            ctx,
            "loop_stop",
            result.returncode == 0,
        )

        await ctx.send(
            "```\n"
            + strip_ansi(result.stdout)
            + "\n```"
        )

    @loop_group.command(name="status")
    async def loop_status(ctx):
        if not await bot.guard(ctx):
            return

        loop_cfg = bot.cfg.get(
            "rcon_loop",
            {},
        )

        control_path = Path(
            loop_cfg["control_path"]
        )

        output_path = Path(
            loop_cfg["output_path"]
        )

        await bot.send_json(
            ctx,
            "🔁 RCON Loop",
            {
                "control": load_json(
                    control_path,
                    None,
                ),
                "output": load_json(
                    output_path,
                    None,
                ),
            },
            "rcon-loop.json",
        )


async def async_main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "-c",
        "--config",
        default="config.json",
    )
    ap.add_argument(
        "-a",
        "--active",
        default="active.json",
    )
    args = ap.parse_args()

    cfg_path = Path(args.config).expanduser().resolve()
    if not cfg_path.is_file():
        raise SystemExit(f"Config not found: {cfg_path}")

    load_env_file(cfg_path.parent / ".env")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    active_path = Path(args.active).expanduser()
    if not active_path.is_absolute():
        active_path = cfg_path.parent / active_path

    active = ActiveConfig(
        active_path
    )

    if (
        not active.enabled(
            "discord_bot"
        )
        or not active.enabled(
            "scripts",
            "discord_bot",
        )
    ):
        raise SystemExit(
            "Discord bot disabled by active.json"
        )

    bot_cfg = cfg.get(
        "discord_bot",
        {},
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
            f"Missing environment variable: "
            f"{token_env}"
        )

    bot = JTWPBot(
        cfg,
        active_path,
    )

    register_commands(bot)


    await bot.start(token)




if __name__ == "__main__":
    asyncio.run(async_main())
