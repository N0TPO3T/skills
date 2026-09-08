from __future__ import annotations

from research_agent.core.transitions import ResearchPhase
from research_agent.schemas.decision import ResearchAction
from research_agent.schemas.state import ResearchState
from research_agent.services.paper_service import PaperService
from research_agent.storage.artifact_store import ArtifactStore


class PaperWorkflow:
    def __init__(self, artifacts: ArtifactStore) -> None:
        self.artifacts = artifacts
        self.service = PaperService()

    async def audit_paper(
        self, state: ResearchState, action: ResearchAction
    ) -> ResearchPhase:
        package = self.service.build_package(state)
        self.artifacts.write_json(
            "artifacts/paper/readiness_audit.json",
            {
                "ready": not package.do_not_claim,
                "do_not_claim": package.do_not_claim,
                "claim_count": len(package.claim_evidence_matrix),
            },
        )
        return ResearchPhase.PAPER_AUDIT

    async def write_paper(
        self, state: ResearchState, action: ResearchAction
    ) -> ResearchPhase:
        package = self.service.build_package(state)
        self.artifacts.write_json(
            "artifacts/paper/paper_package.json", package.model_dump(mode="json")
        )
        self.artifacts.write_text(
            "artifacts/paper/draft.md", self.service.render_draft(package)
        )
        return ResearchPhase.PAPER_ASSEMBLY

    async def review_paper(
        self, state: ResearchState, action: ResearchAction
    ) -> ResearchPhase:
        package = self.service.build_package(state)
        blocking = package.do_not_claim
        self.artifacts.write_json(
            "artifacts/reviews/paper_review.json",
            {"blocking_issues": blocking, "ready": not blocking},
        )
        return ResearchPhase.PAPER_REVIEW

    async def complete_project(
        self, state: ResearchState, action: ResearchAction
    ) -> ResearchPhase:
        package = self.service.build_package(state)
        if package.do_not_claim:
            raise ValueError("Paper cannot complete while readiness blockers remain")
        self.artifacts.write_text(
            "artifacts/reports/research_report.md",
            self.service.render_draft(package),
        )
        return ResearchPhase.COMPLETE

