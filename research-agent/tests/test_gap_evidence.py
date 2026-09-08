from __future__ import annotations

import pytest

from research_agent.schemas.gap import ResearchGap
from research_agent.schemas.literature import (
    ExtractedStatement,
    LiteratureState,
    PaperContent,
    PaperMetadata,
    PaperRelation,
)
from research_agent.schemas.literature_quality import (
    ExtractionCapabilityStatus,
    LiteratureQualityState,
)
from research_agent.schemas.provenance import ProvenanceRecord
from research_agent.schemas.provenance import StatementEpistemicType
from research_agent.services.gap_evidence_service import (
    GapEvidenceService,
    InvalidGapEvidenceError,
)


def gap(statement_id: str) -> ResearchGap:
    return ResearchGap(
        id="GAP-1",
        title="Gap",
        supporting_statement_ids=[statement_id],
        common_limitation="Known failure",
        root_cause_hypothesis="Missing mechanism",
        why_existing_methods_fail="They lack the mechanism",
        missing_capability="Mechanism",
        minimum_viable_experiment="Test mechanism",
        expected_signal="Improvement",
        falsification_criterion="No improvement",
        novelty_score=0.5,
        feasibility_score=0.5,
        research_value_score=0.5,
        publication_score=0.5,
        risk_score=0.5,
    )


def literature(*, verified: bool = True, with_provenance: bool = True) -> LiteratureState:
    metadata = PaperMetadata(
        paper_id="PAPER-1",
        title="Paper",
        authors=["A. Author"],
        source_records=["https://example.test/paper"],
        metadata_verified=verified,
        verification_confidence=0.9 if verified else 0.0,
    )
    content = PaperContent(
        paper_id="PAPER-1",
        content_type="pdf_text",
        artifact_path="artifacts/literature/papers/PAPER-1/content.txt",
        sha256="d" * 64,
        parser_name="test",
        content_verified=verified,
    )
    statement = ExtractedStatement(
        id="STATEMENT-1",
        paper_id="PAPER-1",
        statement_type="limitation_claimed",
        statement="The method fails under shift.",
        provenance_ids=["PROV-1"],
        confidence=0.9,
        epistemic_type=StatementEpistemicType.AUTHOR_STATED,
    )
    records = (
        [
            ProvenanceRecord(
                id="PROV-1",
                entity_type="extracted_statement",
                entity_id="STATEMENT-1",
                source_type="paper_full_text",
                source_id="PAPER-1",
                artifact_path=content.artifact_path,
                confidence=0.9,
            )
        ]
        if with_provenance
        else []
    )
    return LiteratureState(
        paper_metadata=[metadata],
        contents=[content],
        statements=[statement],
        provenance_records=records,
    )


def quality(status: str = "validated") -> LiteratureQualityState:
    return LiteratureQualityState(
        capability_statuses=[
            ExtractionCapabilityStatus(
                capability="limitations",
                precision=0.95,
                recall=0.8,
                status=status,
                evaluation_id="EVAL-1",
                reason="fixture benchmark",
            )
        ]
    )


def test_gap_references_valid_statement_ids() -> None:
    item = gap("STATEMENT-1")
    summary = GapEvidenceService().summarize_and_validate(
        literature(), item, quality()
    )
    assert item.supporting_papers == ["PAPER-1"]
    assert summary.supporting_statement_count == 1
    assert summary.content_verified_paper_count == 1


def test_missing_provenance_cannot_become_verified_statement() -> None:
    with pytest.raises(InvalidGapEvidenceError):
        GapEvidenceService().summarize_and_validate(
            literature(with_provenance=False), gap("STATEMENT-1"), quality()
        )


def test_unverified_paper_cannot_count_as_gap_support() -> None:
    with pytest.raises(InvalidGapEvidenceError):
        GapEvidenceService().summarize_and_validate(
            literature(verified=False), gap("STATEMENT-1"), quality()
        )


def test_same_work_versions_count_as_one_independent_paper() -> None:
    state = literature()
    state.paper_metadata.append(
        state.paper_metadata[0].model_copy(
            update={
                "paper_id": "PAPER-2",
                "source_records": ["https://example.test/paper-2"],
            }
        )
    )
    state.contents.append(state.contents[0].model_copy(update={"paper_id": "PAPER-2"}))
    state.statements.append(
        state.statements[0].model_copy(
            update={
                "id": "STATEMENT-2",
                "paper_id": "PAPER-2",
                "provenance_ids": ["PROV-2"],
            }
        )
    )
    state.provenance_records.append(
        state.provenance_records[0].model_copy(
            update={
                "id": "PROV-2",
                "entity_id": "STATEMENT-2",
                "source_id": "PAPER-2",
            }
        )
    )
    state.relations.append(
        PaperRelation(
            source_paper_id="PAPER-1",
            target_paper_id="PAPER-2",
            relation="same_work_version",
            confidence=0.98,
        )
    )
    item = gap("STATEMENT-1")
    item.supporting_statement_ids.append("STATEMENT-2")
    summary = GapEvidenceService().summarize_and_validate(state, item, quality())
    assert summary.independent_paper_count == 1
