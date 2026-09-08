from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from research_agent.schemas.document import ParsedScientificDocument
from research_agent.schemas.literature import PaperIdentifier, PaperMetadata
from research_agent.schemas.provenance import SourceLocator, StatementEpistemicType


class ProviderCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")
    search: bool = False
    metadata_lookup: bool = False
    abstract: bool = False
    full_text: bool = False
    citation_graph: bool = False
    references: bool = False
    open_access_location: bool = False


class MetadataObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    publication_date: date | None = None
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MetadataConflict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str
    values: dict[str, Any]
    severity: Literal["low", "medium", "high"]
    resolution: str | None = None
    resolved: bool = False


class MetadataCorroboration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    paper_id: str
    observations: list[MetadataObservation] = Field(default_factory=list)
    canonical_title: str
    canonical_authors: list[str]
    identifiers: PaperIdentifier
    conflicts: list[MetadataConflict] = Field(default_factory=list)
    corroborating_provider_count: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)


class CanonicalPaperRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    paper_id: str
    metadata: PaperMetadata
    corroboration: MetadataCorroboration
    work_family_id: str | None = None
    canonical_version: bool = False
    confidence: float = Field(ge=0.0, le=1.0)


class FullTextLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    paper_id: str
    url: str
    source_provider: str
    version_type: Literal[
        "preprint",
        "accepted_manuscript",
        "version_of_record",
        "repository_copy",
        "unknown",
    ] = "unknown"
    access_type: Literal["open", "unknown", "restricted"] = "unknown"
    mime_type: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    content_version_label: str | None = None
    license: str | None = None


class FullTextAcquisitionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    paper_id: str
    location: FullTextLocation
    artifact_path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_count: int = Field(ge=1)
    validated: bool
    acquired_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class VersionDifference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    work_family_id: str
    field: str
    source_versions: dict[str, str]
    scientifically_material: bool


class VerificationTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    paper_id: str
    statement_id: str
    reason: str
    priority: float = Field(ge=0.0, le=1.0)
    status: Literal["pending", "accepted", "weak", "rejected", "edited"] = "pending"
    epistemic_type: StatementEpistemicType | None = None
    source_locator: SourceLocator | None = None
    supported_scope: str | None = None
    overstatement: str | None = None
    content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    verifier: str | None = None
    verification_artifact: str | None = None
    verified_at: datetime | None = None


class FocusedVerificationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    statement_id: str
    verdict: Literal["accept", "weak", "reject"]
    epistemic_type: StatementEpistemicType
    supported_scope: str
    overstatement: str | None = None
    source_passage_id: str
    reason: str


class FocusedVerificationBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str
    decisions: list[FocusedVerificationDecision] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)


class GoldStatement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    statement: str
    source_locator: SourceLocator
    acceptable_paraphrases: list[str] = Field(default_factory=list)
    notes: str | None = None


class GoldPaperAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    paper_id: str
    problem: list[GoldStatement] = Field(default_factory=list)
    main_claims: list[GoldStatement] = Field(default_factory=list)
    methods: list[GoldStatement] = Field(default_factory=list)
    assumptions: list[GoldStatement] = Field(default_factory=list)
    results: list[GoldStatement] = Field(default_factory=list)
    limitations_claimed: list[GoldStatement] = Field(default_factory=list)
    failure_modes: list[GoldStatement] = Field(default_factory=list)


class MetricSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    precision: float | None = Field(default=None, ge=0.0, le=1.0)
    recall: float | None = Field(default=None, ge=0.0, le=1.0)
    f1: float | None = Field(default=None, ge=0.0, le=1.0)
    matched_count: int = Field(default=0, ge=0)
    predicted_count: int = Field(default=0, ge=0)
    gold_count: int = Field(default=0, ge=0)


class ExtractionEvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    exact_metrics: dict[str, MetricSummary] = Field(default_factory=dict)
    semantic_metrics: dict[str, MetricSummary] = Field(default_factory=dict)
    semantic_evaluator: str = "deterministic_lexical"
    unsupported_statement_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    wrong_attribution_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    wrong_epistemic_type_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    locator_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    paper_level_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    evaluated_paper_count: int = Field(default=0, ge=0)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ExtractionCapabilityStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capability: str
    precision: float | None = Field(default=None, ge=0.0, le=1.0)
    recall: float | None = Field(default=None, ge=0.0, le=1.0)
    status: Literal["validated", "experimental", "disabled"]
    evaluation_id: str | None = None
    reason: str


class LiteratureQualityGateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    min_limitation_precision: float = Field(default=0.90, ge=0.0, le=1.0)
    min_result_precision: float = Field(default=0.95, ge=0.0, le=1.0)
    min_other_precision: float = Field(default=0.90, ge=0.0, le=1.0)
    max_unsupported_statement_rate: float = Field(default=0.03, ge=0.0, le=1.0)
    max_wrong_attribution_rate: float = Field(default=0.02, ge=0.0, le=1.0)


class MetadataQualitySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    multi_source_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    conflict_rate: float | None = Field(default=None, ge=0.0, le=1.0)


class ContentQualitySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fulltext_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    abstract_only_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    unavailable_rate: float | None = Field(default=None, ge=0.0, le=1.0)


class ParsingQualitySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    success_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    warning_rate: float | None = Field(default=None, ge=0.0, le=1.0)


class ProvenanceQualitySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    missing_provenance_rate: float | None = Field(default=None, ge=0.0, le=1.0)


class GapQualitySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verified_gap_support_rate: float | None = Field(default=None, ge=0.0, le=1.0)


class LiteratureQualityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str
    metadata: MetadataQualitySummary
    content: ContentQualitySummary
    parsing: ParsingQualitySummary
    extraction: list[ExtractionCapabilityStatus] = Field(default_factory=list)
    provenance: ProvenanceQualitySummary
    gaps: GapQualitySummary
    known_blindspots: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LiteratureQualityState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metadata_observations: list[MetadataObservation] = Field(default_factory=list)
    corroborations: list[MetadataCorroboration] = Field(default_factory=list)
    canonical_records: list[CanonicalPaperRecord] = Field(default_factory=list)
    fulltext_locations: list[FullTextLocation] = Field(default_factory=list)
    fulltext_acquisitions: list[FullTextAcquisitionResult] = Field(default_factory=list)
    parsed_documents: list[ParsedScientificDocument] = Field(default_factory=list)
    version_differences: list[VersionDifference] = Field(default_factory=list)
    verification_tasks: list[VerificationTask] = Field(default_factory=list)
    extraction_evaluations: list[ExtractionEvaluationResult] = Field(
        default_factory=list
    )
    capability_statuses: list[ExtractionCapabilityStatus] = Field(default_factory=list)
    quality_reports: list[LiteratureQualityReport] = Field(default_factory=list)
    gold_annotation_artifacts: list[str] = Field(default_factory=list)
    latest_quality_report_artifact: str | None = None
