#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import subprocess
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

        output = (
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
                "/usr/local/bin/"
                "clear-pavlov-mods",
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

        output = (
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

        output = (
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
        await run_owner_process(
            ctx,
            "RUNcollector",
            [
                "sudo",
                "systemctl",
                "start",
                "jtwp-collector.service",
            ],
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
        if not await bot.guard(
            ctx,
            owner_only=True,
        ):
            return

        ssh_dir = (
            bot.data_root
            / "global"
            / "ssh"
        )

        build_script = (
            ssh_dir
            / "buildIt"
        )

        built_file = (
            ssh_dir
            / "built.txt"
        )

        discord_script = (
            ssh_dir
            / "discordIt"
        )

        build = await asyncio.to_thread(
            subprocess.run,
            [
                "bash",
                str(build_script),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=180,
            check=False,
        )

        if build.returncode != 0:
            error = build.stderr.decode(
                errors="replace"
            )

            bot.audit(
                ctx,
                "RUNssh",
                False,
                error=error,
            )

            await ctx.send(
                "❌ buildIt failed:\n"
                f"```{error[-1500:]}```"
            )
            return

        built_file.write_bytes(
            build.stdout
        )

        send = await asyncio.to_thread(
            subprocess.run,
            [
                "bash",
                str(discord_script),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=180,
            check=False,
        )

        bot.audit(
            ctx,
            "RUNssh",
            send.returncode == 0,
            returncode=send.returncode,
        )

        if send.returncode == 0:
            await ctx.send(
                "✅ SSH report generated "
                "and `discordIt` executed."
            )
        else:
            await ctx.send(
                "❌ discordIt failed:\n"
                f"```{send.stdout[-1500:]}```"
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
            + result.stdout
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
            + result.stdout
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

    cfg = json.loads(
        Path(args.config).read_text(
            encoding="utf-8"
        )
    )

    active = ActiveConfig(
        args.active
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
        Path(args.active),
    )

    register_commands(bot)

    await bot.start(token)


if __name__ == "__main__":
    asyncio.run(async_main())
