from __future__ import annotations

from research_agent.literature.providers.crossref import CrossrefMetadataProvider
from research_agent.literature.providers.openalex import OpenAlexMetadataProvider
from research_agent.schemas.literature import PaperIdentifier, PaperMetadata


def test_crossref_record_conversion_tracks_integrity() -> None:
    provider = CrossrefMetadataProvider()
    metadata = provider._metadata(
        {
            "title": ["Paper Title"],
            "author": [{"given": "Alice", "family": "Smith"}],
            "DOI": "10.1000/example",
            "URL": "https://doi.org/10.1000/example",
            "container-title": ["Journal"],
            "published-online": {"date-parts": [[2025, 2, 3]]},
            "type": "journal-article",
            "update-to": [{"type": "retraction"}],
        }
    )
    assert metadata.metadata_verified
    assert metadata.publication_date.isoformat() == "2025-02-03"
    assert metadata.publication_integrity_status == "retracted"


def test_openalex_record_conversion_reconstructs_abstract() -> None:
    provider = OpenAlexMetadataProvider()
    metadata = provider._metadata(
        {
            "id": "https://openalex.org/W1",
            "title": "Paper Title",
            "doi": "https://doi.org/10.1000/example",
            "publication_year": 2025,
            "publication_date": "2025-03-01",
            "type": "article",
            "authorships": [{"author": {"display_name": "Alice Smith"}}],
            "abstract_inverted_index": {"Adaptive": [0], "compute": [1]},
            "primary_location": {
                "landing_page_url": "https://doi.org/10.1000/example",
                "source": {"display_name": "Journal"},
            },
            "is_retracted": False,
        }
    )
    assert metadata.metadata_verified
    assert metadata.abstract == "Adaptive compute"
    assert metadata.identifiers.openalex_id.endswith("W1")


async def test_openalex_record_is_resolved_across_provider_specific_paper_ids() -> None:
    provider = OpenAlexMetadataProvider()
    item = {
        "id": "https://openalex.org/W1",
        "title": "Paper Title",
        "doi": "https://doi.org/10.1000/example",
        "authorships": [{"author": {"display_name": "Alice Smith"}}],
        "referenced_works": ["https://openalex.org/W2"],
    }
    observed = provider._metadata(item)
    provider._remember(item, observed)
    canonical = PaperMetadata(
        paper_id="PAPER-ARXIV",
        title="Paper Title",
        authors=["Alice Smith"],
        identifiers=PaperIdentifier(doi="10.1000/example"),
        source_records=["https://arxiv.org/abs/1"],
        metadata_verified=True,
        verification_confidence=0.9,
    )
    references = await provider.expand_references(canonical)
    assert references[0].identifiers.openalex_id == "https://openalex.org/W2"
