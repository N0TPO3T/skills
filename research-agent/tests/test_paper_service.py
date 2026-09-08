from __future__ import annotations

from research_agent.schemas.claim import Claim
from research_agent.schemas.evidence import EvidenceLevel
from research_agent.services.paper_service import PaperService


def test_paper_package_enforces_do_not_claim_without_evidence(state) -> None:
    package = PaperService().build_package(state)
    assert any("empirical improvement" in item for item in package.do_not_claim)
    assert any("prior-work facts" in item for item in package.do_not_claim)


def test_paper_draft_uses_claim_language_strength(state) -> None:
    state.claims.items.append(
        Claim(
            id="CLAIM-0",
            statement="Typed gates may prevent invalid state changes.",
            evidence_level=EvidenceLevel.E0_SPECULATION,
            confidence=0.2,
            allowed_language_strength="hypothesizes",
        )
    )
    package = PaperService().build_package(state)
    draft = PaperService.render_draft(package)
    assert "[E0; hypothesizes]" in draft
    assert "Typed gates may prevent" in draft

