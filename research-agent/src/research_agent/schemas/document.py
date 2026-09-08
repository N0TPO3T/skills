from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from research_agent.schemas.provenance import SourceLocator


class DocumentSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str | None = None
    normalized_role: Literal[
        "abstract",
        "introduction",
        "related_work",
        "method",
        "experiments",
        "results",
        "analysis",
        "limitations",
        "conclusion",
        "appendix",
        "unknown",
    ] = "unknown"
    text: str
    order: int = Field(ge=0)
    source_locator: SourceLocator | None = None


class ParsedReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    raw_text: str
    title: str | None = None
    doi: str | None = None
    source_locator: SourceLocator | None = None


class ParsedTable(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    caption: str | None = None
    text: str
    source_locator: SourceLocator | None = None


class ParsedScientificDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    paper_id: str
    parser: str
    parser_version: str | None = None
    title: str | None = None
    abstract: str | None = None
    sections: list[DocumentSection] = Field(default_factory=list)
    references: list[ParsedReference] = Field(default_factory=list)
    tables: list[ParsedTable] = Field(default_factory=list)
    parse_warnings: list[str] = Field(default_factory=list)
    parse_confidence: float = Field(ge=0.0, le=1.0)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_artifact: str | None = None
    raw_tei: str | None = Field(default=None, exclude=True, repr=False)

