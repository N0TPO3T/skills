from __future__ import annotations

from datetime import datetime, timezone

from research_agent.core.ids import stable_id
from research_agent.schemas.literature import (
    LiteratureSearchQuery,
    LiteratureState,
    NoveltySearchInput,
)


class QueryGenerationService:
    def __init__(self, *, max_queries: int = 12, recent_year_window: int = 3) -> None:
        self.max_queries = max_queries
        self.recent_year_window = recent_year_window

    def generate(
        self,
        *,
        topic: str,
        literature: LiteratureState,
        unresolved_questions: list[str] | None = None,
        search_mode: str = "standard",
        novelty: NoveltySearchInput | None = None,
    ) -> list[LiteratureSearchQuery]:
        if search_mode == "novelty_check":
            if novelty is None:
                raise ValueError("novelty_check requires proposed method context")
            specs = self._novelty_specs(novelty)
        else:
            specs = self._standard_specs(
                topic, literature.clusters, unresolved_questions or []
            )
        seen = {item.query.casefold().strip() for item in literature.search_queries}
        queries: list[LiteratureSearchQuery] = []
        for query, purpose, priority, year_from, year_to in specs:
            normalized = query.casefold().strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            queries.append(
                LiteratureSearchQuery(
                    id=stable_id("QUERY", purpose, normalized, year_from, year_to),
                    query=query,
                    purpose=purpose,
                    target_year_from=year_from,
                    target_year_to=year_to,
                    priority=priority,
                )
            )
            if len(queries) >= self.max_queries:
                break
        return queries

    def _standard_specs(
        self, topic: str, clusters: list[str], unresolved: list[str]
    ) -> list[tuple[str, str, float, int | None, int | None]]:
        current_year = datetime.now(timezone.utc).year
        specs: list[tuple[str, str, float, int | None, int | None]] = [
            (f"{topic} foundational canonical methods", "canonical", 1.0, None, None),
            (
                f"{topic} recent advances",
                "recent",
                0.95,
                current_year - self.recent_year_window + 1,
                current_year,
            ),
            (f"{topic} strong baselines benchmark", "baseline", 0.9, None, None),
            (
                f"{topic} failure modes negative results limitations",
                "failure_analysis",
                0.9,
                None,
                None,
            ),
            (f"{topic} adjacent methods survey", "adjacent_method", 0.75, None, None),
            (
                f"{topic} official implementation code reproduction",
                "implementation",
                0.7,
                None,
                None,
            ),
        ]
        specs.extend(
            (f"{topic} {cluster}", "adjacent_method", 0.65, None, None)
            for cluster in clusters[:2]
        )
        specs.extend(
            (f"{topic} {question}", "failure_analysis", 0.85, None, None)
            for question in unresolved[:2]
        )
        return specs

    @staticmethod
    def _novelty_specs(
        novelty: NoveltySearchInput,
    ) -> list[tuple[str, str, float, None, None]]:
        return [
            (
                f'"{novelty.proposed_method}" "{novelty.task}"',
                "novelty_check",
                1.0,
                None,
                None,
            ),
            (
                f'"{novelty.mechanism}" "{novelty.task}"',
                "novelty_check",
                0.95,
                None,
                None,
            ),
            (
                f"{novelty.proposed_method} alternatives related methods {novelty.task}",
                "novelty_check",
                0.9,
                None,
                None,
            ),
            (
                f"{novelty.mechanism} adjacent tasks {novelty.setting}",
                "novelty_check",
                0.85,
                None,
                None,
            ),
            (
                f"{novelty.task} method family {novelty.setting}",
                "novelty_check",
                0.8,
                None,
                None,
            ),
        ]

