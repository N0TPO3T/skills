from __future__ import annotations

from research_agent.core.ids import new_id
from research_agent.core.transitions import ResearchPhase
from research_agent.schemas.decision import HumanCheckpoint, ResearchAction
from research_agent.schemas.gap import ResearchGap
from research_agent.schemas.literature import PaperReference
from research_agent.schemas.state import ResearchState
from research_agent.storage.artifact_store import ArtifactStore
from research_agent.services.gap_evidence_service import GapEvidenceService


class DiscoveryWorkflow:
    def __init__(self, artifacts: ArtifactStore, *, mock: bool) -> None:
        self.artifacts = artifacts
        self.mock = mock

    def _require_mock(self) -> None:
        if not self.mock:
            raise RuntimeError(
                "No live literature adapter is configured. Re-run with --mock or configure a provider."
            )

    async def search_literature(
        self, state: ResearchState, action: ResearchAction
    ) -> ResearchPhase:
        self._require_mock()
        direction = state.project.research_direction or "autonomous ML research"
        query = f"{direction} failure modes strong baselines"
        if query not in state.literature.queries:
            state.literature.queries.append(query)
        if not state.literature.papers:
            state.literature.papers.extend(
                [
                    PaperReference(
                        id="PAPER-MOCK-1",
                        title="Synthetic Survey of Failure-Aware Research Agents",
                        authors=["Synthetic Author"],
                        year=2026,
                        venue="Synthetic Venue",
                        verified=False,
                        main_claim="Synthetic fixture; not scientific evidence.",
                        method="Synthetic structured review fixture",
                        limitations_claimed=["Not a real paper"],
                        open_source=None,
                        relevance=0.8,
                        provenance="synthetic_test_data",
                        synthetic_test_data=True,
                    ),
                    PaperReference(
                        id="PAPER-MOCK-2",
                        title="Synthetic Baselines for Resource-Aware Experiment Planning",
                        authors=["Synthetic Author"],
                        year=2026,
                        venue="Synthetic Venue",
                        verified=False,
                        main_claim="Synthetic fixture; not scientific evidence.",
                        method="Synthetic cost-aware planning fixture",
                        limitations_claimed=["Not a real paper"],
                        open_source=None,
                        relevance=0.7,
                        provenance="synthetic_test_data",
                        synthetic_test_data=True,
                    ),
                ]
            )
        state.literature.clusters = [
            "research-agent reliability",
            "resource-aware experimental design",
        ]
        state.literature.matrix_artifact = self.artifacts.write_json(
            "artifacts/literature/mock_paper_matrix.json",
            {
                "synthetic_test_data": True,
                "query": query,
                "paper_ids": [paper.id for paper in state.literature.papers],
            },
        )
        return ResearchPhase.HORIZON_SCAN

    async def mine_gaps(
        self, state: ResearchState, action: ResearchAction
    ) -> ResearchPhase:
        self._require_mock()
        if not state.gaps.candidates:
            state.gaps.candidates = [
                self._mock_gap(
                    "GAP-MOCK-1",
                    "Decision policies may optimize positive outcomes instead of information gain",
                    0.86,
                    0.90,
                ),
                self._mock_gap(
                    "GAP-MOCK-2",
                    "Unverified literature can silently become strong factual premises",
                    0.78,
                    0.95,
                ),
                self._mock_gap(
                    "GAP-MOCK-3",
                    "Chat history is an unstable substitute for typed research state",
                    0.70,
                    0.92,
                ),
            ]
        self.artifacts.write_json(
            "artifacts/gaps/mock_candidates.json",
            {
                "synthetic_test_data": True,
                "gaps": [gap.model_dump(mode="json") for gap in state.gaps.candidates],
            },
        )
        return ResearchPhase.GAP_MINING

    async def synthesize_gaps(
        self, state: ResearchState, action: ResearchAction
    ) -> ResearchPhase:
        self._require_mock()
        ranked = sorted(
            state.gaps.candidates,
            key=lambda gap: (
                gap.research_value_score + gap.feasibility_score - gap.risk_score
            ),
            reverse=True,
        )[:5]
        for gap in ranked:
            gap.status = "shortlisted"
        state.gaps.synthesis_artifact = self.artifacts.write_json(
            "artifacts/gaps/mock_synthesis.json",
            {
                "synthetic_test_data": True,
                "shortlisted_gap_ids": [gap.id for gap in ranked],
            },
        )
        return ResearchPhase.GAP_SYNTHESIS

    async def request_topic_selection(
        self, state: ResearchState, action: ResearchAction
    ) -> ResearchPhase:
        if not state.project.synthetic_test_data:
            coverage = (
                state.literature.coverage_reports[-1]
                if state.literature.coverage_reports
                else None
            )
            if coverage is None or not coverage.sufficient_for_gap_synthesis:
                raise ValueError(
                    "Literature coverage is insufficient for topic selection"
                )
            gate = GapEvidenceService()
            for gap in state.gaps.candidates:
                if gap.status != "shortlisted":
                    continue
                summary = gate.summarize_and_validate(
                    state.literature, gap, state.literature_quality
                )
                if (
                    summary.independent_paper_count < 2
                    or summary.content_verified_paper_count < 2
                ):
                    raise ValueError(
                        f"Gap {gap.id} lacks two independent content-verified supports"
                    )
                unresolved_high_conflicts = [
                    conflict
                    for corroboration in state.literature_quality.corroborations
                    if corroboration.paper_id in gap.supporting_papers
                    for conflict in corroboration.conflicts
                    if conflict.severity == "high" and not conflict.resolved
                ]
                if unresolved_high_conflicts:
                    raise ValueError(
                        f"Gap {gap.id} has unresolved high-severity metadata conflicts"
                    )
        options = [
            gap.id for gap in state.gaps.candidates if gap.status == "shortlisted"
        ]
        if not options:
            raise ValueError("No shortlisted research gaps are available")
        state.human_checkpoint = HumanCheckpoint(
            type="topic_selection",
            prompt="Select one shortlisted GAP ID before idea formation.",
            options=options,
            resume_phase=ResearchPhase.TOPIC_SELECTION,
        )
        return ResearchPhase.TOPIC_SELECTION

    @staticmethod
    def _mock_gap(
        gap_id: str, title: str, research_value: float, feasibility: float
    ) -> ResearchGap:
        return ResearchGap(
            id=gap_id,
            title=title,
            observed_phenomena=["Synthetic observation used only for workflow testing"],
            supporting_papers=[],
            common_limitation="Synthetic fixture; literature premise remains unverified",
            root_cause_hypothesis="Research decisions lack an explicit evidence gate",
            why_existing_methods_fail="They can pass free-form text directly to execution",
            missing_capability="Typed, validated scientific decisions",
            potential_interventions=["Evidence-aware action validation"],
            related_techniques=["state machines", "typed structured output"],
            minimum_viable_experiment="Compare validated and unvalidated mock decisions",
            expected_signal="Invalid scientific transitions are rejected deterministically",
            falsification_criterion="An invalid transition reaches persistent state",
            novelty_score=0.55,
            feasibility_score=feasibility,
            research_value_score=research_value,
            publication_score=0.45,
            risk_score=0.25,
            synthetic_test_data=True,
        )
