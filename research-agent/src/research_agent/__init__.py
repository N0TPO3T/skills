"""Autonomous ML research workflow engine."""

from research_agent.core.transitions import ResearchPhase
from research_agent.schemas.state import ResearchState

__all__ = ["ResearchPhase", "ResearchState"]
__version__ = "0.2.0"
