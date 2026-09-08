from __future__ import annotations

from research_agent.schemas.literature import PaperMetadata
from research_agent.schemas.literature_quality import ProviderCapabilities
from research_agent.services.citation_expansion_service import CitationExpansionService


class MisleadingProvider:
    name = "misleading"
    capabilities = ProviderCapabilities()

    async def expand_references(self, paper):
        raise AssertionError("unsupported capability must not be invoked")


class LegacyProvider:
    name = "legacy"

    async def expand_references(self, paper):
        return []


async def test_citation_expansion_obeys_declared_capabilities() -> None:
    paper = PaperMetadata(paper_id="PAPER-1", title="Paper")
    result = await CitationExpansionService(
        [MisleadingProvider()]
    ).expand_references(paper)
    assert result.supported is False
    assert result.candidates == []


async def test_legacy_provider_without_capability_model_remains_compatible() -> None:
    paper = PaperMetadata(paper_id="PAPER-1", title="Paper")
    result = await CitationExpansionService([LegacyProvider()]).expand_references(paper)
    assert result.supported is True
