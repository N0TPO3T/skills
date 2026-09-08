from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from research_agent.core.context_builder import ContextBuilder
from research_agent.core.ids import new_id, stable_id
from research_agent.core.orchestrator import ALLOWED_ACTIONS, validate_action
from research_agent.core.transitions import ResearchPhase, require_valid_transition
from research_agent.host_agent import AgentBackend, CodexExecBackend
from research_agent.literature.providers import (
    ArxivLikeProvider,
    GenericWebPaperProvider,
)
from research_agent.schemas.decision import (
    DecisionRecord,
    HumanCheckpoint,
    ResearchAction,
)
from research_agent.schemas.idea import IdeaReviewRecord
from research_agent.schemas.literature import (
    LiteratureSearchQuery,
    PaperCandidate,
    PaperIdentifier,
    PaperReference,
)
from research_agent.schemas.live import (
    HostAgentResult,
    LiveStateUpdate,
    PaperReviewDraft,
)
from research_agent.schemas.state import ResearchState
from research_agent.services.experiment_runner import ExperimentRunner
from research_agent.services.experiment_service import record_runner_execution
from research_agent.services.literature_service import (
    LiteratureService,
    LiteratureSettings,
)
from research_agent.services.paper_service import PaperService
from research_agent.services.repository_attachment_service import (
    RepositoryAttachmentService,
)
from research_agent.skill_context import SkillContextLoader
from research_agent.storage.artifact_store import ArtifactStore
from research_agent.storage.state_store import StateStore
from research_agent.workflows.discovery import DiscoveryWorkflow
from research_agent.workflows.idea import IdeaWorkflow

LIVE_ACTION_TARGETS: dict[tuple[ResearchPhase, str], ResearchPhase] = {
    (ResearchPhase.BOOTSTRAP, "search_literature"): ResearchPhase.HORIZON_SCAN,
    (ResearchPhase.HORIZON_SCAN, "search_literature"): ResearchPhase.HORIZON_SCAN,
    (ResearchPhase.HORIZON_SCAN, "mine_gaps"): ResearchPhase.GAP_MINING,
    (ResearchPhase.GAP_MINING, "expand_literature"): ResearchPhase.HORIZON_SCAN,
    (ResearchPhase.GAP_MINING, "synthesize_gaps"): ResearchPhase.GAP_SYNTHESIS,
    (ResearchPhase.GAP_SYNTHESIS, "expand_literature"): ResearchPhase.HORIZON_SCAN,
    (ResearchPhase.TOPIC_SELECTION, "form_idea"): ResearchPhase.IDEA_FORMATION,
    (ResearchPhase.IDEA_FORMATION, "expand_literature"): ResearchPhase.HORIZON_SCAN,
    (ResearchPhase.IDEA_FORMATION, "review_idea"): ResearchPhase.IDEA_REVIEW,
    (ResearchPhase.IDEA_REVIEW, "form_idea"): ResearchPhase.IDEA_FORMATION,
    (ResearchPhase.IDEA_REVIEW, "expand_literature"): ResearchPhase.HORIZON_SCAN,
    (ResearchPhase.RESOURCE_DESIGN, "reproduce_baseline"): ResearchPhase.BASELINE_REPRODUCTION,
    (ResearchPhase.BASELINE_REPRODUCTION, "request_resources"): ResearchPhase.RESOURCE_DESIGN,
    (ResearchPhase.BASELINE_REPRODUCTION, "design_experiment"): ResearchPhase.CORE_EXPERIMENT,
    (ResearchPhase.BASELINE_REPRODUCTION, "diagnose_failure"): ResearchPhase.DIAGNOSIS,
    (ResearchPhase.CORE_EXPERIMENT, "run_experiment"): ResearchPhase.CORE_EXPERIMENT,
    (ResearchPhase.CORE_EXPERIMENT, "analyze_result"): ResearchPhase.CORE_EXPERIMENT,
    (ResearchPhase.CORE_EXPERIMENT, "diagnose_failure"): ResearchPhase.DIAGNOSIS,
    (ResearchPhase.CORE_EXPERIMENT, "expand_evidence"): ResearchPhase.EVIDENCE_EXPANSION,
    (ResearchPhase.DIAGNOSIS, "run_experiment"): ResearchPhase.CORE_EXPERIMENT,
    (ResearchPhase.DIAGNOSIS, "pivot"): ResearchPhase.PIVOT,
    (ResearchPhase.PIVOT, "form_idea"): ResearchPhase.IDEA_FORMATION,
    (ResearchPhase.PIVOT, "synthesize_gaps"): ResearchPhase.GAP_SYNTHESIS,
    (ResearchPhase.PIVOT, "run_experiment"): ResearchPhase.CORE_EXPERIMENT,
    (ResearchPhase.EVIDENCE_EXPANSION, "run_experiment"): ResearchPhase.CORE_EXPERIMENT,
    (ResearchPhase.EVIDENCE_EXPANSION, "audit_paper"): ResearchPhase.PAPER_AUDIT,
    (ResearchPhase.PAPER_AUDIT, "run_experiment"): ResearchPhase.CORE_EXPERIMENT,
    (ResearchPhase.PAPER_AUDIT, "write_paper"): ResearchPhase.PAPER_ASSEMBLY,
    (ResearchPhase.PAPER_ASSEMBLY, "review_paper"): ResearchPhase.PAPER_REVIEW,
    (ResearchPhase.PAPER_REVIEW, "run_experiment"): ResearchPhase.CORE_EXPERIMENT,
    (ResearchPhase.PAPER_REVIEW, "write_paper"): ResearchPhase.PAPER_ASSEMBLY,
    (ResearchPhase.PAPER_REVIEW, "complete_project"): ResearchPhase.COMPLETE,
}


