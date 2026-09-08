from __future__ import annotations

import pytest

from research_agent.core.transitions import ResearchPhase
from research_agent.core.workflow import WorkflowEngine, WorkflowPaused
from research_agent.schemas.decision import HumanCheckpoint, ResearchAction
from research_agent.schemas.gap import ResearchGap


def sample_gap(gap_id: str = "GAP-1") -> ResearchGap:
    return ResearchGap(
        id=gap_id,
        title="Gap",
        common_limitation="Existing methods conflate signals",
        root_cause_hypothesis="Conditioning is insufficient",
        why_existing_methods_fail="They pool candidate states",
        missing_capability="Candidate-specific prediction",
        minimum_viable_experiment="Compare pooled and conditioned probes",
        expected_signal="Conditioned probe wins",
        falsification_criterion="No win over pooled baseline",
        novelty_score=0.5,
        feasibility_score=0.8,
        research_value_score=0.7,
        publication_score=0.5,
        risk_score=0.4,
        status="shortlisted",
    )


async def test_checkpoint_pauses_execution(state) -> None:
    state.human_checkpoint = HumanCheckpoint(
        type="topic_selection",
        prompt="Choose",
        options=["GAP-1"],
        resume_phase=ResearchPhase.TOPIC_SELECTION,
    )
    engine = WorkflowEngine()
    action = ResearchAction(
        action="form_idea", reason="selected", priority=1.0
    )
    with pytest.raises(WorkflowPaused):
        await engine.execute(state, action)


def test_checkpoint_resume_works(state) -> None:
    state.phase = ResearchPhase.TOPIC_SELECTION
    state.gaps.candidates = [sample_gap()]
    state.human_checkpoint = HumanCheckpoint(
        type="topic_selection",
        prompt="Choose",
        options=["GAP-1"],
        resume_phase=ResearchPhase.TOPIC_SELECTION,
    )
    resumed = WorkflowEngine().resume_checkpoint(state, "GAP-1")
    assert resumed.human_checkpoint is None
    assert resumed.gaps.selected_gap_id == "GAP-1"
    assert resumed.gaps.candidates[0].status == "selected"

