from __future__ import annotations

import pytest
from pydantic import ValidationError

from research_agent.schemas.literature import (
    ExtractedStatement,
    PaperContent,
    PaperExtraction,
    PaperIdentifier,
    PaperMetadata,
)
from research_agent.schemas.provenance import PromptMetadata, ProvenanceRecord


def prompt_metadata() -> PromptMetadata:
    return PromptMetadata(profile="literature_extract", version="1", sha256="a" * 64)


def test_literature_records_roundtrip() -> None:
    metadata = PaperMetadata(
        paper_id="PAPER-1",
        title="A Paper",
        authors=["A. Author"],
        year=2025,
        identifiers=PaperIdentifier(doi="10.1/example"),
        source_records=["https://doi.org/10.1/example"],
        metadata_verified=True,
        verification_confidence=0.95,
    )
    content = PaperContent(
        paper_id="PAPER-1",
        content_type="pdf_text",
        artifact_path="artifacts/literature/papers/PAPER-1/content.txt",
        sha256="b" * 64,
        parser_name="test-parser",
        content_verified=True,
    )
    provenance = ProvenanceRecord(
        id="PROV-1",
        entity_type="extracted_statement",
        entity_id="STATEMENT-1",
        source_type="paper_full_text",
        source_id="PAPER-1",
        artifact_path=content.artifact_path,
        extraction_method="test-extractor",
        confidence=0.9,
    )
    extraction = PaperExtraction(
        paper_id="PAPER-1",
        main_claim="A bounded claim",
        extraction_confidence=0.9,
        provenance_ids=[provenance.id],
        extractor_model="test",
        prompt_metadata=prompt_metadata(),
    )
    assert PaperMetadata.model_validate_json(metadata.model_dump_json()) == metadata
    assert PaperContent.model_validate_json(content.model_dump_json()) == content
    assert PaperExtraction.model_validate_json(extraction.model_dump_json()) == extraction
    assert ProvenanceRecord.model_validate_json(provenance.model_dump_json()) == provenance


def test_synthetic_metadata_cannot_be_verified() -> None:
    with pytest.raises(ValidationError, match="Synthetic"):
        PaperMetadata(
            paper_id="PAPER-MOCK",
            title="Synthetic",
            authors=["Fixture"],
            source_records=["fixture://paper"],
            metadata_verified=True,
            verification_confidence=1.0,
            synthetic_test_data=True,
        )


def test_statement_requires_provenance() -> None:
    with pytest.raises(ValidationError):
        ExtractedStatement(
            id="STATEMENT-1",
            paper_id="PAPER-1",
            statement_type="claim",
            statement="Unsupported statement",
            provenance_ids=[],
            confidence=0.8,
        )
