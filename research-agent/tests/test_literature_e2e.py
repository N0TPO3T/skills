from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from research_agent.core.context_builder import ContextBuilder
from research_agent.core.ids import stable_id
from research_agent.literature.providers.base import ProviderTimeoutError
from research_agent.schemas.literature import (
    LiteratureSearchQuery,
    NoveltySearchInput,
    PaperCandidate,
    PaperContent,
    PaperExtractionDraft,
    PaperIdentifier,
    PaperMetadata,
)
from research_agent.schemas.literature_quality import ExtractionCapabilityStatus
from research_agent.schemas.project import ProjectInfo
from research_agent.schemas.state import ResearchState
from research_agent.services.literature_service import LiteratureService, LiteratureSettings
from research_agent.storage.artifact_store import ArtifactStore


class FixedProvider:
    name = "fixed-provider"

    def __init__(self) -> None:
        self.search_calls = 0

    async def search(self, query: LiteratureSearchQuery) -> list[PaperCandidate]:
        self.search_calls += 1
        paper_number = 2 if query.purpose == "recent" else 1
        return [
            PaperCandidate(
                id=stable_id("CAND", query.id, paper_number),
                query_id=query.id,
                raw_title=f"Verified Fixture Paper {paper_number}",
                raw_authors=[f"Author {paper_number}"],
                raw_year=2024 + paper_number,
                source_provider=self.name,
                source_url=f"https://example.test/paper-{paper_number}",
                identifiers=PaperIdentifier(doi=f"10.1000/fixed-{paper_number}"),
                retrieval_rank=1,
            )
        ]

    async def resolve(self, candidate: PaperCandidate) -> PaperMetadata | None:
        number = candidate.identifiers.doi.rsplit("-", 1)[-1]
        return PaperMetadata(
            paper_id=f"PAPER-{number}",
            title=candidate.raw_title,
            authors=candidate.raw_authors,
            year=candidate.raw_year,
            venue="FixtureConf",
            identifiers=candidate.identifiers,
            abstract=f"Paper {number} studies adaptive compute and reports a bounded result.",
            publication_status="conference",
            source_records=[candidate.source_url],
            metadata_verified=True,
            verification_confidence=0.95,
        )

    async def fetch_content(self, paper: PaperMetadata) -> PaperContent | None:
        return PaperContent(
            paper_id=paper.paper_id,
            content_type="pdf_text",
            source_url=paper.source_records[0],
            parser_name="fixed-parser",
            parser_version="1",
            raw_text=(
                f"{paper.title}. The method allocates compute using uncertainty. "
                "Experiments report gains over a fixed-compute baseline. "
                "The authors state that distribution shift remains a limitation."
            ),
        )

    def safe_configuration(self) -> dict[str, object]:
        return {"fixture": "fixed", "secrets": False}


class FixedExtractor:
    name = "fixed-extractor"
    model = "fixed-model-v1"

    async def extract(self, *, metadata, content, text) -> PaperExtractionDraft:
        return PaperExtractionDraft(
            problem="Fixed compute is inefficient for variable reasoning difficulty.",
            main_claim="Uncertainty-conditioned allocation improves efficiency.",
            method_summary="Allocate test-time compute from uncertainty.",
            core_assumptions=["Uncertainty estimates correlate with difficulty."],
            models=["FixtureLM"],
            datasets=["FixtureReasoning"],
            main_results=["The method exceeds a fixed-compute baseline in the fixture."],
            limitations_claimed=["Distribution shift remains a limitation."],
            limitations_inferred=["The uncertainty estimator may be miscalibrated."],
            extraction_confidence=0.9,
        )


class FailingProvider:
    name = "failing-provider"

    async def search(self, query):
        raise ProviderTimeoutError("fixture timeout")

    async def resolve(self, candidate):
        return None

    async def fetch_content(self, paper):
        return None

    def safe_configuration(self):
        return {"fixture": "failure"}


class SyntheticLaunderingProvider(FixedProvider):
    name = "synthetic-laundering-provider"

    async def search(self, query: LiteratureSearchQuery) -> list[PaperCandidate]:
        candidates = await super().search(query)
        return [
            candidate.model_copy(
                update={
                    "source_provider": self.name,
                    "synthetic_test_data": True,
                }
            )
            for candidate in candidates
        ]


def service(tmp_path: Path, providers=None) -> tuple[LiteratureService, ResearchState]:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    state = ResearchState(
        project=ProjectInfo(
            id="literature-demo",
            name="Literature Demo",
            research_direction="adaptive test-time compute",
        )
    )
    instance = LiteratureService(
        providers=providers or [FixedProvider()],
        artifacts=ArtifactStore(project_dir),
        extractor=FixedExtractor(),
        settings=LiteratureSettings(minimum_content_verified_for_gap=2),
    )
    return instance, state


