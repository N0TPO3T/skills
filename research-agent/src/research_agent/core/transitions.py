from __future__ import annotations

from enum import Enum


class ResearchPhase(str, Enum):
    BOOTSTRAP = "bootstrap"
    HORIZON_SCAN = "horizon_scan"
    GAP_MINING = "gap_mining"
    GAP_SYNTHESIS = "gap_synthesis"
    TOPIC_SELECTION = "topic_selection"
    IDEA_FORMATION = "idea_formation"
    IDEA_REVIEW = "idea_review"
    RESOURCE_DESIGN = "resource_design"
    BASELINE_REPRODUCTION = "baseline_reproduction"
    CORE_EXPERIMENT = "core_experiment"
    DIAGNOSIS = "diagnosis"
    PIVOT = "pivot"
    EVIDENCE_EXPANSION = "evidence_expansion"
    PAPER_AUDIT = "paper_audit"
    PAPER_ASSEMBLY = "paper_assembly"
    PAPER_REVIEW = "paper_review"
    COMPLETE = "complete"


ALLOWED_TRANSITIONS: dict[ResearchPhase, frozenset[ResearchPhase]] = {
    ResearchPhase.BOOTSTRAP: frozenset({ResearchPhase.HORIZON_SCAN}),
    ResearchPhase.HORIZON_SCAN: frozenset(
        {ResearchPhase.HORIZON_SCAN, ResearchPhase.GAP_MINING}
    ),
    ResearchPhase.GAP_MINING: frozenset(
        {ResearchPhase.HORIZON_SCAN, ResearchPhase.GAP_SYNTHESIS}
    ),
    ResearchPhase.GAP_SYNTHESIS: frozenset(
        {ResearchPhase.HORIZON_SCAN, ResearchPhase.TOPIC_SELECTION}
    ),
    ResearchPhase.TOPIC_SELECTION: frozenset({ResearchPhase.IDEA_FORMATION}),
    ResearchPhase.IDEA_FORMATION: frozenset(
        {ResearchPhase.HORIZON_SCAN, ResearchPhase.IDEA_REVIEW}
    ),
    ResearchPhase.IDEA_REVIEW: frozenset(
        {
            ResearchPhase.IDEA_FORMATION,
            ResearchPhase.RESOURCE_DESIGN,
            ResearchPhase.HORIZON_SCAN,
        }
    ),
    ResearchPhase.RESOURCE_DESIGN: frozenset(
        {ResearchPhase.BASELINE_REPRODUCTION}
    ),
    ResearchPhase.BASELINE_REPRODUCTION: frozenset(
        {
            ResearchPhase.RESOURCE_DESIGN,
            ResearchPhase.CORE_EXPERIMENT,
            ResearchPhase.DIAGNOSIS,
        }
    ),
    ResearchPhase.CORE_EXPERIMENT: frozenset(
        {
            ResearchPhase.CORE_EXPERIMENT,
            ResearchPhase.DIAGNOSIS,
            ResearchPhase.EVIDENCE_EXPANSION,
        }
    ),
    ResearchPhase.DIAGNOSIS: frozenset(
        {ResearchPhase.CORE_EXPERIMENT, ResearchPhase.PIVOT}
    ),
    ResearchPhase.PIVOT: frozenset(
        {
            ResearchPhase.IDEA_FORMATION,
            ResearchPhase.GAP_SYNTHESIS,
            ResearchPhase.CORE_EXPERIMENT,
        }
    ),
    ResearchPhase.EVIDENCE_EXPANSION: frozenset(
        {ResearchPhase.CORE_EXPERIMENT, ResearchPhase.PAPER_AUDIT}
    ),
    ResearchPhase.PAPER_AUDIT: frozenset(
        {ResearchPhase.CORE_EXPERIMENT, ResearchPhase.PAPER_ASSEMBLY}
    ),
    ResearchPhase.PAPER_ASSEMBLY: frozenset({ResearchPhase.PAPER_REVIEW}),
    ResearchPhase.PAPER_REVIEW: frozenset(
        {
            ResearchPhase.CORE_EXPERIMENT,
            ResearchPhase.PAPER_ASSEMBLY,
            ResearchPhase.COMPLETE,
        }
    ),
    ResearchPhase.COMPLETE: frozenset(),
}


def validate_transition(current: ResearchPhase, proposed: ResearchPhase) -> bool:
    return proposed in ALLOWED_TRANSITIONS[current]


class InvalidTransitionError(ValueError):
    pass


def require_valid_transition(
    current: ResearchPhase, proposed: ResearchPhase
) -> None:
    if not validate_transition(current, proposed):
        raise InvalidTransitionError(
            f"Illegal research phase transition: {current.value} -> {proposed.value}"
        )
