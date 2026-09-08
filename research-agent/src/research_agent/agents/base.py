from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel

from research_agent.llm.base import LLMClient, Message
from research_agent.llm.router import ModelRouter
from research_agent.prompts.loader import PromptLoader


SchemaT = TypeVar("SchemaT", bound=BaseModel)


class BaseAgent:
    role: str

    def __init__(
        self,
        *,
        client: LLMClient,
        router: ModelRouter,
        prompts: PromptLoader,
    ) -> None:
        self.client = client
        self.router = router
        self.prompts = prompts

    async def run(
        self,
        *,
        prompt_profile: str,
        context: dict[str, object],
        schema: type[SchemaT],
        policies: list[str],
        phase: str | None = None,
        checkpoint_type: str | None = None,
    ) -> SchemaT:
        messages = [
            Message(
                role="system",
                content=self.prompts.compose(
                    role=prompt_profile,
                    policies=policies,
                    phase=phase,
                    checkpoint_type=checkpoint_type,
                ),
            ),
            Message(role="user", content=json.dumps(context, ensure_ascii=False, default=str)),
        ]
        return await self.client.generate_structured(
            messages, schema, model=self.router.for_role(self.role)
        )
