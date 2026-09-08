from __future__ import annotations

import pytest

from research_agent.core.transitions import ResearchPhase
from research_agent.storage.project_store import ProjectStore
from research_agent.workflows.runtime import ResearchRuntime


async def test_mock_e2e_reaches_experiment_plan(projects_root) -> None:
    ProjectStore(projects_root).initialize(
        "demo", direction="adaptive reasoning", synthetic=True
    )
    runtime = ResearchRuntime(projects_root, mock=True)

    first = await runtime.run_until_pause("demo")
    assert first.stopped_reason == "human_checkpoint"
    assert first.state.phase == ResearchPhase.TOPIC_SELECTION
    assert first.state.human_checkpoint is not None
    assert all(not paper.verified for paper in first.state.literature.papers)
    chosen_gap = first.state.human_checkpoint.options[0]

    runtime.resume("demo", chosen_gap)
    second = await runtime.run_until_pause("demo")
    assert second.stopped_reason == "human_checkpoint"
    assert second.state.phase == ResearchPhase.RESOURCE_DESIGN
    assert second.state.human_checkpoint.type == "resource_input"

    runtime.resume("demo", "default")
    final = await runtime.run_until_pause("demo")
    assert final.stopped_reason == "experiment_plan_ready"
    assert final.state.phase == ResearchPhase.CORE_EXPERIMENT
    assert final.state.experiments.baselines[0].status == "PASS"
    assert final.state.experiments.experiments[0].status == "planned"
    assert final.state.experiments.experiments[0].synthetic_test_data is True


async def test_mock_cannot_contaminate_real_project(projects_root) -> None:
    ProjectStore(projects_root).initialize("real", direction="real study")
    with pytest.raises(RuntimeError, match="Refusing to mix"):
        await ResearchRuntime(projects_root, mock=True).run_until_pause("real")
