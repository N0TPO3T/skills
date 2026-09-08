from __future__ import annotations

from pathlib import Path

from research_agent.schemas.literature import (
    PaperCandidate,
    PaperIdentifier,
    PaperMetadata,
    PaperRelation,
)
from research_agent.schemas.literature_quality import ProviderCapabilities
from research_agent.schemas.project import ProjectInfo
from research_agent.schemas.state import ResearchState
from research_agent.services.metadata_corroboration_service import (
    MetadataCorroborationService,
)
from research_agent.storage.artifact_store import ArtifactStore


class ObservationProvider:
    capabilities = ProviderCapabilities(metadata_lookup=True)

    def __init__(self, name: str, metadata: PaperMetadata) -> None:
        self.name = name
        self.metadata = metadata

    async def search(self, query):
        return []

    async def resolve(self, candidate: PaperCandidate):
        return self.metadata

    async def fetch_content(self, paper):
        return None

    def safe_configuration(self):
        return {}


def paper(**updates) -> PaperMetadata:
    values = {
        "paper_id": "PAPER-ARXIV",
        "title": "Adaptive Test-Time Compute",
        "authors": ["Alice Smith", "Bob Jones"],
        "year": 2025,
        "venue": "arXiv",
        "identifiers": PaperIdentifier(
            doi="10.1000/adaptive", arxiv_id="2501.01234"
        ),
        "publication_status": "preprint",
        "source_records": ["https://arxiv.org/abs/2501.01234"],
        "metadata_verified": True,
        "verification_confidence": 0.9,
    }
    values.update(updates)
    return PaperMetadata(**values)


def state_with(*papers: PaperMetadata) -> ResearchState:
    state = ResearchState(project=ProjectInfo(id="demo", name="Demo"))
    state.literature.paper_metadata.extend(papers)
    return state


def service(tmp_path: Path, providers) -> MetadataCorroborationService:
    project = tmp_path / "project"
    project.mkdir()
    return MetadataCorroborationService(
        providers=providers, artifacts=ArtifactStore(project)
    )


async def test_two_providers_agree(tmp_path: Path) -> None:
    canonical = paper()
    providers = [
        ObservationProvider("crossref", paper(paper_id="CR")),
        ObservationProvider("openalex", paper(paper_id="OA")),
    ]
    state = state_with(canonical)
    result = await service(tmp_path, providers).corroborate(state, canonical.paper_id)
    assert result.corroborating_provider_count == 2
    assert result.conflicts == []
    assert result.confidence > canonical.verification_confidence


async def test_year_and_venue_disagreement_are_recorded(tmp_path: Path) -> None:
    canonical = paper()
    disagreeing = paper(paper_id="OTHER", year=2026, venue="ICML")
    state = state_with(canonical)
    result = await service(
        tmp_path, [ObservationProvider("crossref", disagreeing)]
    ).corroborate(state, canonical.paper_id)
    fields = {conflict.field for conflict in result.conflicts}
    assert {"year", "venue"} <= fields


async def test_doi_identity_wins_without_erasing_title_conflict(tmp_path: Path) -> None:
    canonical = paper()
    renamed = paper(paper_id="OTHER", title="A Materially Different Published Title")
    state = state_with(canonical)
    result = await service(
        tmp_path, [ObservationProvider("crossref", renamed)]
    ).corroborate(state, canonical.paper_id)
    conflict = next(item for item in result.conflicts if item.field == "title")
    assert conflict.resolved is True
    assert "DOI" in conflict.resolution
    assert result.canonical_title == canonical.title


async def test_preprint_and_conference_share_work_family(tmp_path: Path) -> None:
    preprint = paper()
    conference = paper(
        paper_id="PAPER-CONF",
        venue="ICML",
        publication_status="conference",
        identifiers=PaperIdentifier(doi="10.1000/published"),
        source_records=["https://doi.org/10.1000/published"],
    )
    state = state_with(preprint, conference)
    state.literature.relations.append(
        PaperRelation(
            source_paper_id=preprint.paper_id,
            target_paper_id=conference.paper_id,
            relation="same_work_version",
            confidence=0.98,
        )
    )
    instance = service(tmp_path, [])
    await instance.corroborate(state, preprint.paper_id)
    await instance.corroborate(state, conference.paper_id)
    records = state.literature_quality.canonical_records
    assert records[0].work_family_id == records[1].work_family_id
    assert next(item for item in records if item.paper_id == "PAPER-CONF").canonical_version

