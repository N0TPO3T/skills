from __future__ import annotations

from research_agent.core.ids import stable_id
from research_agent.literature.extraction import PaperExtractor
from research_agent.prompts.loader import PromptLoader
from research_agent.schemas.document import DocumentSection, ParsedScientificDocument
from research_agent.schemas.literature import (
    ExtractedStatement,
    PaperContent,
    PaperExtraction,
    PaperExtractionDraft,
    PaperMetadata,
)
from research_agent.schemas.provenance import (
    ProvenanceRecord,
    SourceLocator,
    StatementEpistemicType,
)
from research_agent.schemas.state import ResearchState
from research_agent.services.verification_queue_service import VerificationQueueService
from research_agent.services.source_version_comparison_service import (
    SourceVersionComparisonService,
)
from research_agent.storage.artifact_store import ArtifactStore


FIELD_ROLES = {
    "problem": ("abstract", "introduction"),
    "claim": ("abstract", "conclusion"),
    "method": ("method",),
    "assumption": ("method", "analysis"),
    "result": ("results", "experiments"),
    "limitation_claimed": (
        "limitations",
        "analysis",
        "conclusion",
        "experiments",
    ),
    "limitation_inferred": ("limitations", "analysis", "results"),
    "failure_mode": ("results", "analysis", "limitations"),
}


