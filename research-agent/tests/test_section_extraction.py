from __future__ import annotations

from pathlib import Path

from research_agent.literature.extraction import PaperExtractor
from research_agent.schemas.document import DocumentSection, ParsedScientificDocument
from research_agent.schemas.literature import (
    PaperContent,
    PaperExtractionDraft,
    PaperMetadata,
)
from research_agent.schemas.project import ProjectInfo
from research_agent.schemas.provenance import SourceLocator, StatementEpistemicType
from research_agent.schemas.state import ResearchState
from research_agent.services.section_extraction_service import SectionAwareExtractionService
from research_agent.storage.artifact_store import ArtifactStore


class FixedSectionExtractor:
    name = "fixed-section-extractor"
    model = "fixed-v1"

    async def extract(self, *, metadata, content, text):
        assert "[SECTION" in text
        assert "Related work text" not in text
        return PaperExtractionDraft(
            method_summary="The authors allocate compute using uncertainty.",
            main_results=["Adaptive allocation improves the measured result."],
            limitations_claimed=["The study evaluates one model."],
            limitations_inferred=["Calibration shift may reduce reliability."],
            extraction_confidence=0.75,
        )


async def test_section_aware_extraction_tracks_locator_and_epistemic_type(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    artifacts = ArtifactStore(project)
    content_path = artifacts.write_text(
        "artifacts/literature/papers/PAPER-1/content.txt", "parsed content"
    )
    state = ResearchState(project=ProjectInfo(id="demo", name="Demo"))
    state.literature.paper_metadata.append(
        PaperMetadata(
            paper_id="PAPER-1",
            title="Paper",
            authors=["A. Author"],
            source_records=["https://example.test/paper"],
            metadata_verified=True,
            verification_confidence=0.9,
        )
    )
    state.literature.contents.append(
        PaperContent(
            paper_id="PAPER-1",
            content_type="pdf_text",
            artifact_path=content_path,
            sha256="b" * 64,
            parser_name="fixture-parser",
            content_verified=True,
            version_type="accepted_manuscript",
            content_version_label="accepted-v1",
            source_paper_id="PAPER-1",
        )
    )
    sections = [
        DocumentSection(
            id="SEC-METHOD",
            title="Method",
            normalized_role="method",
            text="Method section text.",
            order=0,
            source_locator=SourceLocator(
                section_id="SEC-METHOD", section_title="Method"
            ),
        ),
        DocumentSection(
            id="SEC-RESULT",
            title="Results",
            normalized_role="results",
            text="Result section text.",
            order=1,
        ),
        DocumentSection(
            id="SEC-LIMIT",
            title="Limitations",
            normalized_role="limitations",
            text="Limitation section text.",
            order=2,
        ),
        DocumentSection(
            id="SEC-RELATED",
            title="Related Work",
            normalized_role="related_work",
            text="Related work text.",
            order=3,
        ),
    ]
    state.literature_quality.parsed_documents.append(
        ParsedScientificDocument(
            paper_id="PAPER-1",
            parser="fixture-parser",
            sections=sections,
            parse_confidence=0.9,
            source_sha256="a" * 64,
        )
    )
    extraction = await SectionAwareExtractionService(
        extractor=FixedSectionExtractor(), artifacts=artifacts
    ).extract(state, paper_id="PAPER-1")
    assert extraction.content_version_label == "accepted-v1"
    results = next(
        item for item in state.literature.statements if item.statement_type == "result"
    )
    claimed = next(
        item
        for item in state.literature.statements
        if item.statement_type == "limitation_claimed"
    )
    inferred = next(
        item
        for item in state.literature.statements
        if item.statement_type == "limitation_inferred"
    )
    assert results.epistemic_type == StatementEpistemicType.DIRECT_RESULT
    assert claimed.epistemic_type == StatementEpistemicType.AUTHOR_STATED
    assert inferred.epistemic_type == StatementEpistemicType.AGENT_INFERRED
    provenance = next(
        item
        for item in state.literature.provenance_records
        if item.entity_id == claimed.id
    )
    assert provenance.source_locator.section_id == "SEC-LIMIT"
    assert state.literature_quality.verification_tasks[0].statement_id == claimed.id

