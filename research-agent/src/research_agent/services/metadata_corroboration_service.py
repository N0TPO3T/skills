from __future__ import annotations

import re
from difflib import SequenceMatcher

from research_agent.core.ids import stable_id
from research_agent.literature.deduplication import (
    identifiers_match,
    normalize_doi,
    normalize_title,
)
from research_agent.literature.providers.base import LiteratureProvider
from research_agent.schemas.literature import LiteratureFailure, PaperCandidate, PaperMetadata
from research_agent.schemas.literature_quality import (
    CanonicalPaperRecord,
    MetadataConflict,
    MetadataCorroboration,
    MetadataObservation,
    ProviderCapabilities,
    VersionDifference,
)
from research_agent.schemas.state import ResearchState
from research_agent.storage.artifact_store import ArtifactStore


class MetadataCorroborationService:
    def __init__(
        self, *, providers: list[LiteratureProvider], artifacts: ArtifactStore
    ) -> None:
        self.providers = providers
        self.artifacts = artifacts

    async def corroborate(
        self, state: ResearchState, paper_id: str
    ) -> MetadataCorroboration:
        paper = next(
            (
                item
                for item in state.literature.paper_metadata
                if item.paper_id == paper_id
            ),
            None,
        )
        if paper is None:
            raise KeyError(f"Unknown paper: {paper_id}")
        observations = [self._observation("state", paper)]
        for provider in self.providers:
            capabilities = getattr(provider, "capabilities", ProviderCapabilities())
            if not capabilities.metadata_lookup:
                continue
            candidate = PaperCandidate(
                id=stable_id("CAND-CORROBORATE", provider.name, paper_id),
                query_id="CORROBORATION",
                raw_title=paper.title,
                raw_authors=paper.authors,
                raw_year=paper.year,
                source_provider=provider.name,
                source_url=paper.identifiers.canonical_url,
                identifiers=paper.identifiers,
            )
            try:
                observed = await provider.resolve(candidate)
            except Exception as exc:
                state.literature.failures.append(
                    LiteratureFailure(
                        stage="corroborate",
                        provider=provider.name,
                        entity_id=paper_id,
                        error_type=type(exc).__name__,
                        message=str(exc)[:1000],
                        retryable=False,
                    )
                )
                continue
            if observed is not None and observed.metadata_verified:
                observations.append(self._observation(provider.name, observed))
        conflicts = self._conflicts(observations, paper)
        corroborating_count = sum(
            observation.provider != "state"
            and self._agrees_with_canonical(observation, paper)
            for observation in observations
        )
        penalty = sum(
            0.2
            if conflict.severity == "high" and not conflict.resolved
            else 0.1
            if conflict.severity == "medium" and not conflict.resolved
            else 0.02
            if conflict.severity == "low"
            else 0.0
            for conflict in conflicts
        )
        corroboration = MetadataCorroboration(
            paper_id=paper.paper_id,
            observations=observations,
            canonical_title=paper.title,
            canonical_authors=paper.authors,
            identifiers=paper.identifiers,
            conflicts=conflicts,
            corroborating_provider_count=corroborating_count,
            confidence=max(
                0.0,
                min(
                    1.0,
                    paper.verification_confidence
                    + 0.04 * corroborating_count
                    - penalty,
                ),
            ),
        )
        self._upsert(
            state.literature_quality.corroborations, corroboration, "paper_id"
        )
        record = CanonicalPaperRecord(
            paper_id=paper.paper_id,
            metadata=paper,
            corroboration=corroboration,
            work_family_id=self._work_family_id(state, paper),
            canonical_version=False,
            confidence=corroboration.confidence,
        )
        self._upsert(
            state.literature_quality.canonical_records, record, "paper_id"
        )
        self._refresh_canonical_versions(state)
        self._record_version_differences(state, record.work_family_id)
        self.artifacts.write_json(
            f"artifacts/literature/papers/{paper.paper_id}/corroboration.json",
            corroboration.model_dump(mode="json"),
        )
        return corroboration

    @staticmethod
    def _observation(provider: str, paper: PaperMetadata) -> MetadataObservation:
        return MetadataObservation(
            provider=provider,
            title=paper.title,
            authors=paper.authors,
            year=paper.year,
            venue=paper.venue,
            doi=paper.identifiers.doi,
            arxiv_id=paper.identifiers.arxiv_id,
            publication_date=paper.publication_date,
        )

    def _conflicts(
        self, observations: list[MetadataObservation], canonical: PaperMetadata
    ) -> list[MetadataConflict]:
        conflicts: list[MetadataConflict] = []
        values_by_field = {
            "title": {item.provider: item.title for item in observations if item.title},
            "authors": {
                item.provider: item.authors for item in observations if item.authors
            },
            "year": {item.provider: item.year for item in observations if item.year},
            "venue": {item.provider: item.venue for item in observations if item.venue},
            "doi": {item.provider: item.doi for item in observations if item.doi},
            "arxiv_id": {
                item.provider: item.arxiv_id
                for item in observations
                if item.arxiv_id
            },
        }
        for field, values in values_by_field.items():
            normalized = {self._normalize_field(field, value) for value in values.values()}
            if len(normalized) <= 1:
                raw_values = {str(value) for value in values.values()}
                if len(raw_values) > 1 and field in {"title", "authors"}:
                    conflicts.append(
                        MetadataConflict(
                            field=field,
                            values=values,
                            severity="low",
                            resolution="Formatting-only difference; canonical value preserved.",
                            resolved=True,
                        )
                    )
                continue
            severity = "high" if field in {"doi", "arxiv_id"} else "medium"
            resolved = False
            resolution = None
            if field == "title" and canonical.identifiers.doi:
                dois = {
                    normalize_doi(item.doi) for item in observations if item.doi
                }
                if len(dois) == 1:
                    severity = "medium"
                    resolved = True
                    resolution = (
                        "Shared DOI preserves identity; title conflict remains recorded."
                    )
            conflicts.append(
                MetadataConflict(
                    field=field,
                    values=values,
                    severity=severity,
                    resolution=resolution,
                    resolved=resolved,
                )
            )
        return conflicts

    @staticmethod
    def _normalize_field(field: str, value: object) -> object:
        if field == "title":
            return normalize_title(str(value))
        if field == "doi":
            return normalize_doi(str(value))
        if field == "authors" and isinstance(value, list):
            return tuple(
                re.findall(r"\w+", author.casefold())[-1]
                for author in value
                if re.findall(r"\w+", author.casefold())
            )
        return str(value).casefold().strip()

    @staticmethod
    def _agrees_with_canonical(
        observation: MetadataObservation, canonical: PaperMetadata
    ) -> bool:
        if canonical.identifiers.doi and observation.doi:
            return normalize_doi(canonical.identifiers.doi) == normalize_doi(
                observation.doi
            )
        return (
            SequenceMatcher(
                None,
                normalize_title(canonical.title),
                normalize_title(observation.title or ""),
            ).ratio()
            >= 0.94
        )

    @staticmethod
    def _upsert(items: list, value: object, key: str) -> None:
        expected = getattr(value, key)
        for index, item in enumerate(items):
            if getattr(item, key) == expected:
                items[index] = value
                return
        items.append(value)

    def _work_family_id(self, state: ResearchState, paper: PaperMetadata) -> str:
        for record in state.literature_quality.canonical_records:
            if record.paper_id == paper.paper_id:
                continue
            if identifiers_match(record.metadata.identifiers, paper.identifiers):
                return record.work_family_id or stable_id("WORK", record.paper_id)
            related = any(
                relation.relation == "same_work_version"
                and {relation.source_paper_id, relation.target_paper_id}
                == {record.paper_id, paper.paper_id}
                for relation in state.literature.relations
            )
            if related:
                return record.work_family_id or stable_id("WORK", record.paper_id)
        identity = (
            normalize_doi(paper.identifiers.doi)
            or paper.identifiers.arxiv_id
            or f"{normalize_title(paper.title)}:{paper.authors[0] if paper.authors else ''}"
        )
        return stable_id("WORK", identity)

    @staticmethod
    def _refresh_canonical_versions(state: ResearchState) -> None:
        rank = {"journal": 4, "conference": 3, "workshop": 2, "preprint": 1, "unknown": 0}
        families = {
            record.work_family_id
            for record in state.literature_quality.canonical_records
            if record.work_family_id
        }
        for family in families:
            members = [
                record
                for record in state.literature_quality.canonical_records
                if record.work_family_id == family
            ]
            chosen = max(
                members,
                key=lambda item: (
                    rank[item.metadata.publication_status],
                    item.metadata.publication_date.toordinal()
                    if item.metadata.publication_date
                    else (item.metadata.year or 0) * 366,
                ),
            )
            for member in members:
                member.canonical_version = member.paper_id == chosen.paper_id

    @staticmethod
    def _record_version_differences(
        state: ResearchState, work_family_id: str | None
    ) -> None:
        if not work_family_id:
            return
        members = [
            record
            for record in state.literature_quality.canonical_records
            if record.work_family_id == work_family_id
        ]
        for field in ("title", "year", "venue"):
            values = {
                record.paper_id: str(getattr(record.metadata, field))
                for record in members
                if getattr(record.metadata, field) is not None
            }
            if len(set(values.values())) <= 1:
                continue
            difference = VersionDifference(
                work_family_id=work_family_id,
                field=field,
                source_versions=values,
                scientifically_material=False,
            )
            if all(
                not (
                    item.work_family_id == difference.work_family_id
                    and item.field == difference.field
                )
                for item in state.literature_quality.version_differences
            ):
                state.literature_quality.version_differences.append(difference)
