from __future__ import annotations

import json
from typing import Any, TypeVar

from pydantic import BaseModel


SchemaT = TypeVar("SchemaT", bound=BaseModel)


class StructuredOutputError(ValueError):
    pass


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        first_newline = stripped.find("\n")
        last_fence = stripped.rfind("```")
        if first_newline != -1 and last_fence > first_newline:
            stripped = stripped[first_newline + 1 : last_fence].strip()
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        start = stripped.find("{")
        if start < 0:
            raise StructuredOutputError("No JSON object found in model output")
        try:
            value, _ = decoder.raw_decode(stripped[start:])
        except json.JSONDecodeError as exc:
            raise StructuredOutputError("Invalid JSON object in model output") from exc
    if not isinstance(value, dict):
        raise StructuredOutputError("Structured model output must be a JSON object")
    return value


def parse_structured(text: str, schema: type[SchemaT]) -> SchemaT:
    return schema.model_validate(extract_json_object(text))

