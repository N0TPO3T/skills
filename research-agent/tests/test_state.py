from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from research_agent.schemas.state import ResearchState
from research_agent.storage.state_store import StateStore


def test_state_serialization_roundtrip(state: ResearchState) -> None:
    restored = ResearchState.model_validate_json(state.model_dump_json())
    assert restored == state
    assert restored.schema_version == "1.2"


def test_state_rejects_unknown_fields(state: ResearchState) -> None:
    payload = json.loads(state.model_dump_json())
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        ResearchState.model_validate(payload)


def test_state_store_roundtrip(state: ResearchState, projects_root) -> None:
    store = StateStore(projects_root)
    store.save(state)
    assert store.load("demo").project.research_direction == "adaptive reasoning"


def test_v1_state_remains_loadable(state: ResearchState) -> None:
    payload = state.model_dump(mode="json")
    payload["schema_version"] = "1.0"
    payload["literature"] = {
        "queries": ["legacy query"],
        "papers": [],
        "clusters": [],
        "matrix_artifact": None,
    }
    restored = ResearchState.model_validate(payload)
    assert restored.schema_version == "1.0"
    assert restored.literature.search_queries == []


def test_v11_state_remains_loadable(state: ResearchState) -> None:
    payload = state.model_dump(mode="json")
    payload["schema_version"] = "1.1"
    payload.pop("literature_quality")
    restored = ResearchState.model_validate(payload)
    assert restored.schema_version == "1.1"
    assert restored.literature_quality.capability_statuses == []
