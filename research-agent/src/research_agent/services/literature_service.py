from __future__ import annotations

import asyncio
import json
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from research_agent.core.ids import stable_id
from research_agent.literature.deduplication import PaperDeduplicator, normalize_title
from research_agent.literature.extraction import PaperExtractor, RuleBasedPaperExtractor
from research_agent.literature.providers.base import (
    LiteratureProvider,
    LiteratureProviderError,
)
from research_agent.prompts.loader import PromptLoader
from research_agent.schemas.literature import (
    ExtractedStatement,
    LiteratureCoverageReport,
    LiteratureFailure,
    LiteratureSearchQuery,
    LiteratureSearchRound,
    LiteratureState,
    NoveltySearchInput,
    NoveltySearchRecord,
    PaperCandidate,
    PaperContent,
    PaperExtraction,
    PaperExtractionDraft,
    PaperMetadata,
    PaperReference,
    SearchRoundMetrics,
)
from research_agent.schemas.provenance import (
    ProvenanceRecord,
    SourceLocator,
    StatementEpistemicType,
)
from research_agent.schemas.state import ResearchState
from research_agent.services.query_generation_service import QueryGenerationService
from research_agent.storage.artifact_store import ArtifactStore
from research_agent.storage.literature_cache import LiteratureCache


METADATA_STATEMENT_TYPES = {
    "paper_exists",
    "authors",
    "year",
    "venue",
    "title",
    "identifier",
}
ABSTRACT_STATEMENT_TYPES = {
    "problem",
    "claim",
    "method",
    "result",
    "high_level_problem",
    "high_level_method_claim",
    "high_level_stated_result",
}
FULL_CONTENT_STATEMENT_TYPES = {
    "detailed_method",
    "experiment_design",
    "specific_limitation",
    "limitation_claimed",
    "limitation_inferred",
    "ablation",
    "failure_mode",
    "precise_comparison",
    "assumption",
}


class LiteratureSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_queries_per_round: int = Field(default=12, ge=1)
    max_candidates_per_query: int = Field(default=20, ge=1)
    max_new_verified_papers_per_round: int = Field(default=40, ge=1)
    recent_year_window: int = Field(default=3, ge=1)
    duplicate_title_similarity_threshold: float = Field(
        default=0.94, ge=0.8, le=1.0
    )
    provider_timeout_seconds: float = Field(default=45, gt=0)
    minimum_content_verified_for_gap: int = Field(default=3, ge=1)
    low_information_gain_threshold: float = Field(default=0.1, ge=0, le=1)
    low_information_gain_rounds: int = Field(default=2, ge=1)
    search_cache_ttl_seconds: float = Field(default=86400, ge=0)


class LiteratureRoundResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    round_id: str
    queries: list[LiteratureSearchQuery]
    candidate_ids: list[str]
    newly_verified_paper_ids: list[str]
    newly_content_verified_paper_ids: list[str]
    coverage: LiteratureCoverageReport
    metrics: SearchRoundMetrics


def can_support_literature_claim(
    paper: PaperCandidate | PaperMetadata,
    statement_type: str,
    content: PaperContent | None = None,
) -> bool:
    if isinstance(paper, PaperCandidate):
        return False
    if not paper.metadata_verified or paper.synthetic_test_data:
        return False
    if statement_type in METADATA_STATEMENT_TYPES:
        return True
    if (
        content is None
        or not content.content_verified
        or content.synthetic_test_data
        or content.paper_id != paper.paper_id
    ):
        return False
    if statement_type in ABSTRACT_STATEMENT_TYPES:
        return True
    if statement_type in FULL_CONTENT_STATEMENT_TYPES:
        return content.content_type in {"full_text", "html", "pdf_text"}
    return False


def usable_as_verified_fact(paper: PaperReference) -> bool:
    return paper.verified and not paper.synthetic_test_data


