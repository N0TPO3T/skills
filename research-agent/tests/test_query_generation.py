from __future__ import annotations

from research_agent.schemas.literature import LiteratureState, NoveltySearchInput
from research_agent.services.query_generation_service import QueryGenerationService


def test_query_generation_uses_distinct_axes() -> None:
    queries = QueryGenerationService(max_queries=8).generate(
        topic="adaptive test-time compute",
        literature=LiteratureState(),
        unresolved_questions=["Does compute allocation generalize?"],
    )
    purposes = {query.purpose for query in queries}
    assert {"canonical", "recent", "baseline", "failure_analysis"} <= purposes
    assert len({query.query for query in queries}) == len(queries)


def test_novelty_queries_record_multiple_granularities() -> None:
    novelty = NoveltySearchInput(
        proposed_method="Budget Router",
        mechanism="uncertainty-conditioned compute allocation",
        task="LLM reasoning",
        setting="test-time inference",
    )
    queries = QueryGenerationService().generate(
        topic=novelty.task,
        literature=LiteratureState(),
        search_mode="novelty_check",
        novelty=novelty,
    )
    assert len(queries) == 5
    assert all(query.purpose == "novelty_check" for query in queries)
    assert any(novelty.mechanism in query.query for query in queries)

