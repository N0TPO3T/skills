from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

import pytest
import yaml

from research_agent.core.transitions import ResearchPhase
from research_agent.host_agent import CodexExecBackend
from research_agent.schemas.decision import ResearchAction
from research_agent.schemas.experiment import BaselineReproduction, Experiment
from research_agent.schemas.hypothesis import Hypothesis
from research_agent.schemas.literature import (
    PaperContent,
    PaperMetadata,
    PaperReference,
)
from research_agent.schemas.literature_quality import ProviderCapabilities
from research_agent.schemas.live import (
    ExecutionConfigValue,
    ExecutionRequest,
    ExperimentAnalysisUpdate,
    HostAgentResult,
    HostToolUse,
    LiveStateUpdate,
)
from research_agent.services.live_runtime import LiveResearchRuntime
from research_agent.services.repository_attachment_service import (
    RepositoryAttachmentService,
)
from research_agent.storage.artifact_store import ArtifactStore
from research_agent.storage.project_store import ProjectStore
from research_agent.storage.state_store import StateStore


class FakeHostBackend:
    def __init__(self, *responses: HostAgentResult | Exception) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    async def run(self, instructions, context, tools):
        self.calls.append(
            {"instructions": instructions, "context": context, "tools": tools}
        )
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeArxivProvider:
    name = "arxiv"
    capabilities = ProviderCapabilities(
        search=True,
        metadata_lookup=True,
        abstract=True,
    )

    async def resolve(self, candidate):
        return PaperMetadata(
            paper_id="PAPER-VERIFIED-1",
            title=candidate.raw_title,
            authors=["Researcher"],
            year=2026,
            identifiers=candidate.identifiers,
            abstract="Adaptive allocation changes compute usage under a fixed budget.",
            publication_status="preprint",
            source_records=[candidate.source_url],
            metadata_verified=True,
            verification_confidence=0.95,
        )

    async def fetch_content(self, paper):
        return PaperContent(
            paper_id=paper.paper_id,
            content_type="abstract_only",
            source_url=paper.identifiers.canonical_url,
            parser_name="fake-arxiv",
            raw_text=paper.abstract,
        )

    def safe_configuration(self):
        return {"fixture": True}


def test_host_output_schema_is_strict() -> None:
    def assert_strict(node: object) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                assert node.get("additionalProperties") is False
                assert set(node.get("required", [])) == set(properties)
            assert node.get("additionalProperties") not in (True, {})
            for value in node.values():
                assert_strict(value)
        elif isinstance(node, list):
            for value in node:
                assert_strict(value)

    assert_strict(CodexExecBackend.output_schema())


def test_host_resume_allows_non_git_project(tmp_path: Path) -> None:
    backend = CodexExecBackend(
        cwd=tmp_path,
        artifacts=ArtifactStore(tmp_path),
        command=sys.executable,
    )
    backend.continuation_id = "session-id"
    command = backend._command(
        schema_path=tmp_path / "schema.json",
        output_path=tmp_path / "output.json",
        tools={"read": "read-only"},
    )
    assert command[command.index("resume") + 1 : command.index("session-id")] == [
        "--skip-git-repo-check"
    ]


async def test_important_arxiv_source_enters_existing_literature_layer(
    projects_root: Path, monkeypatch
) -> None:
    state = initialize_real_project(projects_root)
    state.literature.papers.append(
        PaperReference(
            id="PAPER-HOST-1",
            title="Adaptive Compute",
            url="https://arxiv.org/abs/2601.01234",
            identifier="arXiv:2601.01234",
            verified=False,
            provenance="artifacts/live/source.json",
        )
    )
    monkeypatch.setattr(
        "research_agent.services.live_runtime.ArxivLikeProvider",
        lambda **_: FakeArxivProvider(),
    )
    runtime = LiveResearchRuntime(projects_root, backend=FakeHostBackend())
    ingested = await runtime._ingest_pending_sources(
        state, ArtifactStore(projects_root / state.project.id)
    )
    assert ingested == 1
    assert state.literature.paper_metadata[0].metadata_verified is True
    assert state.literature.contents[0].content_verified is True
    assert state.literature.statements
    assert all(
        not paper.id.startswith("PAPER-HOST") for paper in state.literature.papers
    )


def active_hypothesis() -> Hypothesis:
    return Hypothesis(
        id="HYP-1",
        statement="The intervention changes the measured outcome.",
        mechanism="It changes the decision rule.",
        predicted_outcome="Metric increases.",
        falsification_criterion="Metric does not increase.",
        status="active",
    )


def initialize_real_project(projects_root: Path, project_id: str = "live_demo"):
    return ProjectStore(projects_root).initialize(
        project_id, direction="efficient test-time reasoning"
    )


