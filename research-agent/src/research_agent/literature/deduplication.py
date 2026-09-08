from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from research_agent.schemas.literature import (
    LiteratureState,
    PaperCandidate,
    PaperIdentifier,
    PaperMetadata,
    PaperRelation,
)


class PaperDeduplicator:
    def __init__(self, title_similarity_threshold: float = 0.94) -> None:
        self.title_similarity_threshold = title_similarity_threshold

    def find_existing(
        self, candidate: PaperCandidate, literature_state: LiteratureState
    ) -> str | None:
        for paper in literature_state.paper_metadata:
            if identifiers_match(candidate.identifiers, paper.identifiers):
                return paper.paper_id
        candidate_title = normalize_title(candidate.raw_title)
        for paper in literature_state.paper_metadata:
            paper_title = normalize_title(paper.title)
            if candidate_title and candidate_title == paper_title:
                return paper.paper_id
        for paper in literature_state.paper_metadata:
            ratio = SequenceMatcher(
                None, candidate_title, normalize_title(paper.title)
            ).ratio()
            if (
                ratio >= self.title_similarity_threshold
                and author_overlap(candidate.raw_authors, paper.authors) >= 0.5
                and years_compatible(candidate.raw_year, paper.year)
            ):
                return paper.paper_id
        return None

    def same_work_relation(
        self, source: PaperMetadata, target: PaperMetadata
    ) -> PaperRelation | None:
        if identifiers_match(source.identifiers, target.identifiers):
            confidence = 1.0
        else:
            similarity = SequenceMatcher(
                None, normalize_title(source.title), normalize_title(target.title)
            ).ratio()
            if (
                similarity < self.title_similarity_threshold
                or author_overlap(source.authors, target.authors) < 0.5
                or not years_compatible(source.year, target.year)
            ):
                return None
            confidence = min(0.99, similarity)
        return PaperRelation(
            source_paper_id=source.paper_id,
            target_paper_id=target.paper_id,
            relation="same_work_version",
            confidence=confidence,
        )


def identifiers_match(left: PaperIdentifier, right: PaperIdentifier) -> bool:
    pairs = (
        (normalize_doi(left.doi), normalize_doi(right.doi)),
        (normalize_arxiv(left.arxiv_id), normalize_arxiv(right.arxiv_id)),
        (normalize_stable(left.semantic_id), normalize_stable(right.semantic_id)),
        (normalize_stable(left.openalex_id), normalize_stable(right.openalex_id)),
    )
    return any(a and b and a == b for a, b in pairs)


def normalize_doi(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.strip().casefold()
    normalized = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", normalized)
    return normalized.rstrip("./")


def normalize_arxiv(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.strip().casefold()
    normalized = re.sub(r"^https?://arxiv\.org/(?:abs|pdf)/", "", normalized)
    normalized = normalized.removesuffix(".pdf")
    return re.sub(r"v\d+$", "", normalized)


def normalize_stable(value: str | None) -> str:
    return value.strip().casefold().rstrip("/") if value else ""


def normalize_title(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value).casefold()
    alphanumeric = re.sub(r"[^\w]+", " ", decomposed, flags=re.UNICODE)
    return " ".join(alphanumeric.split())


def author_overlap(left: list[str], right: list[str]) -> float:
    left_set = {_author_key(author) for author in left if _author_key(author)}
    right_set = {_author_key(author) for author in right if _author_key(author)}
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / min(len(left_set), len(right_set))


def _author_key(author: str) -> str:
    tokens = re.findall(r"\w+", unicodedata.normalize("NFKD", author).casefold())
    return tokens[-1] if tokens else ""


def years_compatible(left: int | None, right: int | None) -> bool:
    return left is None or right is None or abs(left - right) <= 2

