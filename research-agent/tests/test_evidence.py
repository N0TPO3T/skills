from __future__ import annotations

import pytest

from research_agent.schemas.claim import Claim
from research_agent.schemas.evidence import EvidenceLevel
from research_agent.schemas.experiment import Experiment
from research_agent.services.evidence_service import EvidenceService, UnsupportedClaimError


def claim(level: EvidenceLevel, experiment_ids: list[str]) -> Claim:
    return Claim(
        id="CLAIM-1",
        statement="The method improves the target metric.",
        evidence_level=level,
        supporting_experiments=experiment_ids,
        confidence=0.6,
        allowed_language_strength="suggests",
    )


def test_unexecuted_experiment_cannot_become_e2(state) -> None:
    state.experiments.experiments.append(
        Experiment(
            id="EXP-1",
            hypothesis_id="HYP-1",
            research_question="Does it improve?",
            expected_outcome="improvement",
            success_criterion="positive delta",
            falsification_criterion="no delta",
            status="planned",
        )
    )
    with pytest.raises(UnsupportedClaimError):
        EvidenceService().add_claim(
            state, claim(EvidenceLevel.E2_SINGLE_EXPERIMENT, ["EXP-1"])
        )


def test_unsupported_claim_rejected(state) -> None:
    with pytest.raises(UnsupportedClaimError):
        EvidenceService().add_claim(
            state, claim(EvidenceLevel.E2_SINGLE_EXPERIMENT, ["EXP-MISSING"])
        )

