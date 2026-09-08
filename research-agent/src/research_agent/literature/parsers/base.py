from __future__ import annotations

from pathlib import Path
from typing import Protocol

from research_agent.schemas.document import ParsedScientificDocument


class DocumentParseError(RuntimeError):
    pass


class ScientificDocumentParser(Protocol):
    name: str

    async def parse(self, source: Path) -> ParsedScientificDocument: ...

