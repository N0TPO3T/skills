from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from research_agent.core.ids import stable_id
from research_agent.literature.fulltext.acquisition import FullTextAcquisitionService
from research_agent.schemas.document import DocumentSection, ParsedScientificDocument
from research_agent.schemas.gap import ResearchGap
from research_agent.schemas.literature import (
    LiteratureSearchQuery,
    PaperCandidate,
    PaperContent,
    PaperExtractionDraft,
    PaperIdentifier,
    PaperMetadata,
)
from research_agent.schemas.literature_quality import (
    FullTextLocation,
    GoldPaperAnnotation,
    GoldStatement,
    ProviderCapabilities,
)
from research_agent.schemas.project import ProjectInfo
from research_agent.schemas.provenance import SourceLocator
from research_agent.schemas.state import ResearchState
from research_agent.services.document_parsing_service import DocumentParsingService
from research_agent.services.extraction_evaluation_service import (
    ExtractionEvaluationService,
)
from research_agent.services.gap_evidence_service import GapEvidenceService
from research_agent.services.literature_quality_gate_service import (
    LiteratureQualityGateService,
)
from research_agent.services.literature_service import LiteratureService
from research_agent.services.metadata_corroboration_service import (
    MetadataCorroborationService,
)
from research_agent.services.section_extraction_service import (
    SectionAwareExtractionService,
)
from research_agent.storage.artifact_store import ArtifactStore


PDF_FIXTURE = b"%PDF-1.4\nfixture scientific article\n%%EOF"


def metadata(*, paper_id: str = "PAPER-ARXIV", venue: str = "arXiv") -> PaperMetadata:
    return PaperMetadata(
        paper_id=paper_id,
        title="Adaptive Test-Time Compute",
        authors=["Alice Smith", "Bob Jones"],
        year=2026,
        venue=venue,
        identifiers=PaperIdentifier(
            doi="10.1000/adaptive",
            arxiv_id="2601.01234",
            canonical_url="https://arxiv.org/abs/2601.01234",
        ),
        publication_status="preprint" if venue == "arXiv" else "conference",
        source_records=[f"https://fixture.test/{paper_id}"],
        metadata_verified=True,
        verification_confidence=0.95,
        publication_integrity_status="normal",
    )


class FakeArxiv:
    name = "arxiv"
    capabilities = ProviderCapabilities(
        search=True,
        metadata_lookup=True,
        abstract=True,
        full_text=True,
        open_access_location=True,
    )

    def __init__(self) -> None:
        self.search_calls = 0

    async def search(self, query: LiteratureSearchQuery):
        self.search_calls += 1
        return [
            PaperCandidate(
                id="CANDIDATE-1",
                query_id=query.id,
                raw_title="Adaptive Test-Time Compute",
                raw_authors=["Alice Smith", "Bob Jones"],
                raw_year=2026,
                source_provider=self.name,
                source_url="https://arxiv.org/abs/2601.01234",
                identifiers=PaperIdentifier(
                    doi="10.1000/adaptive", arxiv_id="2601.01234"
                ),
                retrieval_rank=1,
            )
        ]

    async def resolve(self, candidate: PaperCandidate):
        return metadata()

    async def fetch_content(self, paper: PaperMetadata):
        return PaperContent(
            paper_id=paper.paper_id,
            content_type="abstract_only",
            parser_name="fixture",
            raw_text="We study adaptive test-time compute.",
        )

    async def discover_fulltext_locations(self, paper: PaperMetadata):
        return [
            FullTextLocation(
                paper_id=paper.paper_id,
                url="https://arxiv.test/2601.01234.pdf",
                source_provider=self.name,
                version_type="preprint",
                access_type="open",
                mime_type="application/pdf",
                confidence=1.0,
                content_version_label="v2",
            )
        ]

    def safe_configuration(self):
        return {"fixture": True}


class FakeMetadataProvider:
    capabilities = ProviderCapabilities(metadata_lookup=True)

    def __init__(self, name: str, venue: str) -> None:
        self.name = name
        self.venue = venue
        self.search_calls = 0

    async def search(self, query):
        self.search_calls += 1
        raise AssertionError("metadata-only provider must not be searched")

    async def resolve(self, candidate):
        return metadata(paper_id=f"PAPER-{self.name.upper()}", venue=self.venue)

    async def fetch_content(self, paper):
        raise AssertionError("metadata-only provider must not fetch content")

    def safe_configuration(self):
        return {"fixture": True}


class FixtureParser:
    name = "fixture-parser"

    async def parse(self, source: Path):
        return ParsedScientificDocument(
            paper_id="placeholder",
            parser=self.name,
            parser_version="1",
            title="Adaptive Test-Time Compute",
            sections=[
                DocumentSection(
                    id="SEC-RESULT",
                    title="Results",
                    normalized_role="results",
                    text="Adaptive allocation improves accuracy by five points.",
                    order=0,
                    source_locator=SourceLocator(
                        section_id="SEC-RESULT", section_title="Results"
                    ),
                ),
                DocumentSection(
                    id="SEC-LIMIT",
                    title="Limitations",
                    normalized_role="limitations",
                    text="The study evaluates only one model.",
                    order=1,
                    source_locator=SourceLocator(
                        section_id="SEC-LIMIT", section_title="Limitations"
                    ),
                ),
            ],
            parse_confidence=1.0,
            source_sha256=sha256(source.read_bytes()).hexdigest(),
        )


