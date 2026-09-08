from __future__ import annotations

from research_agent.literature.extraction import LLMPaperExtractor
from research_agent.llm.client import MockLLMClient
from research_agent.schemas.literature import PaperContent, PaperMetadata


async def test_llm_extractor_uses_typed_structured_output() -> None:
    client = MockLLMClient(
        {
            "PaperExtractionDraft": {
                "problem": "Variable reasoning difficulty",
                "main_claim": "Adaptive allocation may improve efficiency",
                "method_summary": "Allocate compute from uncertainty",
                "limitations_claimed": ["Evaluated on one setting"],
                "extraction_confidence": 0.8,
            }
        }
    )
    extractor = LLMPaperExtractor(client=client, model="mock-extractor")
    result = await extractor.extract(
        metadata=PaperMetadata(paper_id="PAPER-1", title="Paper"),
        content=PaperContent(
            paper_id="PAPER-1", content_type="pdf_text", parser_name="fixture"
        ),
        text="Source-grounded fixture text.",
    )
    assert result.method_summary == "Allocate compute from uncertainty"
    assert client.calls[0]["schema"] == "PaperExtractionDraft"
