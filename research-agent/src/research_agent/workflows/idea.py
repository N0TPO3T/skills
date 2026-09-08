from __future__ import annotations

from research_agent.core.ids import new_id
from research_agent.core.transitions import ResearchPhase
from research_agent.schemas.decision import HumanCheckpoint, ResearchAction
from research_agent.schemas.hypothesis import Hypothesis
from research_agent.schemas.idea import IdeaReviewRecord, MethodCandidate
from research_agent.schemas.state import ResearchState
from research_agent.storage.artifact_store import ArtifactStore


class IdeaWorkflow:
    def __init__(
        self, artifacts: ArtifactStore, *, mock: bool, max_review_rounds: int = 3
    ) -> None:
        self.artifacts = artifacts
        self.mock = mock
        self.max_review_rounds = max_review_rounds

    def _require_mock(self) -> None:
        if not self.mock:
            raise RuntimeError("No live idea/reviewer provider is configured; use --mock.")

    async def form_idea(
        self, state: ResearchState, action: ResearchAction
    ) -> ResearchPhase:
        self._require_mock()
        gap = next(
            (item for item in state.gaps.candidates if item.id == state.gaps.selected_gap_id),
            None,
        )
        if gap is None:
            raise ValueError("A selected gap is required before idea formation")
        if not state.hypotheses.items:
            hypothesis = Hypothesis(
                id="HYP-MOCK-1",
                statement="Typed action and evidence gates prevent unsupported workflow advancement.",
                mechanism="Code validates phase/action/evidence invariants before persistence.",
                predicted_outcome="Illegal or unsupported decisions fail before state changes.",
                falsification_criterion="A forbidden decision persists or creates E2 evidence.",
                status="active",
            )
            state.hypotheses.items.append(hypothesis)
            state.hypotheses.active_hypothesis_ids = [hypothesis.id]
        hypothesis_id = state.hypotheses.active_hypothesis_ids[0]
        if not state.ideas.candidates:
            idea = MethodCandidate(
                id="IDEA-MOCK-1",
                hypothesis_id=hypothesis_id,
                name="Evidence-gated deterministic workflow",
                mechanism="Separate structured scientific proposals from validated code transitions.",
                simplest_baseline="Free-form sequential prompt without persistent typed state",
                differentiating_test="Attempt illegal transitions and unsupported evidence promotion",
                status="reviewing",
            )
            state.ideas.candidates.append(idea)
            state.ideas.selected_idea_id = idea.id
        self.artifacts.write_json(
            "artifacts/ideas/mock_idea.json",
            {
                "synthetic_test_data": True,
                "selected_gap_id": gap.id,
                "idea": state.ideas.candidates[0].model_dump(mode="json"),
            },
        )
        return ResearchPhase.IDEA_FORMATION

    async def review_idea(
        self, state: ResearchState, action: ResearchAction
    ) -> ResearchPhase:
        self._require_mock()
        if len(state.ideas.review_rounds) >= self.max_review_rounds:
            raise RuntimeError("Maximum idea review rounds reached")
        round_number = len(state.ideas.review_rounds) + 1
        attack = self.artifacts.write_text(
            f"artifacts/reviews/idea_round_{round_number}_attack.md",
            "# Synthetic attack\n\nThe result may reflect workflow validation rather than scientific novelty.\n",
        )
        defense = self.artifacts.write_text(
            f"artifacts/reviews/idea_round_{round_number}_defense.md",
            "# Synthetic defense\n\nConcede novelty uncertainty; retain only the systems reliability claim.\n",
        )
        record = IdeaReviewRecord(
            round=round_number,
            attack_artifact=attack,
            defense_artifact=defense,
            verdict="PROCEED_WITH_MODIFICATIONS",
        )
        state.ideas.review_rounds.append(record)
        selected = next(
            (
                idea
                for idea in state.ideas.candidates
                if idea.id == state.ideas.selected_idea_id
            ),
            None,
        )
        if selected:
            selected.status = "accepted"
        return ResearchPhase.IDEA_REVIEW

    async def request_resources(
        self, state: ResearchState, action: ResearchAction
    ) -> ResearchPhase:
        state.human_checkpoint = HumanCheckpoint(
            type="resource_input",
            prompt=(
                "Provide resource constraints as JSON, or enter 'default' to keep shell execution disabled."
            ),
            options=["default"],
            resume_phase=ResearchPhase.RESOURCE_DESIGN,
        )
        return ResearchPhase.RESOURCE_DESIGN

