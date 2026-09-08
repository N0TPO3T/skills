from __future__ import annotations

from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str


SchemaT = TypeVar("SchemaT", bound=BaseModel)


class LLMClient(Protocol):
    async def generate(
        self,
        messages: list[Message],
        *,
        model: str,
        temperature: float,
    ) -> str: ...

    async def generate_structured(
        self,
        messages: list[Message],
        schema: type[SchemaT],
        *,
        model: str,
    ) -> SchemaT: ...

