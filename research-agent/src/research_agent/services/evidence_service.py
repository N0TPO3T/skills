from __future__ import annotations

from research_agent.schemas.claim import Claim
from research_agent.schemas.evidence import Evidence, EvidenceLevel
from research_agent.schemas.state import ResearchState


class UnsupportedClaimError(ValueError):
    pass


class EvidenceService:
    def add_evidence(self, state: ResearchState, evidence: Evidence) -> None:
        if evidence.synthetic_test_data and evidence.level != EvidenceLevel.E0_SPECULATION:
            raise UnsupportedClaimError(
                "Synthetic test data cannot be promoted above E0"
            )
        if evidence.source_type == "paper" and evidence.level != EvidenceLevel.E1_LITERATURE:
            raise UnsupportedClaimError("Paper evidence must use E1")
        if evidence.source_type == "experiment" and evidence.level in {
            EvidenceLevel.E2_SINGLE_EXPERIMENT,
            EvidenceLevel.E3_REPLICATED,
            EvidenceLevel.E4_ROBUST,
        }:
            probe = Claim(
                id=f"VALIDATE-{evidence.id}",
                statement=evidence.summary,
                evidence_level=evidence.level,
                supporting_experiments=evidence.source_ids,
                confidence=0.5,
                allowed_language_strength="suggests",
            )
            self.validate_claim(state, probe)
        state.evidence.items.append(evidence)

    def validate_claim(self, state: ResearchState, claim: Claim) -> None:
        papers = {paper.id: paper for paper in state.literature.papers}
        experiments = {
            experiment.id: experiment for experiment in state.experiments.experiments
        }
        if claim.evidence_level == EvidenceLevel.E0_SPECULATION:
            return
        if claim.evidence_level == EvidenceLevel.E1_LITERATURE:
            invalid = [
                paper_id
                for paper_id in claim.supporting_papers
                if paper_id not in papers
                or not papers[paper_id].verified
                or papers[paper_id].synthetic_test_data
            ]
            if invalid:
                raise UnsupportedClaimError(
                    f"E1 claim uses missing, unverified, or synthetic papers: {invalid}"
                )
            return
        supporting = []
        for experiment_id in claim.supporting_experiments:
            experiment = experiments.get(experiment_id)
            if (
                experiment is None
                or experiment.status != "completed"
                or not experiment.execution_verified
                or not experiment.execution_artifact
                or experiment.synthetic_test_data
            ):
                raise UnsupportedClaimError(
                    f"Experiment {experiment_id} is not runner-verified scientific evidence"
                )
            supporting.append(experiment)
        if not supporting:
            raise UnsupportedClaimError("E2+ claim has no valid supporting experiment")
        if claim.evidence_level == EvidenceLevel.E3_REPLICATED:
            seeds = {seed for experiment in supporting for seed in experiment.seeds}
            if len(seeds) < 2:
                raise UnsupportedClaimError("E3 requires at least two executed seeds")
        if claim.evidence_level == EvidenceLevel.E4_ROBUST:
            settings = {(item.model, item.dataset) for item in supporting}
            if len(settings) < 2:
                raise UnsupportedClaimError("E4 requires at least two model/dataset settings")

    def add_claim(self, state: ResearchState, claim: Claim) -> None:
        self.validate_claim(state, claim)
        state.claims.items.append(claim)
