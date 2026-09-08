from __future__ import annotations

from research_agent.schemas.literature import ExtractedStatement, PaperIdentifier, PaperMetadata
from research_agent.schemas.literature_quality import (
    CanonicalPaperRecord,
    MetadataCorroboration,
)
from research_agent.schemas.project import ProjectInfo
from research_agent.schemas.provenance import StatementEpistemicType
from research_agent.schemas.state import ResearchState
from research_agent.services.source_version_comparison_service import (
    SourceVersionComparisonService,
)


def test_result_differences_across_work_versions_are_recorded_for_review() -> None:
    state = ResearchState(project=ProjectInfo(id="demo", name="Demo"))
    for paper_id, venue in (("PAPER-ARXIV", "arXiv"), ("PAPER-CONF", "ICML")):
        metadata = PaperMetadata(
            paper_id=paper_id,
            title="Paper",
            authors=["A. Author"],
            venue=venue,
            identifiers=PaperIdentifier(arxiv_id="2601.1"),
            source_records=[f"https://example.test/{paper_id}"],
            metadata_verified=True,
            verification_confidence=0.9,
        )
        state.literature_quality.canonical_records.append(
            CanonicalPaperRecord(
                paper_id=paper_id,
                metadata=metadata,
                corroboration=MetadataCorroboration(
                    paper_id=paper_id,
                    canonical_title=metadata.title,
                    canonical_authors=metadata.authors,
                    identifiers=metadata.identifiers,
                    corroborating_provider_count=1,
                    confidence=0.9,
                ),
                work_family_id="WORK-1",
                canonical_version=paper_id == "PAPER-CONF",
                confidence=0.9,
            )
        )
    state.literature.statements.extend(
        [
            ExtractedStatement(
                id="STATEMENT-A",
                paper_id="PAPER-ARXIV",
                statement_type="result",
                statement="Accuracy improves by three points.",
                provenance_ids=["PROV-A"],
                confidence=0.9,
                epistemic_type=StatementEpistemicType.DIRECT_RESULT,
            ),
            ExtractedStatement(
                id="STATEMENT-B",
                paper_id="PAPER-CONF",
                statement_type="result",
                statement="Accuracy improves by five points.",
                provenance_ids=["PROV-B"],
                confidence=0.9,
                epistemic_type=StatementEpistemicType.DIRECT_RESULT,
            ),
        ]
    )
    differences = SourceVersionComparisonService().refresh(state)
    assert differences[0].field == "result_claims"
    assert differences[0].source_versions["PAPER-ARXIV"].endswith("three points.")
    assert differences[0].scientifically_material is False
