from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from research_agent.core.transitions import ResearchPhase


class ActionType(str, Enum):
    SEARCH_LITERATURE = "search_literature"
    EXPAND_LITERATURE = "expand_literature"
    MINE_GAPS = "mine_gaps"
    SYNTHESIZE_GAPS = "synthesize_gaps"
    REQUEST_TOPIC_SELECTION = "request_topic_selection"
    FORM_IDEA = "form_idea"
    REVIEW_IDEA = "review_idea"
    REQUEST_RESOURCES = "request_resources"
    DESIGN_EXPERIMENT = "design_experiment"
    REPRODUCE_BASELINE = "reproduce_baseline"
    RUN_EXPERIMENT = "run_experiment"
    ANALYZE_RESULT = "analyze_result"
    DIAGNOSE_FAILURE = "diagnose_failure"
    PIVOT = "pivot"
    EXPAND_EVIDENCE = "expand_evidence"
    AUDIT_PAPER = "audit_paper"
    WRITE_PAPER = "write_paper"
    REVIEW_PAPER = "review_paper"
    COMPLETE_PROJECT = "complete_project"


class ResearchAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: ActionType
    target: str | None = None
    reason: str = Field(min_length=1)
    priority: float = Field(ge=0.0, le=1.0)
    estimated_cost: float | None = Field(default=None, ge=0.0)
    expected_information_gain: float | None = Field(default=None, ge=0.0)


class DecisionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    phase: ResearchPhase
    action: ResearchAction
    outcome: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class HumanCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required: bool = True
    type: Literal["topic_selection", "resource_input", "major_pivot"]
    prompt: str
    options: list[str] = Field(default_factory=list)
    resume_phase: ResearchPhase

