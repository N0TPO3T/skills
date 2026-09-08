from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ProjectInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    research_direction: str = ""
    target_venue: str | None = None
    synthetic_test_data: bool = False


class ResourceConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_gpu_hours: float | None = Field(default=None, ge=0)
    available_gpus: list[str] = Field(default_factory=list)
    max_wallclock_hours: float | None = Field(default=None, ge=0)
    budget_notes: str = ""
    shell_execution_allowed: bool = False

