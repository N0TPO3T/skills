from __future__ import annotations

from research_agent.core.ids import stable_id
from research_agent.schemas.literature import ExtractedStatement
from research_agent.schemas.literature_quality import VerificationTask
from research_agent.schemas.provenance import StatementEpistemicType
from research_agent.schemas.state import ResearchState


class VerificationQueueService:
    def enqueue_if_needed(
        self,
        state: ResearchState,
        statement: ExtractedStatement,
        *,
        central_gap_statement_ids: set[str] | None = None,
        explicit_limitation_section: bool = True,
    ) -> VerificationTask | None:
        central = statement.id in (central_gap_statement_ids or set())
        claimed_without_section = (
            statement.statement_type == "limitation_claimed"
            and not explicit_limitation_section
        )
        ambiguous = statement.confidence < 0.8 or claimed_without_section
        high_value = central or statement.statement_type == "limitation_claimed"
        if not ambiguous or not high_value:
            return None
        uncertainty = max(1 - statement.confidence, 0.4 if claimed_without_section else 0)
        impact = 1.0 if central else 0.8
        reason_parts = []
        if statement.confidence < 0.8:
            reason_parts.append("low extraction confidence")
        if claimed_without_section:
            reason_parts.append("claimed limitation lacks an explicit limitations section")
        if statement.epistemic_type == StatementEpistemicType.AGENT_INFERRED:
            reason_parts.append("agent inference proposed as decision-relevant evidence")
        task = VerificationTask(
            id=stable_id("VERIFY", statement.paper_id, statement.id),
            paper_id=statement.paper_id,
            statement_id=statement.id,
            reason="; ".join(reason_parts),
            priority=min(1.0, impact * uncertainty),
        )
        existing = next(
            (
                item
                for item in state.literature_quality.verification_tasks
                if item.id == task.id
            ),
            None,
        )
        if existing is not None:
            return existing
        state.literature_quality.verification_tasks.append(task)
        state.literature_quality.verification_tasks.sort(
            key=lambda item: item.priority, reverse=True
        )
        return task

