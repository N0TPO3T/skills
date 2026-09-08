from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from research_agent.schemas.provenance import (
    PromptMetadata,
    ProvenanceRecord,
    SourceLocator,
    StatementEpistemicType,
)


class PaperIdentifier(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doi: str | None = None
    arxiv_id: str | None = None
    semantic_id: str | None = None
    openalex_id: str | None = None
    canonical_url: str | None = None


class LiteratureSearchQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    query: str
    purpose: Literal[
        "canonical",
        "recent",
        "baseline",
        "failure_analysis",
        "adjacent_method",
        "novelty_check",
        "citation_expansion",
        "implementation",
    ]
    target_year_from: int | None = None
    target_year_to: int | None = None
    related_paper_ids: list[str] = Field(default_factory=list)
    priority: float = Field(ge=0.0, le=1.0)


class PaperCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    query_id: str
    raw_title: str
    raw_authors: list[str] = Field(default_factory=list)
    raw_year: int | None = None
    source_provider: str
    source_url: str | None = None
    identifiers: PaperIdentifier = Field(default_factory=PaperIdentifier)
    retrieval_rank: int | None = Field(default=None, ge=1)
    retrieval_score: float | None = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: Literal[
        "candidate", "metadata_verified", "content_verified", "rejected"
    ] = "candidate"
    rejection_reason: str | None = None
    synthetic_test_data: bool = False


class PaperMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper_id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    publication_date: date | None = None
    venue: str | None = None
    identifiers: PaperIdentifier = Field(default_factory=PaperIdentifier)
    abstract: str | None = None
    publication_status: Literal[
        "preprint", "conference", "journal", "workshop", "unknown"
    ] = "unknown"
    source_records: list[str] = Field(default_factory=list)
    metadata_verified: bool = False
    verification_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    synthetic_test_data: bool = False
    publication_integrity_status: Literal[
        "normal", "corrected", "retracted", "unknown"
    ] = "unknown"

    @model_validator(mode="after")
    def validate_verified_metadata(self) -> "PaperMetadata":
        if self.metadata_verified:
            if self.synthetic_test_data:
                raise ValueError("Synthetic paper metadata cannot be verified as real")
            if not self.title.strip() or not self.authors or not self.source_records:
                raise ValueError(
                    "Verified metadata requires title, authors, and source records"
                )
            if self.verification_confidence < 0.8:
                raise ValueError("Verified metadata requires confidence >= 0.8")
        return self


class PaperContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper_id: str
    content_type: Literal["full_text", "html", "pdf_text", "abstract_only"]
    artifact_path: str = ""
    source_url: str | None = None
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    parser_name: str
    parser_version: str | None = None
    content_verified: bool = False
    synthetic_test_data: bool = False
    version_type: Literal[
        "preprint",
        "accepted_manuscript",
        "version_of_record",
        "repository_copy",
        "unknown",
    ] = "unknown"
    content_version_label: str | None = None
    source_paper_id: str | None = None
    source_mime_type: str | None = None
    raw_text: str | None = Field(default=None, exclude=True, repr=False)

    @model_validator(mode="after")
    def validate_verified_content(self) -> "PaperContent":
        if self.content_verified:
            if self.synthetic_test_data:
                raise ValueError("Synthetic paper content cannot be verified as real")
            if not self.artifact_path or not self.sha256:
                raise ValueError(
                    "Verified content requires an artifact path and content hash"
                )
        return self


class PaperExtractionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    problem: str | None = None
    main_claim: str | None = None
    method_summary: str | None = None
    core_assumptions: list[str] = Field(default_factory=list)
    training_requirements: list[str] = Field(default_factory=list)
    inference_requirements: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)
    datasets: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    baselines: list[str] = Field(default_factory=list)
    main_results: list[str] = Field(default_factory=list)
    ablations: list[str] = Field(default_factory=list)
    limitations_claimed: list[str] = Field(default_factory=list)
    limitations_inferred: list[str] = Field(default_factory=list)
    failure_modes: list[str] = Field(default_factory=list)
    compute_notes: list[str] = Field(default_factory=list)
    open_source_urls: list[str] = Field(default_factory=list)
    extraction_confidence: float = Field(ge=0.0, le=1.0)


class PaperExtraction(PaperExtractionDraft):
    paper_id: str
    provenance_ids: list[str] = Field(min_length=1)
    extractor_model: str
    prompt_metadata: PromptMetadata
    partial: bool = False
    content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    content_version_label: str | None = None
    source_paper_id: str | None = None


