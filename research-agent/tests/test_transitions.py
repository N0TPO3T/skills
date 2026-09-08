from __future__ import annotations

import pytest

from research_agent.core.transitions import (
    InvalidTransitionError,
    ResearchPhase,
    require_valid_transition,
    validate_transition,
)


def test_valid_transition_passes() -> None:
    assert validate_transition(ResearchPhase.BOOTSTRAP, ResearchPhase.HORIZON_SCAN)
    require_valid_transition(ResearchPhase.CORE_EXPERIMENT, ResearchPhase.DIAGNOSIS)


def test_invalid_transition_rejected() -> None:
    assert not validate_transition(ResearchPhase.BOOTSTRAP, ResearchPhase.COMPLETE)
    with pytest.raises(InvalidTransitionError):
        require_valid_transition(ResearchPhase.BOOTSTRAP, ResearchPhase.COMPLETE)

