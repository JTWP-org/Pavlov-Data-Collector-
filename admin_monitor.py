#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from active_config import ActiveConfig


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def now_iso(dt: datetime | None = None) -> str:
    return (dt or utc_now()).isoformat(
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


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8")
        )
    except Exception:
        return default


def atomic_write_json(path: Path, data: Any) -> None:
    """Atomically write JSON using a unique temp file in the same directory.

    A unique temp file prevents concurrent JTWP services from colliding on a
    shared ``filename.tmp`` path.
    """
    import tempfile

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp_path = Path(tmp_name)

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())

        os.replace(tmp_path, path)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass


def append_jsonl(path: Path, data: dict) -> None:
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


def walk_dicts(value: Any):
    if isinstance(value, dict):
        yield value

        for child in value.values():
            yield from walk_dicts(child)

    elif isinstance(value, list):
        for child in value:
            yield from walk_dicts(child)


def extract_players(response: Any) -> list[dict]:
    """
    Be tolerant of different InspectAll response shapes.

    Any nested object containing a player-style name or ID is
    considered a candidate. Score is extracted when present.
    """
    output = []
    seen = set()

    for item in walk_dicts(response):
        name = next(
            (
                item.get(k)
                for k in (
                    "PlayerName",
                    "playerName",
                    "Name",
                    "name",
                )
                if isinstance(item.get(k), str)
            ),
            None,
        )

        unique_id = next(
            (
                item.get(k)
                for k in (
                    "UniqueId",
                    "UniqueID",
                    "uniqueId",
                    "unique_id",
                    "PlayerId",
                    "playerId",
                )
                if item.get(k) is not None
            ),
            None,
        )

        score = next(
            (
                item.get(k)
                for k in ("Score", "score")
                if isinstance(
                    item.get(k),
                    (int, float),
                )
            ),
            None,
        )

        if name is None and unique_id is None:
            continue

        key = (
            str(unique_id),
            str(name),
        )

        if key in seen:
            continue

        seen.add(key)

        output.append(
            {
                "name": name,
                "unique_id": (
                    str(unique_id)
                    if unique_id is not None
                    else None
                ),
                "score": score,
            }
        )

    return output


