from __future__ import annotations

import os
import subprocess
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit, urlunsplit

import yaml


class RepositoryAttachmentService:
    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir.resolve()
        self.config_path = self.project_dir / "project.yaml"

    def attach(self, repository_path: Path) -> dict[str, str | None]:
        repository = repository_path.resolve()
        if not repository.is_dir():
            raise FileNotFoundError(f"Repository path does not exist: {repository}")
        config = self._config()
        record = {
            "path": str(repository),
            "git_commit": self._git(repository, "rev-parse", "HEAD"),
            "remote_url": self._sanitize_url(
                self._git(repository, "remote", "get-url", "origin")
            ),
        }
        config["repository"] = record
        self._write(config)
        return record

    def load(self) -> dict[str, str | None] | None:
        value = self._config().get("repository")
        if not isinstance(value, dict) or not value.get("path"):
            return None
        path = Path(str(value["path"])).resolve()
        if not path.is_dir():
            return None
        return {
            "path": str(path),
            "git_commit": str(value["git_commit"]) if value.get("git_commit") else None,
            "remote_url": str(value["remote_url"]) if value.get("remote_url") else None,
        }

    def execution_configuration(self) -> dict[str, object]:
        value = self._config().get("execution", {})
        return dict(value) if isinstance(value, dict) else {}

    def _config(self) -> dict[str, object]:
        if not self.config_path.is_file():
            raise FileNotFoundError(self.config_path)
        value = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(value, dict):
            raise ValueError("project.yaml must contain a mapping")  # noqa: TRY004
        return value

    def _write(self, value: dict[str, object]) -> None:
        with NamedTemporaryFile(
            "w", encoding="utf-8", dir=self.project_dir, delete=False
        ) as handle:
            yaml.safe_dump(value, handle, sort_keys=False)
            temporary = Path(handle.name)
        os.replace(temporary, self.config_path)

    @staticmethod
    def _git(repository: Path, *arguments: str) -> str | None:
        result = subprocess.run(
            ("git", *arguments),
            cwd=repository,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else None

    @staticmethod
    def _sanitize_url(value: str | None) -> str | None:
        if not value or "://" not in value:
            return value
        parsed = urlsplit(value)
        hostname = parsed.hostname or ""
        if parsed.port:
            hostname += f":{parsed.port}"
        return urlunsplit(
            (parsed.scheme, hostname, parsed.path, parsed.query, parsed.fragment)
        )
