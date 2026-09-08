from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from research_agent.core.transitions import ResearchPhase
from research_agent.schemas.claim import ClaimState
from research_agent.schemas.decision import DecisionRecord, HumanCheckpoint, ResearchAction
from research_agent.schemas.evidence import EvidenceState
from research_agent.schemas.experiment import ExperimentState
from research_agent.schemas.gap import GapState
from research_agent.schemas.hypothesis import HypothesisState
from research_agent.schemas.idea import IdeaState
from research_agent.schemas.literature import LiteratureState
from research_agent.schemas.literature_quality import LiteratureQualityState
from research_agent.schemas.project import ProjectInfo, ResourceConstraints


class ResearchState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0", "1.1", "1.2"] = "1.2"
    project: ProjectInfo
    phase: ResearchPhase = ResearchPhase.BOOTSTRAP
    constraints: ResourceConstraints = Field(default_factory=ResourceConstraints)
    literature: LiteratureState = Field(default_factory=LiteratureState)
    literature_quality: LiteratureQualityState = Field(
        default_factory=LiteratureQualityState
    )
    gaps: GapState = Field(default_factory=GapState)
    hypotheses: HypothesisState = Field(default_factory=HypothesisState)
    ideas: IdeaState = Field(default_factory=IdeaState)
    experiments: ExperimentState = Field(default_factory=ExperimentState)
    evidence: EvidenceState = Field(default_factory=EvidenceState)
    claims: ClaimState = Field(default_factory=ClaimState)
    decisions: list[DecisionRecord] = Field(default_factory=list)
    human_checkpoint: HumanCheckpoint | None = None
    next_actions: list[ResearchAction] = Field(default_factory=list)
    iteration: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
