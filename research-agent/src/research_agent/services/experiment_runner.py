from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from research_agent.core.ids import new_id
from research_agent.schemas.execution import ExperimentExecutionResult
from research_agent.storage.artifact_store import ArtifactStore

SENSITIVE_ENV_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")


class ExperimentRunner:
    def __init__(
        self,
        artifacts: ArtifactStore,
        *,
        allow_shell: bool = False,
        timeout_seconds: float = 3600,
    ) -> None:
        self.artifacts = artifacts
        self.allow_shell = allow_shell
        self.timeout_seconds = timeout_seconds

    async def run_shell_experiment(
        self,
        command: str,
        cwd: Path,
        env: dict[str, str],
        *,
        experiment_id: str | None = None,
        config: dict[str, object] | None = None,
        metrics_path: str | None = None,
    ) -> ExperimentExecutionResult:
        if not self.allow_shell:
            raise PermissionError("Shell execution is disabled by configuration")
        resolved_cwd = cwd.resolve()
        if not resolved_cwd.is_dir():
            raise FileNotFoundError(f"Experiment cwd does not exist: {resolved_cwd}")
        self._validate_metrics_path(resolved_cwd, metrics_path)
        experiment_id = experiment_id or new_id("EXP")
        artifact_root = f"artifacts/experiments/{experiment_id}"
        started_at = datetime.now(UTC)
        started_clock = perf_counter()
        git_commit = await self._git_commit(resolved_cwd)
        merged_env = dict(os.environ)
        merged_env.update(env)
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=resolved_cwd,
            env=merged_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        timed_out = False
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self.timeout_seconds
            )
        except TimeoutError:
            timed_out = True
            process.terminate()
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5)
            except TimeoutError:
                process.kill()
                stdout, stderr = await process.communicate()
        ended_at = datetime.now(UTC)
        runtime_seconds = perf_counter() - started_clock
        return_code = process.returncode if process.returncode is not None else -1
        stdout_path = self.artifacts.write_text(
            f"{artifact_root}/stdout.log", stdout.decode("utf-8", errors="replace")
        )
        stderr_path = self.artifacts.write_text(
            f"{artifact_root}/stderr.log", stderr.decode("utf-8", errors="replace")
        )
        environment_path = self.artifacts.write_json(
            f"{artifact_root}/environment.json", self._redact_environment(env)
        )
        config_path = self.artifacts.write_json(
            f"{artifact_root}/config.json", config or {}
        )
        git_diff = await self._git_diff(resolved_cwd)
        git_diff_path = self.artifacts.write_text(
            f"{artifact_root}/git.diff", git_diff
        )
        metrics_artifact = self._capture_metrics(
            resolved_cwd, metrics_path, artifact_root
        )
        metadata = {
            "experiment_id": experiment_id,
            "command": command,
            "cwd": str(resolved_cwd),
            "return_code": return_code,
            "started_at": started_at,
            "ended_at": ended_at,
            "git_commit": git_commit,
            "git_diff_artifact": git_diff_path,
            "config_artifact": config_path,
            "metrics_artifact": metrics_artifact,
            "runtime_seconds": runtime_seconds,
            "repository": str(resolved_cwd),
            "environment_artifact": environment_path,
            "stdout_artifact": stdout_path,
            "stderr_artifact": stderr_path,
            "timed_out": timed_out,
        }
        metadata_path = self.artifacts.write_json(
            f"{artifact_root}/execution.json", metadata
        )
        return ExperimentExecutionResult(
            **metadata,
            metadata_artifact=metadata_path,
        )

    @staticmethod
    def _redact_environment(environment: dict[str, str]) -> dict[str, str]:
        return {
            key: (
                "[REDACTED]"
                if any(marker in key.upper() for marker in SENSITIVE_ENV_MARKERS)
                else value
            )
            for key, value in sorted(environment.items())
        }

    @staticmethod
    async def _git_commit(cwd: Path) -> str | None:
        process = await asyncio.create_subprocess_exec(
            "git",
            "rev-parse",
            "HEAD",
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await process.communicate()
        return stdout.decode().strip() if process.returncode == 0 else None

    @staticmethod
    async def _git_diff(cwd: Path) -> str:
        process = await asyncio.create_subprocess_exec(
            "git",
            "diff",
            "--no-ext-diff",
            "HEAD",
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await process.communicate()
        return stdout.decode("utf-8", errors="replace") if process.returncode == 0 else ""

    def _capture_metrics(
        self, cwd: Path, metrics_path: str | None, artifact_root: str
    ) -> str | None:
        if metrics_path is None:
            return None
        source = (cwd / metrics_path).resolve()
        if source != cwd and cwd not in source.parents:
            raise ValueError("Metrics path must remain inside the experiment repository")
        if not source.is_file():
            return None
        try:
            metrics = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Experiment metrics must be valid JSON") from exc
        if not isinstance(metrics, dict):
            raise ValueError("Experiment metrics must be a JSON object")  # noqa: TRY004
        return self.artifacts.write_json(f"{artifact_root}/metrics.json", metrics)

    @staticmethod
    def _validate_metrics_path(cwd: Path, metrics_path: str | None) -> None:
        if metrics_path is None:
            return
        source = (cwd / metrics_path).resolve()
        if source != cwd and cwd not in source.parents:
            raise ValueError("Metrics path must remain inside the experiment repository")
