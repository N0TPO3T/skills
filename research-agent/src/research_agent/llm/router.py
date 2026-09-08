from __future__ import annotations

from pathlib import Path

import yaml


class ModelRouter:
    def __init__(self, routes: dict[str, str]) -> None:
        self.routes = routes

    @classmethod
    def from_yaml(cls, path: Path) -> "ModelRouter":
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(routes=dict(raw.get("models", raw)))

    def for_role(self, role: str) -> str:
        if role not in self.routes:
            raise KeyError(f"No model configured for role: {role}")
        return self.routes[role]

