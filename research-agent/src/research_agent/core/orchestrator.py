from __future__ import annotations

import json

from research_agent.core.context_builder import ContextBuilder
from research_agent.llm.base import LLMClient, Message
from research_agent.llm.router import ModelRouter
from research_agent.prompts.loader import PromptLoader
from research_agent.schemas.decision import ActionType, ResearchAction
from research_agent.schemas.state import ResearchState


ALLOWED_ACTIONS: dict[str, frozenset[ActionType]] = {
    "bootstrap": frozenset({ActionType.SEARCH_LITERATURE}),
    "horizon_scan": frozenset(
        {ActionType.SEARCH_LITERATURE, ActionType.MINE_GAPS}
    ),
    "gap_mining": frozenset(
        {ActionType.EXPAND_LITERATURE, ActionType.SYNTHESIZE_GAPS}
    ),
    "gap_synthesis": frozenset(
        {ActionType.EXPAND_LITERATURE, ActionType.REQUEST_TOPIC_SELECTION}
    ),
    "topic_selection": frozenset({ActionType.FORM_IDEA}),
    "idea_formation": frozenset(
        {ActionType.EXPAND_LITERATURE, ActionType.REVIEW_IDEA}
    ),
    "idea_review": frozenset(
        {
            ActionType.FORM_IDEA,
            ActionType.REQUEST_RESOURCES,
            ActionType.EXPAND_LITERATURE,
        }
    ),
    "resource_design": frozenset({ActionType.REPRODUCE_BASELINE}),
    "baseline_reproduction": frozenset(
        {
            ActionType.REQUEST_RESOURCES,
            ActionType.DESIGN_EXPERIMENT,
            ActionType.DIAGNOSE_FAILURE,
        }
    ),
    "core_experiment": frozenset(
        {
            ActionType.RUN_EXPERIMENT,
            ActionType.ANALYZE_RESULT,
            ActionType.DIAGNOSE_FAILURE,
            ActionType.EXPAND_EVIDENCE,
        }
    ),
    "diagnosis": frozenset({ActionType.RUN_EXPERIMENT, ActionType.PIVOT}),
    "pivot": frozenset(
        {ActionType.FORM_IDEA, ActionType.SYNTHESIZE_GAPS, ActionType.RUN_EXPERIMENT}
    ),
    "evidence_expansion": frozenset(
        {ActionType.RUN_EXPERIMENT, ActionType.AUDIT_PAPER}
    ),
    "paper_audit": frozenset({ActionType.RUN_EXPERIMENT, ActionType.WRITE_PAPER}),
    "paper_assembly": frozenset({ActionType.REVIEW_PAPER}),
    "paper_review": frozenset(
        {ActionType.RUN_EXPERIMENT, ActionType.WRITE_PAPER, ActionType.COMPLETE_PROJECT}
    ),
    "complete": frozenset(),
}


class IllegalActionError(ValueError):
    pass


def validate_action(phase: str, action: ResearchAction) -> None:
    if action.action not in ALLOWED_ACTIONS[phase]:
        raise IllegalActionError(
            f"Action {action.action.value} is illegal during phase {phase}"
        )


class Orchestrator:
    def __init__(
        self,
        *,
        client: LLMClient,
        router: ModelRouter,
        prompts: PromptLoader,
        contexts: ContextBuilder,
    ) -> None:
        self.client = client
        self.router = router
        self.prompts = prompts
        self.contexts = contexts

    async def decide(self, state: ResearchState) -> ResearchAction:
        context = self.contexts.for_orchestrator(state)
        messages = [
            Message(
                role="system",
                content=self.prompts.compose(
                    role="orchestrator",
                    policies=["evidence", "resource", "stopping"],
                    phase=state.phase.value,
                    checkpoint_type=(
                        state.human_checkpoint.type
                        if state.human_checkpoint and state.human_checkpoint.required
                        else None
                    ),
                ),
            ),
            Message(role="user", content=json.dumps(context, ensure_ascii=False, default=str)),
        ]
        action = await self.client.generate_structured(
            messages,
            ResearchAction,
            model=self.router.for_role("orchestrator"),
        )
        validate_action(state.phase.value, action)
        return action