class AdminMonitor:
    def __init__(
        self,
        cfg: dict,
        active_path: Path,
    ):
        self.cfg = cfg
        self.active = ActiveConfig(
            active_path
        )

        admin_cfg = cfg.get(
            "admin_notifications",
            {},
        )

        self.data_root = Path(
            cfg["data_path"]
        )

        self.loop_output = Path(
            admin_cfg["loop_output_path"]
        )

        self.poll_interval = float(
            admin_cfg.get(
                "poll_interval_seconds",
                2,
            )
        )

        self.no_admin_delay = int(
            admin_cfg.get(
                "no_admin_delay_seconds",
                60,
            )
        )

        self.negative_score = float(
            admin_cfg.get(
                "negative_score_threshold",
                0,
            )
        )

        self.teamkill_threshold = int(
            admin_cfg.get(
                "teamkill_threshold",
                2,
            )
        )

        self.response_window = int(
            admin_cfg.get(
                "response_window_seconds",
                900,
            )
        )

        self.role_id = str(
            admin_cfg.get(
                "role_id",
                "",
            )
        )

        self.webhook_url = os.getenv(
            admin_cfg.get(
                "webhook_env",
                "JTWP_ADMIN_WEBHOOK_URL",
            ),
            "",
        ).strip()

        self.admin_root = (
            self.data_root
            / "global"
            / "admins"
        )

        self.state_path = (
            self.admin_root
            / "monitor_state.json"
        )

        self.events_path = (
            self.admin_root
            / "events.jsonl"
        )

        self.sessions_path = (
            self.admin_root
            / "sessions.jsonl"
        )

        self.alerts_path = (
            self.admin_root
            / "alerts.jsonl"
        )

        self.stats_path = (
            self.admin_root
            / "admin_stats.json"
        )

        self.state = load_json(
            self.state_path,
            {
                "servers": {},
                "open_alerts": [],
            },
        )

    def resolve_player(
        self,
        player: dict,
    ):
        names = load_json(
            self.data_root
            / "players"
            / "index"
            / "by_name.json",
            {},
        )

        unique_ids = load_json(
            self.data_root
            / "players"
            / "index"
            / "by_unique_id.json",
            {},
        )

        candidates = []

        unique_id = player.get(
            "unique_id"
        )

        if (
            unique_id
            and unique_id in unique_ids
        ):
            value = unique_ids[
                unique_id
            ]

            candidates.extend(
                value
                if isinstance(value, list)
                else [value]
            )

        name = (
            player.get("name")
            or ""
        ).casefold()

        if name and name in names:
            value = names[name]

            candidates.extend(
                value
                if isinstance(value, list)
                else [value]
            )

        product_id = (
            str(candidates[0])
            if candidates
            else None
        )

        if not product_id:
            return None, {}, {}

        player_dir = (
            self.data_root
            / "players"
            / "records"
            / product_id
        )

        record = load_json(
            player_dir / "player.json",
            {},
        )

        stats = load_json(
            player_dir / "stats.json",
            {},
        )

        return (
            product_id,
            record,
            stats,
        )

    def send_webhook(
        self,
        title: str,
        description: str,
        fields: list[dict] | None = None,
    ) -> None:
        if (
            not self.webhook_url
            or not self.active.enabled(
                "admins",
                "notifications",
            )
        ):
            return

        content = None
        roles = []

        if (
            self.role_id
            and self.active.enabled(
                "admins",
                "notifications",
                "ping_admin_role",
            )
        ):
            content = (
                f"<@&{self.role_id}>"
            )

            roles = [
                self.role_id
            ]

        payload = {
            "content": content,
            "allowed_mentions": {
                "parse": [],
                "roles": roles,
            },
            "embeds": [
                {
                    "title": title,
                    "description": description,
                    "fields": fields or [],
                    "footer": {
                        "text": "JTWP.org"
                    },
                    "timestamp": now_iso(),
                }
            ],
        }

        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=8,
            )

            response.raise_for_status()

        except Exception as e:
            print(
                f"Admin webhook failed: {e}",
                flush=True,
            )

    def create_alert(
        self,
        server_id: str,
        alert_type: str,
        player: dict | None,
        details: dict,
    ) -> dict:
        alert = {
            "alert_id": (
                f"{server_id}-"
                f"{alert_type}-"
                f"{uuid.uuid4().hex[:10]}"
            ),
            "created_at": now_iso(),
            "server_id": server_id,
            "type": alert_type,
            "player": player,
            "details": details,
            "response_window_seconds": (
                self.response_window
            ),
            "admin_joined_within_window": False,
            "responding_admin": None,
            "responded_at": None,
            "response_seconds": None,
            "expired": False,
        }

        self.state.setdefault(
            "open_alerts",
            [],
        ).append(alert)

        append_jsonl(
            self.alerts_path,
            alert,
        )

        return alert

    def respond_to_alerts(
        self,
        server_id: str,
        admin: dict,
    ) -> None:
        current = utc_now()

        for alert in self.state.get(
            "open_alerts",
            [],
        ):
            if (
                alert.get("server_id")
                != server_id
                or alert.get(
                    "responded_at"
                )
                or alert.get("expired")
            ):
                continue

            created = (
                datetime.fromisoformat(
                    alert[
                        "created_at"
                    ].replace(
                        "Z",
                        "+00:00",
                    )
                )
            )

            response_seconds = int(
                (
                    current
                    - created
                ).total_seconds()
            )

            if (
                response_seconds
                > self.response_window
            ):
                continue

            alert.update(
                {
                    "admin_joined_within_window": True,
                    "responding_admin": admin,
                    "responded_at": now_iso(
                        current
                    ),
                    "response_seconds": (
                        response_seconds
                    ),
                }
            )

            append_jsonl(
                self.events_path,
                {
                    "timestamp": now_iso(
                        current
                    ),
                    "event": (
                        "admin_alert_response"
                    ),
                    "alert_id": alert[
                        "alert_id"
                    ],
                    "alert_type": alert[
                        "type"
                    ],
                    "server_id": (
                        server_id
                    ),
                    "admin": admin,
                    "response_seconds": (
                        response_seconds
                    ),
                    "within_15_minutes": (
                        response_seconds
                        <= 900
                    ),
                },
            )

    def expire_alerts(self) -> None:
        current = utc_now()

        for alert in self.state.get(
            "open_alerts",
            [],
        ):
            if (
                alert.get(
                    "responded_at"
                )
                or alert.get("expired")
            ):
                continue

            created = (
                datetime.fromisoformat(
                    alert[
                        "created_at"
                    ].replace(
                        "Z",
                        "+00:00",
                    )
                )
            )

            if (
                current
                - created
            ).total_seconds() <= (
                self.response_window
            ):
                continue

            alert["expired"] = True

            append_jsonl(
                self.events_path,
                {
                    "timestamp": (
                        now_iso(current)
                    ),
                    "event": (
                        "admin_alert_expired"
                    ),
                    "alert_id": alert[
                        "alert_id"
                    ],
                    "alert_type": alert[
                        "type"
                    ],
                    "server_id": alert[
                        "server_id"
                    ],
                    "admin_joined_within_window": False,
                },
            )

    def finish_admin_session(
        self,
        server_id: str,
        product_id: str,
        session: dict,
    ) -> None:
        joined = session.get(
            "joined_at"
        )

        if not joined:
            return

        end = utc_now()

        start = (
            datetime.fromisoformat(
                joined.replace(
                    "Z",
                    "+00:00",
                )
            )
        )

        duration = max(
            0,
            int(
                (
                    end
                    - start
                ).total_seconds()
            ),
        )

        record = {
            "server_id": server_id,
            "product_id": product_id,
            "player_name": session.get(
                "player_name"
            ),
            "joined_at": joined,
            "left_at": now_iso(end),
            "duration_seconds": duration,
        }

        append_jsonl(
            self.sessions_path,
            record,
        )

        stats = load_json(
            self.stats_path,
            {},
        )

        entry = stats.setdefault(
            product_id,
            {
                "product_id": (
                    product_id
                ),
                "total_admin_time_seconds": 0,
                "total_admin_sessions": 0,
                "servers": {},
            },
        )

        entry[
            "total_admin_time_seconds"
        ] += duration

        entry[
            "total_admin_sessions"
        ] += 1

        server_stats = (
            entry["servers"].setdefault(
                server_id,
                {
                    "time_seconds": 0,
                    "sessions": 0,
                },
            )
        )

        server_stats[
            "time_seconds"
        ] += duration

        server_stats[
            "sessions"
        ] += 1

        entry.setdefault(
            "first_admin_session",
            joined,
        )

        entry[
            "last_admin_session"
        ] = record["left_at"]

        atomic_write_json(
            self.stats_path,
            stats,
        )

    def cycle(self) -> None:
        loop_data = load_json(
            self.loop_output,
            None,
        )

        if not isinstance(
            loop_data,
            dict,
        ):
            return

        server_id = loop_data.get(
            "server_id"
        )

        inspectall = loop_data.get(
            "inspectall",
            {},
        )

        response = (
            inspectall.get(
                "response"
            )
            if isinstance(
                inspectall,
                dict,
            )
            else None
        )

        if (
            not server_id
            or response is None
        ):
            return

        players = extract_players(
            response
        )

        server_state = (
            self.state.setdefault(
                "servers",
                {},
            ).setdefault(
                server_id,
                {
                    "admins": {},
                    "no_admin_since": None,
                    "no_admin_alert_active": False,
                    "players": {},
                },
            )
        )

        current_admins = {}

        for player in players:
            (
                product_id,
                record,
                stats,
            ) = self.resolve_player(
                player
            )

            if not product_id:
                continue

            player_name = (
                record.get(
                    "current_name"
                )
                or player.get("name")
                or product_id
            )

            is_admin = bool(
                record.get(
                    "admin",
                    False,
                )
            )

            if is_admin:
                current_admins[
                    product_id
                ] = {
                    "product_id": (
                        product_id
                    ),
                    "player_name": (
                        player_name
                    ),
                }

                if (
                    product_id
                    not in server_state[
                        "admins"
                    ]
                ):
                    server_state[
                        "admins"
                    ][product_id] = {
                        "joined_at": (
                            now_iso()
                        ),
                        "player_name": (
                            player_name
                        ),
                    }

                    append_jsonl(
                        self.events_path,
                        {
                            "timestamp": (
                                now_iso()
                            ),
                            "event": (
                                "admin_connected"
                            ),
                            "server_id": (
                                server_id
                            ),
                            "product_id": (
                                product_id
                            ),
                            "player_name": (
                                player_name
                            ),
                        },
                    )

                    self.respond_to_alerts(
                        server_id,
                        {
                            "product_id": (
                                product_id
                            ),
                            "player_name": (
                                player_name
                            ),
                        },
                    )

            player_alert_state = (
                server_state[
                    "players"
                ].setdefault(
                    product_id,
                    {
                        "negative_score_alert": False,
                        "teamkill_alert": False,
                    },
                )
            )

            score = player.get(
                "score"
            )

            if (
                self.active.enabled(
                    "admins",
                    "notifications",
                    "negative_player_score",
                )
                and isinstance(
                    score,
                    (int, float),
                )
            ):
                if (
                    score
                    < self.negative_score
                    and not player_alert_state[
                        "negative_score_alert"
                    ]
                ):
                    player_alert_state[
                        "negative_score_alert"
                    ] = True

                    self.create_alert(
                        server_id,
                        "negative_score",
                        {
                            "product_id": (
                                product_id
                            ),
                            "player_name": (
                                player_name
                            ),
                        },
                        {
                            "score": score
                        },
                    )

                    self.send_webhook(
                        "📉 Player Score Below Zero",
                        (
                            f"Player **{player_name}** "
                            f"has a score of `{score}`."
                        ),
                        [
                            {
                                "name": "Server",
                                "value": (
                                    f"`{server_id}`"
                                ),
                                "inline": True,
                            }
                        ],
                    )

                elif (
                    score
                    >= self.negative_score
                ):
                    player_alert_state[
                        "negative_score_alert"
                    ] = False

            teamkills = int(
                (
                    stats.get(
                        "combat"
                    )
                    or {}
                ).get(
                    "teamkills",
                    0,
                )
                or 0
            )

            if (
                self.active.enabled(
                    "admins",
                    "notifications",
                    "multiple_teamkills",
                )
                and teamkills
                >= self.teamkill_threshold
                and not player_alert_state[
                    "teamkill_alert"
                ]
            ):
                player_alert_state[
                    "teamkill_alert"
                ] = True

                self.create_alert(
                    server_id,
                    "multiple_teamkills",
                    {
                        "product_id": (
                            product_id
                        ),
                        "player_name": (
                            player_name
                        ),
                    },
                    {
                        "teamkills": (
                            teamkills
                        )
                    },
                )

                self.send_webhook(
                    "🔴 Multiple Teamkills Detected",
                    (
                        f"Player **{player_name}** "
                        f"has `{teamkills}` "
                        f"recorded teamkills."
                    ),
                    [
                        {
                            "name": "Server",
                            "value": (
                                f"`{server_id}`"
                            ),
                            "inline": True,
                        }
                    ],
                )

        # Close admin sessions when an admin disappears from InspectAll.
        for product_id, session in list(
            server_state["admins"].items()
        ):
            if product_id in current_admins:
                continue

            self.finish_admin_session(
                server_id,
                product_id,
                session,
            )

            append_jsonl(
                self.events_path,
                {
                    "timestamp": now_iso(),
                    "event": (
                        "admin_disconnected"
                    ),
                    "server_id": (
                        server_id
                    ),
                    "product_id": (
                        product_id
                    ),
                    "player_name": (
                        session.get(
                            "player_name"
                        )
                    ),
                },
            )

            del server_state[
                "admins"
            ][product_id]

        # Players online and no admin.
        if players and not current_admins:
            if not server_state.get(
                "no_admin_since"
            ):
                server_state[
                    "no_admin_since"
                ] = now_iso()

            started = (
                datetime.fromisoformat(
                    server_state[
                        "no_admin_since"
                    ].replace(
                        "Z",
                        "+00:00",
                    )
                )
            )

            elapsed = (
                utc_now()
                - started
            ).total_seconds()

            if (
                elapsed
                >= self.no_admin_delay
                and not server_state.get(
                    "no_admin_alert_active"
                )
                and self.active.enabled(
                    "admins",
                    "notifications",
                    "no_admin_online",
                )
            ):
                server_state[
                    "no_admin_alert_active"
                ] = True

                self.create_alert(
                    server_id,
                    "no_admin_online",
                    None,
                    {
                        "players_online": (
                            len(players)
                        )
                    },
                )

                self.send_webhook(
                    "🚨 Players Online — No Admin Present",
                    (
                        f"`{len(players)}` players "
                        f"are online and no known "
                        f"admin is present."
                    ),
                    [
                        {
                            "name": "Server",
                            "value": (
                                f"`{server_id}`"
                            ),
                            "inline": True,
                        }
                    ],
                )

        else:
            server_state[
                "no_admin_since"
            ] = None

            server_state[
                "no_admin_alert_active"
            ] = False

        self.expire_alerts()

        atomic_write_json(
            self.state_path,
            self.state,
        )

    def run(self) -> None:
        print(
            "JTWP admin monitor started.",
            flush=True,
        )

        while True:
            self.active.reload()

            if (
                self.active.enabled(
                    "scripts",
                    "admin_monitor",
                )
                and self.active.enabled(
                    "admins"
                )
            ):
                self.cycle()

            time.sleep(
                self.poll_interval
            )


def main():
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

    AdminMonitor(
        cfg,
        active_path,
    ).run()


if __name__ == "__main__":
    main()
