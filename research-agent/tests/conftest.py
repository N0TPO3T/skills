from __future__ import annotations

from pathlib import Path

import pytest

from research_agent.schemas.project import ProjectInfo
from research_agent.schemas.state import ResearchState


@pytest.fixture
def state() -> ResearchState:
    return ResearchState(
        project=ProjectInfo(
            id="demo", name="Demo", research_direction="adaptive reasoning"
        )
    )


@pytest.fixture
def projects_root(tmp_path: Path) -> Path:
    return tmp_path / "projects"

