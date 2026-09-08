from __future__ import annotations

import json
import shlex
import sys

import pytest

from research_agent.schemas.experiment import Experiment
from research_agent.schemas.project import ProjectInfo
from research_agent.schemas.state import ResearchState
from research_agent.services.experiment_runner import ExperimentRunner
from research_agent.services.experiment_service import record_runner_execution
from research_agent.storage.artifact_store import ArtifactStore


async def test_experiment_runner_is_disabled_by_default(tmp_path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    runner = ExperimentRunner(ArtifactStore(project_dir))
    with pytest.raises(PermissionError):
        await runner.run_shell_experiment("true", project_dir, {})


async def test_experiment_runner_captures_and_redacts(tmp_path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    runner = ExperimentRunner(
        ArtifactStore(project_dir), allow_shell=True, timeout_seconds=10
    )
    command = f"{shlex.quote(sys.executable)} -c \"print('measured')\""
    result = await runner.run_shell_experiment(
        command, project_dir, {"RESEARCH_SECRET_TOKEN": "do-not-store"}
    )
    assert result.return_code == 0
    assert "measured" in (project_dir / result.stdout_artifact).read_text()
    environment = json.loads((project_dir / result.environment_artifact).read_text())
    assert environment["RESEARCH_SECRET_TOKEN"] == "[REDACTED]"
    assert result.git_commit is None
    assert result.config_artifact
    assert result.git_diff_artifact
    assert result.runtime_seconds is not None
    assert result.repository == str(project_dir.resolve())


async def test_runner_result_binds_to_planned_experiment(tmp_path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    state = ResearchState(project=ProjectInfo(id="demo", name="Demo"))
    state.experiments.experiments.append(
        Experiment(
            id="EXP-PLANNED",
            hypothesis_id="HYP-1",
            research_question="Does the command complete?",
            expected_outcome="zero exit",
            success_criterion="return code zero",
            falsification_criterion="non-zero return",
            status="approved",
        )
    )
    runner = ExperimentRunner(ArtifactStore(project_dir), allow_shell=True)
    result = await runner.run_shell_experiment(
        "true", project_dir, {}, experiment_id="EXP-PLANNED"
    )
    record_runner_execution(state, result)
    experiment = state.experiments.experiments[0]
    assert experiment.status == "completed"
    assert experiment.execution_verified is True
    assert experiment.execution_artifact == result.metadata_artifact


async def test_runner_rejects_non_json_metrics(tmp_path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    metrics_path = project_dir / "metrics.json"
    metrics_path.write_text("not-json", encoding="utf-8")
    runner = ExperimentRunner(ArtifactStore(project_dir), allow_shell=True)
    with pytest.raises(ValueError, match="valid JSON"):
        await runner.run_shell_experiment(
            "true", project_dir, {}, metrics_path="metrics.json"
        )
