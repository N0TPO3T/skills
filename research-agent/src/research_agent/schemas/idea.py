from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MethodCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    hypothesis_id: str
    name: str
    mechanism: str
    simplest_baseline: str
    differentiating_test: str
    status: Literal["draft", "reviewing", "accepted", "rejected"] = "draft"


class IdeaReviewRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    round: int = Field(ge=1)
    attack_artifact: str
    defense_artifact: str
    verdict: Literal[
        "PROCEED",
        "PROCEED_WITH_MODIFICATIONS",
        "RETURN_TO_LITERATURE",
        "SIMPLIFY",
        "PIVOT",
    ]


class IdeaState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[MethodCandidate] = Field(default_factory=list)
    selected_idea_id: str | None = None
    review_rounds: list[IdeaReviewRecord] = Field(default_factory=list)

