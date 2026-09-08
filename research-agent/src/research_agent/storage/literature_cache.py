from __future__ import annotations

import json
import os
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import time
from typing import Any


class LiteratureCache:
    def __init__(self, project_dir: Path) -> None:
        self.root = project_dir.resolve() / "artifacts" / "literature" / "cache"
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def stable_key(operation: str, provider: str, value: object) -> str:
        payload = json.dumps(
            {"operation": operation, "provider": provider, "input": value},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return sha256(payload.encode("utf-8")).hexdigest()

    def get(
        self, operation: str, key: str, *, max_age_seconds: float | None = None
    ) -> Any | None:
        path = self.root / operation / f"{key}.json"
        if not path.is_file():
            return None
        if max_age_seconds is not None and time() - path.stat().st_mtime > max_age_seconds:
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def contains(
        self, operation: str, key: str, *, max_age_seconds: float | None = None
    ) -> bool:
        path = self.root / operation / f"{key}.json"
        if not path.is_file():
            return False
        return not (
            max_age_seconds is not None
            and time() - path.stat().st_mtime > max_age_seconds
        )

    def set(self, operation: str, key: str, value: object) -> Path:
        path = self.root / operation / f"{key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            value, ensure_ascii=False, sort_keys=True, indent=2, default=str
        )
        with NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            handle.write(payload + "\n")
            temp_path = Path(handle.name)
        os.replace(temp_path, path)
        return path
