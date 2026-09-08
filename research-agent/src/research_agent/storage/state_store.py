from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

from research_agent.schemas.state import ResearchState


class StateStore:
    def __init__(self, projects_root: Path) -> None:
        self.projects_root = projects_root.resolve()

    def state_path(self, project_id: str) -> Path:
        return self.projects_root / project_id / "state.json"

    def load(self, project_id: str) -> ResearchState:
        path = self.state_path(project_id)
        if not path.is_file():
            raise FileNotFoundError(f"Research project not found: {project_id}")
        return ResearchState.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, state: ResearchState) -> Path:
        path = self.state_path(state.project.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        state.updated_at = datetime.now(timezone.utc)
        payload = state.model_dump_json(indent=2)
        with NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            handle.write(payload)
            temp_path = Path(handle.name)
        os.replace(temp_path, path)
        return path

