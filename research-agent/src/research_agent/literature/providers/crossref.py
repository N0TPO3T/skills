from __future__ import annotations

import asyncio
import json
import re
from datetime import date
from html import unescape
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

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
from research_agent.schemas.literature_quality import (
    FullTextLocation,
    ProviderCapabilities,
)


class CrossrefMetadataProvider:
    name = "crossref"
    capabilities = ProviderCapabilities(
        search=True,
        metadata_lookup=True,
        abstract=True,
        open_access_location=True,
    )

    def __init__(
        self,
        *,
        base_url: str = "https://api.crossref.org",
        mailto: str | None = None,
        timeout_seconds: float = 30,
        max_results: int = 20,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.mailto = mailto
        self.timeout_seconds = timeout_seconds
        self.max_results = max_results
        self._records: dict[str, dict[str, object]] = {}

    async def search(self, query: LiteratureSearchQuery) -> list[PaperCandidate]:
        parameters: dict[str, object] = {
            "query.bibliographic": query.query,
            "rows": self.max_results,
        }
        if self.mailto:
            parameters["mailto"] = self.mailto
        payload = await self._request_json(f"/works?{urlencode(parameters)}")
        items = payload.get("message", {}).get("items", [])
        if not isinstance(items, list):
            raise MalformedProviderResultError("Crossref response has no work list")
        return [
            self._candidate(item, query.id, rank)
            for rank, item in enumerate(items, start=1)
            if isinstance(item, dict)
        ]

    async def resolve(self, candidate: PaperCandidate) -> PaperMetadata | None:
        doi = candidate.identifiers.doi
        if doi:
            payload = await self._request_json(f"/works/{quote(doi, safe='/()<>:;')}" )
            item = payload.get("message")
        else:
            parameters: dict[str, object] = {
                "query.bibliographic": candidate.raw_title,
                "rows": 1,
            }
            if self.mailto:
                parameters["mailto"] = self.mailto
            payload = await self._request_json(f"/works?{urlencode(parameters)}")
            items = payload.get("message", {}).get("items", [])
            item = items[0] if isinstance(items, list) and items else None
        if not isinstance(item, dict):
            return None
        metadata = self._metadata(item)
        if metadata.identifiers.doi:
            self._records[metadata.identifiers.doi.casefold()] = item
        return metadata

    async def fetch_content(self, paper: PaperMetadata) -> PaperContent | None:
        if not paper.abstract:
            return None
        return PaperContent(
            paper_id=paper.paper_id,
            content_type="abstract_only",
            source_url=paper.identifiers.canonical_url,
            parser_name="crossref-abstract",
            parser_version="1",
            version_type="version_of_record",
            source_paper_id=paper.paper_id,
            source_mime_type="text/plain",
            raw_text=paper.abstract,
        )

    async def discover_fulltext_locations(
        self, paper: PaperMetadata
    ) -> list[FullTextLocation]:
        doi = paper.identifiers.doi
        if not doi:
            return []
        item = self._records.get(doi.casefold())
        if item is None:
            payload = await self._request_json(f"/works/{quote(doi, safe='/()<>:;')}")
            raw = payload.get("message")
            item = raw if isinstance(raw, dict) else None
        if item is None:
            return []
        licenses = [
            str(entry.get("URL", ""))
            for entry in item.get("license", [])
            if isinstance(entry, dict)
        ]
        explicitly_open = any(
            "creativecommons.org" in license_url.casefold()
            for license_url in licenses
        )
        locations: list[FullTextLocation] = []
        for link in item.get("link", []):
            if not isinstance(link, dict) or not link.get("URL"):
                continue
            version = str(link.get("content-version", "")).casefold()
            version_type = {
                "vor": "version_of_record",
                "am": "accepted_manuscript",
                "stm-asf": "accepted_manuscript",
            }.get(version, "unknown")
            locations.append(
                FullTextLocation(
                    paper_id=paper.paper_id,
                    url=str(link["URL"]),
                    source_provider=self.name,
                    version_type=version_type,
                    access_type="open" if explicitly_open else "unknown",
                    mime_type=link.get("content-type"),
                    confidence=0.9 if explicitly_open else 0.6,
                    content_version_label=version or None,
                    license=licenses[0] if licenses else None,
                )
            )
        return locations

    def safe_configuration(self) -> dict[str, object]:
        return {
            "base_url": self.base_url,
            "mailto_configured": bool(self.mailto),
            "timeout_seconds": self.timeout_seconds,
            "max_results": self.max_results,
        }

    def _candidate(
        self, item: dict[str, object], query_id: str, rank: int
    ) -> PaperCandidate:
        title = _first_string(item.get("title")) or ""
        authors = _authors(item.get("author"))
        publication_date = _date_from_parts(item)
        doi = str(item.get("DOI")) if item.get("DOI") else None
        url = str(item.get("URL")) if item.get("URL") else None
        return PaperCandidate(
            id=stable_id("CAND", self.name, doi or title, query_id),
            query_id=query_id,
            raw_title=title,
            raw_authors=authors,
            raw_year=publication_date.year if publication_date else None,
            source_provider=self.name,
            source_url=url,
            identifiers=PaperIdentifier(doi=doi, canonical_url=url),
            retrieval_rank=rank,
            retrieval_score=(
                float(item["score"]) if isinstance(item.get("score"), (int, float)) else None
            ),
        )

    def _metadata(self, item: dict[str, object]) -> PaperMetadata:
        title = _first_string(item.get("title")) or ""
        authors = _authors(item.get("author"))
        publication_date = _date_from_parts(item)
        doi = str(item.get("DOI")) if item.get("DOI") else None
        url = str(item.get("URL")) if item.get("URL") else None
        venue = _first_string(item.get("container-title"))
        item_type = str(item.get("type", ""))
        status = (
            "journal"
            if "journal" in item_type
            else "conference"
            if "proceedings" in item_type
            else "unknown"
        )
        integrity = "normal"
        updates = item.get("update-to", [])
        if isinstance(updates, list):
            update_types = {
                str(update.get("type", "")).casefold()
                for update in updates
                if isinstance(update, dict)
            }
            if any("retract" in value for value in update_types):
                integrity = "retracted"
            elif any("correct" in value for value in update_types):
                integrity = "corrected"
        abstract = _strip_markup(str(item["abstract"])) if item.get("abstract") else None
        verified = bool(title and authors and (doi or url))
        return PaperMetadata(
            paper_id=stable_id("PAPER", self.name, doi or url or title),
            title=title,
            authors=authors,
            year=publication_date.year if publication_date else None,
            publication_date=publication_date,
            venue=venue,
            identifiers=PaperIdentifier(doi=doi, canonical_url=url),
            abstract=abstract,
            publication_status=status,
            source_records=[f"{self.base_url}/works/{doi}" if doi else url] if (doi or url) else [],
            metadata_verified=verified,
            verification_confidence=0.92 if verified else 0.0,
            publication_integrity_status=integrity,
        )

    async def _request_json(self, path: str) -> dict[str, object]:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._request_sync, path),
                timeout=self.timeout_seconds + 1,
            )
        except TimeoutError as exc:
            raise ProviderTimeoutError("Crossref request timed out") from exc

    def _request_sync(self, path: str) -> dict[str, object]:
        headers = {"User-Agent": "autonomous-research-agent/0.1"}
        if self.mailto:
            headers["User-Agent"] += f" (mailto:{self.mailto})"
        request = Request(f"{self.base_url}{path}", headers=headers)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                value = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 429:
                raise ProviderRateLimitError("Crossref rate limit response") from exc
            raise MalformedProviderResultError(
                f"Crossref returned HTTP {exc.code}"
            ) from exc
        except (TimeoutError, URLError) as exc:
            raise ProviderTimeoutError(f"Crossref request failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise MalformedProviderResultError("Crossref returned invalid JSON") from exc
        if not isinstance(value, dict):
            raise MalformedProviderResultError("Crossref response is not an object")
        return value


def _first_string(value: object) -> str | None:
    if isinstance(value, list) and value:
        return str(value[0]).strip() or None
    return str(value).strip() or None if isinstance(value, str) else None


def _authors(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    names = []
    for author in value:
        if not isinstance(author, dict):
            continue
        name = " ".join(
            part for part in (str(author.get("given", "")).strip(), str(author.get("family", "")).strip()) if part
        )
        if name:
            names.append(name)
    return names


def _date_from_parts(item: dict[str, object]) -> date | None:
    for key in ("published-print", "published-online", "published", "issued"):
        value = item.get(key)
        if not isinstance(value, dict):
            continue
        parts = value.get("date-parts")
        if not isinstance(parts, list) or not parts or not isinstance(parts[0], list):
            continue
        values = parts[0]
        try:
            return date(int(values[0]), int(values[1]) if len(values) > 1 else 1, int(values[2]) if len(values) > 2 else 1)
        except (TypeError, ValueError):
            continue
    return None


def _strip_markup(value: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", value)).split())

