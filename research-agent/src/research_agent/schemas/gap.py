from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class GapEvidenceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    independent_paper_count: int = Field(ge=0)
    supporting_statement_count: int = Field(ge=0)
    contradictory_statement_count: int = Field(ge=0)
    content_verified_paper_count: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)


class ResearchGap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    observed_phenomena: list[str] = Field(default_factory=list)
    supporting_papers: list[str] = Field(default_factory=list)
    supporting_statement_ids: list[str] = Field(default_factory=list)
    contradictory_statement_ids: list[str] = Field(default_factory=list)
    evidence_summary: GapEvidenceSummary | None = None
    common_limitation: str
    root_cause_hypothesis: str
    why_existing_methods_fail: str
    missing_capability: str
    potential_interventions: list[str] = Field(default_factory=list)
    related_techniques: list[str] = Field(default_factory=list)
    minimum_viable_experiment: str
    expected_signal: str
    falsification_criterion: str
    novelty_score: float = Field(ge=0.0, le=1.0)
    feasibility_score: float = Field(ge=0.0, le=1.0)
    research_value_score: float = Field(ge=0.0, le=1.0)
    publication_score: float = Field(ge=0.0, le=1.0)
    risk_score: float = Field(ge=0.0, le=1.0)
    status: Literal["candidate", "shortlisted", "selected", "rejected"] = (
        "candidate"
    )
    synthetic_test_data: bool = False


class GapState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[ResearchGap] = Field(default_factory=list)
    selected_gap_id: str | None = None
    synthesis_artifact: str | None = None
