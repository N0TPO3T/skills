from __future__ import annotations

import json

from research_agent.cli import main


def test_cli_mock_lifecycle(projects_root, capsys) -> None:
    prefix = ["--projects-root", str(projects_root)]
    assert main([*prefix, "init", "demo", "--mock"]) == 0
    capsys.readouterr()

    assert main([*prefix, "run", "demo", "--mock"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["stopped_reason"] == "human_checkpoint"
    gap_id = first["checkpoint"]["options"][0]

    assert main([*prefix, "resume", "demo", gap_id, "--mock"]) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["checkpoint"]["type"] == "resource_input"

    assert main([*prefix, "resume", "demo", "default", "--mock"]) == 0
    final = json.loads(capsys.readouterr().out)
    assert final["stopped_reason"] == "experiment_plan_ready"
    assert final["synthetic_test_data"] is True

    assert main([*prefix, "inspect", "demo", "experiments"]) == 0
    experiments = json.loads(capsys.readouterr().out)
    assert experiments["experiments"][0]["id"] == final["experiment_id"]

