from __future__ import annotations

import pytest
from pydantic import ValidationError

from research_agent.schemas.literature import ExtractedStatement
from research_agent.schemas.literature_quality import (
    GoldPaperAnnotation,
    GoldStatement,
    ProviderCapabilities,
)
from research_agent.schemas.provenance import SourceLocator


def test_provider_capabilities_do_not_imply_unsupported_features() -> None:
    capabilities = ProviderCapabilities(metadata_lookup=True)
    assert capabilities.metadata_lookup is True
    assert capabilities.full_text is False
    assert capabilities.citation_graph is False


def test_gold_annotation_roundtrip() -> None:
    annotation = GoldPaperAnnotation(
        paper_id="PAPER-1",
        limitations_claimed=[
            GoldStatement(
                statement="The authors evaluate only one dataset.",
                source_locator=SourceLocator(
                    section_id="SEC-LIMIT",
                    section_title="Limitations",
                    paragraph_index=0,
                ),
            )
        ],
    )
    assert GoldPaperAnnotation.model_validate_json(annotation.model_dump_json()) == annotation


def test_agent_inference_cannot_be_relabelled_as_author_statement() -> None:
    with pytest.raises(ValidationError, match="agent-inferred"):
        ExtractedStatement(
            id="STATEMENT-1",
            paper_id="PAPER-1",
            statement_type="limitation_inferred",
            statement="This dependency may limit deployment.",
            provenance_ids=["PROV-1"],
            confidence=0.7,
            epistemic_type="author_stated",
        )
