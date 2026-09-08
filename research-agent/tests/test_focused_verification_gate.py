from __future__ import annotations

from datetime import UTC, datetime

import pytest

from research_agent.schemas.decision import ResearchAction
from research_agent.schemas.gap import ResearchGap
from research_agent.schemas.literature import (
    ExtractedStatement,
    LiteratureCoverageReport,
    LiteratureState,
    PaperContent,
    PaperMetadata,
    PaperRelation,
)
from research_agent.schemas.literature_quality import (
    ExtractionCapabilityStatus,
    LiteratureQualityState,
    VerificationTask,
)
from research_agent.schemas.project import ProjectInfo
from research_agent.schemas.provenance import (
    ProvenanceRecord,
    SourceLocator,
    StatementEpistemicType,
)
from research_agent.schemas.state import ResearchState
from research_agent.services.gap_evidence_service import (
    GapEvidenceService,
)
from research_agent.storage.artifact_store import ArtifactStore
from research_agent.workflows.discovery import DiscoveryWorkflow


def evidence_fixture(
    paper_id: str = "PAPER-1",
    statement_id: str = "STATEMENT-1",
    *,
    content_type: str = "pdf_text",
    statement_type: str = "method",
) -> tuple[LiteratureState, ExtractedStatement, LiteratureQualityState]:
    locator = SourceLocator(section_id=f"SECTION-{paper_id}", section_title="Method")
    content = PaperContent(
        paper_id=paper_id,
        content_type=content_type,
        artifact_path=f"artifacts/literature/papers/{paper_id}/content.txt",
        sha256="a" * 64,
        parser_name="fixture",
        content_verified=True,
    )
    statement = ExtractedStatement(
        id=statement_id,
        paper_id=paper_id,
        statement_type=statement_type,
        statement="The evaluated policy uses a fixed allocation in this setting.",
        provenance_ids=[f"PROV-{statement_id}"],
        confidence=0.7,
        epistemic_type=StatementEpistemicType.AUTHOR_STATED,
    )
    literature = LiteratureState(
        paper_metadata=[
            PaperMetadata(
                paper_id=paper_id,
                title=f"Paper {paper_id}",
                authors=["A. Author"],
                source_records=[f"https://example.test/{paper_id}"],
                metadata_verified=True,
                verification_confidence=0.95,
            )
        ],
        contents=[content],
        statements=[statement],
        provenance_records=[
            ProvenanceRecord(
                id=f"PROV-{statement_id}",
                entity_type="extracted_statement",
                entity_id=statement_id,
                source_type=(
                    "paper_abstract"
                    if content_type == "abstract_only"
                    else "paper_full_text"
                ),
                source_id=paper_id,
                artifact_path=content.artifact_path,
                source_locator=locator,
                confidence=0.7,
            )
        ],
    )
    return literature, statement, LiteratureQualityState()


def focused_task(
    statement: ExtractedStatement,
    *,
    status: str,
    content_sha256: str = "a" * 64,
) -> VerificationTask:
    return VerificationTask(
        id=f"VERIFY-{statement.id}",
        paper_id=statement.paper_id,
        statement_id=statement.id,
        reason="Independent source-only verification.",
        priority=1.0,
        status=status,
        epistemic_type=statement.epistemic_type,
        source_locator=SourceLocator(
            section_id=f"SECTION-{statement.paper_id}", section_title="Method"
        ),
        supported_scope=statement.statement,
        content_sha256=content_sha256,
        verifier="host_agent",
        verification_artifact=f"artifacts/verifications/{statement.id}.json",
        verified_at=datetime.now(UTC),
    )


def test_focused_accept_can_satisfy_gap_evidence_gate() -> None:
    literature, statement, quality = evidence_fixture()
    quality.verification_tasks.append(focused_task(statement, status="accepted"))
    assert GapEvidenceService().validate_statement(literature, statement, quality)


def test_focused_accept_selects_the_hash_bound_content_version() -> None:
    literature, statement, quality = evidence_fixture()
    literature.contents.insert(
        0,
        PaperContent(
            paper_id=statement.paper_id,
            content_type="abstract_only",
            artifact_path=literature.contents[0].artifact_path,
            sha256="b" * 64,
            parser_name="abstract-parser",
            content_verified=True,
        ),
    )
    quality.verification_tasks.append(focused_task(statement, status="accepted"))
    assert GapEvidenceService().validate_statement(literature, statement, quality)


@pytest.mark.parametrize("status", ["weak", "rejected"])
def test_non_accept_focused_verdict_cannot_satisfy_gate(status: str) -> None:
    literature, statement, quality = evidence_fixture()
    quality.verification_tasks.append(focused_task(statement, status=status))
    assert not GapEvidenceService().validate_statement(literature, statement, quality)


