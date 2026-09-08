from __future__ import annotations

import json

from research_agent.cli import main
from research_agent.storage.state_store import StateStore


def test_literature_cli_mock_commands(projects_root, capsys) -> None:
    prefix = ["--projects-root", str(projects_root)]
    assert main([*prefix, "init", "lit_demo", "--mock"]) == 0
    capsys.readouterr()

    assert (
        main(
            [
                *prefix,
                "literature",
                "search",
                "lit_demo",
                "--provider",
                "mock",
            ]
        )
        == 0
    )
    search = json.loads(capsys.readouterr().out)
    assert search["coverage"]["metadata_verified_count"] == 0
    assert search["coverage"]["content_verified_count"] == 0

    assert main([*prefix, "literature", "status", "lit_demo"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["candidate_count"] > 0
    assert status["metadata_verified_count"] == 0

    assert main([*prefix, "literature", "coverage", "lit_demo"]) == 0
    coverage = json.loads(capsys.readouterr().out)
    assert coverage["sufficient_for_gap_synthesis"] is False

    state = StateStore(projects_root).load("lit_demo")
    paper_id = state.literature.paper_metadata[0].paper_id
    assert main([*prefix, "literature", "inspect", "lit_demo", paper_id]) == 0
    inspection = json.loads(capsys.readouterr().out)
    assert inspection["metadata"]["synthetic_test_data"] is True
    assert inspection["content"] is None

    assert main([*prefix, "inspect", "lit_demo", "literature"]) == 0
    literature = json.loads(capsys.readouterr().out)
    assert literature["candidates"]
