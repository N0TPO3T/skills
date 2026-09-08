from __future__ import annotations

from research_agent.literature.deduplication import PaperDeduplicator
from research_agent.schemas.literature import (
    LiteratureState,
    PaperCandidate,
    PaperIdentifier,
    PaperMetadata,
)


def metadata(**updates) -> PaperMetadata:
    values = {
        "paper_id": "PAPER-1",
        "title": "Adaptive Test-Time Compute for Language Models",
        "authors": ["Alice Smith", "Bob Jones"],
        "year": 2025,
        "identifiers": PaperIdentifier(
            doi="10.1000/example", arxiv_id="2501.01234"
        ),
        "source_records": ["https://arxiv.org/abs/2501.01234"],
        "metadata_verified": True,
        "verification_confidence": 0.95,
    }
    values.update(updates)
    return PaperMetadata(**values)


def candidate(**updates) -> PaperCandidate:
    values = {
        "id": "CAND-1",
        "query_id": "QUERY-1",
        "raw_title": "Adaptive Test-Time Compute for Language Models",
        "raw_authors": ["A. Smith", "B. Jones"],
        "raw_year": 2025,
        "source_provider": "test",
        "identifiers": PaperIdentifier(),
    }
    values.update(updates)
    return PaperCandidate(**values)


def existing_state() -> LiteratureState:
    return LiteratureState(paper_metadata=[metadata()])


def test_dedup_same_doi_across_providers() -> None:
    item = candidate(
        source_provider="other", identifiers=PaperIdentifier(doi="https://doi.org/10.1000/EXAMPLE")
    )
    assert PaperDeduplicator().find_existing(item, existing_state()) == "PAPER-1"


def test_dedup_same_arxiv_version() -> None:
    item = candidate(identifiers=PaperIdentifier(arxiv_id="2501.01234v3"))
    assert PaperDeduplicator().find_existing(item, existing_state()) == "PAPER-1"


def test_dedup_normalizes_case_and_punctuation() -> None:
    item = candidate(raw_title="adaptive test time compute: for language models!")
    assert PaperDeduplicator().find_existing(item, existing_state()) == "PAPER-1"


def test_dedup_near_title_with_author_overlap() -> None:
    item = candidate(raw_title="Adaptive Test-Time Computation for Language Models")
    deduplicator = PaperDeduplicator(title_similarity_threshold=0.88)
    assert deduplicator.find_existing(item, existing_state()) == "PAPER-1"


def test_similar_title_different_authors_is_not_forced_merge() -> None:
    item = candidate(
        raw_title="Adaptive Test-Time Computation for Language Models",
        raw_authors=["Carol White"],
    )
    deduplicator = PaperDeduplicator(title_similarity_threshold=0.88)
    assert deduplicator.find_existing(item, existing_state()) is None


def test_preprint_and_conference_versions_link_as_same_work() -> None:
    preprint = metadata(publication_status="preprint")
    conference = metadata(
        paper_id="PAPER-2",
        venue="ICML",
        publication_status="conference",
        identifiers=PaperIdentifier(doi="10.1000/conference"),
        source_records=["https://doi.org/10.1000/conference"],
    )
    relation = PaperDeduplicator().same_work_relation(preprint, conference)
    assert relation is not None
    assert relation.relation == "same_work_version"

