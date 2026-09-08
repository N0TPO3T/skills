from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ExperimentExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_id: str
    command: str
    cwd: str
    return_code: int
    started_at: datetime
    ended_at: datetime
    git_commit: str | None
    git_diff_artifact: str | None = None
    config_artifact: str | None = None
    metrics_artifact: str | None = None
    runtime_seconds: float | None = None
    repository: str | None = None
    environment_artifact: str
    metadata_artifact: str
    stdout_artifact: str
    stderr_artifact: str
    timed_out: bool = False
