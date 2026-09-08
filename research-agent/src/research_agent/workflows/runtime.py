from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from research_agent.core.orchestrator import validate_action
from research_agent.core.transitions import ResearchPhase
from research_agent.core.workflow import WorkflowEngine
from research_agent.schemas.decision import ActionType, ResearchAction
from research_agent.schemas.state import ResearchState
from research_agent.storage.artifact_store import ArtifactStore
from research_agent.storage.state_store import StateStore
from research_agent.workflows.discovery import DiscoveryWorkflow
from research_agent.workflows.experiment import ExperimentWorkflow
from research_agent.workflows.idea import IdeaWorkflow
from research_agent.workflows.paper import PaperWorkflow


@dataclass(frozen=True)
class WorkflowRunResult:
    state: ResearchState
    stopped_reason: str


class DeterministicMockOrchestrator:
    """Phase-aware decisions for CI; all outputs are synthetic fixtures."""

    ACTIONS: dict[ResearchPhase, ActionType] = {
        ResearchPhase.BOOTSTRAP: ActionType.SEARCH_LITERATURE,
        ResearchPhase.HORIZON_SCAN: ActionType.MINE_GAPS,
        ResearchPhase.GAP_MINING: ActionType.SYNTHESIZE_GAPS,
        ResearchPhase.GAP_SYNTHESIS: ActionType.REQUEST_TOPIC_SELECTION,
        ResearchPhase.TOPIC_SELECTION: ActionType.FORM_IDEA,
        ResearchPhase.IDEA_FORMATION: ActionType.REVIEW_IDEA,
        ResearchPhase.IDEA_REVIEW: ActionType.REQUEST_RESOURCES,
        ResearchPhase.RESOURCE_DESIGN: ActionType.REPRODUCE_BASELINE,
        ResearchPhase.BASELINE_REPRODUCTION: ActionType.DESIGN_EXPERIMENT,
    }

    async def decide(self, state: ResearchState) -> ResearchAction:
        action_type = self.ACTIONS.get(state.phase)
        if action_type is None:
            raise StopAsyncIteration
        action = ResearchAction(
            action=action_type,
            target=state.project.research_direction or state.project.id,
            reason="synthetic_test_data deterministic workflow decision",
            priority=1.0,
            estimated_cost=0.0,
            expected_information_gain=1.0,
        )
        validate_action(state.phase.value, action)
        return action


class ResearchRuntime:
    def __init__(self, projects_root: Path, *, mock: bool = False) -> None:
        self.projects_root = projects_root.resolve()
        self.state_store = StateStore(self.projects_root)
        self.mock = mock

    def _engine(self, project_id: str) -> WorkflowEngine:
        artifacts = ArtifactStore(self.projects_root / project_id)
        discovery = DiscoveryWorkflow(artifacts, mock=self.mock)
        idea = IdeaWorkflow(artifacts, mock=self.mock)
        experiment = ExperimentWorkflow(artifacts, mock=self.mock)
        paper = PaperWorkflow(artifacts)
        return WorkflowEngine(
            {
                ActionType.SEARCH_LITERATURE.value: discovery.search_literature,
                ActionType.EXPAND_LITERATURE.value: discovery.search_literature,
                ActionType.MINE_GAPS.value: discovery.mine_gaps,
                ActionType.SYNTHESIZE_GAPS.value: discovery.synthesize_gaps,
                ActionType.REQUEST_TOPIC_SELECTION.value: discovery.request_topic_selection,
                ActionType.FORM_IDEA.value: idea.form_idea,
                ActionType.REVIEW_IDEA.value: idea.review_idea,
                ActionType.REQUEST_RESOURCES.value: idea.request_resources,
                ActionType.REPRODUCE_BASELINE.value: experiment.reproduce_baseline,
                ActionType.DESIGN_EXPERIMENT.value: experiment.design_experiment,
                ActionType.RUN_EXPERIMENT.value: experiment.run_experiment,
                ActionType.ANALYZE_RESULT.value: experiment.analyze_result,
                ActionType.DIAGNOSE_FAILURE.value: experiment.diagnose_failure,
                ActionType.PIVOT.value: experiment.pivot,
                ActionType.EXPAND_EVIDENCE.value: experiment.expand_evidence,
                ActionType.AUDIT_PAPER.value: paper.audit_paper,
                ActionType.WRITE_PAPER.value: paper.write_paper,
                ActionType.REVIEW_PAPER.value: paper.review_paper,
                ActionType.COMPLETE_PROJECT.value: paper.complete_project,
            },
            artifacts=artifacts,
        )

    async def run_until_pause(self, project_id: str) -> WorkflowRunResult:
        if not self.mock:
            raise RuntimeError(
                "Live workflow composition is not configured. Use --mock for the offline MVP."
            )
        state = self.state_store.load(project_id)
        if self.mock and not state.project.synthetic_test_data:
            raise RuntimeError(
                "Refusing to mix mock fixtures into a non-mock project; initialize a separate project with --mock."
            )
        if state.human_checkpoint and state.human_checkpoint.required:
            return WorkflowRunResult(state, "human_checkpoint")
        engine = self._engine(project_id)
        orchestrator = DeterministicMockOrchestrator()
        while True:
            if (
                state.phase == ResearchPhase.CORE_EXPERIMENT
                and state.experiments.experiments
                and state.experiments.experiments[-1].status == "planned"
            ):
                return WorkflowRunResult(state, "experiment_plan_ready")
            try:
                action = await orchestrator.decide(state)
            except StopAsyncIteration:
                return WorkflowRunResult(state, "no_mock_action")
            state = await engine.execute(state, action)
            self.state_store.save(state)
            if state.human_checkpoint and state.human_checkpoint.required:
                return WorkflowRunResult(state, "human_checkpoint")

    def resume(self, project_id: str, response: str) -> ResearchState:
        state = self.state_store.load(project_id)
        state = self._engine(project_id).resume_checkpoint(state, response)
        self.state_store.save(state)
        return state