async def test_provider_independent_literature_e2e(tmp_path: Path) -> None:
    instance, state = service(tmp_path)
    result = await instance.search_round(state)

    assert result.queries
    assert len(state.literature.paper_metadata) == 2
    assert all(item.metadata_verified for item in state.literature.paper_metadata)
    assert len(state.literature.contents) == 2
    assert all(item.content_verified for item in state.literature.contents)
    assert len(state.literature.extractions) == 2
    assert state.literature.statements
    assert state.literature.provenance_records
    assert state.literature.clusters == [
        "dataset:FixtureReasoning",
        "model:FixtureLM",
    ]
    assert result.coverage.sufficient_for_gap_synthesis is True
    assert result.coverage.duplicate_count > 0
    content_path = tmp_path / "project" / state.literature.contents[0].artifact_path
    assert content_path.is_file()
    assert "allocates compute" in content_path.read_text()
    assert (
        sha256(content_path.read_bytes()).hexdigest()
        == state.literature.contents[0].sha256
    )

    capabilities = {
        "problem",
        "main_claim",
        "method",
        "assumptions",
        "results",
        "limitations",
    }
    state.literature_quality.capability_statuses = [
        ExtractionCapabilityStatus(
            capability=capability,
            precision=1.0,
            recall=1.0,
            status="validated",
            evaluation_id="FIXTURE-EVAL",
            reason="deterministic fixture",
        )
        for capability in capabilities
    ]
    context = ContextBuilder().for_gap_mining(state)
    assert context["extracted_statements"]
    assert context["provenance_summary"]
    assert "allocates compute using uncertainty" not in str(context)


async def test_provider_failure_is_isolated(tmp_path: Path) -> None:
    instance, state = service(tmp_path, [FixedProvider(), FailingProvider()])
    query = LiteratureSearchQuery(
        id="QUERY-FAILURE-ISOLATION",
        query="adaptive compute",
        purpose="canonical",
        priority=1.0,
    )
    candidates = await instance.retrieve_candidates(state.literature, [query])
    assert len(candidates) == 1
    assert candidates[0].source_provider == "fixed-provider"
    assert len(state.literature.failures) == 1
    assert state.literature.failures[0].retryable is True


async def test_synthetic_candidate_cannot_be_laundered_as_verified(tmp_path: Path) -> None:
    provider = SyntheticLaunderingProvider()
    instance, state = service(tmp_path, [provider])
    query = LiteratureSearchQuery(
        id="QUERY-SYNTHETIC",
        query="synthetic",
        purpose="canonical",
        priority=1.0,
    )
    candidates = await instance.retrieve_candidates(state.literature, [query])
    await instance.verify_metadata(state.literature, candidates)
    assert state.literature.paper_metadata
    assert state.literature.paper_metadata[0].metadata_verified is False
    assert state.literature.paper_metadata[0].synthetic_test_data is True
    assert candidates[0].status == "rejected"


async def test_search_cache_uses_stable_input(tmp_path: Path) -> None:
    provider = FixedProvider()
    instance, state = service(tmp_path, [provider])
    query = LiteratureSearchQuery(
        id="QUERY-ONE", query="same query", purpose="canonical", priority=1.0
    )
    await instance.retrieve_candidates(state.literature, [query])
    equivalent = query.model_copy(update={"id": "QUERY-DIFFERENT-RUN-ID"})
    await instance.retrieve_candidates(state.literature, [equivalent])
    assert provider.search_calls == 1


async def test_novelty_scope_and_bounded_conclusion_are_recorded(tmp_path: Path) -> None:
    instance, state = service(tmp_path)
    novelty = NoveltySearchInput(
        proposed_method="Budget Router",
        mechanism="uncertainty-conditioned compute allocation",
        task="LLM reasoning",
        setting="test-time inference",
    )
    await instance.search_round(
        state, search_mode="novelty_check", novelty=novelty
    )
    record = state.literature.novelty_searches[-1]
    assert record.query_ids
    assert record.searched_providers == ["fixed-provider"]
    assert "within the searched corpus" in record.bounded_conclusion


def test_low_information_gain_stop_rule(tmp_path: Path) -> None:
    instance, state = service(tmp_path)
    metric_type = state.literature.search_round_metrics
    from research_agent.schemas.literature import SearchRoundMetrics

    metric_type.extend(
        [
            SearchRoundMetrics(
                new_verified_papers=0,
                new_clusters=0,
                new_gap_evidence=0,
                novelty_landscape_changed=False,
                marginal_information_gain=0.0,
            ),
            SearchRoundMetrics(
                new_verified_papers=0,
                new_clusters=0,
                new_gap_evidence=0,
                novelty_landscape_changed=False,
                marginal_information_gain=0.05,
            ),
        ]
    )
    assert instance.should_stop_search(state.literature)
