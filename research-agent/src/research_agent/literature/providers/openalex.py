from __future__ import annotations

import asyncio
import json
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
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
from research_agent.schemas.literature_quality import FullTextLocation, ProviderCapabilities


class OpenAlexMetadataProvider:
    name = "openalex"
    capabilities = ProviderCapabilities(
        search=True,
        metadata_lookup=True,
        abstract=True,
        citation_graph=True,
        references=True,
        open_access_location=True,
    )

    def __init__(
        self,
        *,
        base_url: str = "https://api.openalex.org",
        api_key: str | None = None,
        timeout_seconds: float = 30,
        max_results: int = 20,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_results = max_results
        self._records: dict[str, dict[str, object]] = {}

    async def search(self, query: LiteratureSearchQuery) -> list[PaperCandidate]:
        parameters: dict[str, object] = {
            "search": query.query,
            "per_page": self.max_results,
        }
        payload = await self._request_json("/works", parameters)
        results = payload.get("results", [])
        if not isinstance(results, list):
            raise MalformedProviderResultError("OpenAlex response has no results list")
        return [
            self._candidate(item, query.id, rank)
            for rank, item in enumerate(results, start=1)
            if isinstance(item, dict)
        ]

    async def resolve(self, candidate: PaperCandidate) -> PaperMetadata | None:
        if candidate.identifiers.openalex_id:
            work_id = candidate.identifiers.openalex_id.rsplit("/", 1)[-1]
            item = await self._request_json(f"/works/{work_id}", {})
        elif candidate.identifiers.doi:
            payload = await self._request_json(
                "/works",
                {
                    "filter": f"doi:{candidate.identifiers.doi}",
                    "per_page": 1,
                },
            )
            results = payload.get("results", [])
            item = results[0] if isinstance(results, list) and results else None
        else:
            payload = await self._request_json(
                "/works", {"search": candidate.raw_title, "per_page": 1}
            )
            results = payload.get("results", [])
            item = results[0] if isinstance(results, list) and results else None
        if not isinstance(item, dict):
            return None
        metadata = self._metadata(item)
        self._remember(item, metadata)
        return metadata

    async def fetch_content(self, paper: PaperMetadata) -> PaperContent | None:
        if not paper.abstract:
            return None
        return PaperContent(
            paper_id=paper.paper_id,
            content_type="abstract_only",
            source_url=paper.identifiers.canonical_url,
            parser_name="openalex-inverted-abstract",
            parser_version="1",
            version_type="unknown",
            source_paper_id=paper.paper_id,
            source_mime_type="text/plain",
            raw_text=paper.abstract,
        )

    async def discover_fulltext_locations(
        self, paper: PaperMetadata
    ) -> list[FullTextLocation]:
        item = self._record_for(paper)
        if item is None:
            candidate = PaperCandidate(
                id="OA-LOOKUP",
                query_id="OA-LOOKUP",
                raw_title=paper.title,
                raw_authors=paper.authors,
                raw_year=paper.year,
                source_provider=self.name,
                identifiers=paper.identifiers,
            )
            await self.resolve(candidate)
            item = self._record_for(paper)
        if item is None:
            return []
        raw_locations = item.get("locations", [])
        if not isinstance(raw_locations, list):
            return []
        locations: list[FullTextLocation] = []
        for location in raw_locations:
            if not isinstance(location, dict) or location.get("is_oa") is not True:
                continue
            url = location.get("pdf_url") or location.get("landing_page_url")
            if not url:
                continue
            version = str(location.get("version", ""))
            version_type = {
                "submittedVersion": "preprint",
                "acceptedVersion": "accepted_manuscript",
                "publishedVersion": "version_of_record",
            }.get(version, "unknown")
            source = location.get("source")
            source_type = source.get("type") if isinstance(source, dict) else None
            if source_type == "repository" and version_type == "unknown":
                version_type = "repository_copy"
            locations.append(
                FullTextLocation(
                    paper_id=paper.paper_id,
                    url=str(url),
                    source_provider=self.name,
                    version_type=version_type,
                    access_type="open",
                    mime_type=("application/pdf" if location.get("pdf_url") else "text/html"),
                    confidence=0.9 if location.get("pdf_url") else 0.75,
                    content_version_label=version or None,
                    license=location.get("license"),
                )
            )
        return locations

    async def expand_references(self, paper: PaperMetadata) -> list[PaperCandidate]:
        item = await self._ensure_record(paper)
        values = item.get("referenced_works", []) if item else []
        return self._identifier_candidates(values, paper.paper_id, "references")

    async def expand_related(self, paper: PaperMetadata) -> list[PaperCandidate]:
        item = await self._ensure_record(paper)
        values = item.get("related_works", []) if item else []
        return self._identifier_candidates(values, paper.paper_id, "related")

    async def expand_citations(self, paper: PaperMetadata) -> list[PaperCandidate]:
        item = await self._ensure_record(paper)
        work_id = _openalex_work_id(item.get("id")) if item else None
        if not work_id:
            return []
        payload = await self._request_json(
            "/works",
            {"filter": f"cites:{work_id}", "per_page": self.max_results},
        )
        results = payload.get("results", [])
        if not isinstance(results, list):
            return []
        return [
            self._candidate(value, f"CITATIONS-{paper.paper_id}", rank)
            for rank, value in enumerate(results, start=1)
            if isinstance(value, dict)
        ]

    def safe_configuration(self) -> dict[str, object]:
        return {
            "base_url": self.base_url,
            "api_key_configured": bool(self.api_key),
            "timeout_seconds": self.timeout_seconds,
            "max_results": self.max_results,
        }

    async def _ensure_record(
        self, paper: PaperMetadata
    ) -> dict[str, object] | None:
        item = self._record_for(paper)
        if item is not None:
            return item
        candidate = PaperCandidate(
            id="OA-LOOKUP",
            query_id="OA-LOOKUP",
            raw_title=paper.title,
            raw_authors=paper.authors,
            raw_year=paper.year,
            source_provider=self.name,
            identifiers=paper.identifiers,
        )
        await self.resolve(candidate)
        return self._record_for(paper)

    def _remember(
        self, item: dict[str, object], metadata: PaperMetadata
    ) -> None:
        keys = {
            metadata.paper_id,
            metadata.identifiers.openalex_id,
            metadata.identifiers.doi.casefold()
            if metadata.identifiers.doi
            else None,
        }
        for key in keys:
            if key:
                self._records[key] = item

    def _record_for(self, paper: PaperMetadata) -> dict[str, object] | None:
        keys = (
            paper.paper_id,
            paper.identifiers.openalex_id,
            paper.identifiers.doi.casefold() if paper.identifiers.doi else None,
        )
        return next((self._records[key] for key in keys if key in self._records), None)

    def _identifier_candidates(
        self, values: object, paper_id: str, mode: str
    ) -> list[PaperCandidate]:
        if not isinstance(values, list):
            return []
        candidates = []
        for rank, value in enumerate(values[: self.max_results], start=1):
            work_id = _openalex_work_id(value)
            if not work_id:
                continue
            url = f"https://openalex.org/{work_id}"
            candidates.append(
                PaperCandidate(
                    id=stable_id("CAND", self.name, work_id, mode, paper_id),
                    query_id=f"{mode.upper()}-{paper_id}",
                    raw_title=work_id,
                    source_provider=self.name,
                    source_url=url,
                    identifiers=PaperIdentifier(
                        openalex_id=url, canonical_url=url
                    ),
                    retrieval_rank=rank,
                )
            )
        return candidates

    def _candidate(
        self, item: dict[str, object], query_id: str, rank: int
    ) -> PaperCandidate:
        identifiers = _identifiers(item)
        title = str(item.get("title") or item.get("display_name") or "")
        authors = _authors(item)
        openalex_id = identifiers.openalex_id or title
        return PaperCandidate(
            id=stable_id("CAND", self.name, openalex_id, query_id),
            query_id=query_id,
            raw_title=title,
            raw_authors=authors,
            raw_year=item.get("publication_year") if isinstance(item.get("publication_year"), int) else None,
            source_provider=self.name,
            source_url=identifiers.canonical_url,
            identifiers=identifiers,
            retrieval_rank=rank,
            retrieval_score=(
                float(item["relevance_score"])
                if isinstance(item.get("relevance_score"), (int, float))
                else None
            ),
        )

    def _metadata(self, item: dict[str, object]) -> PaperMetadata:
        identifiers = _identifiers(item)
        title = str(item.get("title") or item.get("display_name") or "")
        authors = _authors(item)
        publication_date = _parse_date(item.get("publication_date"))
        primary = item.get("primary_location")
        source = primary.get("source") if isinstance(primary, dict) else None
        venue = source.get("display_name") if isinstance(source, dict) else None
        work_type = str(item.get("type", ""))
        status = "preprint" if work_type == "preprint" else "journal" if work_type == "article" else "unknown"
        source_records = [value for value in (identifiers.openalex_id, identifiers.doi, identifiers.canonical_url) if value]
        verified = bool(title and authors and identifiers.openalex_id)
        return PaperMetadata(
            paper_id=stable_id("PAPER", self.name, identifiers.openalex_id or identifiers.doi or title),
            title=title,
            authors=authors,
            year=item.get("publication_year") if isinstance(item.get("publication_year"), int) else None,
            publication_date=publication_date,
            venue=str(venue) if venue else None,
            identifiers=identifiers,
            abstract=_reconstruct_abstract(item.get("abstract_inverted_index")),
            publication_status=status,
            source_records=source_records,
            metadata_verified=verified,
            verification_confidence=0.9 if verified else 0.0,
            publication_integrity_status=("retracted" if item.get("is_retracted") is True else "normal"),
        )

    async def _request_json(
        self, path: str, parameters: dict[str, object]
    ) -> dict[str, object]:
        values = dict(parameters)
        if self.api_key:
            values["api_key"] = self.api_key
        query = f"?{urlencode(values)}" if values else ""
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._request_sync, f"{path}{query}"),
                timeout=self.timeout_seconds + 1,
            )
        except TimeoutError as exc:
            raise ProviderTimeoutError("OpenAlex request timed out") from exc

    def _request_sync(self, path: str) -> dict[str, object]:
        request = Request(
            f"{self.base_url}{path}",
            headers={"User-Agent": "autonomous-research-agent/0.1"},
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                value = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 429:
                raise ProviderRateLimitError("OpenAlex rate limit response") from exc
            raise MalformedProviderResultError(
                f"OpenAlex returned HTTP {exc.code}"
            ) from exc
        except (TimeoutError, URLError) as exc:
            raise ProviderTimeoutError(f"OpenAlex request failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise MalformedProviderResultError("OpenAlex returned invalid JSON") from exc
        if not isinstance(value, dict):
            raise MalformedProviderResultError("OpenAlex response is not an object")
        return value


def _identifiers(item: dict[str, object]) -> PaperIdentifier:
    ids = item.get("ids") if isinstance(item.get("ids"), dict) else {}
    openalex_id = item.get("id") or ids.get("openalex")
    doi_value = item.get("doi") or ids.get("doi")
    doi = str(doi_value).removeprefix("https://doi.org/") if doi_value else None
    primary = item.get("primary_location")
    landing = primary.get("landing_page_url") if isinstance(primary, dict) else None
    return PaperIdentifier(
        doi=doi,
        openalex_id=str(openalex_id) if openalex_id else None,
        canonical_url=str(landing or doi_value or openalex_id) if (landing or doi_value or openalex_id) else None,
    )


def _authors(item: dict[str, object]) -> list[str]:
    values = item.get("authorships", [])
    if not isinstance(values, list):
        return []
    names = []
    for authorship in values:
        author = authorship.get("author") if isinstance(authorship, dict) else None
        name = author.get("display_name") if isinstance(author, dict) else None
        if name:
            names.append(str(name))
    return names


def _parse_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def _reconstruct_abstract(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    positioned: list[tuple[int, str]] = []
    for word, positions in value.items():
        if not isinstance(positions, list):
            continue
        positioned.extend((int(position), str(word)) for position in positions)
    return " ".join(word for _, word in sorted(positioned)) or None


def _openalex_work_id(value: object) -> str | None:
    if not value:
        return None
    candidate = str(value).rstrip("/").rsplit("/", 1)[-1]
    return candidate if candidate.startswith("W") else None
