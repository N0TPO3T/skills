from __future__ import annotations

import asyncio
import re
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

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
from research_agent.schemas.literature_quality import ProviderCapabilities


class GenericWebPaperProvider:
    """Resolves direct paper URLs; it is intentionally not a general web search engine."""

    name = "generic-web-paper"
    capabilities = ProviderCapabilities(
        search=True,
        metadata_lookup=True,
        abstract=True,
        full_text=True,
    )

    def __init__(
        self, *, timeout_seconds: float = 30, minimum_article_characters: int = 1000
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.minimum_article_characters = minimum_article_characters

    async def search(self, query: LiteratureSearchQuery) -> list[PaperCandidate]:
        parsed = urlsplit(query.query)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or any(character.isspace() for character in query.query)
        ):
            return []
        return [
            PaperCandidate(
                id=stable_id("CAND", self.name, query.query),
                query_id=query.id,
                raw_title=query.query,
                source_provider=self.name,
                source_url=query.query,
                identifiers=PaperIdentifier(canonical_url=query.query),
                retrieval_rank=1,
            )
        ]

    async def resolve(self, candidate: PaperCandidate) -> PaperMetadata | None:
        if not candidate.source_url:
            return None
        content_type, payload = await self._request(candidate.source_url)
        if "html" not in content_type:
            return None
        parser = _CitationMetaParser()
        try:
            parser.feed(payload.decode("utf-8", errors="replace"))
        except Exception as exc:
            raise MalformedProviderResultError("Could not parse paper HTML") from exc
        title = parser.first("citation_title") or parser.title
        authors = parser.all("citation_author")
        if not title:
            return None
        year_text = parser.first("citation_publication_date") or parser.first("citation_date")
        year_match = re.search(r"(?:19|20)\d{2}", year_text or "")
        source_records = [candidate.source_url]
        verified = bool(authors)
        return PaperMetadata(
            paper_id=stable_id("PAPER", candidate.source_url),
            title=title,
            authors=authors,
            year=int(year_match.group()) if year_match else None,
            venue=parser.first("citation_conference_title")
            or parser.first("citation_journal_title"),
            identifiers=PaperIdentifier(
                doi=parser.first("citation_doi"), canonical_url=candidate.source_url
            ),
            abstract=parser.first("citation_abstract") or parser.first("description"),
            publication_status="unknown",
            source_records=source_records,
            metadata_verified=verified,
            verification_confidence=0.85 if verified else 0.0,
        )

    async def fetch_content(self, paper: PaperMetadata) -> PaperContent | None:
        url = paper.identifiers.canonical_url
        if not url:
            return None
        content_type, payload = await self._request(url)
        if "html" not in content_type:
            return None
        parser = _CitationMetaParser()
        parser.feed(payload.decode("utf-8", errors="replace"))
        article_text = " ".join(parser.article_text).strip()
        if len(article_text) >= self.minimum_article_characters:
            content_type = "html"
            text = article_text
        elif paper.abstract:
            content_type = "abstract_only"
            text = paper.abstract
        else:
            return None
        return PaperContent(
            paper_id=paper.paper_id,
            content_type=content_type,
            source_url=url,
            parser_name="stdlib-html-parser",
            parser_version="1",
            version_type="unknown",
            source_paper_id=paper.paper_id,
            source_mime_type="text/html",
            raw_text=text,
        )

    def safe_configuration(self) -> dict[str, object]:
        return {
            "direct_urls_only": True,
            "timeout_seconds": self.timeout_seconds,
            "minimum_article_characters": self.minimum_article_characters,
        }

    async def _request(self, url: str) -> tuple[str, bytes]:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._request_sync, url),
                timeout=self.timeout_seconds + 1,
            )
        except TimeoutError as exc:
            raise ProviderTimeoutError("Web paper request timed out") from exc

    def _request_sync(self, url: str) -> tuple[str, bytes]:
        request = Request(url, headers={"User-Agent": "autonomous-research-agent/0.1"})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return response.headers.get_content_type(), response.read()
        except HTTPError as exc:
            if exc.code == 429:
                raise ProviderRateLimitError("Web source rate limit response") from exc
            raise MalformedProviderResultError(
                f"Web source returned HTTP {exc.code}"
            ) from exc
        except (TimeoutError, URLError) as exc:
            raise ProviderTimeoutError(f"Web source request failed: {exc}") from exc


class _CitationMetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.metadata: dict[str, list[str]] = {}
        self.visible_text: list[str] = []
        self.title = ""
        self._in_title = False
        self._ignored_depth = 0
        self._article_depth = 0
        self.article_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if tag in {"script", "style"}:
            self._ignored_depth += 1
        if tag == "article":
            self._article_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            name = (values.get("name") or values.get("property") or "").lower()
            content = values.get("content", "").strip()
            if name and content:
                self.metadata.setdefault(name, []).append(content)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._ignored_depth:
            self._ignored_depth -= 1
        if tag == "article" and self._article_depth:
            self._article_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text or self._ignored_depth:
            return
        if self._in_title:
            self.title = f"{self.title} {text}".strip()
        self.visible_text.append(text)
        if self._article_depth:
            self.article_text.append(text)

    def first(self, key: str) -> str | None:
        values = self.metadata.get(key, [])
        return values[0] if values else None

    def all(self, key: str) -> list[str]:
        return self.metadata.get(key, [])
