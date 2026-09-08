from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from research_agent.literature.providers.base import LiteratureProvider
from research_agent.schemas.literature import PaperCandidate, PaperMetadata


class CitationExpansionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["references", "citations", "related"]
    supported: bool
    candidates: list[PaperCandidate] = Field(default_factory=list)
    reason: str | None = None


class CitationExpansionService:
    def __init__(self, providers: list[LiteratureProvider]) -> None:
        self.providers = providers

    async def expand_references(self, paper: PaperMetadata) -> CitationExpansionResult:
        return await self._expand("references", paper)

    async def expand_citations(self, paper: PaperMetadata) -> CitationExpansionResult:
        return await self._expand("citations", paper)

    async def expand_related(self, paper: PaperMetadata) -> CitationExpansionResult:
        return await self._expand("related", paper)

    async def _expand(
        self, mode: Literal["references", "citations", "related"], paper: PaperMetadata
    ) -> CitationExpansionResult:
        method_name = f"expand_{mode}"
        candidates: list[PaperCandidate] = []
        supported = False
        for provider in self.providers:
            capabilities = getattr(provider, "capabilities", None)
            capability_supported = capabilities is None or (
                capabilities.references
                if mode == "references"
                else capabilities.citation_graph
            )
            method = getattr(provider, method_name, None)
            if not capability_supported or method is None:
                continue
            supported = True
            candidates.extend(await method(paper))
        return CitationExpansionResult(
            mode=mode,
            supported=supported,
            candidates=candidates,
            reason=None if supported else "No configured provider supports this expansion mode",
        )
