from __future__ import annotations

import asyncio
import re
import shutil
from hashlib import sha256
from pathlib import Path

from research_agent.core.ids import stable_id
from research_agent.literature.parsers.base import DocumentParseError
from research_agent.schemas.document import (
    DocumentSection,
    ParsedReference,
    ParsedScientificDocument,
)
from research_agent.schemas.provenance import SourceLocator


SECTION_ROLES = {
    "abstract": "abstract",
    "introduction": "introduction",
    "related work": "related_work",
    "background": "related_work",
    "method": "method",
    "methods": "method",
    "methodology": "method",
    "experiments": "experiments",
    "experimental setup": "experiments",
    "results": "results",
    "analysis": "analysis",
    "discussion": "analysis",
    "limitations": "limitations",
    "limitation": "limitations",
    "conclusion": "conclusion",
    "conclusions": "conclusion",
    "appendix": "appendix",
}


class PlainTextFallbackParser:
    name = "plain-text-fallback"
    version = "1"

    async def parse(self, source: Path) -> ParsedScientificDocument:
        payload = source.read_bytes()
        digest = sha256(payload).hexdigest()
        if source.suffix.casefold() == ".pdf":
            if not payload.startswith(b"%PDF-") or b"%%EOF" not in payload[-4096:]:
                raise DocumentParseError("Invalid or corrupted PDF")
            executable = shutil.which("pdftotext")
            if executable is None:
                raise DocumentParseError("pdftotext is not available")
            process = await asyncio.create_subprocess_exec(
                executable,
                "-layout",
                str(source),
                "-",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                raise DocumentParseError(
                    "pdftotext failed: " + stderr.decode("utf-8", errors="replace")[:500]
                )
            text = stdout.decode("utf-8", errors="replace")
            warnings = ["Page and precise character locators are unavailable."]
        else:
            text = payload.decode("utf-8", errors="strict")
            warnings = ["Parsed from plain text rather than PDF layout."]
        return self.parse_text(
            paper_id=source.parent.name,
            text=text,
            source_sha256=digest,
            source_artifact=str(source),
            warnings=warnings,
        )

    def parse_text(
        self,
        *,
        paper_id: str,
        text: str,
        source_sha256: str,
        source_artifact: str | None = None,
        warnings: list[str] | None = None,
    ) -> ParsedScientificDocument:
        lines = [line.rstrip() for line in text.splitlines()]
        nonempty = [line.strip() for line in lines if line.strip()]
        if not nonempty:
            raise DocumentParseError("Document contains no extractable text")
        title = nonempty[0]
        blocks: list[tuple[str | None, str, list[str]]] = []
        current_title: str | None = None
        current_role = "unknown"
        current_lines: list[str] = []
        for line in lines[1:]:
            stripped = line.strip()
            heading_role = normalize_section_role(stripped)
            if heading_role != "unknown" and len(stripped) <= 80:
                if current_lines:
                    blocks.append((current_title, current_role, current_lines))
                current_title = stripped
                current_role = heading_role
                current_lines = []
            elif stripped:
                current_lines.append(stripped)
        if current_lines:
            blocks.append((current_title, current_role, current_lines))
        if not blocks:
            blocks = [(None, "unknown", nonempty[1:] or nonempty)]
        sections: list[DocumentSection] = []
        references: list[ParsedReference] = []
        for order, (section_title, role, section_lines) in enumerate(blocks):
            section_id = stable_id("SECTION", paper_id, order, section_title or role)
            locator = SourceLocator(
                section_id=section_id,
                section_title=section_title,
            )
            section_text = "\n".join(section_lines)
            sections.append(
                DocumentSection(
                    id=section_id,
                    title=section_title,
                    normalized_role=role,
                    text=section_text,
                    order=order,
                    source_locator=locator,
                )
            )
            if section_title and section_title.casefold().startswith("reference"):
                references.extend(
                    ParsedReference(raw_text=line, source_locator=locator)
                    for line in section_lines
                    if line
                )
        abstract = next(
            (section.text for section in sections if section.normalized_role == "abstract"),
            None,
        )
        return ParsedScientificDocument(
            paper_id=paper_id,
            parser=self.name,
            parser_version=self.version,
            title=title,
            abstract=abstract,
            sections=sections,
            references=references,
            parse_warnings=warnings or [],
            parse_confidence=0.65 if sections else 0.3,
            source_sha256=source_sha256,
            source_artifact=source_artifact,
        )


def normalize_section_role(title: str) -> str:
    normalized = re.sub(r"^\s*(?:\d+(?:\.\d+)*)?[.)]?\s*", "", title).casefold()
    normalized = re.sub(r"[^a-z ]", "", normalized).strip()
    for name, role in SECTION_ROLES.items():
        if normalized == name:
            return role
    return "unknown"
