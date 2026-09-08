from __future__ import annotations

from research_agent.schemas.literature_quality import (
    ContentQualitySummary,
    GapQualitySummary,
    LiteratureQualityReport,
    MetadataQualitySummary,
    ParsingQualitySummary,
    ProvenanceQualitySummary,
)
from research_agent.schemas.state import ResearchState
from research_agent.services.gap_evidence_service import GapEvidenceService
from research_agent.storage.artifact_store import ArtifactStore


class LiteratureQualityReportService:
    def __init__(self, artifacts: ArtifactStore) -> None:
        self.artifacts = artifacts

    def build(self, state: ResearchState) -> LiteratureQualityReport:
        verified = [
            paper
            for paper in state.literature.paper_metadata
            if paper.metadata_verified and not paper.synthetic_test_data
        ]
        corroborations = state.literature_quality.corroborations
        multi_source = [
            item for item in corroborations if item.corroborating_provider_count >= 2
        ]
        conflicts = [item for item in corroborations if item.conflicts]
        fulltext_ids = {
            content.paper_id
            for content in state.literature.contents
            if content.content_verified
            and content.content_type in {"full_text", "html", "pdf_text"}
        }
        abstract_ids = {
            content.paper_id
            for content in state.literature.contents
            if content.content_verified and content.content_type == "abstract_only"
        }
        parsed = state.literature_quality.parsed_documents
        acquisitions = state.literature_quality.fulltext_acquisitions
        statements = state.literature.statements
        provenance = {item.id: item for item in state.literature.provenance_records}
        missing_provenance = sum(
            not statement.provenance_ids
            or any(item not in provenance for item in statement.provenance_ids)
            for statement in statements
        )
        real_gaps = [gap for gap in state.gaps.candidates if not gap.synthetic_test_data]
        gap_evidence = GapEvidenceService()
        statements_by_id = {statement.id: statement for statement in statements}
        supported_gaps = [
            gap
            for gap in real_gaps
            if gap.evidence_summary
            and gap.evidence_summary.supporting_statement_count > 0
            and gap.evidence_summary.independent_paper_count >= 2
            and all(
                statement is not None
                and gap_evidence.validate_statement(
                    state.literature, statement, state.literature_quality
                )
                for statement_id in gap.supporting_statement_ids
                for statement in [statements_by_id.get(statement_id)]
            )
        ]
        report = LiteratureQualityReport(
            project_id=state.project.id,
            metadata=MetadataQualitySummary(
                multi_source_rate=_rate(len(multi_source), len(verified)),
                conflict_rate=_rate(len(conflicts), len(corroborations)),
            ),
            content=ContentQualitySummary(
                fulltext_rate=_rate(len(fulltext_ids), len(verified)),
                abstract_only_rate=_rate(
                    len(abstract_ids - fulltext_ids), len(verified)
                ),
                unavailable_rate=_rate(
                    len(
                        {
                            paper.paper_id for paper in verified
                        }
                        - fulltext_ids
                        - abstract_ids
                    ),
                    len(verified),
                ),
            ),
            parsing=ParsingQualitySummary(
                success_rate=_rate(len(parsed), len(acquisitions)),
                warning_rate=_rate(
                    sum(bool(document.parse_warnings) for document in parsed),
                    len(parsed),
                ),
            ),
            extraction=state.literature_quality.capability_statuses,
            provenance=ProvenanceQualitySummary(
                missing_provenance_rate=_rate(missing_provenance, len(statements))
            ),
            gaps=GapQualitySummary(
                verified_gap_support_rate=_rate(len(supported_gaps), len(real_gaps))
            ),
            known_blindspots=[
                "Search coverage and extraction quality are reported separately.",
                "Provider agreement does not establish semantic correctness.",
                "Paywalled, authentication-gated, robots-disallowed, and unparseable documents remain unavailable.",
                "Capabilities without human gold positives remain disabled.",
                "The default semantic metric is deterministic lexical overlap, not an LLM judge.",
            ],
        )
        state.literature_quality.quality_reports.append(report)
        state.literature_quality.latest_quality_report_artifact = (
            self.artifacts.write_json(
                "artifacts/literature/quality/literature_quality_report.json",
                report.model_dump(mode="json"),
            )
        )
        return report


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None
