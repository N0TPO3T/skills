from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from research_agent.core.ids import stable_id
from research_agent.literature.parsers.base import ScientificDocumentParser
from research_agent.schemas.document import ParsedScientificDocument
from research_agent.schemas.literature import LiteratureFailure, PaperContent
from research_agent.schemas.literature_quality import FullTextAcquisitionResult
from research_agent.schemas.provenance import ProvenanceRecord
from research_agent.schemas.state import ResearchState
from research_agent.storage.artifact_store import ArtifactStore


class DocumentParsingService:
    def __init__(
        self, *, parsers: list[ScientificDocumentParser], artifacts: ArtifactStore
    ) -> None:
        if not parsers:
            raise ValueError("At least one document parser is required")
        self.parsers = parsers
        self.artifacts = artifacts

    async def parse(
        self, state: ResearchState, acquisition: FullTextAcquisitionResult
    ) -> ParsedScientificDocument:
        source = self.artifacts.project_dir / acquisition.artifact_path
        errors: list[str] = []
        for parser in self.parsers:
            try:
                parsed = await parser.parse(source)
                parsed = parsed.model_copy(
                    update={
                        "paper_id": acquisition.paper_id,
                        "source_sha256": acquisition.sha256,
                        "source_artifact": acquisition.artifact_path,
                    }
                )
                if not parsed.sections:
                    raise ValueError("Parser returned no sections")
                document_artifact = self.artifacts.write_json(
                    f"artifacts/literature/papers/{acquisition.paper_id}/parsed_document.json",
                    parsed.model_dump(mode="json"),
                )
                if parsed.raw_tei:
                    self.artifacts.write_text(
                        f"artifacts/literature/papers/{acquisition.paper_id}/parsed_document.tei.xml",
                        parsed.raw_tei,
                    )
                self._upsert_document(state, parsed)
                text = "\n\n".join(section.text for section in parsed.sections)
                content_artifact = self.artifacts.write_text(
                    f"artifacts/literature/papers/{acquisition.paper_id}/content.txt",
                    text,
                )
                content = PaperContent(
                    paper_id=acquisition.paper_id,
                    content_type="pdf_text",
                    artifact_path=content_artifact,
                    source_url=acquisition.location.url,
                    sha256=sha256(text.encode("utf-8")).hexdigest(),
                    parser_name=parsed.parser,
                    parser_version=parsed.parser_version,
                    content_verified=True,
                    version_type=acquisition.location.version_type,
                    content_version_label=acquisition.location.content_version_label,
                    source_paper_id=acquisition.paper_id,
                    source_mime_type="application/pdf",
                )
                state.literature.contents.append(content)
                provenance = ProvenanceRecord(
                    id=stable_id("PROV", acquisition.paper_id, parsed.parser, "parsed"),
                    entity_type="parsed_scientific_document",
                    entity_id=acquisition.paper_id,
                    source_type="parsed_document",
                    source_id=acquisition.paper_id,
                    artifact_path=document_artifact,
                    extraction_method=parsed.parser,
                    confidence=parsed.parse_confidence,
                    notes="Parser confidence is structural and not semantic extraction confidence.",
                )
                if all(
                    item.id != provenance.id
                    for item in state.literature.provenance_records
                ):
                    state.literature.provenance_records.append(provenance)
                return parsed
            except Exception as exc:
                errors.append(f"{parser.name}: {exc}")
                state.literature.failures.append(
                    LiteratureFailure(
                        stage="parse",
                        provider=parser.name,
                        entity_id=acquisition.paper_id,
                        error_type=type(exc).__name__,
                        message=str(exc)[:1000],
                        retryable=False,
                    )
                )
        raise RuntimeError("All document parsers failed: " + "; ".join(errors))

    @staticmethod
    def _upsert_document(
        state: ResearchState, document: ParsedScientificDocument
    ) -> None:
        for index, existing in enumerate(
            state.literature_quality.parsed_documents
        ):
            if (
                existing.paper_id == document.paper_id
                and existing.source_sha256 == document.source_sha256
            ):
                state.literature_quality.parsed_documents[index] = document
                return
        state.literature_quality.parsed_documents.append(document)

