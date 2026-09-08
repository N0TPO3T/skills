from __future__ import annotations

import json
from pathlib import Path

from research_agent.schemas.document import DocumentSection, ParsedScientificDocument
from research_agent.schemas.literature import ExtractedStatement, PaperContent, PaperMetadata
from research_agent.schemas.literature_quality import (
    ExtractionEvaluationResult,
    GoldPaperAnnotation,
    GoldStatement,
    LiteratureQualityGateConfig,
    MetricSummary,
)
from research_agent.schemas.project import ProjectInfo
from research_agent.schemas.provenance import (
    ProvenanceRecord,
    SourceLocator,
    StatementEpistemicType,
)
from research_agent.schemas.state import ResearchState
from research_agent.services.extraction_evaluation_service import (
    ExtractionEvaluationService,
)
from research_agent.services.literature_quality_gate_service import (
    LiteratureQualityGateService,
)
from research_agent.services.literature_quality_report_service import (
    LiteratureQualityReportService,
)
from research_agent.storage.artifact_store import ArtifactStore


def evaluated_state(tmp_path: Path) -> tuple[ResearchState, ArtifactStore]:
    project = tmp_path / "project"
    project.mkdir()
    artifacts = ArtifactStore(project)
    content_path = artifacts.write_text(
        "artifacts/literature/papers/PAPER-1/content.txt", "Limitations text"
    )
    current = ResearchState(project=ProjectInfo(id="demo", name="Demo"))
    current.literature.paper_metadata.append(
        PaperMetadata(
            paper_id="PAPER-1",
            title="Reliable Extraction",
            authors=["A. Author"],
            year=2026,
            source_records=["https://example.test/paper"],
            metadata_verified=True,
            verification_confidence=0.95,
        )
    )
    current.literature.contents.append(
        PaperContent(
            paper_id="PAPER-1",
            content_type="pdf_text",
            artifact_path=content_path,
            sha256="a" * 64,
            parser_name="fixture",
            content_verified=True,
        )
    )
    locator = SourceLocator(section_id="SEC-LIMIT", section_title="Limitations")
    statements = [
        ExtractedStatement(
            id="STATEMENT-CORRECT",
            paper_id="PAPER-1",
            statement_type="limitation_claimed",
            statement="The study evaluates only one model.",
            provenance_ids=["PROV-CORRECT"],
            confidence=0.9,
            epistemic_type=StatementEpistemicType.AUTHOR_STATED,
        ),
        ExtractedStatement(
            id="STATEMENT-UNSUPPORTED",
            paper_id="PAPER-1",
            statement_type="limitation_claimed",
            statement="The authors report a deployment failure.",
            provenance_ids=["PROV-UNSUPPORTED"],
            confidence=0.7,
            epistemic_type=StatementEpistemicType.AUTHOR_STATED,
        ),
        ExtractedStatement(
            id="STATEMENT-WRONG-TYPE",
            paper_id="PAPER-1",
            statement_type="result",
            statement="Accuracy improves by five points.",
            provenance_ids=["PROV-WRONG-TYPE"],
            confidence=0.9,
            epistemic_type=StatementEpistemicType.AUTHOR_STATED,
        ),
    ]
    current.literature.statements.extend(statements)
    for statement in statements:
        current.literature.provenance_records.append(
            ProvenanceRecord(
                id=statement.provenance_ids[0],
                entity_type="extracted_statement",
                entity_id=statement.id,
                source_type="paper_full_text",
                source_id=(
                    "PAPER-WRONG"
                    if statement.id == "STATEMENT-UNSUPPORTED"
                    else statement.paper_id
                ),
                artifact_path=content_path,
                source_locator=locator,
                confidence=statement.confidence,
            )
        )
    current.literature_quality.parsed_documents.append(
        ParsedScientificDocument(
            paper_id="PAPER-1",
            parser="fixture",
            sections=[
                DocumentSection(
                    id="SEC-LIMIT",
                    title="Limitations",
                    normalized_role="limitations",
                    text="The study evaluates only one model.",
                    order=0,
                    source_locator=locator,
                )
            ],
            parse_confidence=1.0,
            source_sha256="b" * 64,
        )
    )
    return current, artifacts


