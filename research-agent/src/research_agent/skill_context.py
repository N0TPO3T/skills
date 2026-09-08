from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from research_agent.core.transitions import ResearchPhase
from research_agent.schemas.state import ResearchState

ARCHIVED_SOP = "references/original_sop.md"


@dataclass(frozen=True)
class LoadedSkillContext:
    phase: str
    loaded_files: tuple[str, ...]
    content: str

    @property
    def character_count(self) -> int:
        return len(self.content)

    @property
    def approximate_tokens(self) -> int:
        return (self.character_count + 3) // 4

    def summary(self) -> dict[str, object]:
        return {
            "phase": self.phase,
            "loaded_skill_files": list(self.loaded_files),
            "character_count": self.character_count,
            "approximate_tokens": self.approximate_tokens,
            "original_sop_loaded": ARCHIVED_SOP in self.loaded_files,
        }


class SkillContextLoader:
    """Load the minimal Research Agent skill bundle for one runtime phase."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or self.resolve_skill_root()).resolve()
        self.manifest = self._read_manifest()

    @staticmethod
    def resolve_skill_root() -> Path:
        module_path = Path(__file__).resolve()
        candidates = (
            module_path.parents[2] / "skills" / "research-agent",
            module_path.parent / "research_skill",
        )
        for candidate in candidates:
            if (candidate / "SKILL.md").is_file() and (
                candidate / "manifest.yaml"
            ).is_file():
                return candidate
        raise FileNotFoundError(
            "Packaged Research Agent skill resources were not found"
        )

    def load_global(self) -> LoadedSkillContext:
        return self._load("global", self._string_list(self.manifest.get("always")))

    def load(
        self,
        phase: ResearchPhase | str,
        *,
        checkpoint_type: str | None = None,
    ) -> LoadedSkillContext:
        phase_name = phase.value if isinstance(phase, ResearchPhase) else str(phase)
        aliases = self._string_map(self.manifest.get("aliases"))
        phase_name = aliases.get(phase_name, phase_name)
        phases = self.manifest.get("phases")
        if not isinstance(phases, dict) or phase_name not in phases:
            raise KeyError(f"No Research Agent skill context for phase: {phase_name}")
        resources = [
            *self._string_list(self.manifest.get("always")),
            *self._string_list(phases[phase_name]),
        ]
        if checkpoint_type is not None:
            checkpoints = self._string_map(self.manifest.get("checkpoints"))
            checkpoint_prompt = checkpoints.get(checkpoint_type)
            if checkpoint_prompt is None:
                raise KeyError(f"Unknown Research Agent checkpoint: {checkpoint_type}")
            reference = self.manifest.get("checkpoint_reference")
            if not isinstance(reference, str):
                raise ValueError("Skill manifest checkpoint_reference must be a path")
            resources.extend((reference, checkpoint_prompt))
        return self._load(phase_name, resources)

    def load_for_state(self, state: ResearchState) -> LoadedSkillContext:
        checkpoint_type = (
            state.human_checkpoint.type
            if state.human_checkpoint and state.human_checkpoint.required
            else None
        )
        return self.load(state.phase, checkpoint_type=checkpoint_type)

    def load_focused_verification(self) -> LoadedSkillContext:
        resources = [
            *self._string_list(self.manifest.get("always")),
            *self._string_list(self.manifest.get("focused_verification")),
        ]
        return self._load("focused_verification", resources)

    def full_sop_character_count(self) -> int:
        return len(self._read_resource(ARCHIVED_SOP))

    def coverage_paths(self) -> dict[str, str]:
        coverage = self.manifest.get("sop_coverage")
        if not isinstance(coverage, dict):
            raise ValueError("Skill manifest has no sop_coverage mapping")
        flattened: dict[str, str] = {}
        for key, value in coverage.items():
            if isinstance(value, str):
                flattened[str(key)] = value
            elif isinstance(value, dict):
                for nested_key, nested_value in value.items():
                    if not isinstance(nested_value, str):
                        raise ValueError("SOP coverage values must be resource paths")
                    flattened[f"{key}.{nested_key}"] = nested_value
            else:
                raise ValueError("SOP coverage values must be paths or mappings")
        return flattened

    def _load(self, phase: str, resources: list[str]) -> LoadedSkillContext:
        unique = tuple(dict.fromkeys(resources))
        if ARCHIVED_SOP in unique:
            raise ValueError("Archived SOP cannot be loaded as runtime context")
        sections = [
            f"<!-- skill-resource: {path} -->\n{self._read_resource(path).strip()}"
            for path in unique
        ]
        return LoadedSkillContext(
            phase=phase,
            loaded_files=unique,
            content="\n\n---\n\n".join(sections),
        )

    def _read_manifest(self) -> dict[str, Any]:
        value = yaml.safe_load(self._read_resource("manifest.yaml"))
        if not isinstance(value, dict):
            raise ValueError("Skill manifest must be a mapping")
        return value

    def _read_resource(self, relative_path: str) -> str:
        if not relative_path or Path(relative_path).is_absolute():
            raise ValueError("Skill resource paths must be non-empty and relative")
        path = (self.root / relative_path).resolve()
        if path != self.root and self.root not in path.parents:
            raise ValueError("Skill resource path escapes the skill root")
        if not path.is_file():
            raise FileNotFoundError(path)
        return path.read_text(encoding="utf-8")

    @staticmethod
    def _string_list(value: object) -> list[str]:
        if not isinstance(value, list) or any(
            not isinstance(item, str) for item in value
        ):
            raise ValueError("Skill manifest phase resources must be a list of paths")
        return list(value)

    @staticmethod
    def _string_map(value: object) -> dict[str, str]:
        if not isinstance(value, dict) or any(
            not isinstance(key, str) or not isinstance(item, str)
            for key, item in value.items()
        ):
            raise ValueError("Skill manifest aliases/checkpoints must map strings")
        return dict(value)