class SectionAwareExtractionService:
    def __init__(
        self,
        *,
        extractor: PaperExtractor,
        artifacts: ArtifactStore,
        prompts: PromptLoader | None = None,
        max_section_characters: int = 12000,
    ) -> None:
        self.extractor = extractor
        self.artifacts = artifacts
        self.prompts = prompts or PromptLoader()
        self.max_section_characters = max_section_characters
        self.verification_queue = VerificationQueueService()

    async def extract(
        self,
        state: ResearchState,
        *,
        paper_id: str,
        source_sha256: str | None = None,
        central_gap_statement_ids: set[str] | None = None,
    ) -> PaperExtraction:
        metadata = self._metadata(state, paper_id)
        document = self._document(state, paper_id, source_sha256)
        content = self._content(state, paper_id, document.source_sha256)
        selected_sections = [
            section
            for section in document.sections
            if section.normalized_role
            in {
                "abstract",
                "introduction",
                "method",
                "experiments",
                "results",
                "analysis",
                "limitations",
                "conclusion",
            }
        ]
        if not selected_sections:
            raise ValueError("No decision-relevant parsed sections are available")
        bounded_text = "\n\n".join(
            f"[SECTION id={section.id} role={section.normalized_role} title={section.title or ''}]\n"
            f"{section.text[: self.max_section_characters]}"
            for section in selected_sections
        )
        draft = await self.extractor.extract(
            metadata=metadata, content=content, text=bounded_text
        )
        draft = PaperExtractionDraft.model_validate(draft)
        statements, provenance = self._build_statements(
            paper_id, content, selected_sections, draft
        )
        if not statements:
            raise ValueError("Section-aware extractor produced no statements")
        for item in provenance:
            if all(
                existing.id != item.id
                for existing in state.literature.provenance_records
            ):
                state.literature.provenance_records.append(item)
        for item in statements:
            if all(
                existing.id != item.id for existing in state.literature.statements
            ):
                state.literature.statements.append(item)
            has_limitations_section = any(
                section.normalized_role == "limitations"
                for section in selected_sections
            )
            self.verification_queue.enqueue_if_needed(
                state,
                item,
                central_gap_statement_ids=central_gap_statement_ids,
                explicit_limitation_section=has_limitations_section,
            )
        prompt = self.prompts.metadata(
            role="literature_extract", policies=["evidence", "citation"], version="2"
        )
        extraction = PaperExtraction(
            paper_id=paper_id,
            **draft.model_dump(),
            provenance_ids=[item.id for item in provenance],
            extractor_model=self.extractor.model,
            prompt_metadata=prompt,
            partial=draft.extraction_confidence < 0.8,
            content_sha256=content.sha256,
            content_version_label=content.content_version_label,
            source_paper_id=content.source_paper_id or paper_id,
        )
        state.literature.extractions.append(extraction)
        SourceVersionComparisonService().refresh(state)
        self.artifacts.write_json(
            f"artifacts/literature/papers/{paper_id}/extraction.json",
            extraction.model_dump(mode="json"),
        )
        self.artifacts.write_json(
            f"artifacts/literature/papers/{paper_id}/provenance.json",
            [item.model_dump(mode="json") for item in provenance],
        )
        return extraction

    def _build_statements(
        self,
        paper_id: str,
        content: PaperContent,
        sections: list[DocumentSection],
        draft: PaperExtractionDraft,
    ) -> tuple[list[ExtractedStatement], list[ProvenanceRecord]]:
        values: list[tuple[str, str]] = []
        for field, statement_type in (
            ("problem", "problem"),
            ("main_claim", "claim"),
            ("method_summary", "method"),
        ):
            value = getattr(draft, field)
            if value:
                values.append((statement_type, value))
        for field, statement_type in (
            ("core_assumptions", "assumption"),
            ("main_results", "result"),
            ("limitations_claimed", "limitation_claimed"),
            ("limitations_inferred", "limitation_inferred"),
            ("failure_modes", "failure_mode"),
        ):
            values.extend((statement_type, value) for value in getattr(draft, field))
        statements = []
        provenance = []
        for statement_type, value in values:
            section = self._source_section(sections, statement_type)
            epistemic = (
                StatementEpistemicType.DIRECT_RESULT
                if statement_type == "result"
                else StatementEpistemicType.AGENT_INFERRED
                if statement_type == "limitation_inferred"
                else StatementEpistemicType.AUTHOR_STATED
            )
            statement_id = stable_id(
                "STATEMENT", paper_id, content.sha256, statement_type, value
            )
            provenance_id = stable_id(
                "PROV", statement_id, section.id if section else "unknown"
            )
            locator = (
                SourceLocator(section_id=section.id, section_title=section.title)
                if section
                else SourceLocator()
            )
            provenance.append(
                ProvenanceRecord(
                    id=provenance_id,
                    entity_type="extracted_statement",
                    entity_id=statement_id,
                    source_type="paper_full_text",
                    source_id=paper_id,
                    artifact_path=content.artifact_path,
                    extraction_method=self.extractor.name,
                    source_locator=locator,
                    confidence=draft.extraction_confidence,
                    notes=(
                        "Agent inference; not an author-stated observation."
                        if epistemic == StatementEpistemicType.AGENT_INFERRED
                        else None
                    ),
                )
            )
            statements.append(
                ExtractedStatement(
                    id=statement_id,
                    paper_id=paper_id,
                    statement_type=statement_type,
                    statement=value,
                    provenance_ids=[provenance_id],
                    confidence=draft.extraction_confidence,
                    epistemic_type=epistemic,
                )
            )
        return statements, provenance

    @staticmethod
    def _source_section(
        sections: list[DocumentSection], statement_type: str
    ) -> DocumentSection | None:
        roles = FIELD_ROLES[statement_type]
        return next(
            (
                section
                for role in roles
                for section in sections
                if section.normalized_role == role
            ),
            None,
        )

    @staticmethod
    def _metadata(state: ResearchState, paper_id: str) -> PaperMetadata:
        metadata = next(
            (
                item
                for item in state.literature.paper_metadata
                if item.paper_id == paper_id
            ),
            None,
        )
        if metadata is None or not metadata.metadata_verified:
            raise ValueError("Verified paper metadata is required")
        return metadata

    @staticmethod
    def _document(
        state: ResearchState, paper_id: str, source_sha256: str | None
    ) -> ParsedScientificDocument:
        documents = [
            item
            for item in state.literature_quality.parsed_documents
            if item.paper_id == paper_id
            and (source_sha256 is None or item.source_sha256 == source_sha256)
        ]
        if not documents:
            raise ValueError("Parsed scientific document is required")
        return documents[-1]

    @staticmethod
    def _content(
        state: ResearchState, paper_id: str, source_sha256: str
    ) -> PaperContent:
        contents = [
            item
            for item in state.literature.contents
            if item.paper_id == paper_id
            and item.content_verified
            and item.content_type == "pdf_text"
        ]
        if not contents:
            raise ValueError("Verified parsed PDF content is required")
        return contents[-1]
