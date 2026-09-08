from __future__ import annotations

from research_agent.core.ids import stable_id
from research_agent.schemas.literature import (
    LiteratureSearchQuery,
    PaperCandidate,
    PaperContent,
    PaperIdentifier,
    PaperMetadata,
)
from research_agent.schemas.literature_quality import ProviderCapabilities


class MockLiteratureProvider:
    name = "mock-literature"
    capabilities = ProviderCapabilities(
        search=True, metadata_lookup=True, abstract=True
    )

    async def search(self, query: LiteratureSearchQuery) -> list[PaperCandidate]:
        return [
            PaperCandidate(
                id=stable_id("CAND", self.name, query.query),
                query_id=query.id,
                raw_title=f"Synthetic paper for {query.query}",
                raw_authors=["Synthetic Author"],
                raw_year=2026,
                source_provider=self.name,
                source_url=None,
                identifiers=PaperIdentifier(),
                retrieval_rank=1,
                retrieval_score=1.0,
                synthetic_test_data=True,
            )
        ]

    async def resolve(self, candidate: PaperCandidate) -> PaperMetadata | None:
        return PaperMetadata(
            paper_id=stable_id("PAPER", candidate.id),
            title=candidate.raw_title,
            authors=candidate.raw_authors,
            year=candidate.raw_year,
            identifiers=candidate.identifiers,
            publication_status="unknown",
            source_records=[f"synthetic_test_data:{candidate.id}"],
            metadata_verified=False,
            verification_confidence=0.0,
            synthetic_test_data=True,
        )

    async def fetch_content(self, paper: PaperMetadata) -> PaperContent | None:
        return PaperContent(
            paper_id=paper.paper_id,
            content_type="abstract_only",
            parser_name="mock-provider",
            content_verified=False,
            synthetic_test_data=True,
            raw_text="synthetic_test_data",
        )

    def safe_configuration(self) -> dict[str, object]:
        return {"synthetic_test_data": True}
