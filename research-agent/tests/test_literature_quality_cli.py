from __future__ import annotations

import json

from research_agent.cli import main
from research_agent.schemas.document import DocumentSection, ParsedScientificDocument
from research_agent.schemas.literature import PaperMetadata
from research_agent.storage.state_store import StateStore


def test_evaluation_and_quality_cli(projects_root, capsys, tmp_path) -> None:
    prefix = ["--projects-root", str(projects_root)]
    assert main([*prefix, "init", "quality_demo"]) == 0
    capsys.readouterr()
    store = StateStore(projects_root)
    state = store.load("quality_demo")
    state.literature.paper_metadata.append(
        PaperMetadata(
            paper_id="PAPER-1",
            title="Paper",
            authors=["A. Author"],
            source_records=["https://example.test"],
            metadata_verified=True,
            verification_confidence=0.9,
        )
    )
    state.literature_quality.parsed_documents.append(
        ParsedScientificDocument(
            paper_id="PAPER-1",
            parser="fixture",
            sections=[
                DocumentSection(
                    id="SEC-1", normalized_role="method", text="Method.", order=0
                )
            ],
            parse_confidence=1.0,
            source_sha256="a" * 64,
        )
    )
    store.save(state)

    assert main([*prefix, "eval", "literature", "create-set", "quality_demo", "--size", "1"]) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["artifact"].endswith("manifest.json")

    assert main([*prefix, "eval", "literature", "export-annotation", "quality_demo", "PAPER-1", "--format", "json"]) == 0
    exported = json.loads(capsys.readouterr().out)
    template = projects_root / "quality_demo" / exported["artifact"]
    assert template.is_file()

    assert main([*prefix, "eval", "literature", "import-annotation", "quality_demo", str(template)]) == 0
    capsys.readouterr()
    assert main([*prefix, "eval", "literature", "run", "quality_demo"]) == 0
    run = json.loads(capsys.readouterr().out)
    assert run["evaluation"]["evaluated_paper_count"] == 1
    assert {item["status"] for item in run["capabilities"]} == {"disabled"}

    assert main([*prefix, "eval", "literature", "report", "quality_demo"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["available"] is True

    assert main([*prefix, "literature", "quality", "quality_demo"]) == 0
    quality = json.loads(capsys.readouterr().out)
    assert quality["project_id"] == "quality_demo"
    assert "metadata" in quality and "extraction" in quality
