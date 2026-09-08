from __future__ import annotations

import json

from research_agent.cli import main


def test_attach_repo_doctor_dry_run_and_skill_install(
    projects_root, tmp_path, capsys
) -> None:
    prefix = ["--projects-root", str(projects_root)]
    assert main([*prefix, "init", "live_cli", "--direction", "toy reasoning"]) == 0
    capsys.readouterr()
    repository = tmp_path / "repo"
    repository.mkdir()
    assert main([*prefix, "attach-repo", "live_cli", str(repository)]) == 0
    attached = json.loads(capsys.readouterr().out)
    assert attached["repository"]["path"] == str(repository.resolve())

    assert main([*prefix, "run", "live_cli", "--live", "--dry-run"]) == 0
    dry_run = json.loads(capsys.readouterr().out)
    assert dry_run["mode"] == "live_dry_run"
    assert dry_run["will_execute"] is False
    assert dry_run["available_tools"].get("shell") is None

    assert main([*prefix, "doctor", "live_cli"]) == 0
    doctor = json.loads(capsys.readouterr().out)
    assert doctor["state_valid"] is True
    assert doctor["skill_found"] is True
    assert doctor["skill_resources_found"] is True
    assert "discovered" in doctor["host_skill"]
    assert doctor["repository"]["path"] == str(repository.resolve())

    target = tmp_path / "installed-skills" / "research-agent"
    assert main(["install-skill", "--target", str(target)]) == 0
    installed = json.loads(capsys.readouterr().out)
    assert installed["installed"] is True
    assert (target / "SKILL.md").is_file()
    assert (target / "manifest.yaml").is_file()
