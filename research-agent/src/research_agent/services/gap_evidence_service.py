from __future__ import annotations

from research_agent.core.ids import stable_id
from research_agent.schemas.gap import GapEvidenceSummary, ResearchGap
from research_agent.schemas.literature import (
    ExtractedStatement,
    LiteratureState,
    PaperContent,
    PaperMetadata,
)
from research_agent.schemas.literature_quality import (
    LiteratureQualityState,
    VerificationTask,
)
from research_agent.schemas.provenance import ProvenanceRecord, StatementEpistemicType
from research_agent.services.literature_service import can_support_literature_claim


class InvalidGapEvidenceError(ValueError):
    pass


STATEMENT_CLAIM_TYPES = {
    "problem": "problem",
    "claim": "claim",
    "method": "method",
    "result": "result",
    "limitation_claimed": "specific_limitation",
    "limitation_inferred": "specific_limitation",
    "failure_mode": "failure_mode",
    "assumption": "assumption",
}

STATEMENT_CAPABILITIES = {
    "problem": "problem",
    "claim": "main_claim",
    "method": "method",
    "result": "results",
    "limitation_claimed": "limitations",
    "limitation_inferred": "limitations",
    "failure_mode": "failure_modes",
    "assumption": "assumptions",
}


class GapEvidenceService:
    def validate_statement(
        self,
        literature: LiteratureState,
        statement: ExtractedStatement,
        quality: LiteratureQualityState | None = None,
    ) -> bool:
        return (
            self.classify_statement(literature, statement, quality)
            == "verified_observation"
        )

    def classify_statement(
        self,
        literature: LiteratureState,
        statement: ExtractedStatement,
        quality: LiteratureQualityState | None = None,
    ) -> str:
        paper = self._metadata(literature, statement.paper_id)
        if paper is None or paper.publication_integrity_status == "retracted":
            return "blocked"
        provenance = {item.id: item for item in literature.provenance_records}
        records = [provenance.get(item) for item in statement.provenance_ids]
        if any(record is None for record in records):
            return "blocked"
        artifact_paths = {
            record.artifact_path for record in records if record is not None
        }
        task = (
            next(
                (
                    item
                    for item in quality.verification_tasks
                    if item.statement_id == statement.id
                ),
                None,
            )
            if quality is not None
            else None
        )
        focused_hash = (
            task.content_sha256
            if task is not None and task.verifier == "host_agent"
            else None
        )
        content = next(
            (
                item
                for item in reversed(literature.contents)
                if item.paper_id == statement.paper_id
                and item.artifact_path in artifact_paths
                and (focused_hash is None or item.sha256 == focused_hash)
            ),
            None,
        )
        if content is None:
            return "blocked"
        for record in records:
            assert record is not None
            if (
                record.entity_id != statement.id
                or record.source_id != statement.paper_id
                or record.source_type
                not in {"paper_abstract", "paper_full_text", "web_source"}
                or not record.artifact_path
                or record.artifact_path != content.artifact_path
            ):
                return "blocked"
        if statement.statement_type == "limitation_inferred" and not all(
            record and record.notes and "inference" in record.notes.casefold()
            for record in records
        ):
            return "blocked"
        if not can_support_literature_claim(
            paper, STATEMENT_CLAIM_TYPES[statement.statement_type], content
        ):
            return "blocked"
        if quality is None:
            return "unverified_clue"
        capability = STATEMENT_CAPABILITIES[statement.statement_type]
        status = next(
            (
                item
                for item in quality.capability_statuses
                if item.capability == capability
            ),
            None,
        )
        if task and task.status == "rejected":
            return "blocked"
        focused_verified = self._focused_verified(task, statement, content, records)
        human_verified = bool(
            task
            and task.status in {"accepted", "edited"}
            and task.verifier in {None, "human"}
        )
        if focused_verified or human_verified:
            return "verified_observation"
        if status is not None and status.status == "disabled":
            return "blocked"
        if task and task.status in {"pending", "weak"}:
            return (
                "agent_inference"
                if statement.epistemic_type == StatementEpistemicType.AGENT_INFERRED
                else "probable_observation"
            )
        if statement.epistemic_type == StatementEpistemicType.AGENT_INFERRED:
            return "agent_inference"
        if status is None:
            return "unverified_clue"
        if status.status == "experimental":
            return "probable_observation"
        return "verified_observation"

    @staticmethod
    def _focused_verified(
        task: VerificationTask | None,
        statement: ExtractedStatement,
        content: PaperContent,
        records: list[ProvenanceRecord | None],
    ) -> bool:
        if (
            task is None
            or task.status != "accepted"
            or task.verifier != "host_agent"
            or task.paper_id != statement.paper_id
            or task.statement_id != statement.id
            or task.epistemic_type != statement.epistemic_type
            or task.epistemic_type == StatementEpistemicType.AGENT_INFERRED
            or task.supported_scope != statement.statement
            or task.content_sha256 != content.sha256
            or task.source_locator is None
            or not task.verification_artifact
            or task.verified_at is None
        ):
            return False
        return any(
            record is not None
            and record.source_locator == task.source_locator
            and record.artifact_path == content.artifact_path
            for record in records
        )

    def summarize_and_validate(
        self,
        literature: LiteratureState,
        gap: ResearchGap,
        quality: LiteratureQualityState | None = None,
    ) -> GapEvidenceSummary:
        if gap.synthetic_test_data and not gap.supporting_statement_ids:
            summary = GapEvidenceSummary(
                independent_paper_count=0,
                supporting_statement_count=0,
                contradictory_statement_count=0,
                content_verified_paper_count=0,
                confidence=0.0,
            )
            gap.evidence_summary = summary
            return summary
        if not gap.supporting_statement_ids:
            raise InvalidGapEvidenceError(
                "A non-synthetic gap requires statement-level evidence"
            )
        statements = {item.id: item for item in literature.statements}
        supporting: list[ExtractedStatement] = []
        for statement_id in gap.supporting_statement_ids:
            statement = statements.get(statement_id)
            if statement is None:
                raise InvalidGapEvidenceError(
                    f"Gap references missing or unverified statement: {statement_id}"
                )
            classification = self.classify_statement(literature, statement, quality)
            if quality is not None and (
                statement.confidence < 0.8
                or classification in {"probable_observation", "agent_inference"}
            ):
                self._enqueue_central_verification(quality, statement, classification)
                classification = self.classify_statement(literature, statement, quality)
            if classification != "verified_observation":
                raise InvalidGapEvidenceError(
                    f"Gap references missing or unverified statement: {statement_id}"
                )
            supporting.append(statement)
        contradictory: list[ExtractedStatement] = []
        for statement_id in gap.contradictory_statement_ids:
            statement = statements.get(statement_id)
            if statement is None or not self.validate_statement(
                literature, statement, quality
            ):
                raise InvalidGapEvidenceError(
                    f"Gap references missing or unverified contradiction: {statement_id}"
                )
            contradictory.append(statement)
        paper_ids = {item.paper_id for item in supporting}
        declared = set(gap.supporting_papers)
        if declared and not declared <= paper_ids:
            raise InvalidGapEvidenceError(
                "supporting_papers contains papers without supporting statements"
            )
        gap.supporting_papers = sorted(paper_ids)
        independent_count = self._independent_count(literature, paper_ids, quality)
        content_verified_ids = {
            content.paper_id
            for content in literature.contents
            if content.content_verified and not content.synthetic_test_data
        }
        mean_confidence = sum(item.confidence for item in supporting) / len(supporting)
        independence_factor = min(1.0, independent_count / 2)
        contradiction_factor = 1 / (1 + len(contradictory))
        summary = GapEvidenceSummary(
            independent_paper_count=independent_count,
            supporting_statement_count=len(supporting),
            contradictory_statement_count=len(contradictory),
            content_verified_paper_count=len(paper_ids & content_verified_ids),
            confidence=mean_confidence * independence_factor * contradiction_factor,
        )
        gap.evidence_summary = summary
        return summary

    @staticmethod
    def _enqueue_central_verification(
        quality: LiteratureQualityState,
        statement: ExtractedStatement,
        classification: str,
    ) -> None:
        existing = next(
            (
                item
                for item in quality.verification_tasks
                if item.statement_id == statement.id
            ),
            None,
        )
        if existing is not None:
            return
        uncertainty = max(1 - statement.confidence, 0.4)
        quality.verification_tasks.append(
            VerificationTask(
                id=stable_id("VERIFY", statement.paper_id, statement.id),
                paper_id=statement.paper_id,
                statement_id=statement.id,
                reason=(
                    "Central GAP evidence requires human verification; "
                    f"classification={classification}."
                ),
                priority=min(1.0, uncertainty),
            )
        )
        quality.verification_tasks.sort(key=lambda item: item.priority, reverse=True)

    @staticmethod
    def _metadata(literature: LiteratureState, paper_id: str) -> PaperMetadata | None:
        return next(
            (item for item in literature.paper_metadata if item.paper_id == paper_id),
            None,
        )

    @staticmethod
    def _independent_count(
        literature: LiteratureState,
        paper_ids: set[str],
        quality: LiteratureQualityState | None = None,
    ) -> int:
        if quality is not None:
            families = {
                record.paper_id: record.work_family_id
                for record in quality.canonical_records
                if record.paper_id in paper_ids and record.work_family_id
            }
            if len(families) == len(paper_ids):
                return len(set(families.values()))
        parent = {paper_id: paper_id for paper_id in paper_ids}

        def find(item: str) -> str:
            while parent[item] != item:
                parent[item] = parent[parent[item]]
                item = parent[item]
            return item

        def union(left: str, right: str) -> None:
            root_left, root_right = find(left), find(right)
            if root_left != root_right:
                parent[root_right] = root_left

        for relation in literature.relations:
            if (
                relation.relation == "same_work_version"
                and relation.source_paper_id in parent
                and relation.target_paper_id in parent
            ):
                union(relation.source_paper_id, relation.target_paper_id)
        return len({find(item) for item in paper_ids})
