from __future__ import annotations

import re

from research_agent.schemas.literature_quality import VersionDifference
from research_agent.schemas.state import ResearchState


SCIENTIFIC_FIELDS = {
    "result_claims": "result",
    "claimed_limitations": "limitation_claimed",
}


class SourceVersionComparisonService:
    """Record text-level claim differences without pretending semantic adjudication."""

    def refresh(self, state: ResearchState) -> list[VersionDifference]:
        recorded: list[VersionDifference] = []
        families = {
            record.work_family_id
            for record in state.literature_quality.canonical_records
            if record.work_family_id
        }
        for family in families:
            paper_ids = {
                record.paper_id
                for record in state.literature_quality.canonical_records
                if record.work_family_id == family
            }
            if len(paper_ids) < 2:
                continue
            for field, statement_type in SCIENTIFIC_FIELDS.items():
                versions = {
                    paper_id: "\n".join(
                        sorted(
                            statement.statement
                            for statement in state.literature.statements
                            if statement.paper_id == paper_id
                            and statement.statement_type == statement_type
                        )
                    )
                    for paper_id in sorted(paper_ids)
                }
                versions = {key: value for key, value in versions.items() if value}
                if len(versions) < 2 or len({_normalize(value) for value in versions.values()}) <= 1:
                    continue
                difference = VersionDifference(
                    work_family_id=family,
                    field=field,
                    source_versions=versions,
                    scientifically_material=False,
                )
                self._upsert(state, difference)
                recorded.append(difference)
        return recorded

    @staticmethod
    def _upsert(state: ResearchState, difference: VersionDifference) -> None:
        for index, existing in enumerate(
            state.literature_quality.version_differences
        ):
            if (
                existing.work_family_id == difference.work_family_id
                and existing.field == difference.field
            ):
                state.literature_quality.version_differences[index] = difference
                return
        state.literature_quality.version_differences.append(difference)


def _normalize(value: str) -> str:
    return " ".join(re.findall(r"\w+", value.casefold()))

