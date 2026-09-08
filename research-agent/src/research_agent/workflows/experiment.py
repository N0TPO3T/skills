from __future__ import annotations

from research_agent.core.transitions import ResearchPhase
from research_agent.schemas.decision import ResearchAction
from research_agent.schemas.diagnosis import FailureExplanation
from research_agent.schemas.experiment import BaselineReproduction, Experiment
from research_agent.schemas.state import ResearchState
from research_agent.storage.artifact_store import ArtifactStore


class ExperimentWorkflow:
    def __init__(self, artifacts: ArtifactStore, *, mock: bool) -> None:
        self.artifacts = artifacts
        self.mock = mock

    def _require_mock(self) -> None:
        if not self.mock:
            raise RuntimeError("No live experiment planner is configured; use --mock.")

    async def reproduce_baseline(
        self, state: ResearchState, action: ResearchAction
    ) -> ResearchPhase:
        self._require_mock()
        if not state.experiments.baselines:
            state.experiments.baselines.append(
                BaselineReproduction(
                    id="BASE-MOCK-1",
                    name="Synthetic free-form workflow baseline",
                    status="PASS",
                    reported_result="synthetic_test_data: accepts invalid action",
                    reproduced_result="synthetic_test_data: accepts invalid action",
                    difference="none in deterministic fixture",
                    variance="not applicable to synthetic fixture",
                    environment_diff="offline mock only",
                    diagnosis="Synthetic gate test; not a scientific result",
                    synthetic_test_data=True,
                )
            )
        self.artifacts.write_json(
            "artifacts/experiments/baseline_mock.json",
            {
                "synthetic_test_data": True,
                "baseline": state.experiments.baselines[0].model_dump(mode="json"),
            },
        )
        return ResearchPhase.BASELINE_REPRODUCTION

    async def design_experiment(
        self, state: ResearchState, action: ResearchAction
    ) -> ResearchPhase:
        self._require_mock()
        if not any(item.status == "PASS" for item in state.experiments.baselines):
            raise ValueError("A PASS baseline reproduction is required for core planning")
        if not state.hypotheses.active_hypothesis_ids:
            raise ValueError("An active hypothesis is required")
        if not state.experiments.experiments:
            experiment = Experiment(
                id="EXP-MOCK-0001",
                hypothesis_id=state.hypotheses.active_hypothesis_ids[0],
                research_question="Does the evidence gate reject unsupported advancement?",
                baseline_ids=[state.experiments.baselines[0].id],
                independent_variables=["validation gate enabled"],
                dependent_variables=["illegal transition persistence rate"],
                control_variables=["same synthetic action sequence"],
                expected_outcome="Persistence rate falls from one to zero in the fixture.",
                success_criterion="All invalid fixture actions are rejected.",
                falsification_criterion="Any invalid fixture action reaches saved state.",
                model="deterministic mock",
                dataset="synthetic_test_data",
                seeds=[0],
                estimated_gpu_hours=0,
                level="L1",
                status="planned",
                execution_verified=False,
                confounders=["This is workflow validation, not scientific evidence"],
                synthetic_test_data=True,
            )
            state.experiments.experiments.append(experiment)
            self.artifacts.write_json(
                f"artifacts/experiments/{experiment.id}/config.json",
                experiment.model_dump(mode="json"),
            )
        return ResearchPhase.CORE_EXPERIMENT

    async def analyze_result(
        self, state: ResearchState, action: ResearchAction
    ) -> ResearchPhase:
        if not state.experiments.experiments:
            raise ValueError("No experiment is available for analysis")
        experiment = state.experiments.experiments[-1]
        if experiment.status not in {"completed", "failed"}:
            raise ValueError("Only completed or failed runner results can be analyzed")
        return ResearchPhase.CORE_EXPERIMENT

    async def diagnose_failure(
        self, state: ResearchState, action: ResearchAction
    ) -> ResearchPhase:
        explanations = [
            FailureExplanation(
                explanation="implementation bug",
                evidence_for=["Result diverges from expected control behavior"],
                evidence_against=[],
                probability=0.35,
                cheapest_diagnostic_experiment="Run one deterministic L0 control",
                estimated_cost=0.1,
                expected_information_gain=0.8,
            ),
            FailureExplanation(
                explanation="false hypothesis",
                evidence_for=["No target signal observed"],
                evidence_against=["Implementation has not yet passed L0 checks"],
                probability=0.2,
                cheapest_diagnostic_experiment="Test the simplest oracle/headroom baseline",
                estimated_cost=0.2,
                expected_information_gain=0.7,
            ),
        ]
        state.experiments.consecutive_diagnostics += 1
        self.artifacts.write_json(
            "artifacts/experiments/latest_diagnosis.json",
            {
                "explanations": [item.model_dump(mode="json") for item in explanations],
                "selected": max(
                    explanations, key=lambda item: item.information_gain_per_cost
                ).explanation,
            },
        )
        return ResearchPhase.DIAGNOSIS

    async def pivot(
        self, state: ResearchState, action: ResearchAction
    ) -> ResearchPhase:
        self.artifacts.write_json(
            "artifacts/ideas/latest_pivot.json",
            {
                "reason": action.reason,
                "target": action.target,
                "preserved_evidence_ids": [item.id for item in state.evidence.items],
            },
        )
        return ResearchPhase.PIVOT

    async def run_experiment(
        self, state: ResearchState, action: ResearchAction
    ) -> ResearchPhase:
        if not state.constraints.shell_execution_allowed:
            raise PermissionError(
                "Project constraints do not authorize shell experiment execution"
            )
        return ResearchPhase.CORE_EXPERIMENT

    async def expand_evidence(
        self, state: ResearchState, action: ResearchAction
    ) -> ResearchPhase:
        return ResearchPhase.EVIDENCE_EXPANSION
