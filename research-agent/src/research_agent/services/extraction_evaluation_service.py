from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from research_agent.core.ids import stable_id
from research_agent.schemas.literature import ExtractedStatement
from research_agent.schemas.literature_quality import (
    ExtractionEvaluationResult,
    GoldPaperAnnotation,
    GoldStatement,
    MetricSummary,
)
from research_agent.schemas.provenance import SourceLocator, StatementEpistemicType
from research_agent.schemas.state import ResearchState
from research_agent.storage.artifact_store import ArtifactStore


GOLD_FIELDS = (
    "problem",
    "main_claims",
    "methods",
    "assumptions",
    "results",
    "limitations_claimed",
    "failure_modes",
)

STATEMENT_TO_CAPABILITY = {
    "problem": "problem",
    "claim": "main_claims",
    "method": "methods",
    "assumption": "assumptions",
    "result": "results",
    "limitation_claimed": "limitations_claimed",
    "limitation_inferred": "limitations_inferred",
    "failure_mode": "failure_modes",
}


class ExtractionEvaluationService:
    def __init__(self, artifacts: ArtifactStore) -> None:
        self.artifacts = artifacts

    def create_set(self, state: ResearchState, *, size: int = 30) -> str:
        if size < 1 or size > 50:
            raise ValueError("Evaluation set size must be between 1 and 50")
        parsed_ids = {
            document.paper_id
            for document in state.literature_quality.parsed_documents
        }
        selected = [
            paper.paper_id
            for paper in state.literature.paper_metadata
            if paper.paper_id in parsed_ids
            and paper.metadata_verified
            and not paper.synthetic_test_data
        ][:size]
        return self.artifacts.write_json(
            "artifacts/literature/evaluation/manifest.json",
            {
                "target_size": size,
                "selected_paper_ids": selected,
                "selected_count": len(selected),
                "status": "ready" if len(selected) >= size else "incomplete",
                "note": "Gold labels must be supplied by a human; fixtures do not count.",
            },
        )

    def export_annotation(
        self, state: ResearchState, paper_id: str, *, output_format: str = "yaml"
    ) -> str:
        if not any(
            paper.paper_id == paper_id
            for paper in state.literature.paper_metadata
        ):
            raise KeyError(f"Unknown paper: {paper_id}")
        annotation = GoldPaperAnnotation(paper_id=paper_id)
        if output_format == "json":
            return self.artifacts.write_json(
                f"artifacts/literature/evaluation/templates/{paper_id}.json",
                annotation.model_dump(mode="json"),
            )
        if output_format != "yaml":
            raise ValueError("Annotation format must be json or yaml")
        return self.artifacts.write_text(
            f"artifacts/literature/evaluation/templates/{paper_id}.yaml",
            yaml.safe_dump(
                annotation.model_dump(mode="json"),
                sort_keys=False,
                allow_unicode=True,
            ),
        )

    def import_annotation(self, state: ResearchState, source: Path) -> str:
        if not source.is_file():
            raise FileNotFoundError(source)
        text = source.read_text(encoding="utf-8")
        value = (
            json.loads(text)
            if source.suffix.casefold() == ".json"
            else yaml.safe_load(text)
        )
        annotation = GoldPaperAnnotation.model_validate(value)
        if not any(
            paper.paper_id == annotation.paper_id
            for paper in state.literature.paper_metadata
        ):
            raise ValueError(
                f"Gold annotation references unknown paper: {annotation.paper_id}"
            )
        path = self.artifacts.write_json(
            f"artifacts/literature/evaluation/gold/{annotation.paper_id}.json",
            annotation.model_dump(mode="json"),
        )
        if path not in state.literature_quality.gold_annotation_artifacts:
            state.literature_quality.gold_annotation_artifacts.append(path)
        return path

    def load_annotations(self, state: ResearchState) -> list[GoldPaperAnnotation]:
        return [
            GoldPaperAnnotation.model_validate_json(self.artifacts.read_text(path))
            for path in state.literature_quality.gold_annotation_artifacts
        ]

    def evaluate(
        self,
        state: ResearchState,
        annotations: list[GoldPaperAnnotation] | None = None,
    ) -> ExtractionEvaluationResult:
        gold = annotations if annotations is not None else self.load_annotations(state)
        gold_by_capability = {
            capability: [
                (annotation.paper_id, statement)
                for annotation in gold
                for statement in getattr(annotation, capability)
            ]
            for capability in GOLD_FIELDS
        }
        evaluated_ids = {annotation.paper_id for annotation in gold}
        predictions = [
            statement
            for statement in state.literature.statements
            if statement.paper_id in evaluated_ids
        ]
        predictions_by_capability = {
            capability: [
                statement
                for statement in predictions
                if STATEMENT_TO_CAPABILITY[statement.statement_type] == capability
            ]
            for capability in {*GOLD_FIELDS, "limitations_inferred"}
        }
        exact_metrics = {}
        semantic_metrics = {}
        semantic_pairs: dict[
            str, list[tuple[ExtractedStatement, GoldStatement]]
        ] = {}
        for capability in GOLD_FIELDS:
            predicted = predictions_by_capability[capability]
            expected = gold_by_capability[capability]
            exact_pairs = self._match(predicted, expected, self._exact_match)
            lexical_pairs = self._match(predicted, expected, self._lexical_match)
            exact_metrics[capability] = self._metrics(
                len(exact_pairs), len(predicted), len(expected)
            )
            semantic_metrics[capability] = self._metrics(
                len(lexical_pairs), len(predicted), len(expected)
            )
            semantic_pairs[capability] = lexical_pairs
        semantic_matched = sum(
            metric.matched_count for metric in semantic_metrics.values()
        )
        scorable_predictions = [
            statement
            for statement in predictions
            if statement.epistemic_type != StatementEpistemicType.AGENT_INFERRED
        ]
        unsupported_rate = (
            (len(scorable_predictions) - semantic_matched)
            / len(scorable_predictions)
            if scorable_predictions
            else None
        )
        provenance = {item.id: item for item in state.literature.provenance_records}
        wrong_attribution = sum(
            not statement.provenance_ids
            or any(
                provenance.get(provenance_id) is None
                or provenance[provenance_id].entity_id != statement.id
                or provenance[provenance_id].source_id != statement.paper_id
                for provenance_id in statement.provenance_ids
            )
            for statement in predictions
        )
        wrong_epistemic = sum(
            not self._epistemic_is_consistent(statement) for statement in predictions
        )
        locator_checks = []
        for pairs in semantic_pairs.values():
            for predicted, expected in pairs:
                expected_fields = expected.source_locator.model_dump(exclude_none=True)
                if not expected_fields:
                    continue
                records = [
                    provenance.get(item) for item in predicted.provenance_ids
                ]
                locator_checks.append(
                    any(
                        record is not None
                        and isinstance(record.source_locator, SourceLocator)
                        and all(
                            getattr(record.source_locator, key) == value
                            for key, value in expected_fields.items()
                        )
                        for record in records
                    )
                )
        covered_papers = {
            statement.paper_id for statement in predictions
        }
        evaluation_id = stable_id(
            "EVAL",
            *(annotation.model_dump_json() for annotation in gold),
            *(statement.id for statement in predictions),
        )
        result = ExtractionEvaluationResult(
            id=evaluation_id,
            exact_metrics=exact_metrics,
            semantic_metrics=semantic_metrics,
            unsupported_statement_rate=unsupported_rate,
            wrong_attribution_rate=(
                wrong_attribution / len(predictions) if predictions else None
            ),
            wrong_epistemic_type_rate=(
                wrong_epistemic / len(predictions) if predictions else None
            ),
            locator_accuracy=(
                sum(locator_checks) / len(locator_checks) if locator_checks else None
            ),
            paper_level_coverage=(
                len(covered_papers) / len(gold) if gold else None
            ),
            evaluated_paper_count=len(gold),
        )
        state.literature_quality.extraction_evaluations.append(result)
        self.artifacts.write_json(
            f"artifacts/literature/evaluation/predictions/{evaluation_id}.json",
            [item.model_dump(mode="json") for item in predictions],
        )
        self.artifacts.write_json(
            f"artifacts/literature/evaluation/reports/{evaluation_id}.json",
            result.model_dump(mode="json"),
        )
        return result

    @staticmethod
    def _match(
        predicted: list[ExtractedStatement],
        expected: list[tuple[str, GoldStatement]],
        matcher,
    ) -> list[tuple[ExtractedStatement, GoldStatement]]:
        matches = []
        used: set[int] = set()
        for prediction in predicted:
            for index, (paper_id, gold) in enumerate(expected):
                if index in used or paper_id != prediction.paper_id:
                    continue
                if matcher(prediction.statement, gold):
                    used.add(index)
                    matches.append((prediction, gold))
                    break
        return matches

    @staticmethod
    def _exact_match(prediction: str, gold: GoldStatement) -> bool:
        expected = [gold.statement, *gold.acceptable_paraphrases]
        return _normalize(prediction) in {_normalize(item) for item in expected}

    @staticmethod
    def _lexical_match(prediction: str, gold: GoldStatement) -> bool:
        predicted_tokens = set(_normalize(prediction).split())
        for expected in (gold.statement, *gold.acceptable_paraphrases):
            expected_tokens = set(_normalize(expected).split())
            union = predicted_tokens | expected_tokens
            if union and len(predicted_tokens & expected_tokens) / len(union) >= 0.6:
                return True
        return False

    @staticmethod
    def _metrics(matched: int, predicted: int, gold: int) -> MetricSummary:
        precision = matched / predicted if predicted else None
        recall = matched / gold if gold else None
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision is not None
            and recall is not None
            and precision + recall > 0
            else None
        )
        return MetricSummary(
            precision=precision,
            recall=recall,
            f1=f1,
            matched_count=matched,
            predicted_count=predicted,
            gold_count=gold,
        )

    @staticmethod
    def _epistemic_is_consistent(statement: ExtractedStatement) -> bool:
        if statement.statement_type == "limitation_inferred":
            return statement.epistemic_type == StatementEpistemicType.AGENT_INFERRED
        if statement.statement_type == "result":
            return statement.epistemic_type == StatementEpistemicType.DIRECT_RESULT
        if statement.statement_type in {
            "problem",
            "claim",
            "method",
            "assumption",
            "limitation_claimed",
            "failure_mode",
        }:
            return statement.epistemic_type == StatementEpistemicType.AUTHOR_STATED
        return True


def _normalize(value: str) -> str:
    return " ".join(re.findall(r"\w+", value.casefold()))
