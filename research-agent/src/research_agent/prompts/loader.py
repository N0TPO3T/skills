from __future__ import annotations

from pathlib import Path
from hashlib import sha256

from research_agent.schemas.provenance import PromptMetadata
from research_agent.skill_context import SkillContextLoader


ROLE_PATHS: dict[str, str] = {
    "orchestrator": "orchestrator.md",
    "bootstrap": "research/bootstrap.md",
    "horizon_scan": "research/horizon_scan.md",
    "literature_extract": "research/literature_extract.md",
    "gap_miner": "research/gap_miner.md",
    "gap_synthesizer": "research/gap_synthesizer.md",
    "idea_designer": "research/idea_designer.md",
    "idea_attack": "review/idea_attack.md",
    "idea_defense": "review/idea_defense.md",
    "meta_review": "review/meta_review.md",
    "resource_planner": "experiment/resource_planner.md",
    "baseline_reproduction": "experiment/baseline_reproduction.md",
    "experiment_designer": "experiment/experiment_designer.md",
    "result_analyzer": "experiment/result_analyzer.md",
    "failure_diagnosis": "experiment/failure_diagnosis.md",
    "pivot": "experiment/pivot.md",
    "evidence_expansion": "experiment/evidence_expansion.md",
    "readiness_audit": "paper/readiness_audit.md",
    "package_builder": "paper/package_builder.md",
    "writer": "paper/writer.md",
    "paper_reviewer": "paper/reviewer.md",
}


class PromptLoader:
    def __init__(
        self,
        root: Path | None = None,
        *,
        skill_contexts: SkillContextLoader | None = None,
    ) -> None:
        self.root = root or Path(__file__).parent
        self.skill_contexts = skill_contexts or SkillContextLoader()

    def compose(
        self,
        *,
        role: str,
        policies: list[str],
        phase: str | None = None,
        checkpoint_type: str | None = None,
    ) -> str:
        if role not in ROLE_PATHS:
            raise KeyError(f"Unknown prompt profile: {role}")
        skill_context = (
            self.skill_contexts.load(
                phase, checkpoint_type=checkpoint_type
            )
            if phase is not None
            else self.skill_contexts.load_global()
        )
        sections = [skill_context.content]
        sections.extend(self._read(f"../policies/{policy}.md") for policy in policies)
        sections.append(self._read(ROLE_PATHS[role]))
        return "\n\n---\n\n".join(section.strip() for section in sections)

    def metadata(
        self,
        *,
        role: str,
        policies: list[str],
        version: str = "1",
        phase: str | None = None,
        checkpoint_type: str | None = None,
    ) -> PromptMetadata:
        prompt = self.compose(
            role=role,
            policies=policies,
            phase=phase,
            checkpoint_type=checkpoint_type,
        )
        return PromptMetadata(
            profile=role,
            version=version,
            sha256=sha256(prompt.encode("utf-8")).hexdigest(),
        )

    def _read(self, relative_path: str) -> str:
        path = (self.root / relative_path).resolve()
        allowed_roots = {self.root.resolve(), (self.root.parent / "policies").resolve()}
        if not any(path == root or root in path.parents for root in allowed_roots):
            raise ValueError("Prompt path escapes configured prompt roots")
        if not path.is_file():
            raise FileNotFoundError(path)
        return path.read_text(encoding="utf-8")