PHASE_UPDATE_FIELDS: dict[ResearchPhase, frozenset[str]] = {
    ResearchPhase.BOOTSTRAP: frozenset({"search_queries", "important_sources"}),
    ResearchPhase.HORIZON_SCAN: frozenset({"search_queries", "important_sources"}),
    ResearchPhase.GAP_MINING: frozenset({"search_queries", "important_sources", "gaps"}),
    ResearchPhase.GAP_SYNTHESIS: frozenset({"search_queries", "important_sources", "gaps"}),
    ResearchPhase.TOPIC_SELECTION: frozenset(),
    ResearchPhase.IDEA_FORMATION: frozenset({"hypotheses", "ideas", "selected_idea_id"}),
    ResearchPhase.IDEA_REVIEW: frozenset({"ideas", "selected_idea_id", "idea_review"}),
    ResearchPhase.RESOURCE_DESIGN: frozenset({"baselines", "experiments"}),
    ResearchPhase.BASELINE_REPRODUCTION: frozenset(
        {"baselines", "experiments", "experiment_analyses", "important_sources"}
    ),
    ResearchPhase.CORE_EXPERIMENT: frozenset(
        {"hypotheses", "experiments", "experiment_analyses"}
    ),
    ResearchPhase.DIAGNOSIS: frozenset(
        {"hypotheses", "experiments", "experiment_analyses"}
    ),
    ResearchPhase.PIVOT: frozenset({"gaps", "hypotheses", "ideas", "selected_idea_id"}),
    ResearchPhase.EVIDENCE_EXPANSION: frozenset(
        {"hypotheses", "experiments", "experiment_analyses"}
    ),
    ResearchPhase.PAPER_AUDIT: frozenset(),
    ResearchPhase.PAPER_ASSEMBLY: frozenset({"paper_draft"}),
    ResearchPhase.PAPER_REVIEW: frozenset({"paper_review"}),
    ResearchPhase.COMPLETE: frozenset(),
}


@dataclass
class LiveRunResult:
    state: ResearchState
    stopped_reason: str
    host_turn_artifacts: list[str] = field(default_factory=list)


