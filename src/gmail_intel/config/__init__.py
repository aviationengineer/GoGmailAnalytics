"""Configuration loading: config.yaml + environment expansion, privacy defaults."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

import yaml

_ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):
        return _ENV_RE.sub(lambda m: os.environ.get(m.group(1), m.group(2) or ""), value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


@dataclass
class Config:
    raw: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | None = None) -> "Config":
        if path is None:
            here = os.path.dirname(os.path.abspath(__file__))
            path = os.path.normpath(os.path.join(here, "..", "..", "..", "config.yaml"))
        with open(path, encoding="utf-8") as f:
            raw = _expand_env(yaml.safe_load(f) or {})
        return cls(raw=raw)

    def get(self, *keys: str, default: Any = None) -> Any:
        node: Any = self.raw
        for k in keys:
            if not isinstance(node, dict) or k not in node:
                return default
            node = node[k]
        return node

    @property
    def project_root(self) -> str:
        here = os.path.dirname(os.path.abspath(__file__))
        return os.path.normpath(os.path.join(here, "..", "..", ".."))

    def data_path(self, *parts: str) -> str:
        return os.path.join(self.project_root, "data", *parts)

    def enabled_accounts(self) -> list[dict]:
        return [a for a in self.get("gmail", "accounts", default=[]) if a.get("enabled")]

    @property
    def privacy(self) -> dict:
        return self.get("privacy", default={}) or {}
