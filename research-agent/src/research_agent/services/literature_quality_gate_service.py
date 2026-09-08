from __future__ import annotations

from research_agent.schemas.literature_quality import (
    ExtractionCapabilityStatus,
    ExtractionEvaluationResult,
    LiteratureQualityGateConfig,
)
from research_agent.schemas.state import ResearchState


EVALUATION_TO_CAPABILITY = {
    "problem": "problem",
    "main_claims": "main_claim",
    "methods": "method",
    "assumptions": "assumptions",
    "results": "results",
    "limitations_claimed": "limitations",
    "failure_modes": "failure_modes",
}


class LiteratureQualityGateService:
    def __init__(self, config: LiteratureQualityGateConfig | None = None) -> None:
        self.config = config or LiteratureQualityGateConfig()

    def apply(
        self, state: ResearchState, evaluation: ExtractionEvaluationResult
    ) -> list[ExtractionCapabilityStatus]:
        statuses = []
        global_safe = (
            evaluation.unsupported_statement_rate is not None
            and evaluation.unsupported_statement_rate
            <= self.config.max_unsupported_statement_rate
            and evaluation.wrong_attribution_rate is not None
            and evaluation.wrong_attribution_rate
            <= self.config.max_wrong_attribution_rate
        )
        for metric_name, capability in EVALUATION_TO_CAPABILITY.items():
            metric = evaluation.semantic_metrics.get(metric_name)
            if metric is None or metric.gold_count == 0:
                status = ExtractionCapabilityStatus(
                    capability=capability,
                    precision=metric.precision if metric else None,
                    recall=metric.recall if metric else None,
                    status="disabled",
                    evaluation_id=evaluation.id,
                    reason="No human-labelled positive examples for this capability.",
                )
            else:
                threshold = (
                    self.config.min_limitation_precision
                    if capability == "limitations"
                    else self.config.min_result_precision
                    if capability == "results"
                    else self.config.min_other_precision
                )
                validated = (
                    self.config.enabled
                    and global_safe
                    and metric.precision is not None
                    and metric.precision >= threshold
                )
                status = ExtractionCapabilityStatus(
                    capability=capability,
                    precision=metric.precision,
                    recall=metric.recall,
                    status="validated" if validated else "experimental",
                    evaluation_id=evaluation.id,
                    reason=(
                        "Capability passed the configured human-labelled quality gate."
                        if validated
                        else "Capability has labels but did not pass every configured gate."
                    ),
                )
            statuses.append(status)
        state.literature_quality.capability_statuses = statuses
        return statuses

