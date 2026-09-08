from __future__ import annotations

import pytest

from research_agent.core.context_builder import ContextBuilder
from research_agent.core.orchestrator import IllegalActionError, Orchestrator
from research_agent.llm.client import MockLLMClient
from research_agent.llm.router import ModelRouter
from research_agent.prompts.loader import PromptLoader


async def test_orchestrator_parses_structured_action(state) -> None:
    client = MockLLMClient(
        {
            "ResearchAction": {
                "action": "search_literature",
                "reason": "bootstrap requires a bounded scan",
                "priority": 0.9,
            }
        }
    )
    orchestrator = Orchestrator(
        client=client,
        router=ModelRouter({"orchestrator": "mock"}),
        prompts=PromptLoader(),
        contexts=ContextBuilder(),
    )
    action = await orchestrator.decide(state)
    assert action.action.value == "search_literature"


async def test_orchestrator_rejects_illegal_action(state) -> None:
    client = MockLLMClient(
        {
            "ResearchAction": {
                "action": "write_paper",
                "reason": "premature",
                "priority": 0.9,
            }
        }
    )
    orchestrator = Orchestrator(
        client=client,
        router=ModelRouter({"orchestrator": "mock"}),
        prompts=PromptLoader(),
        contexts=ContextBuilder(),
    )
    with pytest.raises(IllegalActionError):
        await orchestrator.decide(state)

