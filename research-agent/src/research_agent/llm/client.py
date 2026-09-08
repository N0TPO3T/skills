from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any, TypeVar
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from pydantic import BaseModel

from research_agent.llm.base import Message
from research_agent.llm.structured_output import parse_structured


SchemaT = TypeVar("SchemaT", bound=BaseModel)


class MockLLMClient:
    """Deterministic fixture-backed client; it never performs network I/O."""

    def __init__(
        self,
        fixtures: dict[str, dict[str, Any] | Callable[[], dict[str, Any]]] | None = None,
    ) -> None:
        self.fixtures = fixtures or {}
        self.calls: list[dict[str, Any]] = []

    async def generate(
        self,
        messages: list[Message],
        *,
        model: str,
        temperature: float,
    ) -> str:
        self.calls.append({"model": model, "messages": messages, "structured": False})
        return "synthetic_test_data"

    async def generate_structured(
        self,
        messages: list[Message],
        schema: type[SchemaT],
        *,
        model: str,
    ) -> SchemaT:
        self.calls.append(
            {"model": model, "messages": messages, "schema": schema.__name__}
        )
        fixture = self.fixtures.get(schema.__name__)
        if fixture is None:
            raise KeyError(f"No mock fixture registered for {schema.__name__}")
        value = fixture() if callable(fixture) else fixture
        return schema.model_validate(value)


class OpenAICompatibleClient:
    """Small adapter for APIs exposing the OpenAI chat-completions contract."""

    def __init__(self, *, base_url: str, api_key: str, timeout_seconds: float = 120) -> None:
        self.endpoint = base_url.rstrip("/") + "/chat/completions"
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    async def generate(
        self,
        messages: list[Message],
        *,
        model: str,
        temperature: float,
    ) -> str:
        payload = {
            "model": model,
            "temperature": temperature,
            "messages": [message.model_dump() for message in messages],
        }
        data = await asyncio.to_thread(self._post, payload)
        return str(data["choices"][0]["message"]["content"])

    async def generate_structured(
        self,
        messages: list[Message],
        schema: type[SchemaT],
        *,
        model: str,
    ) -> SchemaT:
        schema_instruction = Message(
            role="system",
            content=(
                "Return exactly one JSON object matching this JSON Schema:\n"
                + json.dumps(schema.model_json_schema(), ensure_ascii=False)
            ),
        )
        text = await self.generate(
            [*messages, schema_instruction], model=model, temperature=0.0
        )
        return parse_structured(text, schema)

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM provider returned HTTP {exc.code}: {body}") from exc

