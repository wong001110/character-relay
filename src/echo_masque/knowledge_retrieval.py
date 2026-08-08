"""Deterministic sparse retrieval for Character Relay RAG V1."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from echo_masque.expression_retrieval import normalize_text, semantic_tokens


@dataclass(frozen=True, slots=True)
class KnowledgeResource:
    chunk_id: str
    knowledge_base_id: str
    document_id: str
    document_title: str
    chunk_index: int
    content: str


@dataclass(frozen=True, slots=True)
class KnowledgeCandidate:
    resource: KnowledgeResource
    score: float
    signals: dict[str, float]


def _cosine(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    dot = sum(value * right.get(key, 0) for key, value in left.items())
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def _overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / math.sqrt(len(left) * len(right))


def rank_knowledge_resources(
    resources: list[KnowledgeResource],
    *,
    query: str,
    top_k: int = 4,
    minimum_score: float = 0.05,
) -> list[KnowledgeCandidate]:
    """Rank already-authorized knowledge chunks without an LLM or vector database."""

    normalized_query = normalize_text(query)
    query_counter = Counter(semantic_tokens(query))
    query_tokens = set(query_counter)
    if not query_tokens:
        return []

    ranked: list[KnowledgeCandidate] = []
    for resource in resources:
        document = f"{resource.document_title} {resource.content}"
        document_counter = Counter(semantic_tokens(document))
        semantic = _cosine(query_counter, document_counter)
        overlap = _overlap(query_tokens, set(document_counter))
        normalized_document = normalize_text(document)
        exact = 0.0
        if normalized_query and normalized_query in normalized_document:
            exact = 1.0
        score = semantic * 0.72 + overlap * 0.18 + exact * 0.10
        score = round(score, 6)
        if score < minimum_score:
            continue
        ranked.append(
            KnowledgeCandidate(
                resource=resource,
                score=score,
                signals={
                    "semantic": round(semantic, 6),
                    "overlap": round(overlap, 6),
                    "exact": exact,
                },
            )
        )

    ranked.sort(
        key=lambda item: (
            -item.score,
            item.resource.document_title.casefold(),
            item.resource.chunk_index,
            item.resource.chunk_id,
        )
    )
    return ranked[: max(1, min(top_k, 8))]
