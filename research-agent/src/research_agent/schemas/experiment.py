from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BaselineReproduction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    status: Literal["PENDING", "PASS", "MARGINAL", "FAIL"] = "PENDING"
    reported_result: str | None = None
    reproduced_result: str | None = None
    difference: str | None = None
    variance: str | None = None
    environment_diff: str | None = None
    diagnosis: str | None = None
    synthetic_test_data: bool = False


class Experiment(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    id: str
    hypothesis_id: str
    research_question: str
    baseline_ids: list[str] = Field(default_factory=list)
    independent_variables: list[str] = Field(default_factory=list)
    dependent_variables: list[str] = Field(default_factory=list)
    control_variables: list[str] = Field(default_factory=list)
    expected_outcome: str
    success_criterion: str
    falsification_criterion: str
    model: str | None = None
    dataset: str | None = None
    seeds: list[int] = Field(default_factory=list)
    estimated_gpu_hours: float | None = Field(default=None, ge=0)
    level: Literal["L0", "L1", "L2", "L3", "L4", "L5"] = "L1"
    status: Literal[
        "planned", "approved", "running", "completed", "failed", "cancelled"
    ] = "planned"
    execution_verified: bool = False
    execution_artifact: str | None = None
    metrics_artifact: str | None = None
    observation: str | None = None
    interpretation: str | None = None
    confounders: list[str] = Field(default_factory=list)
    next_experiment_ids: list[str] = Field(default_factory=list)
    synthetic_test_data: bool = False

    @model_validator(mode="after")
    def verified_results_require_execution(self) -> "Experiment":
        if self.execution_verified and self.status != "completed":
            raise ValueError("execution_verified requires status='completed'")
        if self.execution_verified and not self.execution_artifact:
            raise ValueError("execution_verified requires a runner execution artifact")
        return self


class ExperimentState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baselines: list[BaselineReproduction] = Field(default_factory=list)
    experiments: list[Experiment] = Field(default_factory=list)
    consecutive_diagnostics: int = Field(default=0, ge=0)
    major_method_revisions: int = Field(default=0, ge=0)
