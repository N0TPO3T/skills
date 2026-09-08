from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


class ArtifactStore:
    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir.resolve()
        self.root = self.project_dir / "artifacts"
        self.root.mkdir(parents=True, exist_ok=True)
        self.written_paths: list[str] = []

    def _resolve(self, relative_path: str) -> Path:
        candidate = (self.project_dir / relative_path).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ValueError("Artifact path must remain inside the artifact root")
        return candidate

    def write_text(self, relative_path: str, content: str) -> str:
        path = self._resolve(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        relative = str(path.relative_to(self.project_dir))
        self.written_paths.append(relative)
        return relative

    def write_bytes(self, relative_path: str, content: bytes) -> str:
        path = self._resolve(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("wb", dir=path.parent, delete=False) as handle:
            handle.write(content)
            temp_path = Path(handle.name)
        os.replace(temp_path, path)
        relative = str(path.relative_to(self.project_dir))
        self.written_paths.append(relative)
        return relative

    def read_bytes(self, relative_path: str) -> bytes:
        return self._resolve(relative_path).read_bytes()

    def write_json(self, relative_path: str, value: Any) -> str:
        return self.write_text(
            relative_path,
            json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n",
        )

    def read_text(self, relative_path: str) -> str:
        return self._resolve(relative_path).read_text(encoding="utf-8")
