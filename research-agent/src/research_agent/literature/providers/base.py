from __future__ import annotations

from typing import Protocol

from research_agent.schemas.literature import (
    LiteratureSearchQuery,
    PaperCandidate,
    PaperContent,
    PaperMetadata,
)
from research_agent.schemas.literature_quality import ProviderCapabilities


class LiteratureProviderError(RuntimeError):
    retryable = False


class ProviderTimeoutError(LiteratureProviderError):
    retryable = True


class ProviderRateLimitError(LiteratureProviderError):
    retryable = True


class MalformedProviderResultError(LiteratureProviderError):
    pass


class LiteratureProvider(Protocol):
    name: str
    capabilities: ProviderCapabilities

    async def search(self, query: LiteratureSearchQuery) -> list[PaperCandidate]: ...

    async def resolve(self, candidate: PaperCandidate) -> PaperMetadata | None: ...

    async def fetch_content(self, paper: PaperMetadata) -> PaperContent | None: ...

    def safe_configuration(self) -> dict[str, object]: ...