def gold() -> GoldPaperAnnotation:
    locator = SourceLocator(section_id="SEC-LIMIT", section_title="Limitations")
    return GoldPaperAnnotation(
        paper_id="PAPER-1",
        limitations_claimed=[
            GoldStatement(
                statement="The study evaluates only one model.",
                acceptable_paraphrases=["Only one model is evaluated."],
                source_locator=locator,
            )
        ],
        results=[
            GoldStatement(
                statement="Accuracy improves by five points.",
                source_locator=locator,
            )
        ],
    )


def test_gold_loading_and_quality_metrics(tmp_path: Path) -> None:
    current, artifacts = evaluated_state(tmp_path)
    source = tmp_path / "gold.yaml"
    source.write_text(gold().model_dump_json(), encoding="utf-8")
    service = ExtractionEvaluationService(artifacts)
    artifact = service.import_annotation(current, source)
    assert service.load_annotations(current) == [gold()]
    assert artifact.endswith("gold/PAPER-1.json")

    result = service.evaluate(current)
    limitation = result.semantic_metrics["limitations_claimed"]
    assert limitation.precision == 0.5
    assert limitation.recall == 1.0
    assert limitation.f1 == 2 / 3
    assert result.unsupported_statement_rate == 1 / 3
    assert result.wrong_attribution_rate == 1 / 3
    assert result.wrong_epistemic_type_rate == 1 / 3
    assert result.locator_accuracy == 1.0
    assert result.paper_level_coverage == 1.0


def test_annotation_template_and_manifest_are_human_labelled_scaffolds(
    tmp_path: Path,
) -> None:
    current, artifacts = evaluated_state(tmp_path)
    service = ExtractionEvaluationService(artifacts)
    manifest_path = service.create_set(current, size=1)
    manifest = json.loads(artifacts.read_text(manifest_path))
    assert manifest["selected_paper_ids"] == ["PAPER-1"]
    assert "human" in manifest["note"].casefold()
    template_path = service.export_annotation(
        current, "PAPER-1", output_format="json"
    )
    template = json.loads(artifacts.read_text(template_path))
    assert template["paper_id"] == "PAPER-1"
    assert template["limitations_claimed"] == []


def test_capability_gate_is_validated_experimental_or_disabled() -> None:
    metrics = {
        "problem": MetricSummary(),
        "main_claims": MetricSummary(),
        "methods": MetricSummary(),
        "assumptions": MetricSummary(),
        "results": MetricSummary(
            precision=0.94, recall=1.0, f1=0.969, matched_count=94,
            predicted_count=100, gold_count=94
        ),
        "limitations_claimed": MetricSummary(
            precision=0.95, recall=0.8, f1=0.868, matched_count=19,
            predicted_count=20, gold_count=24
        ),
        "failure_modes": MetricSummary(),
    }
    evaluation = ExtractionEvaluationResult(
        id="EVAL-1",
        semantic_metrics=metrics,
        unsupported_statement_rate=0.02,
        wrong_attribution_rate=0.01,
    )
    current = ResearchState(project=ProjectInfo(id="demo", name="Demo"))
    statuses = LiteratureQualityGateService(
        LiteratureQualityGateConfig()
    ).apply(current, evaluation)
    by_capability = {item.capability: item.status for item in statuses}
    assert by_capability["limitations"] == "validated"
    assert by_capability["results"] == "experimental"
    assert by_capability["failure_modes"] == "disabled"


def test_quality_report_keeps_dimensions_separate(tmp_path: Path) -> None:
    current, artifacts = evaluated_state(tmp_path)
    report = LiteratureQualityReportService(artifacts).build(current)
    assert report.metadata.multi_source_rate == 0.0
    assert report.content.fulltext_rate == 1.0
    assert report.parsing.success_rate is None
    assert report.provenance.missing_provenance_rate == 0.0
    assert current.literature_quality.latest_quality_report_artifact

