from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from research_agent.literature.fulltext.acquisition import (
    FullTextAcquisitionError,
    FullTextAcquisitionService,
)
from research_agent.schemas.literature_quality import FullTextLocation
from research_agent.schemas.project import ProjectInfo
from research_agent.schemas.state import ResearchState
from research_agent.storage.artifact_store import ArtifactStore


VALID_PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF"


def state() -> ResearchState:
    return ResearchState(project=ProjectInfo(id="demo", name="Demo"))


def location(**updates) -> FullTextLocation:
    values = {
        "paper_id": "PAPER-1",
        "url": "https://repository.test/paper.pdf",
        "source_provider": "fixture",
        "version_type": "accepted_manuscript",
        "access_type": "open",
        "mime_type": "application/pdf",
        "confidence": 0.95,
        "content_version_label": "accepted-v1",
    }
    values.update(updates)
    return FullTextLocation(**values)


def service(tmp_path: Path, payload: bytes = VALID_PDF) -> FullTextAcquisitionService:
    project = tmp_path / "project"
    project.mkdir()

    async def download(url: str):
        return payload, "application/pdf"

    async def robots(url: str):
        return True

    return FullTextAcquisitionService(
        providers=[],
        artifacts=ArtifactStore(project),
        downloader=download,
        robots_checker=robots,
    )


async def test_legal_oa_location_is_acquired_and_versioned(tmp_path: Path) -> None:
    instance = service(tmp_path)
    current = state()
    result = await instance.acquire(current, location())
    assert result.validated
    assert result.location.version_type == "accepted_manuscript"
    assert result.location.content_version_label == "accepted-v1"
    assert result.sha256 == sha256(VALID_PDF).hexdigest()
    assert await instance.validate(result)


async def test_restricted_location_is_rejected(tmp_path: Path) -> None:
    instance = service(tmp_path)
    current = state()
    with pytest.raises(FullTextAcquisitionError, match="requires open access"):
        await instance.acquire(current, location(access_type="restricted"))
    assert current.literature.failures[-1].stage == "acquire"


async def test_corrupted_pdf_is_rejected(tmp_path: Path) -> None:
    instance = service(tmp_path, b"not a pdf")
    with pytest.raises(FullTextAcquisitionError, match="not a PDF"):
        await instance.acquire(state(), location())


async def test_stored_pdf_hash_is_revalidated(tmp_path: Path) -> None:
    instance = service(tmp_path)
    result = await instance.acquire(state(), location())
    path = instance.artifacts.project_dir / result.artifact_path
    path.write_bytes(VALID_PDF + b"tampered")
    with pytest.raises(FullTextAcquisitionError, match="hash"):
        await instance.validate(result)