async def test_host_receives_phase_skill_context_and_live_tool_bindings(
    projects_root: Path,
) -> None:
    state = initialize_real_project(projects_root)
    state.phase = ResearchPhase.GAP_MINING
    StateStore(projects_root).save(state)
    backend = FakeHostBackend(
        HostAgentResult(status="blocked", summary="Need verified literature")
    )
    runtime = LiveResearchRuntime(projects_root, backend=backend)
    _, response, _, _ = await runtime.run_one_phase(state)
    assert response.status == "blocked"
    call = backend.calls[0]
    assert "skill-resource: references/scientific_rules.md" in call["instructions"]
    assert "skill-resource: prompts/gap_mining.md" in call["instructions"]
    assert call["context"]["phase"] == "gap_mining"
    assert call["context"]["allowed_actions"] == [
        "expand_literature",
        "synthesize_gaps",
    ]
    assert call["context"]["allowed_state_update_fields"] == [
        "gaps",
        "important_sources",
        "search_queries",
    ]
    assert call["context"]["repository_attachment_allowed"] is False
    assert set(call["tools"]) == {"search", "read", "filesystem"}


async def test_host_cannot_report_unexposed_tool_capability(
    projects_root: Path,
) -> None:
    state = initialize_real_project(projects_root)
    response = HostAgentResult(
        status="blocked",
        summary="Tried an unavailable capability",
        tool_uses=[
            HostToolUse(tool="shell", purpose="run command", outcome="not accepted")
        ],
    )
    with pytest.raises(PermissionError, match="unavailable tool"):
        await LiveResearchRuntime(
            projects_root, backend=FakeHostBackend(response)
        ).run_one_phase(state)


async def test_host_cannot_attach_repository_during_research_phase(
    projects_root: Path,
) -> None:
    state = initialize_real_project(projects_root)
    response = HostAgentResult(
        status="blocked",
        summary="Tried to attach too early",
        repository_path=str(projects_root),
    )
    with pytest.raises(PermissionError, match="unavailable during bootstrap"):
        await LiveResearchRuntime(
            projects_root, backend=FakeHostBackend(response)
        ).run_one_phase(state)


async def test_live_mode_rejects_mock_project(projects_root: Path) -> None:
    ProjectStore(projects_root).initialize("mock_demo", synthetic=True)
    runtime = LiveResearchRuntime(
        projects_root,
        backend=FakeHostBackend(
            HostAgentResult(status="blocked", summary="not called")
        ),
    )
    with pytest.raises(ValueError, match="synthetic mock"):
        await runtime.run_until_pause("mock_demo")


async def test_host_cannot_assert_unexecuted_result(projects_root: Path) -> None:
    state = initialize_real_project(projects_root)
    state.phase = ResearchPhase.CORE_EXPERIMENT
    state.hypotheses.items.append(active_hypothesis())
    state.hypotheses.active_hypothesis_ids = ["HYP-1"]
    fake_result = Experiment(
        id="EXP-FAKE",
        hypothesis_id="HYP-1",
        research_question="Did it run?",
        expected_outcome="yes",
        success_criterion="metric > 0",
        falsification_criterion="metric <= 0",
        status="completed",
        execution_verified=True,
        execution_artifact="artifacts/fake.json",
        observation="invented result",
    )
    backend = FakeHostBackend(
        HostAgentResult(
            status="completed",
            summary="claimed execution",
            state_update=LiveStateUpdate(experiments=[fake_result]),
            proposed_action=ResearchAction(
                action="expand_evidence", reason="claimed success", priority=1.0
            ),
        )
    )
    with pytest.raises(ValueError, match="cannot assert execution"):
        await LiveResearchRuntime(
            projects_root, backend=backend
        ).run_one_phase(state)


async def test_execution_requires_both_shell_authority_gates(
    projects_root: Path, tmp_path: Path
) -> None:
    state = initialize_real_project(projects_root)
    repository = tmp_path / "repository"
    repository.mkdir()
    RepositoryAttachmentService(projects_root / state.project.id).attach(repository)
    state.phase = ResearchPhase.CORE_EXPERIMENT
    state.hypotheses.items.append(active_hypothesis())
    state.hypotheses.active_hypothesis_ids = ["HYP-1"]
    state.experiments.experiments.append(
        Experiment(
            id="EXP-LOCKED",
            hypothesis_id="HYP-1",
            research_question="Should this execute?",
            expected_outcome="No execution without authorization.",
            success_criterion="No process starts.",
            falsification_criterion="A process starts.",
            status="approved",
        )
    )
    response = HostAgentResult(
        status="completed",
        summary="Request execution without authority",
        execution_request=ExecutionRequest(
            experiment_id="EXP-LOCKED", command="echo must-not-run"
        ),
    )
    with pytest.raises(PermissionError, match="requires project execution"):
        await LiveResearchRuntime(
            projects_root, backend=FakeHostBackend(response)
        ).run_one_phase(state)


