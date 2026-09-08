from __future__ import annotations

import re
import json
from typing import Protocol

from research_agent.llm.base import LLMClient, Message
from research_agent.prompts.loader import PromptLoader
from research_agent.schemas.literature import (
    PaperContent,
    PaperExtractionDraft,
    PaperMetadata,
)


class PaperExtractor(Protocol):
    name: str
    model: str

    async def extract(
        self, *, metadata: PaperMetadata, content: PaperContent, text: str
    ) -> PaperExtractionDraft: ...


class RuleBasedPaperExtractor:
    """Conservative fallback extractor; it makes no detailed unsupported inferences."""

    name = "rule-based-paper-extractor"
    model = "deterministic-rules-v1"

    async def extract(
        self, *, metadata: PaperMetadata, content: PaperContent, text: str
    ) -> PaperExtractionDraft:
        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
            if sentence.strip()
        ]
        first = sentences[0] if sentences else None
        return PaperExtractionDraft(
            problem=first,
            main_claim=metadata.abstract if content.content_type == "abstract_only" else first,
            extraction_confidence=0.55 if first else 0.0,
        )


class LLMPaperExtractor:
    """Structured extractor for an explicitly configured LLM client."""

    name = "llm-paper-extractor"

    def __init__(
        self,
        *,
        client: LLMClient,
        model: str,
        prompts: PromptLoader | None = None,
    ) -> None:
        self.client = client
        self.model = model
        self.prompts = prompts or PromptLoader()

    async def extract(
        self, *, metadata: PaperMetadata, content: PaperContent, text: str
    ) -> PaperExtractionDraft:
        messages = [
            Message(
                role="system",
                content=self.prompts.compose(
                    role="literature_extract", policies=["evidence", "citation"]
                ),
            ),
            Message(
                role="user",
                content=json.dumps(
                    {
                        "metadata": metadata.model_dump(mode="json"),
                        "content_type": content.content_type,
                        "content": text,
                    },
                    ensure_ascii=False,
                ),
            ),
        ]
        return await self.client.generate_structured(
            messages, PaperExtractionDraft, model=self.model
        )
