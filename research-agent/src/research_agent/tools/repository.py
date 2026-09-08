from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class RepositoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cwd: Path


class RepositoryOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    git_commit: str | None


class RepositoryTool:
    name = "repository"

    async def run(self, input: RepositoryInput) -> RepositoryOutput:
        process = await asyncio.create_subprocess_exec(
            "git",
            "rev-parse",
            "HEAD",
            cwd=input.cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await process.communicate()
        commit = stdout.decode().strip() if process.returncode == 0 else None
        return RepositoryOutput(git_commit=commit)

