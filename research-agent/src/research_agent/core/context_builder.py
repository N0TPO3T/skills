from __future__ import annotations

from typing import Any

from research_agent.schemas.experiment import Experiment
from research_agent.schemas.state import ResearchState
from research_agent.services.gap_evidence_service import GapEvidenceService


class ContextBuilder:
    """Builds bounded, task-specific contexts from typed state metadata."""

    def for_orchestrator(self, state: ResearchState) -> dict[str, Any]:
        active_ids = set(state.hypotheses.active_hypothesis_ids)
        active_hypotheses = [
            hypothesis.model_dump(mode="json")
            for hypothesis in state.hypotheses.items
            if hypothesis.id in active_ids
        ]
        selected_gap = next(
            (
                gap.model_dump(mode="json")
                for gap in state.gaps.candidates
                if gap.id == state.gaps.selected_gap_id
            ),
            None,
        )
        return {
            "project_id": state.project.id,
            "phase": state.phase.value,
            "iteration": state.iteration,
            "active_hypotheses": active_hypotheses,
            "recent_decisions": [
                decision.model_dump(mode="json") for decision in state.decisions[-5:]
            ],
            "largest_uncertainty": self._largest_uncertainty(state),
            "recent_experiments": [
                self._experiment_summary(experiment)
                for experiment in state.experiments.experiments[-3:]
            ],
            "current_gap": selected_gap,
            "resource_budget": state.constraints.model_dump(mode="json"),
            "next_candidates": [
                action.model_dump(mode="json") for action in state.next_actions[:5]
            ],
            "human_checkpoint": (
                state.human_checkpoint.model_dump(mode="json")
                if state.human_checkpoint
                else None
            ),
        }

    def for_literature(self, state: ResearchState) -> dict[str, Any]:
        return {
            "research_direction": state.project.research_direction,
            "queries": [
                query.model_dump(mode="json")
                for query in state.literature.search_queries[-12:]
            ],
            "paper_metadata": [
                {
                    "id": paper.paper_id,
                    "title": paper.title,
                    "year": paper.year,
                    "venue": paper.venue,
                    "metadata_verified": paper.metadata_verified,
                    "verification_confidence": paper.verification_confidence,
                }
                for paper in state.literature.paper_metadata
            ],
            "clusters": state.literature.clusters,
            "latest_coverage": (
                state.literature.coverage_reports[-1].model_dump(mode="json")
                if state.literature.coverage_reports
                else None
            ),
        }

    def for_gap_mining(self, state: ResearchState) -> dict[str, Any]:
        valid_paper_ids = {
            paper.paper_id
            for paper in state.literature.paper_metadata
            if paper.metadata_verified and not paper.synthetic_test_data
        }
        statement_gate = GapEvidenceService()
        valid_statements = [
            item
            for item in state.literature.statements
            if item.paper_id in valid_paper_ids
            and statement_gate.validate_statement(
                state.literature, item, state.literature_quality
            )
        ]
        candidate_clues = [
            {
                **item.model_dump(mode="json"),
                "evidence_class": statement_gate.classify_statement(
                    state.literature, item, state.literature_quality
                ),
                "requires_verification": True,
            }
            for item in state.literature.statements
            if item.paper_id in valid_paper_ids
            and statement_gate.classify_statement(
                state.literature, item, state.literature_quality
            )
            in {"probable_observation", "agent_inference", "unverified_clue"}
        ]
        valid_provenance_ids = {
            provenance_id
            for item in valid_statements
            for provenance_id in item.provenance_ids
        }
        return {
            "research_direction": state.project.research_direction,
            "paper_extractions": [
                item.model_dump(mode="json")
                for item in state.literature.extractions
                if item.paper_id in valid_paper_ids
            ],
            "extracted_statements": [
                item.model_dump(mode="json")
                for item in valid_statements
            ],
            "candidate_clues": candidate_clues,
            "provenance_summary": [
                {
                    "id": item.id,
                    "entity_id": item.entity_id,
                    "source_type": item.source_type,
                    "source_id": item.source_id,
                    "artifact_path": item.artifact_path,
                    "source_locator": item.source_locator,
                    "confidence": item.confidence,
                    "notes": item.notes,
                }
                for item in state.literature.provenance_records
                if item.id in valid_provenance_ids
            ],
            "research_clusters": state.literature.clusters,
            "coverage": (
                state.literature.coverage_reports[-1].model_dump(mode="json")
                if state.literature.coverage_reports
                else None
            ),
        }

    def for_paper_extraction(
        self, state: ResearchState, paper_id: str
    ) -> dict[str, Any]:
        metadata = next(
            (
                item
                for item in state.literature.paper_metadata
                if item.paper_id == paper_id
            ),
            None,
        )
        content = next(
            (item for item in state.literature.contents if item.paper_id == paper_id),
            None,
        )
        return {
            "paper_metadata": metadata.model_dump(mode="json") if metadata else None,
            "content_descriptor": content.model_dump(mode="json") if content else None,
            "content_text": None,
        }

    def for_literature_map(self, state: ResearchState) -> dict[str, Any]:
        return {
            "verified_papers": [
                item.model_dump(mode="json")
                for item in state.literature.paper_metadata
                if item.metadata_verified and not item.synthetic_test_data
            ],
            "extractions": [
                item.model_dump(mode="json") for item in state.literature.extractions
            ],
            "statements": [
                item.model_dump(mode="json") for item in state.literature.statements
            ],
            "clusters": state.literature.clusters,
            "coverage": (
                state.literature.coverage_reports[-1].model_dump(mode="json")
                if state.literature.coverage_reports
                else None
            ),
        }

    def for_novelty_check(
        self,
        state: ResearchState,
        *,
        proposed_method: str,
        mechanism: str,
        task: str,
        setting: str,
    ) -> dict[str, Any]:
        return {
            "proposal": {
                "proposed_method": proposed_method,
                "mechanism": mechanism,
                "task": task,
                "setting": setting,
            },
            "search_scope": [
                item.model_dump(mode="json")
                for item in state.literature.novelty_searches[-3:]
            ],
            "closest_prior_works": [
                item.model_dump(mode="json")
                for item in state.literature.paper_metadata
                if item.metadata_verified and not item.synthetic_test_data
            ][:10],
        }

    def for_idea_review(self, state: ResearchState) -> dict[str, Any]:
        return {
            "selected_gap": self._selected_gap(state),
            "active_hypotheses": self._active_hypotheses(state),
            "idea_candidates": [
                idea.model_dump(mode="json") for idea in state.ideas.candidates
            ],
            "previous_reviews": [
                review.model_dump(mode="json") for review in state.ideas.review_rounds[-3:]
            ],
        }

    def for_experiment(self, state: ResearchState) -> dict[str, Any]:
        return {
            "selected_idea_id": state.ideas.selected_idea_id,
            "active_hypotheses": self._active_hypotheses(state),
            "baselines": [
                baseline.model_dump(mode="json")
                for baseline in state.experiments.baselines
            ],
            "previous_experiment_summaries": [
                self._experiment_summary(experiment)
                for experiment in state.experiments.experiments[-5:]
            ],
            "resource_constraints": state.constraints.model_dump(mode="json"),
        }

    def for_diagnosis(self, state: ResearchState) -> dict[str, Any]:
        current = state.experiments.experiments[-1] if state.experiments.experiments else None
        parent = None
        if current:
            parent = next(
                (
                    item.model_dump(mode="json")
                    for item in state.hypotheses.items
                    if item.id == current.hypothesis_id
                ),
                None,
            )
        return {
            "current_experiment": current.model_dump(mode="json") if current else None,
            "parent_hypothesis": parent,
            "relevant_previous_experiments": [
                self._experiment_summary(experiment)
                for experiment in state.experiments.experiments[-6:-1]
            ],
            "baselines": [
                baseline.model_dump(mode="json")
                for baseline in state.experiments.baselines
            ],
            "resource_constraints": state.constraints.model_dump(mode="json"),
            "observed_artifact_paths": [
                experiment.metrics_artifact
                for experiment in state.experiments.experiments[-6:]
                if experiment.metrics_artifact
            ],
            "relevant_literature": [
                {"id": paper.id, "title": paper.title, "verified": paper.verified}
                for paper in state.literature.papers
                if paper.verified
            ][:20],
        }

    def for_paper(self, state: ResearchState) -> dict[str, Any]:
        return {
            "project": state.project.model_dump(mode="json"),
            "selected_gap": self._selected_gap(state),
            "hypotheses": [item.model_dump(mode="json") for item in state.hypotheses.items],
            "selected_idea_id": state.ideas.selected_idea_id,
            "experiment_ledger": [
                experiment.model_dump(mode="json")
                for experiment in state.experiments.experiments
            ],
            "evidence": [item.model_dump(mode="json") for item in state.evidence.items],
            "claims": [item.model_dump(mode="json") for item in state.claims.items],
            "verified_literature": [
                paper.model_dump(mode="json")
                for paper in state.literature.paper_metadata
                if paper.metadata_verified and not paper.synthetic_test_data
            ],
        }

    @staticmethod
    def _experiment_summary(experiment: Experiment) -> dict[str, Any]:
        return {
            "id": experiment.id,
            "hypothesis_id": experiment.hypothesis_id,
            "level": experiment.level,
            "status": experiment.status,
            "execution_verified": experiment.execution_verified,
            "execution_artifact": experiment.execution_artifact,
            "metrics_artifact": experiment.metrics_artifact,
            "observation": experiment.observation,
            "interpretation": experiment.interpretation,
        }

    @staticmethod
    def _largest_uncertainty(state: ResearchState) -> str:
        if state.human_checkpoint:
            return f"human decision pending: {state.human_checkpoint.type}"
        if not state.gaps.selected_gap_id:
            return "which research gap is evidence-backed and worth selecting"
        if not state.hypotheses.active_hypothesis_ids:
            return "whether the selected gap has a falsifiable root-cause hypothesis"
        if not state.experiments.experiments:
            return "whether the hypothesis produces a measurable L1 signal"
        return "whether current evidence is robust enough to change the research decision"

    @staticmethod
    def _selected_gap(state: ResearchState) -> dict[str, Any] | None:
        return next(
            (
                gap.model_dump(mode="json")
                for gap in state.gaps.candidates
                if gap.id == state.gaps.selected_gap_id
            ),
            None,
        )

    @staticmethod
    def _active_hypotheses(state: ResearchState) -> list[dict[str, Any]]:
        active_ids = set(state.hypotheses.active_hypothesis_ids)
        return [
            item.model_dump(mode="json")
            for item in state.hypotheses.items
            if item.id in active_ids
        ]
