from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ClaimEvidenceRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    statement: str
    evidence_level: str
    supporting_papers: list[str] = Field(default_factory=list)
    supporting_experiments: list[str] = Field(default_factory=list)
    allowed_language_strength: str


class PaperPackage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    problem: str
    gap: str
    root_cause: str
    hypothesis: list[str]
    method: str
    contributions: list[str]
    related_work_positioning: list[str]
    experimental_setup: list[str]
    main_results: list[str]
    ablations: list[str]
    analysis: list[str]
    failure_cases: list[str]
    limitations: list[str]
    claim_evidence_matrix: list[ClaimEvidenceRow]
    tables: list[str]
    figure_requirements: list[str]
    citations: list[str]
    do_not_claim: list[str]
    synthetic_test_data: bool = False

