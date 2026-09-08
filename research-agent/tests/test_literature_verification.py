from __future__ import annotations

from research_agent.schemas.literature import (
    PaperCandidate,
    PaperContent,
    PaperIdentifier,
    PaperMetadata,
)
from research_agent.services.literature_service import can_support_literature_claim


def verified_metadata() -> PaperMetadata:
    return PaperMetadata(
        paper_id="PAPER-1",
        title="Verified Paper",
        authors=["A. Author"],
        year=2025,
        identifiers=PaperIdentifier(doi="10.1/example"),
        source_records=["https://doi.org/10.1/example"],
        metadata_verified=True,
        verification_confidence=0.95,
    )


def content(content_type: str) -> PaperContent:
    return PaperContent(
        paper_id="PAPER-1",
        content_type=content_type,
        artifact_path="artifacts/literature/papers/PAPER-1/content.txt",
        sha256="c" * 64,
        parser_name="test",
        content_verified=True,
    )


def test_candidate_cannot_support_claims() -> None:
    candidate = PaperCandidate(
        id="CAND-1",
        query_id="QUERY-1",
        raw_title="Candidate",
        source_provider="test",
    )
    assert not can_support_literature_claim(candidate, "title")


def test_metadata_verified_supports_metadata_only() -> None:
    paper = verified_metadata()
    assert can_support_literature_claim(paper, "year")
    assert not can_support_literature_claim(paper, "specific_limitation")


def test_abstract_only_cannot_support_detailed_limitation() -> None:
    paper = verified_metadata()
    assert can_support_literature_claim(paper, "claim", content("abstract_only"))
    assert not can_support_literature_claim(
        paper, "specific_limitation", content("abstract_only")
    )


def test_content_verified_supports_detailed_extraction() -> None:
    assert can_support_literature_claim(
        verified_metadata(), "specific_limitation", content("pdf_text")
    )

