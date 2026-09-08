from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from research_agent.schemas.decision import ResearchAction
from research_agent.schemas.experiment import BaselineReproduction, Experiment
from research_agent.schemas.gap import ResearchGap
from research_agent.schemas.hypothesis import Hypothesis
from research_agent.schemas.idea import MethodCandidate

HostToolName = Literal["search", "read", "filesystem", "code", "shell", "git"]


class HostToolUse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: HostToolName
    purpose: str
    outcome: str


class LiveSourceNote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["paper", "repository", "web"]
    title: str
    url: str
    identifier: str | None = None
    why_important: str


class ExperimentAnalysisUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_id: str
    observation: str
    interpretation: str
    confounders: list[str] = Field(default_factory=list)


class IdeaReviewDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attack: str
    defense: str
    verdict: Literal[
        "PROCEED",
        "PROCEED_WITH_MODIFICATIONS",
        "RETURN_TO_LITERATURE",
        "SIMPLIFY",
        "PIVOT",
    ]


class PaperReviewDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    must_fix: list[str] = Field(default_factory=list)
    should_fix: list[str] = Field(default_factory=list)
    disposition: Literal["writing_fix", "analysis_fix", "additional_experiment", "ready"]


class EnvironmentVariable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    value: str


class ExecutionConfigValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    value: str | int | float | bool | None


class ExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_id: str
    command: str = Field(min_length=1)
    environment: list[EnvironmentVariable] = Field(default_factory=list)
    config: list[ExecutionConfigValue] = Field(default_factory=list)
    metrics_path: str | None = None


class LiveStateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    search_queries: list[str] = Field(default_factory=list)
    important_sources: list[LiveSourceNote] = Field(default_factory=list)
    gaps: list[ResearchGap] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    ideas: list[MethodCandidate] = Field(default_factory=list)
    selected_idea_id: str | None = None
    idea_review: IdeaReviewDraft | None = None
    baselines: list[BaselineReproduction] = Field(default_factory=list)
    experiments: list[Experiment] = Field(default_factory=list)
    experiment_analyses: list[ExperimentAnalysisUpdate] = Field(default_factory=list)
    paper_draft: str | None = None
    paper_review: PaperReviewDraft | None = None


class HostAgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["completed", "blocked", "failed"]
    summary: str
    state_update: LiveStateUpdate = Field(default_factory=LiveStateUpdate)
    proposed_action: ResearchAction | None = None
    execution_request: ExecutionRequest | None = None
    tool_uses: list[HostToolUse] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    repository_path: str | None = None
    major_pivot: bool = False
    pivot_options: list[str] = Field(default_factory=list)
    continuation_id: str | None = None

    @model_validator(mode="after")
    def validate_control_flow(self) -> HostAgentResult:
        if (
            self.status == "completed"
            and self.proposed_action is None
            and self.execution_request is None
        ):
            raise ValueError(
                "A completed host turn requires a proposed action or execution request"
            )
        if self.major_pivot and (
            self.proposed_action is None
            or self.proposed_action.action.value != "pivot"
        ):
            raise ValueError("major_pivot requires a pivot action")
        return self
