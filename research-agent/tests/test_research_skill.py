from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import yaml

from research_agent.cli import main
from research_agent.core.transitions import ResearchPhase
from research_agent.prompts.loader import PromptLoader
from research_agent.schemas.decision import HumanCheckpoint
from research_agent.skill_context import ARCHIVED_SOP, SkillContextLoader
from research_agent.storage.project_store import ProjectStore
from research_agent.storage.state_store import StateStore

SKILL_ROOT = Path(__file__).parents[1] / "skills" / "research-agent"


def test_skill_entrypoint_is_present_and_small() -> None:
    skill = SKILL_ROOT / "SKILL.md"
    content = skill.read_text(encoding="utf-8")
    assert content.startswith("---\nname: research-agent\n")
    assert len(content) < 4_000
    assert "Do not load the complete SOP" in content


def test_skill_frontmatter_matches_agent_skills_spec() -> None:
    content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    _, raw_frontmatter, _ = content.split("---", 2)
    frontmatter = yaml.safe_load(raw_frontmatter)
    name = frontmatter["name"]
    description = frontmatter["description"]

    assert name == SKILL_ROOT.name == "research-agent"
    assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name)
    assert len(name) <= 64
    assert 1 <= len(description) <= 1024
    assert "Use when" in description
    assert frontmatter["license"] == "Apache-2.0"
    assert frontmatter["metadata"] == {"version": "0.2.0"}


