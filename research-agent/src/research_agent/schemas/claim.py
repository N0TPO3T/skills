from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from research_agent.schemas.evidence import EvidenceLevel


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    statement: str
    evidence_level: EvidenceLevel
    supporting_papers: list[str] = Field(default_factory=list)
    supporting_experiments: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    allowed_language_strength: str

    @model_validator(mode="after")
    def validate_minimum_support(self) -> "Claim":
        if self.evidence_level == EvidenceLevel.E1_LITERATURE and not self.supporting_papers:
            raise ValueError("E1 claims require at least one supporting paper")
        if self.evidence_level in {
            EvidenceLevel.E2_SINGLE_EXPERIMENT,
            EvidenceLevel.E3_REPLICATED,
            EvidenceLevel.E4_ROBUST,
        } and not self.supporting_experiments:
            raise ValueError("E2+ claims require supporting experiments")
        return self


class ClaimState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[Claim] = Field(default_factory=list)

