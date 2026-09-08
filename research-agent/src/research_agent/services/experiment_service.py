from __future__ import annotations

from research_agent.schemas.execution import ExperimentExecutionResult
from research_agent.schemas.state import ResearchState


def baseline_gate_passes(state: ResearchState) -> bool:
    return any(item.status == "PASS" for item in state.experiments.baselines)


def record_runner_execution(
    state: ResearchState, result: ExperimentExecutionResult
) -> None:
    experiment = next(
        (
            item
            for item in state.experiments.experiments
            if item.id == result.experiment_id
        ),
        None,
    )
    if experiment is None:
        raise ValueError(
            f"Runner result does not match a planned experiment: {result.experiment_id}"
        )
    experiment.execution_artifact = result.metadata_artifact
    experiment.metrics_artifact = result.metrics_artifact
    experiment.status = (
        "completed"
        if result.return_code == 0 and not result.timed_out
        else "failed"
    )
    experiment.execution_verified = experiment.status == "completed"
