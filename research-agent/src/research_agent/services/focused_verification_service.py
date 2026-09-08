from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from research_agent.core.ids import stable_id
from research_agent.schemas.document import DocumentSection
from research_agent.schemas.gap import ResearchGap
from research_agent.schemas.literature import ExtractedStatement, PaperContent
from research_agent.schemas.literature_quality import (
    FocusedVerificationBatch,
    FocusedVerificationDecision,
    VerificationTask,
)
from research_agent.schemas.provenance import (
    ProvenanceRecord,
    SourceLocator,
    StatementEpistemicType,
)
from research_agent.schemas.state import ResearchState
from research_agent.skill_context import SkillContextLoader
from research_agent.storage.artifact_store import ArtifactStore


class StructuredBackend(Protocol):
    async def run_structured(
        self,
        instructions: str,
        context: dict[str, object],
        tools: dict[str, str],
        *,
        response_model: type[FocusedVerificationBatch],
        workflow_contract: bool = False,
    ) -> FocusedVerificationBatch: ...


@dataclass(frozen=True)
class SourcePassage:
    id: str
    paper_id: str
    content: PaperContent
    locator: SourceLocator
    text: str


class FocusedEvidenceVerificationService:
    def __init__(
        self,
        *,
        backend_factory: Callable[[], StructuredBackend],
        artifacts: ArtifactStore,
        skills: SkillContextLoader | None = None,
        max_passage_characters: int = 3000,
    ) -> None:
        self.backend_factory = backend_factory
        self.artifacts = artifacts
        self.skills = skills or SkillContextLoader()
        self.max_passage_characters = max_passage_characters

    async def verify_gap(
        self,
        state: ResearchState,
        gap_id: str,
    ) -> list[VerificationTask]:
        gap = next((item for item in state.gaps.candidates if item.id == gap_id), None)
        if gap is None:
            raise KeyError(f"Unknown GAP: {gap_id}")
        requested_ids = list(
            dict.fromkeys(
                [*gap.supporting_statement_ids, *gap.contradictory_statement_ids]
            )
        )
        statements = {
            item.id: item
            for item in state.literature.statements
            if item.id in requested_ids
        }
        if set(statements) != set(requested_ids):
            missing = sorted(set(requested_ids) - set(statements))
            raise ValueError(f"GAP references missing statements: {missing}")
        pending = [
            statements[statement_id]
            for statement_id in requested_ids
            if not self._already_focused(state, statements[statement_id])
        ]
        if not pending:
            return []
        passages_by_statement = {
            statement.id: self._passages(state, gap, statement) for statement in pending
        }
        context = {
            "gap": {
                "id": gap.id,
                "title": gap.title,
                "observed_phenomena": gap.observed_phenomena,
                "common_limitation": gap.common_limitation,
                "root_cause_hypothesis": gap.root_cause_hypothesis,
                "remaining_rule": (
                    "Root-cause hypotheses remain agent inference even when source "
                    "observations are accepted."
                ),
            },
            "statements": [
                self._statement_context(state, statement, passages_by_statement)
                for statement in pending
            ],
        }
        result = await self.backend_factory().run_structured(
            self.skills.load_focused_verification().content,
            context,
            {},
            response_model=FocusedVerificationBatch,
        )
        decisions = {item.statement_id: item for item in result.decisions}
        if set(decisions) != {item.id for item in pending}:
            raise ValueError(
                "Focused verifier must return exactly one decision per statement"
            )
        passage_index = {
            passage.id: passage
            for passages in passages_by_statement.values()
            for passage in passages
        }
        for decision in result.decisions:
            passage = passage_index.get(decision.source_passage_id)
            if (
                passage is None
                or passage.paper_id != statements[decision.statement_id].paper_id
            ):
                raise ValueError("Focused verifier selected an unknown source passage")
        recorded: list[VerificationTask] = []
        for decision in result.decisions:
            statement = statements[decision.statement_id]
            references = self._gap_references(state, statement.id)
            recorded.append(
                self._record_decision(
                    state,
                    gap_id=gap.id,
                    statement=statement,
                    decision=decision,
                    passage=passage_index[decision.source_passage_id],
                    batch=result,
                )
            )
            if self._retryable_weak(statement, decision):
                retry_task = await self._retry_narrowed(
                    state,
                    gap=gap,
                    statement=statement,
                    decision=decision,
                    passages=passages_by_statement[statement.id],
                )
                recorded.append(retry_task)
                if retry_task.status == "accepted":
                    self._restore_gap_references(
                        state, references, retry_task.statement_id
                    )
        return recorded

    async def _retry_narrowed(
        self,
        state: ResearchState,
        *,
        gap: ResearchGap,
        statement: ExtractedStatement,
        decision: FocusedVerificationDecision,
        passages: list[SourcePassage],
    ) -> VerificationTask:
        narrowed = statement.model_copy(
            update={
                "statement": decision.supported_scope.strip(),
                "epistemic_type": decision.epistemic_type,
            }
        )
        context = {
            "gap": {
                "id": gap.id,
                "title": gap.title,
                "observed_phenomena": gap.observed_phenomena,
                "common_limitation": gap.common_limitation,
                "root_cause_hypothesis": gap.root_cause_hypothesis,
                "remaining_rule": (
                    "Root-cause hypotheses remain agent inference even when source "
                    "observations are accepted."
                ),
            },
            "retry": (
                "This is a separate verification pass over wording narrowed after "
                "a WEAK decision. Judge the narrowed statement from source only."
            ),
            "statements": [
                self._statement_context(state, narrowed, {narrowed.id: passages})
            ],
        }
        result = await self.backend_factory().run_structured(
            self.skills.load_focused_verification().content,
            context,
            {},
            response_model=FocusedVerificationBatch,
        )
        if len(result.decisions) != 1:
            raise ValueError(
                "Narrowed focused verification must return exactly one decision"
            )
        retry = result.decisions[0]
        passage_index = {item.id: item for item in passages}
        passage = passage_index.get(retry.source_passage_id)
        if retry.statement_id != narrowed.id or passage is None:
            raise ValueError(
                "Narrowed focused verifier selected an unknown statement or passage"
            )
        return self._record_decision(
            state,
            gap_id=gap.id,
            statement=narrowed,
            decision=retry,
            passage=passage,
            batch=result,
        )

    def _passages(
        self,
        state: ResearchState,
        gap: ResearchGap,
        statement: ExtractedStatement,
    ) -> list[SourcePassage]:
        content = next(
            (
                item
                for item in reversed(state.literature.contents)
                if item.paper_id == statement.paper_id
                and item.content_verified
                and item.content_type in {"full_text", "html", "pdf_text"}
            ),
            None,
        )
        document = next(
            (
                item
                for item in reversed(state.literature_quality.parsed_documents)
                if item.paper_id == statement.paper_id
            ),
            None,
        )
        if content is None or document is None:
            raise ValueError(
                f"Focused verification requires parsed full text for {statement.paper_id}"
            )
        query = " ".join(
            [
                statement.statement,
                *gap.observed_phenomena,
                gap.common_limitation,
            ]
        )
        keywords = self._keywords(query)
        chunks = [
            (self._score(keywords, text), section, start, end, text)
            for section in document.sections
            for start, end, text in self._chunks(section)
        ]
        selected = sorted(chunks, key=lambda item: item[0], reverse=True)[:3]
        if not selected:
            raise ValueError(f"No readable source passage for {statement.paper_id}")
        return [
            SourcePassage(
                id=stable_id(
                    "PASSAGE", statement.id, section.id, start, end, content.sha256
                ),
                paper_id=statement.paper_id,
                content=content,
                locator=SourceLocator(
                    section_id=section.id,
                    section_title=section.title,
                    char_start=start,
                    char_end=end,
                ),
                text=text,
            )
            for _, section, start, end, text in selected
        ]

    def _chunks(self, section: DocumentSection):
        text = section.text
        step = max(self.max_passage_characters - 400, 1)
        for start in range(0, len(text), step):
            end = min(start + self.max_passage_characters, len(text))
            yield start, end, text[start:end]
            if end == len(text):
                break

    @staticmethod
    def _keywords(value: str) -> set[str]:
        stop = {"that", "this", "with", "from", "their", "under", "which", "while"}
        return {
            token
            for token in re.findall(r"[a-z0-9]+", value.casefold())
            if len(token) > 3 and token not in stop
        }

    @staticmethod
    def _score(keywords: set[str], passage: str) -> int:
        return len(keywords & set(re.findall(r"[a-z0-9]+", passage.casefold())))

    @staticmethod
    def _statement_context(
        state: ResearchState,
        statement: ExtractedStatement,
        passages: dict[str, list[SourcePassage]],
    ) -> dict[str, object]:
        paper = next(
            item
            for item in state.literature.paper_metadata
            if item.paper_id == statement.paper_id
        )
        return {
            "statement_id": statement.id,
            "proposed_statement": statement.statement,
            "statement_type": statement.statement_type,
            "current_epistemic_type": statement.epistemic_type.value,
            "paper_metadata": paper.model_dump(mode="json"),
            "source_passages": [
                {
                    "passage_id": passage.id,
                    "content_sha256": passage.content.sha256,
                    "content_version": passage.content.content_version_label,
                    "source_locator": passage.locator.model_dump(mode="json"),
                    "text": passage.text,
                }
                for passage in passages[statement.id]
            ],
        }

    def _record_decision(
        self,
        state: ResearchState,
        *,
        gap_id: str,
        statement: ExtractedStatement,
        decision: FocusedVerificationDecision,
        passage: SourcePassage,
        batch: FocusedVerificationBatch,
    ) -> VerificationTask:
        decision = self._normalize_decision(statement, decision)
        verified_at = datetime.now(UTC)
        artifact_id = stable_id(
            "FOCUSED-VERIFY",
            statement.id,
            passage.content.sha256,
            decision.verdict,
            decision.supported_scope,
        )
        artifact_path = self.artifacts.write_json(
            f"artifacts/literature/verifications/{artifact_id}.json",
            {
                "gap_id": gap_id,
                "original_statement_id": statement.id,
                "decision": decision.model_dump(mode="json"),
                "paper_id": statement.paper_id,
                "content_sha256": passage.content.sha256,
                "content_version": passage.content.content_version_label,
                "source_artifact": passage.content.artifact_path,
                "source_locator": passage.locator.model_dump(mode="json"),
                "source_passage": passage.text,
                "batch_summary": batch.summary,
                "uncertainties": batch.uncertainties,
                "verified_at": verified_at,
                "verifier": "host_agent",
            },
        )
        if decision.verdict != "accept":
            task = VerificationTask(
                id=stable_id("VERIFY", statement.paper_id, statement.id),
                paper_id=statement.paper_id,
                statement_id=statement.id,
                reason=decision.reason,
                priority=1.0,
                status="weak" if decision.verdict == "weak" else "rejected",
                epistemic_type=decision.epistemic_type,
                source_locator=passage.locator,
                supported_scope=decision.supported_scope,
                overstatement=decision.overstatement,
                content_sha256=passage.content.sha256,
                verifier="host_agent",
                verification_artifact=artifact_path,
                verified_at=verified_at,
            )
            self._upsert_task(state, task)
            self._remove_gap_reference(state, statement.id)
            return task
        statement_type = (
            "result"
            if decision.epistemic_type == StatementEpistemicType.DIRECT_RESULT
            else "limitation_inferred"
            if decision.epistemic_type == StatementEpistemicType.AGENT_INFERRED
            and statement.statement_type == "limitation_claimed"
            else statement.statement_type
        )
        verified_statement_id = stable_id(
            "STATEMENT-FOCUSED",
            statement.paper_id,
            passage.content.sha256,
            statement_type,
            decision.supported_scope,
        )
        provenance_id = stable_id("PROV", verified_statement_id, passage.id)
        verified_statement = ExtractedStatement(
            id=verified_statement_id,
            paper_id=statement.paper_id,
            statement_type=statement_type,
            statement=decision.supported_scope,
            provenance_ids=[provenance_id],
            confidence=0.95,
            epistemic_type=decision.epistemic_type,
        )
        provenance = ProvenanceRecord(
            id=provenance_id,
            entity_type="extracted_statement",
            entity_id=verified_statement.id,
            source_type="paper_full_text",
            source_id=statement.paper_id,
            artifact_path=passage.content.artifact_path,
            extraction_method="focused-host-verification",
            source_locator=passage.locator,
            confidence=0.95,
            notes=(
                "Agent inference; not an author-stated observation."
                if decision.epistemic_type == StatementEpistemicType.AGENT_INFERRED
                else None
            ),
        )
        self._upsert_statement(state, verified_statement)
        self._upsert_provenance(state, provenance)
        task = VerificationTask(
            id=stable_id("VERIFY", statement.paper_id, verified_statement.id),
            paper_id=statement.paper_id,
            statement_id=verified_statement.id,
            reason=decision.reason,
            priority=1.0,
            status="accepted",
            epistemic_type=decision.epistemic_type,
            source_locator=passage.locator,
            supported_scope=decision.supported_scope,
            overstatement=decision.overstatement,
            content_sha256=passage.content.sha256,
            verifier="host_agent",
            verification_artifact=artifact_path,
            verified_at=verified_at,
        )
        self._upsert_task(state, task)
        self._replace_gap_reference(state, statement.id, verified_statement.id)
        return task

    @staticmethod
    def _normalize_decision(
        statement: ExtractedStatement,
        decision: FocusedVerificationDecision,
    ) -> FocusedVerificationDecision:
        if decision.verdict != "accept":
            return decision
        scope = decision.supported_scope.strip()
        meta_scope = scope.casefold()
        if "full proposed statement" in meta_scope or meta_scope in {
            "supported as written",
            "the statement as written",
        }:
            return decision.model_copy(update={"supported_scope": statement.statement})
        return decision.model_copy(update={"supported_scope": scope})

    @staticmethod
    def _retryable_weak(
        statement: ExtractedStatement,
        decision: FocusedVerificationDecision,
    ) -> bool:
        scope = decision.supported_scope.strip()
        return (
            decision.verdict == "weak"
            and bool(scope)
            and scope.casefold() != statement.statement.strip().casefold()
        )

    @staticmethod
    def _gap_references(
        state: ResearchState, statement_id: str
    ) -> list[tuple[str, str]]:
        references: list[tuple[str, str]] = []
        for gap in state.gaps.candidates:
            if statement_id in gap.supporting_statement_ids:
                references.append((gap.id, "supporting"))
            if statement_id in gap.contradictory_statement_ids:
                references.append((gap.id, "contradictory"))
        return references

    @staticmethod
    def _restore_gap_references(
        state: ResearchState,
        references: list[tuple[str, str]],
        statement_id: str,
    ) -> None:
        gaps = {gap.id: gap for gap in state.gaps.candidates}
        for gap_id, role in references:
            values = (
                gaps[gap_id].supporting_statement_ids
                if role == "supporting"
                else gaps[gap_id].contradictory_statement_ids
            )
            if statement_id not in values:
                values.append(statement_id)

    @staticmethod
    def _already_focused(state: ResearchState, statement: ExtractedStatement) -> bool:
        return any(
            task.statement_id == statement.id
            and task.verifier == "host_agent"
            and task.status in {"accepted", "weak", "rejected"}
            for task in state.literature_quality.verification_tasks
        )

    @staticmethod
    def _upsert_task(state: ResearchState, task: VerificationTask) -> None:
        for index, existing in enumerate(state.literature_quality.verification_tasks):
            if existing.statement_id == task.statement_id:
                state.literature_quality.verification_tasks[index] = task
                return
        state.literature_quality.verification_tasks.append(task)

    @staticmethod
    def _upsert_statement(state: ResearchState, statement: ExtractedStatement) -> None:
        for index, existing in enumerate(state.literature.statements):
            if existing.id == statement.id:
                state.literature.statements[index] = statement
                return
        state.literature.statements.append(statement)

    @staticmethod
    def _upsert_provenance(state: ResearchState, provenance: ProvenanceRecord) -> None:
        for index, existing in enumerate(state.literature.provenance_records):
            if existing.id == provenance.id:
                state.literature.provenance_records[index] = provenance
                return
        state.literature.provenance_records.append(provenance)

    @staticmethod
    def _replace_gap_reference(
        state: ResearchState, old_statement_id: str, new_statement_id: str
    ) -> None:
        for gap in state.gaps.candidates:
            gap.supporting_statement_ids = [
                new_statement_id if item == old_statement_id else item
                for item in gap.supporting_statement_ids
            ]
            gap.contradictory_statement_ids = [
                new_statement_id if item == old_statement_id else item
                for item in gap.contradictory_statement_ids
            ]

    @staticmethod
    def _remove_gap_reference(state: ResearchState, statement_id: str) -> None:
        for gap in state.gaps.candidates:
            gap.supporting_statement_ids = [
                item for item in gap.supporting_statement_ids if item != statement_id
            ]
            gap.contradictory_statement_ids = [
                item for item in gap.contradictory_statement_ids if item != statement_id
            ]
