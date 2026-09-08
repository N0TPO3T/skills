from __future__ import annotations

from research_agent.schemas.paper import ClaimEvidenceRow, PaperPackage
from research_agent.schemas.state import ResearchState


class PaperService:
    def build_package(self, state: ResearchState) -> PaperPackage:
        gap = next(
            (item for item in state.gaps.candidates if item.id == state.gaps.selected_gap_id),
            None,
        )
        idea = next(
            (item for item in state.ideas.candidates if item.id == state.ideas.selected_idea_id),
            None,
        )
        completed = [
            experiment
            for experiment in state.experiments.experiments
            if experiment.status == "completed"
            and experiment.execution_verified
            and experiment.execution_artifact
        ]
        matrix = [
            ClaimEvidenceRow(
                claim_id=claim.id,
                statement=claim.statement,
                evidence_level=claim.evidence_level.value,
                supporting_papers=claim.supporting_papers,
                supporting_experiments=claim.supporting_experiments,
                allowed_language_strength=claim.allowed_language_strength,
            )
            for claim in state.claims.items
        ]
        verified_papers = [
            paper for paper in state.literature.papers if paper.verified and not paper.synthetic_test_data
        ]
        do_not_claim = []
        if not completed:
            do_not_claim.append("Do not claim empirical improvement without runner-verified experiments.")
        if not verified_papers:
            do_not_claim.append("Do not claim prior-work facts from unverified or synthetic references.")
        if not matrix:
            do_not_claim.append("Do not introduce central claims absent from the claim-evidence matrix.")
        return PaperPackage(
            problem=state.project.research_direction or state.project.name,
            gap=gap.title if gap else "Unselected",
            root_cause=gap.root_cause_hypothesis if gap else "Unknown",
            hypothesis=[item.statement for item in state.hypotheses.items],
            method=idea.mechanism if idea else "Unspecified",
            contributions=[row.statement for row in matrix],
            related_work_positioning=[paper.id for paper in verified_papers],
            experimental_setup=[f"{item.id}: {item.research_question}" for item in completed],
            main_results=[
                f"{item.id}: {item.observation}" for item in completed if item.observation
            ],
            ablations=[],
            analysis=[
                f"{item.id}: {item.interpretation}"
                for item in completed
                if item.interpretation
            ],
            failure_cases=[
                f"{item.id}: {item.observation}"
                for item in state.experiments.experiments
                if item.status == "failed" and item.observation
            ],
            limitations=sorted(
                {confounder for item in state.experiments.experiments for confounder in item.confounders}
            ),
            claim_evidence_matrix=matrix,
            tables=[item.metrics_artifact for item in completed if item.metrics_artifact],
            figure_requirements=[],
            citations=[paper.id for paper in verified_papers],
            do_not_claim=do_not_claim,
            synthetic_test_data=state.project.synthetic_test_data,
        )

    @staticmethod
    def render_draft(package: PaperPackage) -> str:
        claims = "\n".join(
            f"- [{row.evidence_level}; {row.allowed_language_strength}] {row.statement}"
            for row in package.claim_evidence_matrix
        ) or "- No evidence-backed claims are ready."
        limitations = "\n".join(f"- {item}" for item in package.limitations) or "- Not yet assessed."
        do_not_claim = "\n".join(f"- {item}" for item in package.do_not_claim) or "- None."
        return (
            "# Research Draft\n\n"
            f"## Problem\n\n{package.problem}\n\n"
            f"## Gap and hypothesis\n\n{package.gap}. {package.root_cause}\n\n"
            f"## Method\n\n{package.method}\n\n"
            f"## Evidence-bounded claims\n\n{claims}\n\n"
            f"## Limitations\n\n{limitations}\n\n"
            f"## Do not claim\n\n{do_not_claim}\n"
        )