class ExtractedStatement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    paper_id: str
    statement_type: Literal[
        "problem",
        "claim",
        "method",
        "result",
        "limitation_claimed",
        "limitation_inferred",
        "failure_mode",
        "assumption",
    ]
    statement: str
    provenance_ids: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    epistemic_type: StatementEpistemicType = StatementEpistemicType.AGENT_INFERRED

    @model_validator(mode="after")
    def preserve_inference_boundary(self) -> "ExtractedStatement":
        if (
            self.statement_type == "limitation_inferred"
            and self.epistemic_type != StatementEpistemicType.AGENT_INFERRED
        ):
            raise ValueError(
                "An inferred limitation must remain epistemically agent-inferred"
            )
        if (
            self.epistemic_type == StatementEpistemicType.DIRECT_RESULT
            and self.statement_type != "result"
        ):
            raise ValueError("direct_result epistemic type requires a result statement")
        return self


class PaperRelation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_paper_id: str
    target_paper_id: str
    relation: Literal["same_work_version", "extends", "cites", "related"]
    confidence: float = Field(ge=0.0, le=1.0)


class LiteratureCoverageReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    metadata_verified_count: int = Field(ge=0)
    content_verified_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    publication_year_distribution: dict[int, int] = Field(default_factory=dict)
    cluster_coverage: dict[str, int] = Field(default_factory=dict)
    unresolved_search_questions: list[str] = Field(default_factory=list)
    known_search_blindspots: list[str] = Field(default_factory=list)
    sufficient_for_gap_synthesis: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SearchRoundMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_verified_papers: int = Field(ge=0)
    new_clusters: int = Field(ge=0)
    new_gap_evidence: int = Field(ge=0)
    novelty_landscape_changed: bool
    marginal_information_gain: float = Field(ge=0.0, le=1.0)


class LiteratureFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: Literal[
        "search",
        "resolve",
        "fetch",
        "extract",
        "parse",
        "corroborate",
        "acquire",
        "validate",
        "evaluate",
    ]
    provider: str
    entity_id: str | None = None
    error_type: str
    message: str
    retryable: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LiteratureSearchRound(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    providers: list[str]
    provider_configuration: dict[str, dict[str, object]] = Field(default_factory=dict)
    query_ids: list[str]
    raw_result_count: int = Field(ge=0)
    selected_candidate_ids: list[str]
    verification_decisions: dict[str, str] = Field(default_factory=dict)
    extractor_model: str
    extractor_prompt_version: str
    extractor_prompt_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    metrics: SearchRoundMetrics


class NoveltySearchRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    proposed_method: str
    mechanism: str
    task: str
    setting: str
    query_ids: list[str]
    searched_providers: list[str]
    search_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    candidate_count: int = Field(ge=0)
    verified_paper_count: int = Field(ge=0)
    closest_prior_work_ids: list[str] = Field(default_factory=list)
    bounded_conclusion: str


class NoveltySearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposed_method: str
    mechanism: str
    task: str
    setting: str


class PaperReference(BaseModel):
    """Backward-compatible M6 literature summary view."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    url: str | None = None
    identifier: str | None = None
    verified: bool = False
    main_claim: str = ""
    method: str = ""
    limitations_claimed: list[str] = Field(default_factory=list)
    limitations_inferred: list[str] = Field(default_factory=list)
    open_source: bool | None = None
    relevance: float = Field(default=0.0, ge=0.0, le=1.0)
    provenance: str = "unknown"
    synthetic_test_data: bool = False


class LiteratureState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queries: list[str] = Field(default_factory=list)
    papers: list[PaperReference] = Field(default_factory=list)
    clusters: list[str] = Field(default_factory=list)
    matrix_artifact: str | None = None

    search_queries: list[LiteratureSearchQuery] = Field(default_factory=list)
    candidates: list[PaperCandidate] = Field(default_factory=list)
    paper_metadata: list[PaperMetadata] = Field(default_factory=list)
    contents: list[PaperContent] = Field(default_factory=list)
    extractions: list[PaperExtraction] = Field(default_factory=list)
    statements: list[ExtractedStatement] = Field(default_factory=list)
    provenance_records: list[ProvenanceRecord] = Field(default_factory=list)
    relations: list[PaperRelation] = Field(default_factory=list)
    candidate_paper_links: dict[str, str] = Field(default_factory=dict)
    failures: list[LiteratureFailure] = Field(default_factory=list)
    search_rounds: list[LiteratureSearchRound] = Field(default_factory=list)
    coverage_reports: list[LiteratureCoverageReport] = Field(default_factory=list)
    search_round_metrics: list[SearchRoundMetrics] = Field(default_factory=list)
    novelty_searches: list[NoveltySearchRecord] = Field(default_factory=list)
    literature_map_artifact: str | None = None
    coverage_artifact: str | None = None
