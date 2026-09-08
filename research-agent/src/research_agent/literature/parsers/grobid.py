from __future__ import annotations

import asyncio
from hashlib import sha256
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4
from xml.etree import ElementTree

from research_agent.core.ids import stable_id
from research_agent.literature.parsers.base import DocumentParseError
from research_agent.literature.parsers.plain_text import normalize_section_role
from research_agent.schemas.document import (
    DocumentSection,
    ParsedReference,
    ParsedScientificDocument,
    ParsedTable,
)
from research_agent.schemas.provenance import SourceLocator


TEI = "{http://www.tei-c.org/ns/1.0}"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"


class GrobidParserAdapter:
    name = "grobid"

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:8070",
        timeout_seconds: float = 120,
        version: str | None = None,
    ) -> None:
        self.endpoint = base_url.rstrip("/") + "/api/processFulltextDocument"
        self.timeout_seconds = timeout_seconds
        self.version = version

    async def parse(self, source: Path) -> ParsedScientificDocument:
        payload = source.read_bytes()
        if not payload.startswith(b"%PDF-"):
            raise DocumentParseError("GROBID input is not a PDF")
        try:
            tei = await asyncio.wait_for(
                asyncio.to_thread(self._post_pdf, source),
                timeout=self.timeout_seconds + 1,
            )
        except TimeoutError as exc:
            raise DocumentParseError("GROBID request timed out") from exc
        return self.parse_tei(
            paper_id=source.parent.name,
            tei=tei,
            source_sha256=sha256(payload).hexdigest(),
            source_artifact=str(source),
        )

    def parse_tei(
        self,
        *,
        paper_id: str,
        tei: str,
        source_sha256: str,
        source_artifact: str | None = None,
    ) -> ParsedScientificDocument:
        try:
            root = ElementTree.fromstring(tei)
        except ElementTree.ParseError as exc:
            raise DocumentParseError("GROBID returned invalid TEI XML") from exc
        title = _node_text(root.find(f".//{TEI}titleStmt/{TEI}title")) or None
        abstract_node = root.find(f".//{TEI}profileDesc/{TEI}abstract")
        abstract = _node_text(abstract_node) or None
        sections: list[DocumentSection] = []
        for order, div in enumerate(root.findall(f".//{TEI}body/{TEI}div")):
            head = _node_text(div.find(f"{TEI}head")) or None
            text = "\n".join(
                value for value in (_node_text(node) for node in div.findall(f"{TEI}p")) if value
            )
            if not text:
                continue
            section_id = div.get(XML_ID) or stable_id("SECTION", paper_id, order, head or "")
            sections.append(
                DocumentSection(
                    id=section_id,
                    title=head,
                    normalized_role=normalize_section_role(head or ""),
                    text=text,
                    order=order,
                    source_locator=SourceLocator(
                        section_id=section_id, section_title=head
                    ),
                )
            )
        references = []
        for item in root.findall(f".//{TEI}listBibl/{TEI}biblStruct"):
            raw = _node_text(item)
            title_node = item.find(f".//{TEI}analytic/{TEI}title")
            doi_node = next(
                (
                    node
                    for node in item.findall(f".//{TEI}idno")
                    if (node.get("type") or "").casefold() == "doi"
                ),
                None,
            )
            if raw:
                references.append(
                    ParsedReference(
                        raw_text=raw,
                        title=_node_text(title_node) or None,
                        doi=_node_text(doi_node) or None,
                    )
                )
        tables = []
        for index, figure in enumerate(root.findall(f".//{TEI}figure")):
            if (figure.get("type") or "").casefold() != "table":
                continue
            tables.append(
                ParsedTable(
                    id=figure.get(XML_ID) or stable_id("TABLE", paper_id, index),
                    caption=_node_text(figure.find(f"{TEI}head")) or None,
                    text=_node_text(figure),
                )
            )
        warnings = [] if sections else ["GROBID returned no body sections."]
        return ParsedScientificDocument(
            paper_id=paper_id,
            parser=self.name,
            parser_version=self.version,
            title=title,
            abstract=abstract,
            sections=sections,
            references=references,
            tables=tables,
            parse_warnings=warnings,
            parse_confidence=0.9 if sections else 0.4,
            source_sha256=source_sha256,
            source_artifact=source_artifact,
            raw_tei=tei,
        )

    def _post_pdf(self, source: Path) -> str:
        boundary = f"----ResearchAgent{uuid4().hex}"
        payload = source.read_bytes()
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="input"; filename="source.pdf"\r\n'
            "Content-Type: application/pdf\r\n\r\n"
        ).encode("utf-8") + payload + f"\r\n--{boundary}--\r\n".encode("utf-8")
        request = Request(
            self.endpoint,
            data=body,
            method="POST",
            headers={
                "Accept": "application/xml",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return response.read().decode("utf-8")
        except (HTTPError, URLError, TimeoutError) as exc:
            raise DocumentParseError(f"GROBID request failed: {exc}") from exc


def _node_text(node: ElementTree.Element | None) -> str:
    if node is None:
        return ""
    return " ".join("".join(node.itertext()).split())

