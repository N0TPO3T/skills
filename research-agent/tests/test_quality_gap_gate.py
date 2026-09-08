from __future__ import annotations

import pytest

from research_agent.schemas.gap import ResearchGap
from research_agent.schemas.literature import (
    ExtractedStatement,
    LiteratureState,
    PaperContent,
    PaperMetadata,
)
from research_agent.schemas.literature_quality import (
    ExtractionCapabilityStatus,
    LiteratureQualityState,
    VerificationTask,
)
from research_agent.schemas.provenance import ProvenanceRecord, StatementEpistemicType
from research_agent.services.gap_evidence_service import (
    GapEvidenceService,
    InvalidGapEvidenceError,
)


def fixture(epistemic: str = "author_stated"):
    content = PaperContent(
        paper_id="PAPER-1",
        content_type="pdf_text",
        artifact_path="artifacts/literature/papers/PAPER-1/content.txt",
        sha256="a" * 64,
        parser_name="fixture",
        content_verified=True,
    )
    statement = ExtractedStatement(
        id="STATEMENT-1",
        paper_id="PAPER-1",
        statement_type="method",
        statement="The authors use adaptive allocation.",
        provenance_ids=["PROV-1"],
        confidence=0.8,
        epistemic_type=epistemic,
    )
    literature = LiteratureState(
        paper_metadata=[
            PaperMetadata(
                paper_id="PAPER-1",
                title="Paper",
                authors=["A. Author"],
                source_records=["https://example.test"],
                metadata_verified=True,
                verification_confidence=0.9,
            )
        ],
        contents=[content],
        statements=[statement],
        provenance_records=[
            ProvenanceRecord(
                id="PROV-1",
                entity_type="extracted_statement",
                entity_id="STATEMENT-1",
                source_type="paper_full_text",
                source_id="PAPER-1",
                artifact_path=content.artifact_path,
                confidence=0.8,
            )
        ],
    )
    return literature, statement


def quality(status: str) -> LiteratureQualityState:
    return LiteratureQualityState(
        capability_statuses=[
            ExtractionCapabilityStatus(
                capability="method",
                precision=0.95 if status != "disabled" else None,
                recall=0.8 if status != "disabled" else None,
                status=status,
                evaluation_id="EVAL-1",
                reason="fixture",
            )
        ]
    )


def test_validated_capability_is_accepted() -> None:
    literature, statement = fixture()
    assert GapEvidenceService().validate_statement(
        literature, statement, quality("validated")
    )


def test_experimental_capability_requires_human_verification() -> None:
    literature, statement = fixture()
    current = quality("experimental")
    assert not GapEvidenceService().validate_statement(literature, statement, current)
    current.verification_tasks.append(
        VerificationTask(
            id="VERIFY-1",
            paper_id="PAPER-1",
            statement_id=statement.id,
            reason="central evidence",
            priority=1.0,
            status="accepted",
        )
    )
    assert GapEvidenceService().validate_statement(literature, statement, current)


def test_disabled_capability_is_blocked() -> None:
    literature, statement = fixture()
    assert (
        GapEvidenceService().classify_statement(
            literature, statement, quality("disabled")
        )
        == "blocked"
    )


def test_agent_inference_requires_human_acceptance_even_when_validated() -> None:
    literature, statement = fixture(StatementEpistemicType.AGENT_INFERRED)
    current = quality("validated")
    assert (
        GapEvidenceService().classify_statement(literature, statement, current)
        == "agent_inference"
    )


def test_pending_verification_blocks_validated_capability() -> None:
    literature, statement = fixture()
    current = quality("validated")
    current.verification_tasks.append(
        VerificationTask(
            id="VERIFY-1",
            paper_id="PAPER-1",
            statement_id=statement.id,
            reason="high-value ambiguous evidence",
            priority=1.0,
        )
    )
    assert (
        GapEvidenceService().classify_statement(literature, statement, current)
        == "probable_observation"
    )


def test_experimental_central_gap_creates_verification_task() -> None:
    literature, statement = fixture()
    current = quality("experimental")
    gap = ResearchGap(
        id="GAP-1",
        title="Gap",
        supporting_statement_ids=[statement.id],
        common_limitation="Limitation",
        root_cause_hypothesis="Cause",
        why_existing_methods_fail="Failure",
        missing_capability="Capability",
        minimum_viable_experiment="Test",
        expected_signal="Signal",
        falsification_criterion="No signal",
        novelty_score=0.5,
        feasibility_score=0.5,
        research_value_score=0.5,
        publication_score=0.5,
        risk_score=0.5,
    )
    with pytest.raises(InvalidGapEvidenceError):
        GapEvidenceService().summarize_and_validate(literature, gap, current)
    assert current.verification_tasks[0].statement_id == statement.id
    assert "Central GAP" in current.verification_tasks[0].reason
