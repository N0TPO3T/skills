from __future__ import annotations

from pathlib import Path

import yaml

from research_agent.schemas.project import ProjectInfo
from research_agent.schemas.state import ResearchState
from research_agent.storage.state_store import StateStore


ARTIFACT_DIRECTORIES = (
    "literature",
    "gaps",
    "ideas",
    "experiments",
    "reviews",
    "reports",
    "paper",
)


class ProjectStore:
    def __init__(self, projects_root: Path) -> None:
        self.projects_root = projects_root.resolve()
        self.state_store = StateStore(self.projects_root)

    def initialize(
        self, project_id: str, *, direction: str = "", synthetic: bool = False
    ) -> ResearchState:
        if not project_id or any(part in project_id for part in ("/", "\\", "..")):
            raise ValueError("project_id must be a simple directory name")
        project_dir = self.projects_root / project_id
        if project_dir.exists():
            raise FileExistsError(f"Project already exists: {project_id}")
        for name in ARTIFACT_DIRECTORIES:
            (project_dir / "artifacts" / name).mkdir(parents=True, exist_ok=True)
        config = {
            "project": {
                "id": project_id,
                "name": project_id,
                "research_direction": direction,
            }
        }
        (project_dir / "project.yaml").write_text(
            yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
        )
        state = ResearchState(
            project=ProjectInfo(
                id=project_id,
                name=project_id,
                research_direction=direction,
                synthetic_test_data=synthetic,
            )
        )
        self.state_store.save(state)
        return state