def test_openai_interface_metadata_is_small_and_consistent() -> None:
    interface = yaml.safe_load(
        (SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
    )["interface"]
    assert interface["display_name"] == "Research Agent"
    assert 25 <= len(interface["short_description"]) <= 64
    assert "$research-agent" in interface["default_prompt"]


def test_every_runtime_phase_and_sop_entry_maps_to_existing_resources() -> None:
    loader = SkillContextLoader(SKILL_ROOT)
    phases = loader.manifest["phases"]
    assert set(phases) == {phase.value for phase in ResearchPhase}
    for phase in ResearchPhase:
        loaded = loader.load(phase)
        assert loaded.loaded_files[0] == "references/scientific_rules.md"
        assert all((SKILL_ROOT / path).is_file() for path in loaded.loaded_files)
    coverage = loader.coverage_paths()
    assert {
        "global_system",
        "bootstrap",
        "horizon_scan",
        "gap_mining",
        "gap_synthesis",
        "evidence_verify",
        "idea_formation",
        "idea_attack",
        "idea_defense",
        "meta_review",
        "resource_design",
        "baseline_reproduction",
        "experiment_loop",
        "diagnosis",
        "pivot",
        "evidence_expansion",
        "paper_readiness",
        "paper_package",
        "paper_writer",
        "paper_review",
        "research_report",
        "checkpoints.topic",
        "checkpoints.resources",
        "checkpoints.pivot",
    } == set(coverage)
    assert all((SKILL_ROOT / path).is_file() for path in coverage.values())


def test_focused_verification_loads_only_research_evidence_resources() -> None:
    loaded = SkillContextLoader(SKILL_ROOT).load_focused_verification()
    assert loaded.loaded_files == (
        "references/scientific_rules.md",
        "references/research_loop.md",
        "prompts/evidence_verify.md",
    )
    assert "prompts/gap_mining.md" not in loaded.loaded_files
    assert "references/experiment_loop.md" not in loaded.loaded_files


def test_progressive_phase_loading_excludes_unrelated_resources() -> None:
    loader = SkillContextLoader(SKILL_ROOT)
    gap = loader.load(ResearchPhase.GAP_MINING)
    assert gap.loaded_files == (
        "references/scientific_rules.md",
        "references/research_loop.md",
        "prompts/gap_mining.md",
    )
    assert "prompts/paper_writer.md" not in gap.loaded_files
    assert "references/experiment_loop.md" not in gap.loaded_files

    experiment = loader.load("core_experiment_loop")
    assert experiment.loaded_files == (
        "references/scientific_rules.md",
        "references/experiment_loop.md",
        "prompts/core_experiment.md",
    )
    assert "references/research_loop.md" not in experiment.loaded_files

    paper = loader.load("paper_writing")
    assert paper.loaded_files == (
        "references/scientific_rules.md",
        "references/paper_loop.md",
        "prompts/paper_package.md",
        "prompts/paper_writer.md",
    )
    assert "prompts/paper_review.md" not in paper.loaded_files
    assert (
        ARCHIVED_SOP
        not in gap.loaded_files + experiment.loaded_files + paper.loaded_files
    )


def test_checkpoint_prompt_loads_only_for_active_checkpoint() -> None:
    loader = SkillContextLoader(SKILL_ROOT)
    ordinary = loader.load(ResearchPhase.TOPIC_SELECTION)
    checkpoint = loader.load(
        ResearchPhase.TOPIC_SELECTION, checkpoint_type="topic_selection"
    )
    assert "references/checkpoints.md" not in ordinary.loaded_files
    assert "prompts/checkpoint_topic.md" not in ordinary.loaded_files
    assert checkpoint.loaded_files[-2:] == (
        "references/checkpoints.md",
        "prompts/checkpoint_topic.md",
    )
    assert "prompts/checkpoint_resources.md" not in checkpoint.loaded_files


def test_original_sop_is_archived_but_never_in_default_context() -> None:
    loader = SkillContextLoader(SKILL_ROOT)
    archive = SKILL_ROOT / ARCHIVED_SOP
    content = archive.read_text(encoding="utf-8")
    assert archive.is_file()
    assert "ARCHIVAL SOURCE OF TRUTH" in content
    assert loader.full_sop_character_count() == len(content)
    assert loader.full_sop_character_count() > 20_000
    for phase in ResearchPhase:
        assert ARCHIVED_SOP not in loader.load(phase).loaded_files


def test_phase_context_is_substantially_smaller_than_full_sop() -> None:
    loader = SkillContextLoader(SKILL_ROOT)
    full_size = loader.full_sop_character_count()
    for phase in ("gap_mining", "core_experiment", "paper_writing"):
        assert loader.load(phase).character_count < full_size / 3


def test_prompt_loader_composes_global_and_current_phase_skill_context() -> None:
    prompt = PromptLoader().compose(
        role="orchestrator",
        policies=["evidence"],
        phase="diagnosis",
    )
    assert "skill-resource: references/scientific_rules.md" in prompt
    assert "skill-resource: references/experiment_loop.md" in prompt
    assert "skill-resource: prompts/diagnosis.md" in prompt
    assert "prompts/paper_writer.md" not in prompt
    assert "original_sop.md" not in prompt


def test_skill_context_cli_reports_active_checkpoint(projects_root, capsys) -> None:
    state = ProjectStore(projects_root).initialize("skill_demo", direction="reasoning")
    state.phase = ResearchPhase.TOPIC_SELECTION
    state.human_checkpoint = HumanCheckpoint(
        type="topic_selection",
        prompt="Choose a GAP",
        options=["GAP-1"],
        resume_phase=ResearchPhase.TOPIC_SELECTION,
    )
    StateStore(projects_root).save(state)
    assert (
        main(
            [
                "--projects-root",
                str(projects_root),
                "skill-context",
                "skill_demo",
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["phase"] == "topic_selection"
    assert output["original_sop_loaded"] is False
    assert output["loaded_skill_files"][-1] == "prompts/checkpoint_topic.md"
    assert output["character_count"] < output["full_sop_character_count"]


def test_wheel_configuration_maps_single_skill_source_into_package() -> None:
    config = tomllib.loads(
        (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    )
    force_include = config["tool"]["hatch"]["build"]["targets"]["wheel"][
        "force-include"
    ]
    assert force_include == {
        "skills/research-agent": "research_agent/research_skill"
    }
