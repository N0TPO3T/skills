from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FailureExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    explanation: str
    evidence_for: list[str] = Field(default_factory=list)
    evidence_against: list[str] = Field(default_factory=list)
    probability: float = Field(ge=0.0, le=1.0)
    cheapest_diagnostic_experiment: str
    estimated_cost: float = Field(default=0.0, ge=0.0)
    expected_information_gain: float = Field(default=0.0, ge=0.0)

    @property
    def information_gain_per_cost(self) -> float:
        if self.estimated_cost == 0:
            return float("inf") if self.expected_information_gain > 0 else 0.0
        return self.expected_information_gain / self.estimated_cost