async def test_runner_artifact_flows_back_to_host_analysis(
    projects_root: Path, tmp_path: Path
) -> None:
    state = initialize_real_project(projects_root)
    repository = tmp_path / "repository"
    repository.mkdir()
    RepositoryAttachmentService(projects_root / state.project.id).attach(repository)
    config_path = projects_root / state.project.id / "project.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["execution"] = {"allow_shell": True, "timeout_seconds": 30}
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    state.phase = ResearchPhase.CORE_EXPERIMENT
    state.constraints.shell_execution_allowed = True
    state.hypotheses.items.append(active_hypothesis())
    state.hypotheses.active_hypothesis_ids = ["HYP-1"]
    state.experiments.baselines.append(
        BaselineReproduction(id="BASE-1", name="Toy baseline", status="PASS")
    )
    state.experiments.experiments.append(
        Experiment(
            id="EXP-001",
            hypothesis_id="HYP-1",
            research_question="Does the toy metric equal one?",
            baseline_ids=["BASE-1"],
            expected_outcome="metric is one",
            success_criterion="metric == 1",
            falsification_criterion="metric != 1",
            status="approved",
        )
    )
    metrics_code = "import json;open('metrics.json','w').write(json.dumps({'metric':1}))"
    command = f"{shlex.quote(sys.executable)} -c {shlex.quote(metrics_code)}"
    execute = HostAgentResult(
        status="completed",
        summary="Execute the approved toy experiment",
        execution_request=ExecutionRequest(
            experiment_id="EXP-001",
            command=command,
            config=[ExecutionConfigValue(key="fixture", value=True)],
            metrics_path="metrics.json",
        ),
    )
    analyze = HostAgentResult(
        status="completed",
        summary="Observed the runner-produced metric",
        state_update=LiveStateUpdate(
            experiment_analyses=[
                ExperimentAnalysisUpdate(
                    experiment_id="EXP-001",
                    observation="Runner metric equals one.",
                    interpretation="The toy success criterion is met.",
                    confounders=["Toy execution only"],
                )
            ]
        ),
        proposed_action=ResearchAction(
            action="expand_evidence",
            reason="Plan a second decision-relevant test",
            priority=0.8,
        ),
    )
    backend = FakeHostBackend(execute, analyze)
    updated, response, turns, latest = await LiveResearchRuntime(
        projects_root, backend=backend
    ).run_one_phase(state)
    experiment = updated.experiments.experiments[0]
    assert response is analyze
    assert updated.phase == ResearchPhase.EVIDENCE_EXPANSION
    assert experiment.execution_verified is True
    assert experiment.execution_artifact
    assert experiment.metrics_artifact
    assert experiment.observation == "Runner metric equals one."
    assert latest["experiment_id"] == "EXP-001"
    assert backend.calls[1]["context"]["latest_execution"]["metadata_artifact"]
    assert len(turns) == 2
    metrics = json.loads(
        (projects_root / state.project.id / experiment.metrics_artifact).read_text()
    )
    assert metrics == {"metric": 1}


async def test_host_failure_is_saved_and_surfaced(projects_root: Path) -> None:
    state = initialize_real_project(projects_root)
    runtime = LiveResearchRuntime(
        projects_root, backend=FakeHostBackend(RuntimeError("tool unavailable"))
    )
    with pytest.raises(RuntimeError, match="details saved"):
        await runtime.run_one_phase(state)
    failure = projects_root / state.project.id / "artifacts/live/latest_failure.json"
    assert failure.is_file()
    assert "tool unavailable" in failure.read_text(encoding="utf-8")


async def test_only_major_pivot_creates_checkpoint_c(projects_root: Path) -> None:
    state = initialize_real_project(projects_root)
    state.phase = ResearchPhase.DIAGNOSIS
    response = HostAgentResult(
        status="completed",
        summary="The central hypothesis should be abandoned.",
        proposed_action=ResearchAction(
            action="pivot", reason="hypothesis rejected", priority=1.0
        ),
        major_pivot=True,
        pivot_options=["approve", "stop"],
    )
    updated, _, _, _ = await LiveResearchRuntime(
        projects_root, backend=FakeHostBackend(response)
    ).run_one_phase(state)
    assert updated.phase == ResearchPhase.PIVOT
    assert updated.human_checkpoint
    assert updated.human_checkpoint.type == "major_pivot"


def test_live_dry_run_does_not_call_host(projects_root: Path) -> None:
    initialize_real_project(projects_root)
    backend = FakeHostBackend(RuntimeError("must not run"))
    result = LiveResearchRuntime(projects_root, backend=backend).dry_run("live_demo")
    assert result["will_execute"] is False
    assert result["phase"] == "bootstrap"
    assert backend.calls == []