class LiteratureService:
    def __init__(
        self,
        *,
        providers: list[LiteratureProvider],
        artifacts: ArtifactStore,
        settings: LiteratureSettings | None = None,
        extractor: PaperExtractor | None = None,
        prompts: PromptLoader | None = None,
        cache: LiteratureCache | None = None,
    ) -> None:
        if not providers:
            raise ValueError("At least one literature provider is required")
        self.providers = {provider.name: provider for provider in providers}
        if len(self.providers) != len(providers):
            raise ValueError("Literature provider names must be unique")
        self.artifacts = artifacts
        self.settings = settings or LiteratureSettings()
        self.extractor = extractor or RuleBasedPaperExtractor()
        self.prompts = prompts or PromptLoader()
        self.cache = cache or LiteratureCache(artifacts.project_dir)
        self.queries = QueryGenerationService(
            max_queries=self.settings.max_queries_per_round,
            recent_year_window=self.settings.recent_year_window,
        )
        self.deduplicator = PaperDeduplicator(
            self.settings.duplicate_title_similarity_threshold
        )

    async def search_round(
        self,
        state: ResearchState,
        *,
        topic: str | None = None,
        unresolved_questions: list[str] | None = None,
        search_mode: Literal["standard", "novelty_check"] = "standard",
        novelty: NoveltySearchInput | None = None,
        queries_override: list[LiteratureSearchQuery] | None = None,
    ) -> LiteratureRoundResult:
        topic = topic or state.project.research_direction or state.project.name
        before_metadata = self._verified_ids(state.literature)
        before_content = self._content_verified_ids(state.literature)
        before_clusters = set(state.literature.clusters)
        before_statements = len(state.literature.statements)
        queries = (
            queries_override[: self.settings.max_queries_per_round]
            if queries_override
            else self.queries.generate(
                topic=topic,
                literature=state.literature,
                unresolved_questions=unresolved_questions,
                search_mode=search_mode,
                novelty=novelty,
            )
        )
        if not queries:
            queries = [
                LiteratureSearchQuery(
                    id=stable_id("QUERY", "citation_expansion", topic),
                    query=topic,
                    purpose="citation_expansion",
                    priority=0.5,
                )
            ]
        for query in queries:
            self._upsert_query(state.literature, query)
            self.artifacts.write_json(
                f"artifacts/literature/queries/{query.id}.json",
                query.model_dump(mode="json"),
            )
        candidates = await self.retrieve_candidates(state.literature, queries)
        await self.verify_metadata(state.literature, candidates)
        await self.fetch_contents(state.literature)
        await self.extract_papers(state.literature)
        await self.build_literature_map(state.literature)

        new_verified = sorted(self._verified_ids(state.literature) - before_metadata)
        new_content = sorted(
            self._content_verified_ids(state.literature) - before_content
        )
        new_clusters = len(set(state.literature.clusters) - before_clusters)
        new_statements = len(state.literature.statements) - before_statements
        novelty_changed = bool(new_verified) if search_mode == "novelty_check" else False
        information_gain = min(
            1.0,
            0.5
            * len(new_verified)
            / self.settings.max_new_verified_papers_per_round
            + 0.25 * min(1.0, new_clusters / 3)
            + 0.25 * min(1.0, max(new_statements, 0) / 10),
        )
        metrics = SearchRoundMetrics(
            new_verified_papers=len(new_verified),
            new_clusters=new_clusters,
            new_gap_evidence=max(new_statements, 0),
            novelty_landscape_changed=novelty_changed,
            marginal_information_gain=information_gain,
        )
        state.literature.search_round_metrics.append(metrics)
        coverage = self.build_coverage_report(
            state.literature, unresolved_questions=unresolved_questions or []
        )
        state.literature.coverage_reports.append(coverage)
        state.literature.coverage_artifact = self.artifacts.write_json(
            "artifacts/literature/reports/coverage.json",
            coverage.model_dump(mode="json"),
        )
        prompt_metadata = self.prompts.metadata(
            role="literature_extract", policies=["evidence", "citation"]
        )
        round_id = stable_id(
            "LIT-ROUND",
            state.project.id,
            *(query.id for query in queries),
            len(state.literature.search_rounds),
        )
        search_round = LiteratureSearchRound(
            id=round_id,
            providers=list(self.providers),
            provider_configuration={
                name: provider.safe_configuration()
                for name, provider in self.providers.items()
            },
            query_ids=[query.id for query in queries],
            raw_result_count=len(candidates),
            selected_candidate_ids=[candidate.id for candidate in candidates],
            verification_decisions={
                candidate.id: candidate.status for candidate in candidates
            },
            extractor_model=self.extractor.model,
            extractor_prompt_version=prompt_metadata.version,
            extractor_prompt_hash=prompt_metadata.sha256,
            metrics=metrics,
        )
        state.literature.search_rounds.append(search_round)
        self.artifacts.write_json(
            f"artifacts/literature/reports/{round_id}.json",
            search_round.model_dump(mode="json"),
        )
        if search_mode == "novelty_check" and novelty is not None:
            self._record_novelty_search(
                state.literature, novelty, queries, candidates
            )
        return LiteratureRoundResult(
            round_id=round_id,
            queries=queries,
            candidate_ids=[candidate.id for candidate in candidates],
            newly_verified_paper_ids=new_verified,
            newly_content_verified_paper_ids=new_content,
            coverage=coverage,
            metrics=metrics,
        )

    async def retrieve_candidates(
        self,
        literature: LiteratureState,
        queries: list[LiteratureSearchQuery],
    ) -> list[PaperCandidate]:
        calls = [
            self._search_provider(literature, provider, query)
            for query in queries[: self.settings.max_queries_per_round]
            for provider in self.providers.values()
            if getattr(provider, "capabilities", None) is None
            or provider.capabilities.search
        ]
        batches = await asyncio.gather(*calls)
        selected: list[PaperCandidate] = []
        known = {candidate.id: candidate for candidate in literature.candidates}
        for batch in batches:
            for candidate in batch:
                if candidate.id not in known:
                    literature.candidates.append(candidate)
                    known[candidate.id] = candidate
                selected_candidate = known[candidate.id]
                selected.append(selected_candidate)
                self._write_candidate(selected_candidate)
        return selected

    async def verify_metadata(
        self, literature: LiteratureState, candidates: list[PaperCandidate]
    ) -> list[PaperMetadata]:
        newly_verified: list[PaperMetadata] = []
        for candidate in candidates:
            existing = self.deduplicator.find_existing(candidate, literature)
            if existing:
                self._link_duplicate(literature, candidate, existing)
                continue
            if len(newly_verified) >= self.settings.max_new_verified_papers_per_round:
                break
            provider = self.providers.get(candidate.source_provider)
            if provider is None:
                self._failure(
                    literature,
                    "resolve",
                    candidate.source_provider,
                    candidate.id,
                    KeyError(candidate.source_provider),
                )
                continue
            metadata = await self._resolve_provider(literature, provider, candidate)
            if metadata is None:
                candidate.status = "rejected"
                candidate.rejection_reason = "metadata could not be resolved"
                self._write_candidate(candidate)
                continue
            if candidate.synthetic_test_data:
                values = metadata.model_dump(mode="json")
                values.update(
                    {
                        "metadata_verified": False,
                        "verification_confidence": 0.0,
                        "synthetic_test_data": True,
                    }
                )
                metadata = PaperMetadata.model_validate(values)
            duplicate = self.deduplicator.find_existing(
                PaperCandidate(
                    id=candidate.id,
                    query_id=candidate.query_id,
                    raw_title=metadata.title,
                    raw_authors=metadata.authors,
                    raw_year=metadata.year,
                    source_provider=candidate.source_provider,
                    source_url=candidate.source_url,
                    identifiers=metadata.identifiers,
                    synthetic_test_data=metadata.synthetic_test_data,
                ),
                literature,
            )
            if duplicate:
                target = next(
                    paper for paper in literature.paper_metadata if paper.paper_id == duplicate
                )
                relation = self.deduplicator.same_work_relation(metadata, target)
                if relation and relation not in literature.relations:
                    literature.relations.append(relation)
                self._link_duplicate(literature, candidate, duplicate)
                continue
            literature.paper_metadata.append(metadata)
            literature.candidate_paper_links[candidate.id] = metadata.paper_id
            if metadata.metadata_verified and not metadata.synthetic_test_data:
                candidate.status = "metadata_verified"
                newly_verified.append(metadata)
            else:
                candidate.status = "rejected"
                candidate.rejection_reason = (
                    "synthetic test record"
                    if metadata.synthetic_test_data
                    else "metadata verification threshold not met"
                )
            metadata_artifact = self.artifacts.write_json(
                f"artifacts/literature/papers/{metadata.paper_id}/metadata.json",
                metadata.model_dump(mode="json"),
            )
            if metadata.metadata_verified:
                provenance = ProvenanceRecord(
                    id=stable_id("PROV", metadata.paper_id, "metadata"),
                    entity_type="paper_metadata",
                    entity_id=metadata.paper_id,
                    source_type="paper_metadata",
                    source_id=metadata.source_records[0],
                    artifact_path=metadata_artifact,
                    extraction_method=f"{provider.name}.resolve",
                    retrieved_at=candidate.retrieved_at,
                    confidence=metadata.verification_confidence,
                )
                self._upsert_provenance(literature, provenance)
                self._write_provenance(literature, metadata.paper_id)
            self._sync_legacy_reference(literature, metadata)
            self._write_candidate(candidate)
        return newly_verified

    async def fetch_contents(
        self, literature: LiteratureState, paper_ids: list[str] | None = None
    ) -> list[PaperContent]:
        existing_ids = {content.paper_id for content in literature.contents}
        selected = [
            paper
            for paper in literature.paper_metadata
            if paper.metadata_verified
            and not paper.synthetic_test_data
            and paper.paper_id not in existing_ids
            and (paper_ids is None or paper.paper_id in paper_ids)
        ]
        fetched: list[PaperContent] = []
        for paper in selected:
            provider = self._provider_for_paper(literature, paper.paper_id)
            if provider is None:
                self._failure(
                    literature,
                    "fetch",
                    "unknown",
                    paper.paper_id,
                    RuntimeError("No source provider linked to paper"),
                )
                continue
            raw_content = await self._fetch_provider(literature, provider, paper)
            if (
                raw_content is None
                or raw_content.synthetic_test_data
                or not (raw_content.raw_text or "").strip()
            ):
                self._failure(
                    literature,
                    "fetch",
                    provider.name,
                    paper.paper_id,
                    RuntimeError("No accessible parseable paper content"),
                )
                continue
            text = raw_content.raw_text.strip()
            digest = sha256(text.encode("utf-8")).hexdigest()
            artifact_path = self.artifacts.write_text(
                f"artifacts/literature/papers/{paper.paper_id}/content.txt", text
            )
            content = PaperContent(
                paper_id=paper.paper_id,
                content_type=raw_content.content_type,
                artifact_path=artifact_path,
                source_url=raw_content.source_url,
                fetched_at=raw_content.fetched_at,
                sha256=digest,
                parser_name=raw_content.parser_name,
                parser_version=raw_content.parser_version,
                content_verified=True,
                synthetic_test_data=False,
                version_type=raw_content.version_type,
                content_version_label=raw_content.content_version_label,
                source_paper_id=raw_content.source_paper_id or paper.paper_id,
                source_mime_type=raw_content.source_mime_type,
            )
            literature.contents.append(content)
            fetched.append(content)
            for candidate_id, linked_id in literature.candidate_paper_links.items():
                if linked_id == paper.paper_id:
                    candidate = self._candidate(literature, candidate_id)
                    if candidate:
                        candidate.status = "content_verified"
                        self._write_candidate(candidate)
        return fetched

    async def extract_papers(
        self, literature: LiteratureState, paper_ids: list[str] | None = None
    ) -> list[PaperExtraction]:
        existing_versions = {
            (extraction.paper_id, extraction.content_sha256)
            for extraction in literature.extractions
        }
        prompt_metadata = self.prompts.metadata(
            role="literature_extract", policies=["evidence", "citation"]
        )
        extracted: list[PaperExtraction] = []
        for content in literature.contents:
            if (
                not content.content_verified
                or content.synthetic_test_data
                or (content.paper_id, content.sha256) in existing_versions
                or (paper_ids is not None and content.paper_id not in paper_ids)
            ):
                continue
            metadata = self._metadata(literature, content.paper_id)
            if metadata is None or not metadata.metadata_verified:
                continue
            try:
                text = self.artifacts.read_text(content.artifact_path)
                draft = await self._extract_with_cache(
                    metadata, content, text, prompt_metadata.sha256
                )
                if content.content_type == "abstract_only":
                    draft = draft.model_copy(
                        update={
                            "core_assumptions": [],
                            "training_requirements": [],
                            "inference_requirements": [],
                            "models": [],
                            "datasets": [],
                            "metrics": [],
                            "baselines": [],
                            "main_results": [],
                            "ablations": [],
                            "limitations_claimed": [],
                            "limitations_inferred": [],
                            "failure_modes": [],
                            "compute_notes": [],
                        }
                    )
                statements, provenance = self._statements_and_provenance(
                    metadata, content, draft
                )
                if not statements:
                    raise ValueError("Extractor produced no source-grounded statements")
                for item in provenance:
                    self._upsert_provenance(literature, item)
                for item in statements:
                    if all(existing.id != item.id for existing in literature.statements):
                        literature.statements.append(item)
                extraction = PaperExtraction(
                    paper_id=metadata.paper_id,
                    **draft.model_dump(),
                    provenance_ids=[item.id for item in provenance],
                    extractor_model=self.extractor.model,
                    prompt_metadata=prompt_metadata,
                    partial=(
                        content.content_type == "abstract_only"
                        or draft.extraction_confidence < 0.8
                    ),
                    content_sha256=content.sha256,
                    content_version_label=content.content_version_label,
                    source_paper_id=content.source_paper_id or metadata.paper_id,
                )
                literature.extractions.append(extraction)
                extracted.append(extraction)
                self.artifacts.write_json(
                    f"artifacts/literature/papers/{metadata.paper_id}/extraction.json",
                    extraction.model_dump(mode="json"),
                )
                self._write_provenance(literature, metadata.paper_id)
            except Exception as exc:
                self._failure(
                    literature,
                    "extract",
                    self.extractor.name,
                    content.paper_id,
                    exc,
                )
        return extracted

    async def deduplicate(
        self, literature: LiteratureState, candidates: list[PaperCandidate]
    ) -> dict[str, str]:
        matches: dict[str, str] = {}
        for candidate in candidates:
            existing = self.deduplicator.find_existing(candidate, literature)
            if existing:
                self._link_duplicate(literature, candidate, existing)
                matches[candidate.id] = existing
        return matches

    async def build_literature_map(self, literature: LiteratureState) -> str:
        clusters: Counter[str] = Counter()
        for extraction in literature.extractions:
            metadata = self._metadata(literature, extraction.paper_id)
            fallback = (
                f"publication:{metadata.publication_status}"
                if metadata
                else "publication:unknown"
            )
            labels = [
                *(f"model:{item}" for item in extraction.models),
                *(f"dataset:{item}" for item in extraction.datasets),
            ] or [fallback]
            for label in set(labels):
                clusters[label] += 1
        literature.clusters = sorted(clusters)
        lines = ["# Literature Map", ""]
        if not clusters:
            lines.append("Literature coverage is currently insufficient.")
        else:
            lines.extend(f"- {name}: {count} paper(s)" for name, count in sorted(clusters.items()))
        path = self.artifacts.write_text(
            "artifacts/literature/reports/literature_map.md", "\n".join(lines) + "\n"
        )
        literature.literature_map_artifact = path
        literature.matrix_artifact = self.artifacts.write_json(
            "artifacts/literature/reports/paper_matrix.json",
            {
                "papers": [paper.model_dump(mode="json") for paper in literature.paper_metadata],
                "extractions": [
                    extraction.model_dump(mode="json")
                    for extraction in literature.extractions
                ],
                "clusters": dict(clusters),
            },
        )
        return path

    def build_coverage_report(
        self, literature: LiteratureState, *, unresolved_questions: list[str]
    ) -> LiteratureCoverageReport:
        years = Counter(
            paper.year
            for paper in literature.paper_metadata
            if paper.metadata_verified and paper.year is not None
        )
        content_ids = self._content_verified_ids(literature)
        failure_blindspots = sorted(
            {f"{failure.stage}:{failure.provider}" for failure in literature.failures}
        )
        inaccessible = sum(
            1
            for paper in literature.paper_metadata
            if paper.metadata_verified and paper.paper_id not in content_ids
        )
        blindspots = [
            "Configured providers may not index all venues or non-English work.",
            "Citation neighborhoods are incomplete when providers lack expansion APIs.",
        ]
        if inaccessible:
            blindspots.append(f"{inaccessible} verified paper(s) lack accessible parsed content.")
        blindspots.extend(failure_blindspots)
        cluster_coverage = {
            cluster: sum(
                1
                for extraction in literature.extractions
                if cluster
                in {
                    *(f"model:{item}" for item in extraction.models),
                    *(f"dataset:{item}" for item in extraction.datasets),
                    f"publication:{(self._metadata(literature, extraction.paper_id) or PaperMetadata(paper_id='unknown', title='unknown')).publication_status}",
                }
            )
            for cluster in literature.clusters
        }
        sufficient = (
            len(content_ids) >= self.settings.minimum_content_verified_for_gap
            and len(literature.statements) >= self.settings.minimum_content_verified_for_gap
            and not unresolved_questions
        )
        return LiteratureCoverageReport(
            query_count=len(literature.search_queries),
            candidate_count=len(literature.candidates),
            metadata_verified_count=len(self._verified_ids(literature)),
            content_verified_count=len(content_ids),
            duplicate_count=max(
                0,
                len(literature.candidate_paper_links)
                - len(literature.paper_metadata),
            ),
            rejected_count=sum(
                candidate.status == "rejected" for candidate in literature.candidates
            ),
            publication_year_distribution=dict(sorted(years.items())),
            cluster_coverage=cluster_coverage,
            unresolved_search_questions=unresolved_questions,
            known_search_blindspots=blindspots,
            sufficient_for_gap_synthesis=sufficient,
        )

    def should_stop_search(self, literature: LiteratureState) -> bool:
        count = self.settings.low_information_gain_rounds
        recent = literature.search_round_metrics[-count:]
        return len(recent) == count and all(
            item.marginal_information_gain
            <= self.settings.low_information_gain_threshold
            and not item.novelty_landscape_changed
            for item in recent
        )

    async def verify_paper(
        self, literature: LiteratureState, paper_or_candidate_id: str
    ) -> PaperMetadata | None:
        metadata = self._metadata(literature, paper_or_candidate_id)
        if metadata:
            await self.fetch_contents(literature, [metadata.paper_id])
            await self.extract_papers(literature, [metadata.paper_id])
            return metadata
        candidate = self._candidate(literature, paper_or_candidate_id)
        if candidate is None:
            raise KeyError(f"Unknown paper or candidate: {paper_or_candidate_id}")
        await self.verify_metadata(literature, [candidate])
        linked = literature.candidate_paper_links.get(candidate.id)
        if linked:
            await self.fetch_contents(literature, [linked])
            await self.extract_papers(literature, [linked])
            return self._metadata(literature, linked)
        return None

    async def _search_provider(
        self,
        literature: LiteratureState,
        provider: LiteratureProvider,
        query: LiteratureSearchQuery,
    ) -> list[PaperCandidate]:
        key_input = query.model_dump(mode="json", exclude={"id"})
        key = self.cache.stable_key("search", provider.name, key_input)
        cached = self.cache.get(
            "search", key, max_age_seconds=self.settings.search_cache_ttl_seconds
        )
        if cached is not None:
            try:
                return [PaperCandidate.model_validate(item) for item in cached]
            except ValidationError:
                pass
        try:
            raw = await asyncio.wait_for(
                provider.search(query), timeout=self.settings.provider_timeout_seconds
            )
            candidates: list[PaperCandidate] = []
            for item in raw[: self.settings.max_candidates_per_query]:
                candidate = PaperCandidate.model_validate(item)
                if candidate.source_provider != provider.name:
                    raise ValueError("Candidate source_provider does not match adapter")
                candidates.append(candidate)
            self.cache.set(
                "search",
                key,
                [candidate.model_dump(mode="json") for candidate in candidates],
            )
            return candidates
        except Exception as exc:
            self._failure(literature, "search", provider.name, query.id, exc)
            return []

    async def _resolve_provider(
        self,
        literature: LiteratureState,
        provider: LiteratureProvider,
        candidate: PaperCandidate,
    ) -> PaperMetadata | None:
        key_input = {
            "title": normalize_title(candidate.raw_title),
            "authors": sorted(author.casefold() for author in candidate.raw_authors),
            "year": candidate.raw_year,
            "identifiers": candidate.identifiers.model_dump(mode="json"),
        }
        key = self.cache.stable_key("resolve", provider.name, key_input)
        cached = self.cache.get("resolve", key)
        if cached is not None or self.cache.contains("resolve", key):
            try:
                return PaperMetadata.model_validate(cached) if cached else None
            except ValidationError:
                pass
        try:
            metadata = await asyncio.wait_for(
                provider.resolve(candidate), timeout=self.settings.provider_timeout_seconds
            )
            if metadata is not None:
                metadata = PaperMetadata.model_validate(metadata)
            self.cache.set(
                "resolve",
                key,
                metadata.model_dump(mode="json") if metadata else None,
            )
            return metadata
        except Exception as exc:
            self._failure(literature, "resolve", provider.name, candidate.id, exc)
            return None

    async def _fetch_provider(
        self,
        literature: LiteratureState,
        provider: LiteratureProvider,
        paper: PaperMetadata,
    ) -> PaperContent | None:
        key_input = {
            "paper_id": paper.paper_id,
            "identifiers": paper.identifiers.model_dump(mode="json"),
            "source_records": paper.source_records,
        }
        key = self.cache.stable_key("fetch", provider.name, key_input)
        cached = self.cache.get("fetch", key)
        if cached is not None or self.cache.contains("fetch", key):
            try:
                if cached is None:
                    return None
                raw_text = cached.pop("raw_text", None)
                return PaperContent.model_validate({**cached, "raw_text": raw_text})
            except (ValidationError, AttributeError):
                pass
        try:
            content = await asyncio.wait_for(
                provider.fetch_content(paper),
                timeout=self.settings.provider_timeout_seconds,
            )
            if content is not None:
                content = PaperContent.model_validate(content)
                value = content.model_dump(mode="json")
                value["raw_text"] = content.raw_text
                self.cache.set("fetch", key, value)
            else:
                self.cache.set("fetch", key, None)
            return content
        except Exception as exc:
            self._failure(literature, "fetch", provider.name, paper.paper_id, exc)
            return None

    async def _extract_with_cache(
        self,
        metadata: PaperMetadata,
        content: PaperContent,
        text: str,
        prompt_hash: str,
    ) -> PaperExtractionDraft:
        key = self.cache.stable_key(
            "extract",
            self.extractor.name,
            {
                "paper_id": metadata.paper_id,
                "content_sha256": content.sha256,
                "model": self.extractor.model,
                "prompt_hash": prompt_hash,
            },
        )
        cached = self.cache.get("extract", key)
        if cached is not None:
            try:
                return PaperExtractionDraft.model_validate(cached)
            except ValidationError:
                pass
        draft = await self.extractor.extract(
            metadata=metadata, content=content, text=text
        )
        draft = PaperExtractionDraft.model_validate(draft)
        self.cache.set("extract", key, draft.model_dump(mode="json"))
        return draft

    def _statements_and_provenance(
        self,
        metadata: PaperMetadata,
        content: PaperContent,
        draft: PaperExtractionDraft,
    ) -> tuple[list[ExtractedStatement], list[ProvenanceRecord]]:
        values: list[tuple[str, str]] = []
        scalar_fields = (
            ("problem", "problem"),
            ("main_claim", "claim"),
            ("method_summary", "method"),
        )
        list_fields = (
            ("core_assumptions", "assumption"),
            ("main_results", "result"),
            ("limitations_claimed", "limitation_claimed"),
            ("limitations_inferred", "limitation_inferred"),
            ("failure_modes", "failure_mode"),
        )
        for field, statement_type in scalar_fields:
            value = getattr(draft, field)
            if value:
                values.append((statement_type, value))
        for field, statement_type in list_fields:
            values.extend((statement_type, value) for value in getattr(draft, field) if value)
        statements: list[ExtractedStatement] = []
        provenance_records: list[ProvenanceRecord] = []
        source_type = (
            "paper_abstract"
            if content.content_type == "abstract_only"
            else "paper_full_text"
        )
        for statement_type, statement_text in values:
            statement_id = stable_id(
                "STATEMENT", metadata.paper_id, statement_type, statement_text
            )
            provenance_id = stable_id("PROV", statement_id, content.sha256)
            provenance = ProvenanceRecord(
                id=provenance_id,
                entity_type="extracted_statement",
                entity_id=statement_id,
                source_type=source_type,
                source_id=metadata.paper_id,
                artifact_path=content.artifact_path,
                extraction_method=self.extractor.name,
                source_locator=(
                    SourceLocator(section_title="Abstract")
                    if content.content_type == "abstract_only"
                    else None
                ),
                retrieved_at=content.fetched_at,
                confidence=draft.extraction_confidence,
                notes=(
                    "Agent inference; not an author-stated limitation."
                    if statement_type == "limitation_inferred"
                    else None
                ),
            )
            provenance_records.append(provenance)
            statements.append(
                ExtractedStatement(
                    id=statement_id,
                    paper_id=metadata.paper_id,
                    statement_type=statement_type,
                    statement=statement_text,
                    provenance_ids=[provenance_id],
                    confidence=draft.extraction_confidence,
                    epistemic_type=(
                        StatementEpistemicType.DIRECT_RESULT
                        if statement_type == "result"
                        else StatementEpistemicType.AGENT_INFERRED
                        if statement_type == "limitation_inferred"
                        else StatementEpistemicType.AUTHOR_STATED
                    ),
                )
            )
        return statements, provenance_records

    def _record_novelty_search(
        self,
        literature: LiteratureState,
        novelty: NoveltySearchInput,
        queries: list[LiteratureSearchQuery],
        candidates: list[PaperCandidate],
    ) -> None:
        scoped_ids = {
            literature.candidate_paper_links[candidate.id]
            for candidate in candidates
            if candidate.id in literature.candidate_paper_links
        }
        verified = [
            paper
            for paper in literature.paper_metadata
            if paper.paper_id in scoped_ids
            and paper.metadata_verified
            and not paper.synthetic_test_data
        ]
        target = normalize_title(f"{novelty.proposed_method} {novelty.task}")
        ranked = sorted(
            verified,
            key=lambda paper: SequenceMatcher(
                None, target, normalize_title(paper.title)
            ).ratio(),
            reverse=True,
        )
        closest = [paper.paper_id for paper in ranked[:5]]
        bounded = (
            f"Closest prior works identified within the searched corpus: {', '.join(closest)}."
            if closest
            else (
                "We did not identify prior work matching "
                f"{novelty.proposed_method} within the searched corpus."
            )
        )
        record = NoveltySearchRecord(
            id=stable_id(
                "NOVELTY", novelty.proposed_method, *(query.id for query in queries)
            ),
            **novelty.model_dump(),
            query_ids=[query.id for query in queries],
            searched_providers=list(self.providers),
            candidate_count=len(candidates),
            verified_paper_count=len(verified),
            closest_prior_work_ids=closest,
            bounded_conclusion=bounded,
        )
        literature.novelty_searches.append(record)
        self.artifacts.write_json(
            f"artifacts/literature/reports/{record.id}.json",
            record.model_dump(mode="json"),
        )

    def _link_duplicate(
        self, literature: LiteratureState, candidate: PaperCandidate, paper_id: str
    ) -> None:
        literature.candidate_paper_links[candidate.id] = paper_id
        content_ids = self._content_verified_ids(literature)
        candidate.status = (
            "content_verified" if paper_id in content_ids else "metadata_verified"
        )
        self._write_candidate(candidate)

    def _sync_legacy_reference(
        self, literature: LiteratureState, metadata: PaperMetadata
    ) -> None:
        if any(paper.id == metadata.paper_id for paper in literature.papers):
            return
        literature.papers.append(
            PaperReference(
                id=metadata.paper_id,
                title=metadata.title,
                authors=metadata.authors,
                year=metadata.year,
                venue=metadata.venue,
                url=metadata.identifiers.canonical_url,
                identifier=metadata.identifiers.doi or metadata.identifiers.arxiv_id,
                verified=metadata.metadata_verified,
                main_claim=metadata.abstract or "",
                open_source=bool(metadata.identifiers.canonical_url),
                provenance=metadata.source_records[0] if metadata.source_records else "unknown",
                synthetic_test_data=metadata.synthetic_test_data,
            )
        )

    def _failure(
        self,
        literature: LiteratureState,
        stage: Literal["search", "resolve", "fetch", "extract", "parse"],
        provider: str,
        entity_id: str | None,
        error: Exception,
    ) -> None:
        literature.failures.append(
            LiteratureFailure(
                stage=stage,
                provider=provider,
                entity_id=entity_id,
                error_type=type(error).__name__,
                message=str(error)[:1000],
                retryable=(
                    isinstance(error, (TimeoutError, LiteratureProviderError))
                    and getattr(error, "retryable", isinstance(error, TimeoutError))
                ),
            )
        )

    def _write_candidate(self, candidate: PaperCandidate) -> None:
        self.artifacts.write_json(
            f"artifacts/literature/candidates/{candidate.id}.json",
            candidate.model_dump(mode="json"),
        )

    def _write_provenance(
        self, literature: LiteratureState, paper_id: str
    ) -> None:
        self.artifacts.write_json(
            f"artifacts/literature/papers/{paper_id}/provenance.json",
            [
                item.model_dump(mode="json")
                for item in literature.provenance_records
                if item.source_id == paper_id
                or (item.entity_type == "paper_metadata" and item.entity_id == paper_id)
            ],
        )

    @staticmethod
    def _upsert_query(literature: LiteratureState, query: LiteratureSearchQuery) -> None:
        if all(existing.id != query.id for existing in literature.search_queries):
            literature.search_queries.append(query)
        if query.query not in literature.queries:
            literature.queries.append(query.query)

    @staticmethod
    def _upsert_provenance(
        literature: LiteratureState, provenance: ProvenanceRecord
    ) -> None:
        if all(existing.id != provenance.id for existing in literature.provenance_records):
            literature.provenance_records.append(provenance)

    @staticmethod
    def _candidate(
        literature: LiteratureState, candidate_id: str
    ) -> PaperCandidate | None:
        return next(
            (item for item in literature.candidates if item.id == candidate_id), None
        )

    @staticmethod
    def _metadata(
        literature: LiteratureState, paper_id: str
    ) -> PaperMetadata | None:
        return next(
            (item for item in literature.paper_metadata if item.paper_id == paper_id),
            None,
        )

    def _provider_for_paper(
        self, literature: LiteratureState, paper_id: str
    ) -> LiteratureProvider | None:
        candidate_id = next(
            (
                candidate_id
                for candidate_id, linked_id in literature.candidate_paper_links.items()
                if linked_id == paper_id
            ),
            None,
        )
        candidate = self._candidate(literature, candidate_id) if candidate_id else None
        return self.providers.get(candidate.source_provider) if candidate else None

    @staticmethod
    def _verified_ids(literature: LiteratureState) -> set[str]:
        return {
            paper.paper_id
            for paper in literature.paper_metadata
            if paper.metadata_verified and not paper.synthetic_test_data
        }

    @staticmethod
    def _content_verified_ids(literature: LiteratureState) -> set[str]:
        return {
            content.paper_id
            for content in literature.contents
            if content.content_verified and not content.synthetic_test_data
        }
