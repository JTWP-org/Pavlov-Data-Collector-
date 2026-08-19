#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ActiveConfig:
    """
    Shared active.json reader.

    Missing values default to True for upgrade compatibility.
    Any parent object with enabled=false disables all descendants.
    """

    def __init__(self, path: str | Path = "active.json"):
        self.path = Path(path)
        self.data: dict[str, Any] = {}
        self.last_error: str | None = None
        self.reload()

    def reload(self) -> None:
        if not self.path.exists():
            self.data = {}
            self.last_error = f"Active config not found: {self.path}"
            return

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self.data = raw if isinstance(raw, dict) else {}
            self.last_error = None
        except Exception as exc:
            # Preserve the historical fail-open behavior, but retain diagnostics.
            self.data = {}
            self.last_error = f"{type(exc).__name__}: {exc}"

    def enabled(self, *keys: str, default: bool = True) -> bool:
        node: Any = self.data

        for key in keys:
            if isinstance(node, dict) and node.get("enabled") is False:
                return False

            if not isinstance(node, dict) or key not in node:
                return default

            node = node[key]

        if isinstance(node, dict):
            return bool(node.get("enabled", default))

        if isinstance(node, bool):
            return node

        return default
