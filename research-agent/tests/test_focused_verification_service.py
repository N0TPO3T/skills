from __future__ import annotations

from research_agent.schemas.document import DocumentSection, ParsedScientificDocument
from research_agent.schemas.gap import ResearchGap
from research_agent.schemas.literature import (
    ExtractedStatement,
    PaperContent,
    PaperMetadata,
)
from research_agent.schemas.literature_quality import (
    FocusedVerificationBatch,
    FocusedVerificationDecision,
)
from research_agent.schemas.project import ProjectInfo
from research_agent.schemas.provenance import (
    ProvenanceRecord,
    SourceLocator,
    StatementEpistemicType,
)
from research_agent.schemas.state import ResearchState
from research_agent.services.focused_verification_service import (
    FocusedEvidenceVerificationService,
)
from research_agent.services.gap_evidence_service import GapEvidenceService
from research_agent.storage.artifact_store import ArtifactStore


class AcceptingBackend:
    def __init__(self) -> None:
        self.calls = []

    async def run_structured(
        self,
        instructions,
        context,
        tools,
        *,
        response_model,
        workflow_contract=False,
    ):
        self.calls.append((instructions, context, tools, response_model))
        item = context["statements"][0]
        return FocusedVerificationBatch(
            summary="Independent source-only pass",
            decisions=[
                FocusedVerificationDecision(
                    statement_id=item["statement_id"],
                    verdict="accept",
                    epistemic_type="author_stated",
                    supported_scope=(
                        "The evaluated policy uses a fixed allocation in this setting."
                    ),
                    source_passage_id=item["source_passages"][0]["passage_id"],
                    reason="The supplied method passage states this bounded scope.",
                )
            ],
            uncertainties=[],
        )


class WeakThenAcceptBackend:
    def __init__(self, verdict: str) -> None:
        self.verdict = verdict

    async def run_structured(
        self,
        instructions,
        context,
        tools,
        *,
        response_model,
        workflow_contract=False,
    ):
        item = context["statements"][0]
        if self.verdict == "weak":
            return FocusedVerificationBatch(
                summary="Initial scope is too broad",
                decisions=[
                    FocusedVerificationDecision(
                        statement_id=item["statement_id"],
                        verdict="weak",
                        epistemic_type="author_stated",
                        supported_scope=(
                            "The evaluated policy uses a fixed allocation in this "
                            "setting."
                        ),
                        overstatement="Always is broader than the evaluated setting.",
                        source_passage_id=item["source_passages"][0]["passage_id"],
                        reason="Only the bounded setting is supported.",
                    )
                ],
                uncertainties=[],
            )
        return FocusedVerificationBatch(
            summary="Narrowed wording is supported",
            decisions=[
                FocusedVerificationDecision(
                    statement_id=item["statement_id"],
                    verdict="accept",
                    epistemic_type="author_stated",
                    supported_scope="supported as written",
                    source_passage_id=item["source_passages"][0]["passage_id"],
                    reason="The supplied method passage states the narrowed scope.",
                )
            ],
            uncertainties=[],
        )


async def test_focused_verifier_records_scoped_fulltext_evidence(tmp_path) -> None:
    artifacts = ArtifactStore(tmp_path)
    content_path = artifacts.write_text(
        "artifacts/literature/papers/PAPER-1/content.txt",
        "Method\nThe evaluated policy uses a fixed allocation in this setting.",
    )
    locator = SourceLocator(section_id="SECTION-1", section_title="Method")
    state = ResearchState(project=ProjectInfo(id="focused", name="Focused"))
    state.literature.paper_metadata.append(
        PaperMetadata(
            paper_id="PAPER-1",
            title="Paper",
            authors=["A. Author"],
            source_records=["https://example.test/paper"],
            metadata_verified=True,
            verification_confidence=0.95,
        )
    )
    state.literature.contents.append(
        PaperContent(
            paper_id="PAPER-1",
            content_type="pdf_text",
            artifact_path=content_path,
            sha256="a" * 64,
            parser_name="fixture",
            content_verified=True,
        )
    )
    state.literature_quality.parsed_documents.append(
        ParsedScientificDocument(
            paper_id="PAPER-1",
            parser="fixture",
            sections=[
                DocumentSection(
                    id="SECTION-1",
                    title="Method",
                    normalized_role="method",
                    text=(
                        "The evaluated policy uses a fixed allocation in this setting."
                    ),
                    order=0,
                    source_locator=locator,
                )
            ],
            parse_confidence=0.9,
            source_sha256="b" * 64,
        )
    )
    state.literature.statements.append(
        ExtractedStatement(
            id="STATEMENT-OLD",
            paper_id="PAPER-1",
            statement_type="method",
            statement="The policy always uses fixed compute.",
            provenance_ids=["PROV-OLD"],
            confidence=0.55,
            epistemic_type=StatementEpistemicType.AUTHOR_STATED,
        )
    )
    state.literature.provenance_records.append(
        ProvenanceRecord(
            id="PROV-OLD",
            entity_type="extracted_statement",
            entity_id="STATEMENT-OLD",
            source_type="paper_abstract",
            source_id="PAPER-1",
            artifact_path=content_path,
            source_locator=locator,
            confidence=0.55,
        )
    )
    state.gaps.candidates.append(
        ResearchGap(
            id="GAP-1",
            title="Bounded gap",
            observed_phenomena=["The evaluated policy uses a fixed allocation."],
            supporting_statement_ids=["STATEMENT-OLD"],
            common_limitation="Only the evaluated setting is established.",
            root_cause_hypothesis="The controller is static.",
            why_existing_methods_fail="The method does not adapt in this setting.",
            missing_capability="Online adaptation.",
            minimum_viable_experiment="Replay with a causal controller.",
            expected_signal="Lower regret.",
            falsification_criterion="No lower regret.",
            novelty_score=0.5,
            feasibility_score=0.8,
            research_value_score=0.8,
            publication_score=0.6,
            risk_score=0.4,
        )
    )
    backend = AcceptingBackend()
    tasks = await FocusedEvidenceVerificationService(
        backend_factory=lambda: backend,
        artifacts=artifacts,
    ).verify_gap(state, "GAP-1")
    assert len(tasks) == 1
    assert tasks[0].status == "accepted"
    assert state.literature_quality.capability_statuses == []
    verified_id = state.gaps.candidates[0].supporting_statement_ids[0]
    assert verified_id != "STATEMENT-OLD"
    verified = next(
        item for item in state.literature.statements if item.id == verified_id
    )
    assert verified.statement == tasks[0].supported_scope
    assert GapEvidenceService().validate_statement(
        state.literature, verified, state.literature_quality
    )
    assert "prompts/evidence_verify.md" in backend.calls[0][0]
    assert backend.calls[0][2] == {}