def test_project_local_verification_does_not_change_global_capabilities() -> None:
    literature, statement, quality = evidence_fixture()
    quality.verification_tasks.append(focused_task(statement, status="accepted"))
    assert GapEvidenceService().validate_statement(literature, statement, quality)
    assert quality.capability_statuses == []


def test_focused_accept_is_independent_of_disabled_global_extractor() -> None:
    literature, statement, quality = evidence_fixture()
    quality.capability_statuses.append(
        ExtractionCapabilityStatus(
            capability="method",
            status="disabled",
            reason="Global extractor is not certified.",
        )
    )
    quality.verification_tasks.append(focused_task(statement, status="accepted"))
    assert GapEvidenceService().validate_statement(literature, statement, quality)


def test_abstract_only_detailed_limitation_remains_blocked() -> None:
    literature, statement, quality = evidence_fixture(
        content_type="abstract_only", statement_type="limitation_claimed"
    )
    quality.verification_tasks.append(focused_task(statement, status="accepted"))
    assert not GapEvidenceService().validate_statement(literature, statement, quality)


def test_focused_accept_must_match_content_hash_and_locator() -> None:
    literature, statement, quality = evidence_fixture()
    quality.verification_tasks.append(
        focused_task(statement, status="accepted", content_sha256="b" * 64)
    )
    assert not GapEvidenceService().validate_statement(literature, statement, quality)


def test_two_versions_of_one_work_count_once() -> None:
    left, left_statement, quality = evidence_fixture("PAPER-1", "STATEMENT-1")
    right, right_statement, _ = evidence_fixture("PAPER-2", "STATEMENT-2")
    left.paper_metadata.extend(right.paper_metadata)
    left.contents.extend(right.contents)
    left.statements.extend(right.statements)
    left.provenance_records.extend(right.provenance_records)
    left.relations.append(
        PaperRelation(
            source_paper_id="PAPER-1",
            target_paper_id="PAPER-2",
            relation="same_work_version",
            confidence=0.99,
        )
    )
    quality.verification_tasks.extend(
        [
            focused_task(left_statement, status="accepted"),
            focused_task(right_statement, status="accepted"),
        ]
    )
    summary = GapEvidenceService().summarize_and_validate(
        left,
        gap([left_statement.id, right_statement.id]),
        quality,
    )
    assert summary.independent_paper_count == 1


async def test_checkpoint_a_accepts_focused_verified_evidence(tmp_path) -> None:
    left, left_statement, quality = evidence_fixture("PAPER-1", "STATEMENT-1")
    right, right_statement, _ = evidence_fixture("PAPER-2", "STATEMENT-2")
    left.paper_metadata.extend(right.paper_metadata)
    left.contents.extend(right.contents)
    left.statements.extend(right.statements)
    left.provenance_records.extend(right.provenance_records)
    left.coverage_reports.append(
        LiteratureCoverageReport(
            query_count=2,
            candidate_count=2,
            metadata_verified_count=2,
            content_verified_count=2,
            duplicate_count=0,
            rejected_count=0,
            publication_year_distribution={},
            cluster_coverage={},
            sufficient_for_gap_synthesis=True,
        )
    )
    quality.verification_tasks.extend(
        [
            focused_task(left_statement, status="accepted"),
            focused_task(right_statement, status="accepted"),
        ]
    )
    state = ResearchState(
        project=ProjectInfo(id="focused", name="Focused"),
        literature=left,
        literature_quality=quality,
    )
    state.gaps.candidates.append(
        gap([left_statement.id, right_statement.id], status="shortlisted")
    )
    target = await DiscoveryWorkflow(
        ArtifactStore(tmp_path), mock=False
    ).request_topic_selection(
        state,
        ResearchAction(
            action="request_topic_selection", reason="Evidence passed", priority=1.0
        ),
    )
    assert target.value == "topic_selection"
    assert state.human_checkpoint is not None
    assert state.human_checkpoint.options == ["GAP-FOCUSED"]


def gap(statement_ids: list[str], *, status: str = "candidate") -> ResearchGap:
    return ResearchGap(
        id="GAP-FOCUSED",
        title="Focused evidence gap",
        supporting_statement_ids=statement_ids,
        common_limitation="A recurring bounded limitation.",
        root_cause_hypothesis="A falsifiable mechanism hypothesis.",
        why_existing_methods_fail="The compared methods do not cover the setting.",
        missing_capability="A missing bounded capability.",
        minimum_viable_experiment="Run a discriminative replay.",
        expected_signal="A measurable separation.",
        falsification_criterion="No separation.",
        novelty_score=0.6,
        feasibility_score=0.8,
        research_value_score=0.8,
        publication_score=0.7,
        risk_score=0.4,
        status=status,
    )
