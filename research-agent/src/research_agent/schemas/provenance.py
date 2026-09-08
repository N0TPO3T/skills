from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StatementEpistemicType(str, Enum):
    AUTHOR_STATED = "author_stated"
    DIRECT_RESULT = "direct_result"
    AGENT_INFERRED = "agent_inferred"


class SourceLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_id: str | None = None
    section_title: str | None = None
    paragraph_index: int | None = Field(default=None, ge=0)
    page: int | None = Field(default=None, ge=1)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)


class PromptMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: str
    version: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ProvenanceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    entity_type: str
    entity_id: str
    source_type: Literal[
        "paper_metadata",
        "paper_abstract",
        "paper_full_text",
        "paper_pdf",
        "parsed_document",
        "web_source",
        "human_input",
        "experiment",
        "synthetic_test_data",
    ]
    source_id: str
    artifact_path: str | None = None
    extraction_method: str | None = None
    source_locator: SourceLocator | str | None = None
    retrieved_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    confidence: float = Field(ge=0.0, le=1.0)
    notes: str | None = None
