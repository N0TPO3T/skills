from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from research_agent.literature.parsers.base import DocumentParseError
from research_agent.literature.parsers.grobid import GrobidParserAdapter
from research_agent.literature.parsers.plain_text import PlainTextFallbackParser
from research_agent.schemas.document import DocumentSection, ParsedScientificDocument
from research_agent.schemas.literature_quality import (
    FullTextAcquisitionResult,
    FullTextLocation,
)
from research_agent.schemas.project import ProjectInfo
from research_agent.schemas.state import ResearchState
from research_agent.services.document_parsing_service import DocumentParsingService
from research_agent.storage.artifact_store import ArtifactStore


TEI_FIXTURE = """<TEI xmlns="http://www.tei-c.org/ns/1.0">
<teiHeader><fileDesc><titleStmt><title>Fixture Paper</title></titleStmt></fileDesc>
<profileDesc><abstract><p>Fixture abstract.</p></abstract></profileDesc></teiHeader>
<text><body>
<div xml:id="sec-method"><head>Method</head><p>We allocate compute.</p></div>
<div xml:id="sec-limit"><head>Limitations</head><p>We test one model.</p></div>
</body><back><listBibl><biblStruct><analytic><title>Prior Work</title></analytic>
<idno type="DOI">10.1/prior</idno></biblStruct></listBibl></back></text></TEI>"""


async def test_plain_text_parser_preserves_structured_sections(tmp_path: Path) -> None:
    source = tmp_path / "PAPER-1" / "source.txt"
    source.parent.mkdir()
    source.write_text(
        "Paper Title\n\nAbstract\nWe study adaptive compute.\n\n"
        "1 Introduction\nMotivation.\n\n2 Method\nMethod details.\n\n"
        "Limitations\nOnly one model.\n"
    )
    parsed = await PlainTextFallbackParser().parse(source)
    assert [section.normalized_role for section in parsed.sections] == [
        "abstract",
        "introduction",
        "method",
        "limitations",
    ]
    assert parsed.source_sha256 == sha256(source.read_bytes()).hexdigest()


async def test_plain_parser_rejects_corrupted_pdf(tmp_path: Path) -> None:
    source = tmp_path / "PAPER-1" / "source.pdf"
    source.parent.mkdir()
    source.write_bytes(b"corrupt")
    with pytest.raises(DocumentParseError):
        await PlainTextFallbackParser().parse(source)


def test_grobid_tei_preserves_sections_and_references() -> None:
    parsed = GrobidParserAdapter(version="fixture").parse_tei(
        paper_id="PAPER-1",
        tei=TEI_FIXTURE,
        source_sha256="a" * 64,
    )
    assert [section.normalized_role for section in parsed.sections] == [
        "method",
        "limitations",
    ]
    assert parsed.sections[0].source_locator.section_id == "sec-method"
    assert parsed.references[0].doi == "10.1/prior"
    assert parsed.raw_tei == TEI_FIXTURE


class FailingParser:
    name = "failing-parser"

    async def parse(self, source: Path):
        raise DocumentParseError("fixture failure")


class FixtureParser:
    name = "fixture-parser"

    async def parse(self, source: Path):
        return ParsedScientificDocument(
            paper_id="placeholder",
            parser=self.name,
            sections=[
                DocumentSection(
                    id="SEC-1",
                    title="Method",
                    normalized_role="method",
                    text="Method text.",
                    order=0,
                )
            ],
            parse_confidence=0.8,
            source_sha256=sha256(source.read_bytes()).hexdigest(),
        )


async def test_parser_failure_is_isolated_and_fallback_succeeds(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    artifacts = ArtifactStore(project)
    source_path = artifacts.write_bytes(
        "artifacts/literature/papers/PAPER-1/source.pdf",
        b"%PDF-1.4\nfixture\n%%EOF",
    )
    acquisition = FullTextAcquisitionResult(
        paper_id="PAPER-1",
        location=FullTextLocation(
            paper_id="PAPER-1",
            url="https://example.test/paper.pdf",
            source_provider="fixture",
            access_type="open",
            mime_type="application/pdf",
            confidence=1.0,
        ),
        artifact_path=source_path,
        sha256=sha256(artifacts.read_bytes(source_path)).hexdigest(),
        byte_count=len(artifacts.read_bytes(source_path)),
        validated=True,
    )
    state = ResearchState(project=ProjectInfo(id="demo", name="Demo"))
    parsed = await DocumentParsingService(
        parsers=[FailingParser(), FixtureParser()], artifacts=artifacts
    ).parse(state, acquisition)
    assert parsed.parser == "fixture-parser"
    assert state.literature.failures[0].provider == "failing-parser"
    assert state.literature_quality.parsed_documents[0].source_sha256 == acquisition.sha256

