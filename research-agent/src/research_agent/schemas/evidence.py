from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EvidenceLevel(str, Enum):
    E0_SPECULATION = "E0"
    E1_LITERATURE = "E1"
    E2_SINGLE_EXPERIMENT = "E2"
    E3_REPLICATED = "E3"
    E4_ROBUST = "E4"


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source_type: Literal["hypothesis", "paper", "experiment"]
    source_ids: list[str] = Field(default_factory=list)
    level: EvidenceLevel
    summary: str
    artifact: str | None = None
    synthetic_test_data: bool = False


class EvidenceState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[Evidence] = Field(default_factory=list)

