from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Hypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    statement: str
    mechanism: str
    predicted_outcome: str
    falsification_criterion: str
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    status: Literal[
        "proposed",
        "active",
        "weakly_supported",
        "supported",
        "inconclusive",
        "weakly_rejected",
        "rejected",
    ] = "proposed"


class HypothesisState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[Hypothesis] = Field(default_factory=list)
    active_hypothesis_ids: list[str] = Field(default_factory=list)

