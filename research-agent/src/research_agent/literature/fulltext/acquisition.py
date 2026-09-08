from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from hashlib import sha256
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

from research_agent.core.ids import stable_id
from research_agent.literature.providers.base import LiteratureProvider
from research_agent.schemas.literature import LiteratureFailure, PaperMetadata
from research_agent.schemas.literature_quality import (
    FullTextAcquisitionResult,
    FullTextLocation,
    ProviderCapabilities,
)
from research_agent.schemas.provenance import ProvenanceRecord
from research_agent.schemas.state import ResearchState
from research_agent.storage.artifact_store import ArtifactStore


DownloadFunction = Callable[[str], Awaitable[tuple[bytes, str | None]]]
RobotsFunction = Callable[[str], Awaitable[bool]]


class FullTextAcquisitionError(RuntimeError):
    pass


class FullTextAcquisitionService:
    def __init__(
        self,
        *,
        providers: list[LiteratureProvider],
        artifacts: ArtifactStore,
        downloader: DownloadFunction | None = None,
        robots_checker: RobotsFunction | None = None,
        timeout_seconds: float = 60,
        max_bytes: int = 100 * 1024 * 1024,
    ) -> None:
        self.providers = providers
        self.artifacts = artifacts
        self.downloader = downloader or self._download
        self.robots_checker = robots_checker or self._robots_allowed
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes

    async def discover_locations(
        self, state: ResearchState, paper: PaperMetadata
    ) -> list[FullTextLocation]:
        found = [
            item
            for item in state.literature_quality.fulltext_locations
            if item.paper_id == paper.paper_id
        ]
        for provider in self.providers:
            capabilities = getattr(provider, "capabilities", ProviderCapabilities())
            method = getattr(provider, "discover_fulltext_locations", None)
            if not capabilities.open_access_location or method is None:
                continue
            try:
                provider_locations = await method(paper)
            except Exception as exc:
                self._failure(state, "fetch", provider.name, paper.paper_id, exc)
                continue
            for location in provider_locations:
                candidate = FullTextLocation.model_validate(location)
                if all(existing.url != candidate.url for existing in found):
                    found.append(candidate)
                    state.literature_quality.fulltext_locations.append(candidate)
        version_rank = {
            "version_of_record": 4,
            "accepted_manuscript": 3,
            "repository_copy": 2,
            "preprint": 1,
            "unknown": 0,
        }
        return sorted(
            found,
            key=lambda item: (
                item.access_type == "open",
                version_rank[item.version_type],
                item.mime_type == "application/pdf",
                item.confidence,
            ),
            reverse=True,
        )

    async def acquire(
        self, state: ResearchState, location: FullTextLocation
    ) -> FullTextAcquisitionResult:
        existing = next(
            (
                item
                for item in state.literature_quality.fulltext_acquisitions
                if item.paper_id == location.paper_id
                and item.location.url == location.url
                and item.validated
            ),
            None,
        )
        if existing is not None:
            await self.validate(existing)
            return existing
        try:
            if location.access_type != "open":
                raise FullTextAcquisitionError(
                    f"Full text access is {location.access_type}; automatic acquisition requires open access"
                )
            if location.mime_type not in {None, "application/pdf"} and not location.url.casefold().endswith(".pdf"):
                raise FullTextAcquisitionError(
                    "Scientific PDF acquisition requires a PDF location"
                )
            if not await self.robots_checker(location.url):
                raise FullTextAcquisitionError("Source access policy disallows acquisition")
            payload, observed_mime = await asyncio.wait_for(
                self.downloader(location.url), timeout=self.timeout_seconds
            )
            if len(payload) > self.max_bytes:
                raise FullTextAcquisitionError("PDF exceeds configured maximum size")
            self._validate_pdf_bytes(payload, observed_mime or location.mime_type)
            digest = sha256(payload).hexdigest()
            artifact_path = self.artifacts.write_bytes(
                f"artifacts/literature/papers/{location.paper_id}/source.pdf",
                payload,
            )
            result = FullTextAcquisitionResult(
                paper_id=location.paper_id,
                location=location,
                artifact_path=artifact_path,
                sha256=digest,
                byte_count=len(payload),
                validated=True,
            )
            state.literature_quality.fulltext_acquisitions.append(result)
            provenance = ProvenanceRecord(
                id=stable_id("PROV", location.paper_id, digest, "pdf"),
                entity_type="paper_fulltext_source",
                entity_id=location.paper_id,
                source_type="paper_pdf",
                source_id=location.url,
                artifact_path=artifact_path,
                extraction_method="legal-open-access-download",
                confidence=location.confidence,
                notes=(
                    f"version_type={location.version_type}; "
                    f"content_version_label={location.content_version_label or 'unknown'}"
                ),
            )
            if all(
                item.id != provenance.id
                for item in state.literature.provenance_records
            ):
                state.literature.provenance_records.append(provenance)
            return result
        except Exception as exc:
            self._failure(state, "acquire", location.source_provider, location.paper_id, exc)
            raise

    async def validate(self, result: FullTextAcquisitionResult) -> bool:
        payload = self.artifacts.read_bytes(result.artifact_path)
        self._validate_pdf_bytes(payload, result.location.mime_type)
        if sha256(payload).hexdigest() != result.sha256:
            raise FullTextAcquisitionError("Stored PDF hash does not match acquisition record")
        return True

    @staticmethod
    def _validate_pdf_bytes(payload: bytes, mime_type: str | None) -> None:
        if mime_type and "pdf" not in mime_type.casefold():
            raise FullTextAcquisitionError(f"Unexpected content type: {mime_type}")
        if not payload.startswith(b"%PDF-"):
            raise FullTextAcquisitionError("Downloaded content is not a PDF")
        if b"%%EOF" not in payload[-4096:]:
            raise FullTextAcquisitionError("PDF is truncated or missing EOF marker")

    async def _download(self, url: str) -> tuple[bytes, str | None]:
        return await asyncio.to_thread(self._download_sync, url)

    def _download_sync(self, url: str) -> tuple[bytes, str | None]:
        request = Request(
            url, headers={"User-Agent": "autonomous-research-agent/0.1"}
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = response.read(self.max_bytes + 1)
                return payload, response.headers.get_content_type()
        except (HTTPError, URLError, TimeoutError) as exc:
            raise FullTextAcquisitionError(f"Full-text download failed: {exc}") from exc

    async def _robots_allowed(self, url: str) -> bool:
        return await asyncio.to_thread(self._robots_allowed_sync, url)

    def _robots_allowed_sync(self, url: str) -> bool:
        parsed = urlsplit(url)
        robots_url = urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))
        request = Request(
            robots_url, headers={"User-Agent": "autonomous-research-agent/0.1"}
        )
        try:
            with urlopen(request, timeout=min(self.timeout_seconds, 15)) as response:
                lines = response.read().decode("utf-8", errors="replace").splitlines()
        except HTTPError as exc:
            if exc.code == 404:
                return True
            return False
        except (URLError, TimeoutError):
            return False
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(lines)
        return parser.can_fetch("autonomous-research-agent/0.1", url)

    @staticmethod
    def _failure(
        state: ResearchState,
        stage: str,
        provider: str,
        entity_id: str,
        error: Exception,
    ) -> None:
        state.literature.failures.append(
            LiteratureFailure(
                stage=stage,
                provider=provider,
                entity_id=entity_id,
                error_type=type(error).__name__,
                message=str(error)[:1000],
                retryable=False,
            )
        )
