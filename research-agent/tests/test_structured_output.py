from __future__ import annotations

import pytest
from pydantic import BaseModel

from research_agent.llm.client import MockLLMClient
from research_agent.llm.structured_output import StructuredOutputError, parse_structured
from research_agent.prompts.loader import PromptLoader


class Answer(BaseModel):
    value: int


def test_structured_output_accepts_fenced_json() -> None:
    assert parse_structured('```json\n{"value": 3}\n```', Answer).value == 3


def test_structured_output_rejects_non_json() -> None:
    with pytest.raises(StructuredOutputError):
        parse_structured("not structured", Answer)


async def test_mock_client_validates_fixture() -> None:
    client = MockLLMClient({"Answer": {"value": 7}})
    result = await client.generate_structured([], Answer, model="mock")
    assert result.value == 7


def test_prompt_loader_composes_role_and_policies() -> None:
    loader = PromptLoader()
    prompt = loader.compose(
        role="failure_diagnosis", policies=["evidence", "experiment"]
    )
    assert "Evidence levels are strict" in prompt
    assert "Rank candidate explanations" in prompt
    assert "paper/reviewer" not in prompt
    metadata = loader.metadata(
        role="failure_diagnosis", policies=["evidence", "experiment"]
    )
    assert metadata.profile == "failure_diagnosis"
    assert len(metadata.sha256) == 64