class FixtureExtractor:
    name = "fixture-extractor"
    model = "fixture-v1"

    async def extract(self, *, metadata, content, text):
        assert "SEC-RESULT" in text and "SEC-LIMIT" in text
        return PaperExtractionDraft(
            main_results=["Adaptive allocation improves accuracy by five points."],
            limitations_claimed=["The study evaluates only one model."],
            extraction_confidence=0.99,
        )


async def test_offline_literature_quality_pipeline(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    artifacts = ArtifactStore(project)
    current = ResearchState(
        project=ProjectInfo(id="demo", name="Demo", research_direction="adaptive compute")
    )
    arxiv = FakeArxiv()
    crossref = FakeMetadataProvider("crossref", "ICML")
    openalex = FakeMetadataProvider("openalex", "ICML")
    providers = [arxiv, crossref, openalex]
    query = LiteratureSearchQuery(
        id="QUERY-1", query="adaptive compute", purpose="canonical", priority=1.0
    )

    retrieval = LiteratureService(providers=providers, artifacts=artifacts)
    candidates = await retrieval.retrieve_candidates(current.literature, [query])
    verified = await retrieval.verify_metadata(current.literature, candidates)
    assert len(verified) == 1
    assert arxiv.search_calls == 1
    assert crossref.search_calls == openalex.search_calls == 0
    paper = verified[0]

    corroboration = await MetadataCorroborationService(
        providers=providers, artifacts=artifacts
    ).corroborate(current, paper.paper_id)
    assert corroboration.corroborating_provider_count == 3
    assert any(conflict.field == "venue" for conflict in corroboration.conflicts)
    canonical = current.literature_quality.canonical_records[0]
    assert canonical.work_family_id and canonical.canonical_version

    async def download(url: str):
        return PDF_FIXTURE, "application/pdf"

    async def robots(url: str):
        return True

    acquisition_service = FullTextAcquisitionService(
        providers=providers,
        artifacts=artifacts,
        downloader=download,
        robots_checker=robots,
    )
    locations = await acquisition_service.discover_locations(current, paper)
    acquisition = await acquisition_service.acquire(current, locations[0])
    document = await DocumentParsingService(
        parsers=[FixtureParser()], artifacts=artifacts
    ).parse(current, acquisition)
    assert document.source_sha256 == acquisition.sha256

    extraction = await SectionAwareExtractionService(
        extractor=FixtureExtractor(), artifacts=artifacts
    ).extract(current, paper_id=paper.paper_id)
    assert extraction.content_version_label == "v2"
    assert extraction.content_sha256
    result_statement = next(
        item for item in current.literature.statements if item.statement_type == "result"
    )
    limitation_statement = next(
        item
        for item in current.literature.statements
        if item.statement_type == "limitation_claimed"
    )

    evaluation = ExtractionEvaluationService(artifacts).evaluate(
        current,
        [
            GoldPaperAnnotation(
                paper_id=paper.paper_id,
                results=[
                    GoldStatement(
                        statement=result_statement.statement,
                        source_locator=SourceLocator(
                            section_id="SEC-RESULT", section_title="Results"
                        ),
                    )
                ],
                limitations_claimed=[
                    GoldStatement(
                        statement=limitation_statement.statement,
                        source_locator=SourceLocator(
                            section_id="SEC-LIMIT", section_title="Limitations"
                        ),
                    )
                ],
            )
        ],
    )
    assert evaluation.unsupported_statement_rate == 0.0
    statuses = LiteratureQualityGateService().apply(current, evaluation)
    status_by_name = {item.capability: item.status for item in statuses}
    assert status_by_name["results"] == "validated"
    assert status_by_name["limitations"] == "validated"

    gap = ResearchGap(
        id=stable_id("GAP", "single-model evaluation"),
        title="Single-model evaluation gap",
        supporting_statement_ids=[limitation_statement.id],
        common_limitation=limitation_statement.statement,
        root_cause_hypothesis="Evaluation breadth is costly.",
        why_existing_methods_fail="Evidence covers only one model.",
        missing_capability="Cross-model validation",
        minimum_viable_experiment="Evaluate a second model.",
        expected_signal="The reported gain persists.",
        falsification_criterion="The gain disappears on the second model.",
        novelty_score=0.5,
        feasibility_score=0.8,
        research_value_score=0.7,
        publication_score=0.6,
        risk_score=0.4,
    )
    summary = GapEvidenceService().summarize_and_validate(
        current.literature, gap, current.literature_quality
    )
    assert summary.supporting_statement_count == 1
    assert GapEvidenceService().classify_statement(
        current.literature, limitation_statement, current.literature_quality
    ) == "verified_observation"
