from __future__ import annotations

import asyncio
import re
from datetime import datetime
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from research_agent.core.ids import stable_id
from research_agent.literature.providers.base import (
    MalformedProviderResultError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from research_agent.schemas.literature import (
    LiteratureSearchQuery,
    PaperCandidate,
    PaperContent,
    PaperIdentifier,
    PaperMetadata,
)
from research_agent.schemas.literature_quality import FullTextLocation, ProviderCapabilities


ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"


class ArxivLikeProvider:
    name = "arxiv"
    capabilities = ProviderCapabilities(
        search=True,
        metadata_lookup=True,
        abstract=True,
        full_text=True,
        open_access_location=True,
    )

    def __init__(
        self,
        *,
        endpoint: str = "https://export.arxiv.org/api/query",
        timeout_seconds: float = 30,
        max_results: int = 20,
        minimum_request_interval: float = 3.0,
        user_agent: str = "autonomous-research-agent/0.1",
    ) -> None:
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.max_results = max_results
        self.minimum_request_interval = minimum_request_interval
        self.user_agent = user_agent
        self._request_lock = asyncio.Lock()
        self._last_request_at: float | None = None

    async def search(self, query: LiteratureSearchQuery) -> list[PaperCandidate]:
        search_query = f"all:{query.query}"
        if query.target_year_from is not None or query.target_year_to is not None:
            year_from = query.target_year_from or 1991
            year_to = query.target_year_to or datetime.now().year
            search_query += (
                f" AND submittedDate:[{year_from}01010000 TO {year_to}12312359]"
            )
        params = {
            "search_query": search_query,
            "start": 0,
            "max_results": self.max_results,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        payload = await self._request(params)
        entries = self.parse_feed(payload)
        return [
            self._candidate_from_entry(entry, query.id, rank)
            for rank, entry in enumerate(entries, start=1)
        ]

    async def resolve(self, candidate: PaperCandidate) -> PaperMetadata | None:
        arxiv_id = candidate.identifiers.arxiv_id
        if not arxiv_id:
            return None
        payload = await self._request({"id_list": arxiv_id, "max_results": 1})
        entries = self.parse_feed(payload)
        if not entries:
            return None
        entry = entries[0]
        title = entry["title"]
        authors = entry["authors"]
        source_url = entry["source_url"]
        verified = bool(title and authors and source_url)
        return PaperMetadata(
            paper_id=stable_id("PAPER", "arxiv", entry["arxiv_id"]),
            title=title,
            authors=authors,
            year=entry["year"],
            venue=entry["journal_ref"],
            identifiers=PaperIdentifier(
                doi=entry["doi"],
                arxiv_id=entry["arxiv_id"],
                canonical_url=source_url,
            ),
            abstract=entry["abstract"] or None,
            publication_status=(
                "journal" if entry["journal_ref"] else "preprint"
            ),
            source_records=[source_url],
            metadata_verified=verified,
            verification_confidence=0.95 if verified else 0.0,
        )

    async def fetch_content(self, paper: PaperMetadata) -> PaperContent | None:
        if not paper.abstract:
            return None
        return PaperContent(
            paper_id=paper.paper_id,
            content_type="abstract_only",
            source_url=paper.identifiers.canonical_url,
            parser_name="arxiv-atom-summary",
            parser_version="1",
            version_type="preprint",
            content_version_label=paper.identifiers.arxiv_id,
            source_paper_id=paper.paper_id,
            source_mime_type="text/plain",
            raw_text=paper.abstract,
        )

    def safe_configuration(self) -> dict[str, object]:
        return {
            "endpoint": self.endpoint,
            "max_results": self.max_results,
            "minimum_request_interval": self.minimum_request_interval,
            "timeout_seconds": self.timeout_seconds,
        }

    async def discover_fulltext_locations(
        self, paper: PaperMetadata
    ) -> list[FullTextLocation]:
        if not paper.identifiers.arxiv_id:
            return []
        return [
            FullTextLocation(
                paper_id=paper.paper_id,
                url=f"https://arxiv.org/pdf/{paper.identifiers.arxiv_id}",
                source_provider=self.name,
                version_type="preprint",
                access_type="open",
                mime_type="application/pdf",
                confidence=0.99,
                content_version_label=paper.identifiers.arxiv_id,
            )
        ]

    async def _request(self, parameters: dict[str, object]) -> bytes:
        async with self._request_lock:
            if self._last_request_at is not None:
                remaining = self.minimum_request_interval - (
                    monotonic() - self._last_request_at
                )
                if remaining > 0:
                    await asyncio.sleep(remaining)
            try:
                payload = await asyncio.wait_for(
                    asyncio.to_thread(self._request_sync, parameters),
                    timeout=self.timeout_seconds + 1,
                )
            except TimeoutError as exc:
                raise ProviderTimeoutError("arXiv request timed out") from exc
            finally:
                self._last_request_at = monotonic()
            return payload

    def _request_sync(self, parameters: dict[str, object]) -> bytes:
        url = f"{self.endpoint}?{urlencode(parameters)}"
        request = Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return response.read()
        except HTTPError as exc:
            if exc.code == 429:
                raise ProviderRateLimitError("arXiv rate limit response") from exc
            raise MalformedProviderResultError(
                f"arXiv returned HTTP {exc.code}"
            ) from exc
        except (TimeoutError, URLError) as exc:
            raise ProviderTimeoutError(f"arXiv request failed: {exc}") from exc

    @staticmethod
    def parse_feed(payload: bytes) -> list[dict[str, object]]:
        try:
            root = ElementTree.fromstring(payload)
        except ElementTree.ParseError as exc:
            raise MalformedProviderResultError("Invalid arXiv Atom response") from exc
        entries: list[dict[str, object]] = []
        for node in root.findall(f"{ATOM}entry"):
            source_url = _text(node, f"{ATOM}id")
            raw_id = source_url.rsplit("/", 1)[-1]
            arxiv_id = re.sub(r"v\d+$", "", raw_id)
            published = _text(node, f"{ATOM}published")
            try:
                year = datetime.fromisoformat(published.replace("Z", "+00:00")).year
            except ValueError:
                year = None
            entries.append(
                {
                    "title": _clean(_text(node, f"{ATOM}title")),
                    "authors": [
                        _clean(_text(author, f"{ATOM}name"))
                        for author in node.findall(f"{ATOM}author")
                    ],
                    "year": year,
                    "source_url": source_url,
                    "arxiv_id": arxiv_id,
                    "abstract": _clean(_text(node, f"{ATOM}summary")),
                    "doi": _text(node, f"{ARXIV}doi") or None,
                    "journal_ref": _text(node, f"{ARXIV}journal_ref") or None,
                }
            )
        return entries

    def _candidate_from_entry(
        self, entry: dict[str, object], query_id: str, rank: int
    ) -> PaperCandidate:
        return PaperCandidate(
            id=stable_id("CAND", self.name, entry["arxiv_id"], query_id),
            query_id=query_id,
            raw_title=str(entry["title"]),
            raw_authors=list(entry["authors"]),
            raw_year=entry["year"],
            source_provider=self.name,
            source_url=str(entry["source_url"]),
            identifiers=PaperIdentifier(
                doi=entry["doi"],
                arxiv_id=str(entry["arxiv_id"]),
                canonical_url=str(entry["source_url"]),
            ),
            retrieval_rank=rank,
        )


def _text(node: ElementTree.Element, path: str) -> str:
    child = node.find(path)
    return child.text.strip() if child is not None and child.text else ""


def _clean(value: str) -> str:
    return " ".join(value.split())