class LiveResearchRuntime:
    def __init__(
        self,
        projects_root: Path,
        *,
        backend: AgentBackend | None = None,
        max_turns: int = 12,
    ) -> None:
        self.projects_root = projects_root.resolve()
        self.state_store = StateStore(self.projects_root)
        self.backend = backend
        self._managed_backend: CodexExecBackend | None = None
        self.max_turns = max_turns
        self.contexts = ContextBuilder()
        self.skill_contexts = SkillContextLoader()

    async def run_until_pause(self, project_id: str) -> LiveRunResult:
        state = self.state_store.load(project_id)
        if state.project.synthetic_test_data:
            raise ValueError("Live mode cannot run a synthetic mock project")
        if state.human_checkpoint and state.human_checkpoint.required:
            return LiveRunResult(state, "human_checkpoint")
        artifacts: list[str] = []
        latest_execution: dict[str, object] | None = None
        for _ in range(self.max_turns):
            state, response, turn_paths, latest_execution = await self.run_one_phase(
                state,
                latest_execution=latest_execution,
            )
            artifacts.extend(turn_paths)
            self.state_store.save(state)
            if response.status != "completed":
                return LiveRunResult(state, f"host_{response.status}", artifacts)
            if state.human_checkpoint and state.human_checkpoint.required:
                return LiveRunResult(state, "human_checkpoint", artifacts)
            if state.phase == ResearchPhase.COMPLETE:
                return LiveRunResult(state, "complete", artifacts)
        return LiveRunResult(state, "max_live_turns", artifacts)

    async def run_one_phase(
        self,
        state: ResearchState,
        *,
        latest_execution: dict[str, object] | None = None,
    ) -> tuple[
        ResearchState,
        HostAgentResult,
        list[str],
        dict[str, object] | None,
    ]:
        project_dir = self.projects_root / state.project.id
        artifacts = ArtifactStore(project_dir)
        repository_service = RepositoryAttachmentService(project_dir)
        repository = repository_service.load()
        execution_allowed = self._execution_allowed(state, repository_service)
        if state.phase in {
            ResearchPhase.BOOTSTRAP,
            ResearchPhase.HORIZON_SCAN,
            ResearchPhase.GAP_MINING,
            ResearchPhase.GAP_SYNTHESIS,
        } and await self._ingest_pending_sources(state, artifacts):
            self.state_store.save(state)
        backend = self._host_backend(
            cwd=Path(repository["path"]) if repository else project_dir,
            artifacts=artifacts,
        )
        tools = self.available_tools(state.phase, execution_allowed)
        context = self._phase_context(
            state,
            project_dir=project_dir,
            repository=repository,
            execution_allowed=execution_allowed,
            latest_execution=latest_execution,
        )
        instructions = self.skill_contexts.load_for_state(state).content
        turn_paths: list[str] = []
        try:
            response = await backend.run(instructions, context, tools)
        except Exception as exc:
            failure_path = artifacts.write_json(
                "artifacts/live/latest_failure.json",
                {
                    "phase": state.phase.value,
                    "error_type": type(exc).__name__,
                    "message": str(exc)[:2000],
                },
            )
            raise RuntimeError(
                f"Host agent failed; details saved to {failure_path}: {exc}"
            ) from exc
        self._validate_tool_uses(response, tools)
        if response.repository_path and state.phase not in {
            ResearchPhase.RESOURCE_DESIGN,
            ResearchPhase.BASELINE_REPRODUCTION,
            ResearchPhase.CORE_EXPERIMENT,
            ResearchPhase.DIAGNOSIS,
        }:
            raise PermissionError(
                f"Repository attachment is unavailable during {state.phase.value}"
            )
        turn_paths.append(self._record_turn(artifacts, state, response))
        self._apply_update(state, response.state_update, artifacts)
        if response.repository_path:
            repository = repository_service.attach(Path(response.repository_path))
            backend = self._host_backend(
                cwd=Path(repository["path"]), artifacts=artifacts
            )
        if response.execution_request is not None:
            if not execution_allowed:
                raise PermissionError(
                    "Execution requires project execution.allow_shell=true and "
                    "ResourceConstraints.shell_execution_allowed=true"
                )
            if repository is None:
                raise ValueError("Attach a repository before executing an experiment")
            experiment = next(
                (
                    item
                    for item in state.experiments.experiments
                    if item.id == response.execution_request.experiment_id
                ),
                None,
            )
            if experiment is None or experiment.status != "approved":
                raise ValueError(
                    "Execution request must reference an approved experiment"
                )
            runner_result = await ExperimentRunner(
                artifacts,
                allow_shell=True,
                timeout_seconds=float(
                    repository_service.execution_configuration().get(
                        "timeout_seconds", 3600
                    )
                ),
            ).run_shell_experiment(
                response.execution_request.command,
                Path(repository["path"]),
                {
                    item.key: item.value
                    for item in response.execution_request.environment
                },
                experiment_id=response.execution_request.experiment_id,
                config={
                    item.key: item.value
                    for item in response.execution_request.config
                },
                metrics_path=response.execution_request.metrics_path,
            )
            record_runner_execution(state, runner_result)
            latest_execution = runner_result.model_dump(mode="json")
            self.state_store.save(state)
            analysis_context = self._phase_context(
                state,
                project_dir=project_dir,
                repository=repository,
                execution_allowed=execution_allowed,
                latest_execution=latest_execution,
            )
            try:
                response = await backend.run(instructions, analysis_context, tools)
            except Exception as exc:
                failure_path = artifacts.write_json(
                    "artifacts/live/latest_failure.json",
                    {
                        "phase": state.phase.value,
                        "stage": "result_analysis",
                        "error_type": type(exc).__name__,
                        "message": str(exc)[:2000],
                        "execution_artifact": runner_result.metadata_artifact,
                    },
                )
                raise RuntimeError(
                    f"Result analysis failed; details saved to {failure_path}: {exc}"
                ) from exc
            self._validate_tool_uses(response, tools)
            turn_paths.append(self._record_turn(artifacts, state, response))
            self._apply_update(state, response.state_update, artifacts)
        if response.status == "completed":
            await self._advance(state, response, artifacts, turn_paths[-1])
        return state, response, turn_paths, latest_execution

    def dry_run(self, project_id: str) -> dict[str, object]:
        state = self.state_store.load(project_id)
        if state.project.synthetic_test_data:
            raise ValueError("Live dry-run cannot target a synthetic mock project")
        project_dir = self.projects_root / project_id
        repository_service = RepositoryAttachmentService(project_dir)
        repository = repository_service.load()
        execution_allowed = self._execution_allowed(state, repository_service)
        skill = self.skill_contexts.load_for_state(state)
        return {
            "project_id": project_id,
            "mode": "live_dry_run",
            "phase": state.phase.value,
            "loaded_skill_files": list(skill.loaded_files),
            "relevant_context": self._phase_context(
                state,
                project_dir=project_dir,
                repository=repository,
                execution_allowed=execution_allowed,
                latest_execution=None,
            ),
            "available_tools": self.available_tools(
                state.phase, execution_allowed
            ),
            "planned_high_level_action": self._default_action(state.phase),
            "will_execute": False,
        }

    def doctor(self, project_id: str) -> dict[str, object]:
        state = self.state_store.load(project_id)
        project_dir = self.projects_root / project_id
        repository_service = RepositoryAttachmentService(project_dir)
        repository = repository_service.load()
        host_command = os.environ.get("RESEARCH_AGENT_HOST_COMMAND", "codex")
        executable = shutil.which(host_command)
        login = self._host_login_status(executable)
        coverage = self.skill_contexts.coverage_paths()
        resources_found = all(
            (self.skill_contexts.root / path).is_file()
            for path in coverage.values()
        )
        codex_root = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
        host_skill_path = codex_root / "skills" / "research-agent"
        execution_config = repository_service.execution_configuration()
        return {
            "project_id": project_id,
            "state_valid": True,
            "skill_found": (self.skill_contexts.root / "SKILL.md").is_file(),
            "skill_resources_found": resources_found,
            "host_skill": {
                "path": str(host_skill_path),
                "discovered": (host_skill_path / "SKILL.md").is_file(),
            },
            "host_agent": {
                "command": executable,
                "available": executable is not None,
                "llm_available": login[0],
                "status": login[1],
            },
            "capabilities": {
                "search": executable is not None,
                "read": True,
                "filesystem": os.access(project_dir, os.R_OK),
                "shell": self._execution_allowed(state, repository_service),
                "git": shutil.which("git") is not None,
            },
            "execution": {
                "config_allow_shell": bool(execution_config.get("allow_shell", False)),
                "project_allow_shell": state.constraints.shell_execution_allowed,
            },
            "repository": repository,
        }

    @staticmethod
    def available_tools(
        phase: ResearchPhase, execution_allowed: bool
    ) -> dict[str, str]:
        tools = {
            "read": "Read project files, verified artifacts, papers, and web pages.",
            "filesystem": "Inspect the attached project workspace; typed updates are returned to runtime.",
        }
        if phase in {
            ResearchPhase.BOOTSTRAP,
            ResearchPhase.HORIZON_SCAN,
            ResearchPhase.GAP_MINING,
            ResearchPhase.GAP_SYNTHESIS,
            ResearchPhase.IDEA_FORMATION,
            ResearchPhase.IDEA_REVIEW,
            ResearchPhase.BASELINE_REPRODUCTION,
            ResearchPhase.DIAGNOSIS,
        }:
            tools["search"] = "Use live web/paper search for decision-relevant evidence."
        if phase in {
            ResearchPhase.BASELINE_REPRODUCTION,
            ResearchPhase.CORE_EXPERIMENT,
            ResearchPhase.DIAGNOSIS,
        }:
            tools["git"] = "Inspect repository identity, history, status, and diffs."
            if execution_allowed:
                tools["code"] = "Modify code/config inside the attached repository."
                tools["shell"] = "Run authorized tests and experiment commands through the runner."
        return tools

    def _phase_context(
        self,
        state: ResearchState,
        *,
        project_dir: Path,
        repository: dict[str, str | None] | None,
        execution_allowed: bool,
        latest_execution: dict[str, object] | None,
    ) -> dict[str, object]:
        if state.phase in {ResearchPhase.BOOTSTRAP, ResearchPhase.HORIZON_SCAN}:
            context = self.contexts.for_literature(state)
        elif state.phase in {ResearchPhase.GAP_MINING, ResearchPhase.GAP_SYNTHESIS}:
            context = self.contexts.for_gap_mining(state)
        elif state.phase in {
            ResearchPhase.IDEA_FORMATION,
            ResearchPhase.IDEA_REVIEW,
        }:
            context = self.contexts.for_idea_review(state)
        elif state.phase == ResearchPhase.DIAGNOSIS:
            context = self.contexts.for_diagnosis(state)
        elif state.phase in {
            ResearchPhase.RESOURCE_DESIGN,
            ResearchPhase.BASELINE_REPRODUCTION,
            ResearchPhase.CORE_EXPERIMENT,
            ResearchPhase.PIVOT,
            ResearchPhase.EVIDENCE_EXPANSION,
        }:
            context = self.contexts.for_experiment(state)
        elif state.phase in {
            ResearchPhase.PAPER_AUDIT,
            ResearchPhase.PAPER_ASSEMBLY,
            ResearchPhase.PAPER_REVIEW,
            ResearchPhase.COMPLETE,
        }:
            context = self.contexts.for_paper(state)
            context["paper_package"] = PaperService().build_package(state).model_dump(
                mode="json"
            )
        else:
            context = self.contexts.for_orchestrator(state)
        return {
            "phase": state.phase.value,
            "allowed_actions": sorted(
                action.value for action in ALLOWED_ACTIONS[state.phase.value]
            ),
            "allowed_state_update_fields": sorted(PHASE_UPDATE_FIELDS[state.phase]),
            "repository_attachment_allowed": state.phase
            in {
                ResearchPhase.RESOURCE_DESIGN,
                ResearchPhase.BASELINE_REPRODUCTION,
                ResearchPhase.CORE_EXPERIMENT,
                ResearchPhase.DIAGNOSIS,
            },
            "project_id": state.project.id,
            "project_dir": str(project_dir),
            "repository": repository,
            "execution_authorized": execution_allowed,
            "phase_context": context,
            "latest_execution": latest_execution,
        }

    def _apply_update(
        self,
        state: ResearchState,
        update: LiveStateUpdate,
        artifacts: ArtifactStore,
    ) -> None:
        nonempty = self._nonempty_update_fields(update)
        unexpected = nonempty - PHASE_UPDATE_FIELDS[state.phase]
        if unexpected:
            raise ValueError(
                f"Host state update is not allowed during {state.phase.value}: "
                f"{sorted(unexpected)}"
            )
        for query in update.search_queries:
            normalized = query.strip()
            if not normalized or normalized in state.literature.queries:
                continue
            state.literature.queries.append(normalized)
            typed = LiteratureSearchQuery(
                id=stable_id("QUERY", "host", normalized),
                query=normalized,
                purpose="canonical",
                priority=0.5,
            )
            if all(item.id != typed.id for item in state.literature.search_queries):
                state.literature.search_queries.append(typed)
        if update.important_sources:
            source_path = artifacts.write_json(
                f"artifacts/live/sources/{new_id('SOURCE-SET')}.json",
                [item.model_dump(mode="json") for item in update.important_sources],
            )
            for source in update.important_sources:
                if source.kind != "paper":
                    continue
                paper = PaperReference(
                    id=stable_id("PAPER-HOST", source.identifier or source.url),
                    title=source.title,
                    url=source.url,
                    identifier=source.identifier,
                    verified=False,
                    main_claim=source.why_important,
                    provenance=source_path,
                )
                self._upsert(state.literature.papers, paper)
        for gap in update.gaps:
            if gap.synthetic_test_data:
                raise ValueError("Live host cannot inject synthetic GAP fixtures")
            self._upsert(state.gaps.candidates, gap)
        for hypothesis in update.hypotheses:
            self._upsert(state.hypotheses.items, hypothesis)
            if hypothesis.status in {"active", "weakly_supported", "supported"}:
                if hypothesis.id not in state.hypotheses.active_hypothesis_ids:
                    state.hypotheses.active_hypothesis_ids.append(hypothesis.id)
            elif hypothesis.id in state.hypotheses.active_hypothesis_ids:
                state.hypotheses.active_hypothesis_ids.remove(hypothesis.id)
        known_hypotheses = {item.id for item in state.hypotheses.items}
        for idea in update.ideas:
            if idea.hypothesis_id not in known_hypotheses:
                raise ValueError(f"Idea references unknown hypothesis: {idea.hypothesis_id}")
            self._upsert(state.ideas.candidates, idea)
        if update.selected_idea_id is not None:
            if update.selected_idea_id not in {item.id for item in state.ideas.candidates}:
                raise ValueError("selected_idea_id does not reference a known idea")
            state.ideas.selected_idea_id = update.selected_idea_id
        if update.idea_review is not None:
            round_number = len(state.ideas.review_rounds) + 1
            attack = artifacts.write_text(
                f"artifacts/reviews/idea_round_{round_number}_attack.md",
                update.idea_review.attack,
            )
            defense = artifacts.write_text(
                f"artifacts/reviews/idea_round_{round_number}_defense.md",
                update.idea_review.defense,
            )
            state.ideas.review_rounds.append(
                IdeaReviewRecord(
                    round=round_number,
                    attack_artifact=attack,
                    defense_artifact=defense,
                    verdict=update.idea_review.verdict,
                )
            )
        for experiment in update.experiments:
            if (
                experiment.synthetic_test_data
                or experiment.status not in {"planned", "approved"}
                or experiment.execution_verified
                or experiment.execution_artifact
                or experiment.metrics_artifact
                or experiment.observation
                or experiment.interpretation
            ):
                raise ValueError(
                    "Host may plan/approve experiments but cannot assert execution or results"
                )
            if experiment.hypothesis_id not in known_hypotheses:
                raise ValueError(
                    f"Experiment references unknown hypothesis: {experiment.hypothesis_id}"
                )
            self._upsert(state.experiments.experiments, experiment)
        for baseline in update.baselines:
            if baseline.synthetic_test_data:
                raise ValueError("Live host cannot inject synthetic baselines")
            if baseline.status != "PENDING" and not self._baseline_has_execution(
                state, baseline.id
            ):
                raise ValueError(
                    "Baseline status cannot advance without a runner-verified execution"
                )
            self._upsert(state.experiments.baselines, baseline)
        for analysis in update.experiment_analyses:
            experiment = next(
                (
                    item
                    for item in state.experiments.experiments
                    if item.id == analysis.experiment_id
                ),
                None,
            )
            if (
                experiment is None
                or experiment.status not in {"completed", "failed"}
                or not experiment.execution_artifact
            ):
                raise ValueError(
                    "Experiment analysis requires an actual runner execution artifact"
                )
            experiment.observation = analysis.observation
            experiment.interpretation = analysis.interpretation
            experiment.confounders = analysis.confounders
        if update.paper_draft is not None:
            artifacts.write_text("artifacts/paper/draft.md", update.paper_draft)
        if update.paper_review is not None:
            artifacts.write_json(
                "artifacts/reviews/paper_review.json",
                update.paper_review.model_dump(mode="json"),
            )
    async def _checkpoint_target(
        self,
        state: ResearchState,
        action: ResearchAction,
        artifacts: ArtifactStore,
    ) -> ResearchPhase:
        if action.action.value == "request_topic_selection":
            return await DiscoveryWorkflow(
                artifacts, mock=False
            ).request_topic_selection(state, action)
        if action.action.value == "request_resources":
            return await IdeaWorkflow(
                artifacts, mock=False
            ).request_resources(state, action)
        raise KeyError(action.action.value)

    async def _advance(
        self,
        state: ResearchState,
        response: HostAgentResult,
        artifacts: ArtifactStore,
        turn_artifact: str,
    ) -> None:
        action = response.proposed_action
        if action is None:
            raise ValueError("Host result has no action after execution analysis")
        validate_action(state.phase.value, action)
        old_phase = state.phase
        if action.action.value in {"request_topic_selection", "request_resources"}:
            target = await self._checkpoint_target(state, action, artifacts)
        else:
            target = LIVE_ACTION_TARGETS.get((old_phase, action.action.value))
            if target is None:
                raise ValueError(
                    f"No live handler target for {old_phase.value}:{action.action.value}"
                )
        require_valid_transition(old_phase, target)
        if response.major_pivot:
            state.human_checkpoint = HumanCheckpoint(
                type="major_pivot",
                prompt=response.summary,
                options=response.pivot_options or ["approve", "stop"],
                resume_phase=ResearchPhase.PIVOT,
            )
        if (
            old_phase == ResearchPhase.PAPER_ASSEMBLY
            and target == ResearchPhase.PAPER_REVIEW
            and not (artifacts.project_dir / "artifacts/paper/draft.md").is_file()
        ):
            raise ValueError("Paper assembly must produce draft.md before review")
        if old_phase == ResearchPhase.PAPER_AUDIT:
            package = PaperService().build_package(state)
            artifacts.write_json(
                "artifacts/paper/readiness_audit.json",
                {
                    "ready": not package.do_not_claim,
                    "do_not_claim": package.do_not_claim,
                },
            )
        if target == ResearchPhase.COMPLETE:
            review_path = artifacts.project_dir / "artifacts/reviews/paper_review.json"
            if not review_path.is_file():
                raise ValueError("Paper review artifact is required before completion")
            review = PaperReviewDraft.model_validate_json(
                review_path.read_text(encoding="utf-8")
            )
            if review.must_fix or review.disposition != "ready":
                raise ValueError(
                    "Paper review still contains unresolved MUST_FIX items"
                )
            package = PaperService().build_package(state)
            if package.do_not_claim:
                raise ValueError("Paper cannot complete while readiness blockers remain")
            artifacts.write_json(
                "artifacts/paper/final_audit.json",
                {"ready": True, "do_not_claim": []},
            )
            artifacts.write_text(
                "artifacts/reports/research_report.md",
                PaperService().render_draft(package),
            )
        state.phase = target
        state.decisions.append(
            DecisionRecord(
                id=new_id("DEC"),
                phase=old_phase,
                action=action,
                outcome=f"live_host_transition:{target.value}; turn={turn_artifact}",
            )
        )
        state.next_actions = []
        state.iteration += 1

    @staticmethod
    def _record_turn(
        artifacts: ArtifactStore,
        state: ResearchState,
        response: HostAgentResult,
    ) -> str:
        return artifacts.write_json(
            f"artifacts/live/turns/{new_id('TURN')}.json",
            {
                "phase": state.phase.value,
                "response": response.model_dump(mode="json"),
            },
        )

    @staticmethod
    def _execution_allowed(
        state: ResearchState,
        repository_service: RepositoryAttachmentService,
    ) -> bool:
        execution = repository_service.execution_configuration()
        return bool(execution.get("allow_shell", False)) and bool(
            state.constraints.shell_execution_allowed
        )

    @staticmethod
    def _validate_tool_uses(
        response: HostAgentResult, tools: dict[str, str]
    ) -> None:
        unexpected = {item.tool for item in response.tool_uses} - set(tools)
        if unexpected:
            raise PermissionError(
                f"Host reported unavailable tool capabilities: {sorted(unexpected)}"
            )

    def _host_backend(self, *, cwd: Path, artifacts: ArtifactStore) -> AgentBackend:
        if self.backend is not None:
            return self.backend
        resolved_cwd = cwd.resolve()
        if (
            self._managed_backend is None
            or self._managed_backend.cwd != resolved_cwd
        ):
            self._managed_backend = CodexExecBackend(
                cwd=resolved_cwd,
                artifacts=artifacts,
                command=os.environ.get("RESEARCH_AGENT_HOST_COMMAND", "codex"),
                model=os.environ.get("RESEARCH_AGENT_HOST_MODEL"),
            )
        return self._managed_backend

    async def _ingest_pending_sources(
        self,
        state: ResearchState,
        artifacts: ArtifactStore,
        *,
        limit: int = 8,
    ) -> int:
        attempted_urls = {
            candidate.source_url
            for candidate in state.literature.candidates
            if candidate.source_url
        }
        pending = [
            paper
            for paper in state.literature.papers
            if paper.id.startswith("PAPER-HOST")
            and paper.url
            and paper.url not in attempted_urls
        ][:limit]
        if not pending:
            return 0
        settings = LiteratureSettings(
            max_queries_per_round=limit,
            max_candidates_per_query=1,
            max_new_verified_papers_per_round=limit,
            provider_timeout_seconds=30,
        )
        arxiv_service = LiteratureService(
            providers=[ArxivLikeProvider(max_results=1)],
            artifacts=artifacts,
            settings=settings,
        )
        arxiv_candidates: list[PaperCandidate] = []
        web_queries: list[LiteratureSearchQuery] = []
        for paper in pending:
            assert paper.url is not None
            query = LiteratureSearchQuery(
                id=stable_id("QUERY", "host-source", paper.url),
                query=paper.url,
                purpose="canonical",
                priority=1.0,
            )
            if all(item.id != query.id for item in state.literature.search_queries):
                state.literature.search_queries.append(query)
            if paper.url not in state.literature.queries:
                state.literature.queries.append(paper.url)
            arxiv_id = self._arxiv_id(paper.identifier, paper.url)
            if arxiv_id:
                candidate = PaperCandidate(
                    id=stable_id("CAND", "arxiv", arxiv_id, query.id),
                    query_id=query.id,
                    raw_title=paper.title,
                    source_provider="arxiv",
                    source_url=paper.url,
                    identifiers=PaperIdentifier(
                        arxiv_id=arxiv_id,
                        canonical_url=f"https://arxiv.org/abs/{arxiv_id}",
                    ),
                    retrieval_rank=1,
                )
                state.literature.candidates.append(candidate)
                arxiv_candidates.append(candidate)
            else:
                web_queries.append(query)
        if arxiv_candidates:
            await arxiv_service.verify_metadata(
                state.literature, arxiv_candidates
            )
            arxiv_paper_ids = [
                paper_id
                for candidate in arxiv_candidates
                if (
                    paper_id := state.literature.candidate_paper_links.get(
                        candidate.id
                    )
                )
            ]
            await arxiv_service.fetch_contents(
                state.literature, arxiv_paper_ids
            )
            await arxiv_service.extract_papers(
                state.literature, arxiv_paper_ids
            )
        if web_queries:
            await LiteratureService(
                providers=[GenericWebPaperProvider(timeout_seconds=30)],
                artifacts=artifacts,
                settings=settings,
            ).search_round(state, queries_override=web_queries)
        else:
            await arxiv_service.build_literature_map(state.literature)
            coverage = arxiv_service.build_coverage_report(
                state.literature, unresolved_questions=[]
            )
            state.literature.coverage_reports.append(coverage)
            state.literature.coverage_artifact = artifacts.write_json(
                "artifacts/literature/reports/coverage.json",
                coverage.model_dump(mode="json"),
            )
        self._remove_ingested_placeholders(state)
        return len(pending)

    @staticmethod
    def _arxiv_id(identifier: str | None, url: str) -> str | None:
        value = f"{identifier or ''} {url}"
        match = re.search(r"(?:arXiv:|arxiv\.org/(?:abs|pdf)/)(\d{4}\.\d{4,5})", value)
        return match.group(1) if match else None

    @staticmethod
    def _remove_ingested_placeholders(state: ResearchState) -> None:
        verified_urls = {
            value
            for paper in state.literature.paper_metadata
            for value in [paper.identifiers.canonical_url, *paper.source_records]
            if value
        }
        verified_arxiv_ids = {
            paper.identifiers.arxiv_id
            for paper in state.literature.paper_metadata
            if paper.identifiers.arxiv_id
        }
        state.literature.papers = [
            paper
            for paper in state.literature.papers
            if not (
                paper.id.startswith("PAPER-HOST")
                and paper.url
                and (
                    paper.url in verified_urls
                    or LiveResearchRuntime._arxiv_id(paper.identifier, paper.url)
                    in verified_arxiv_ids
                )
            )
        ]

    @staticmethod
    def _nonempty_update_fields(update: LiveStateUpdate) -> set[str]:
        values = update.model_dump()
        return {
            key
            for key, value in values.items()
            if value is not None and value != [] and value != {}
        }

    @staticmethod
    def _upsert(items: list, value: object) -> None:
        identifier = value.id
        for index, existing in enumerate(items):
            if existing.id == identifier:
                items[index] = value
                return
        items.append(value)

    @staticmethod
    def _baseline_has_execution(state: ResearchState, baseline_id: str) -> bool:
        return any(
            experiment.status == "completed"
            and experiment.execution_verified
            and baseline_id in experiment.baseline_ids
            for experiment in state.experiments.experiments
        )

    @staticmethod
    def _default_action(phase: ResearchPhase) -> str:
        defaults = {
            ResearchPhase.BOOTSTRAP: "live literature search",
            ResearchPhase.HORIZON_SCAN: "expand literature or mine GAPs",
            ResearchPhase.GAP_MINING: "mine evidence-backed GAP candidates",
            ResearchPhase.GAP_SYNTHESIS: "synthesize GAPs or request more evidence",
            ResearchPhase.TOPIC_SELECTION: "await or apply topic selection",
            ResearchPhase.IDEA_FORMATION: "form a mechanism-first idea",
            ResearchPhase.IDEA_REVIEW: "attack, defend, and meta-review the idea",
            ResearchPhase.RESOURCE_DESIGN: "design a resource-bounded baseline plan",
            ResearchPhase.BASELINE_REPRODUCTION: "reproduce or diagnose the baseline",
            ResearchPhase.CORE_EXPERIMENT: "execute/analyze the approved MVE",
            ResearchPhase.DIAGNOSIS: "run the cheapest discriminative diagnostic",
            ResearchPhase.PIVOT: "apply a bounded pivot or request major-pivot approval",
            ResearchPhase.EVIDENCE_EXPANSION: "expand only claim-critical evidence",
            ResearchPhase.PAPER_AUDIT: "audit claim-evidence readiness",
            ResearchPhase.PAPER_ASSEMBLY: "write from PaperPackage",
            ResearchPhase.PAPER_REVIEW: "review or return to experiment",
            ResearchPhase.COMPLETE: "no action",
        }
        return defaults[phase]

    @staticmethod
    def _host_login_status(executable: str | None) -> tuple[bool, str]:
        if executable is None:
            return False, "host command not found"
        try:
            result = subprocess.run(
                (executable, "login", "status"),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, str(exc)
        message = result.stdout.strip()
        return result.returncode == 0, message