async def test_weak_scope_is_reverified_in_a_separate_backend_session(
    tmp_path,
) -> None:
    artifacts = ArtifactStore(tmp_path)
    content_path = artifacts.write_text(
        "artifacts/literature/papers/PAPER-1/content.txt",
        "The evaluated policy uses a fixed allocation in this setting.",
    )
    state = ResearchState(project=ProjectInfo(id="focused", name="Focused"))
    state.literature.paper_metadata.append(
        PaperMetadata(
            paper_id="PAPER-1",
            title="Paper",
            authors=["A. Author"],
            source_records=["https://example.test/paper"],
            metadata_verified=True,
            verification_confidence=0.95,
        )
    )
    state.literature.contents.append(
        PaperContent(
            paper_id="PAPER-1",
            content_type="pdf_text",
            artifact_path=content_path,
            sha256="a" * 64,
            parser_name="fixture",
            content_verified=True,
        )
    )
    state.literature_quality.parsed_documents.append(
        ParsedScientificDocument(
            paper_id="PAPER-1",
            parser="fixture",
            sections=[
                DocumentSection(
                    id="SECTION-1",
                    title="Method",
                    normalized_role="method",
                    text=(
                        "The evaluated policy uses a fixed allocation in this setting."
                    ),
                    order=0,
                )
            ],
            parse_confidence=0.9,
            source_sha256="b" * 64,
        )
    )
    state.literature.statements.append(
        ExtractedStatement(
            id="STATEMENT-OLD",
            paper_id="PAPER-1",
            statement_type="method",
            statement="The policy always uses fixed compute.",
            provenance_ids=["PROV-OLD"],
            confidence=0.55,
            epistemic_type=StatementEpistemicType.AUTHOR_STATED,
        )
    )
    state.gaps.candidates.append(
        ResearchGap(
            id="GAP-1",
            title="Bounded gap",
            supporting_statement_ids=["STATEMENT-OLD"],
            common_limitation="Only the evaluated setting is established.",
            root_cause_hypothesis="The controller is static.",
            why_existing_methods_fail="The method does not adapt in this setting.",
            missing_capability="Online adaptation.",
            minimum_viable_experiment="Replay with a causal controller.",
            expected_signal="Lower regret.",
            falsification_criterion="No lower regret.",
            novelty_score=0.5,
            feasibility_score=0.8,
            research_value_score=0.8,
            publication_score=0.6,
            risk_score=0.4,
        )
    )
    backends = iter([WeakThenAcceptBackend("weak"), WeakThenAcceptBackend("accept")])
    tasks = await FocusedEvidenceVerificationService(
        backend_factory=lambda: next(backends),
        artifacts=artifacts,
    ).verify_gap(state, "GAP-1")
    assert [task.status for task in tasks] == ["weak", "accepted"]
    verified_id = state.gaps.candidates[0].supporting_statement_ids[0]
    verified = next(
        item for item in state.literature.statements if item.id == verified_id
    )
    assert verified.statement == (
        "The evaluated policy uses a fixed allocation in this setting."
    )
    assert state.literature_quality.capability_statuses == []
    assert GapEvidenceService().validate_statement(
        state.literature, verified, state.literature_quality
    )
