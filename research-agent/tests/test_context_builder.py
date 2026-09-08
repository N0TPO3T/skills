from __future__ import annotations

from research_agent.core.context_builder import ContextBuilder
from research_agent.schemas.experiment import Experiment


def test_context_builder_excludes_unrelated_artifact_content(state) -> None:
    state.experiments.experiments.append(
        Experiment(
            id="EXP-1",
            hypothesis_id="HYP-1",
            research_question="Does it work?",
            expected_outcome="A measurable signal",
            success_criterion="metric > baseline",
            falsification_criterion="metric <= baseline",
            metrics_artifact="artifacts/experiments/EXP-1/metrics.json",
            observation="short summary",
        )
    )
    context = ContextBuilder().for_orchestrator(state)
    rendered = str(context)
    assert "artifacts/experiments/EXP-1/metrics.json" in rendered
    assert "raw stdout" not in rendered
    assert "paper_metadata" not in context


def test_diagnosis_context_is_task_specific(state) -> None:
    context = ContextBuilder().for_diagnosis(state)
    assert "current_experiment" in context
    assert "observed_artifact_paths" in context
    assert "claims" not in context

