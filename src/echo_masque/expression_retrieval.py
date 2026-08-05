"""Deterministic hybrid retrieval for Server Emoji and Sticker expressions.

The first release intentionally avoids a heavyweight vector database. It combines
metadata filtering, exact aliases, sparse semantic similarity, tags, confidence,
and recent-use penalties. The public contract is stable enough to replace the
sparse scorer with a dense embedding adapter later without changing Connector or
workflow state schemas.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

_WORD_PATTERN = re.compile(r"[a-z0-9_]+|[\u3400-\u9fff]+", re.IGNORECASE)
_CJK_PATTERN = re.compile(r"^[\u3400-\u9fff]+$")


@dataclass(frozen=True, slots=True)
class ExpressionResource:
    key: str
    resource_type: str
    resource_id: str
    name: str
    description: str
    semantic_intent: str
    semantic_emotion: str
    semantic_description: str
    aliases: tuple[str, ...]
    tags: tuple[str, ...]
    situations: tuple[str, ...]
    avoid_when: tuple[str, ...]
    allowed_actions: tuple[str, ...]
    animated: bool
    available: bool
    enabled: bool
    semantic_confidence: float
    asset_url: str
    format_type: str


@dataclass(frozen=True, slots=True)
class ExpressionCandidate:
    resource: ExpressionResource
    score: float
    signals: dict[str, float]


def normalize_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def semantic_tokens(value: str) -> list[str]:
    normalized = normalize_text(value)
    tokens: list[str] = []
    for match in _WORD_PATTERN.findall(normalized):
        tokens.append(match)
        if _CJK_PATTERN.match(match):
            tokens.extend(match)
            tokens.extend(match[index : index + 2] for index in range(len(match) - 1))
    return tokens


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


def _document(resource: ExpressionResource) -> str:
    return " ".join(
        (
            resource.name,
            resource.description,
            resource.semantic_intent,
            resource.semantic_emotion,
            resource.semantic_description,
            " ".join(resource.aliases),
            " ".join(resource.tags),
            " ".join(resource.situations),
        )
    )


def rank_expression_resources(
    resources: list[ExpressionResource],
    *,
    query: str,
    allowed_actions: set[str],
    recent_resource_keys: set[str] | None = None,
    excluded_resource_keys: set[str] | None = None,
    top_k: int = 6,
) -> list[ExpressionCandidate]:
    """Return a deterministic Top-K list without sending the full dictionary to an LLM."""

    recent = recent_resource_keys or set()
    excluded = excluded_resource_keys or set()
    query_normalized = normalize_text(query)
    query_counter = Counter(semantic_tokens(query))
    query_tokens = set(query_counter)
    ranked: list[ExpressionCandidate] = []

    for resource in resources:
        if not resource.enabled or not resource.available or resource.key in excluded:
            continue
        if not allowed_actions.intersection(resource.allowed_actions):
            continue

        document_counter = Counter(semantic_tokens(_document(resource)))
        semantic = _cosine(query_counter, document_counter)
        metadata_tokens = set(
            semantic_tokens(
                " ".join(
                    (
                        resource.semantic_intent,
                        resource.semantic_emotion,
                        " ".join(resource.tags),
                        " ".join(resource.situations),
                    )
                )
            )
        )
        metadata_overlap = _overlap(query_tokens, metadata_tokens)
        names = (resource.name, *resource.aliases)
        exact = 0.0
        for name in names:
            normalized_name = normalize_text(name)
            if normalized_name and (
                normalized_name in query_normalized or query_normalized in normalized_name
            ):
                exact = 1.0
                break

        confidence = min(1.0, max(0.0, resource.semantic_confidence))
        recent_penalty = 0.24 if resource.key in recent else 0.0
        score = (
            semantic * 0.55
            + metadata_overlap * 0.25
            + exact * 0.15
            + confidence * 0.05
            - recent_penalty
        )
        ranked.append(
            ExpressionCandidate(
                resource=resource,
                score=round(score, 6),
                signals={
                    "semantic": round(semantic, 6),
                    "metadata_overlap": round(metadata_overlap, 6),
                    "exact": exact,
                    "confidence": round(confidence, 6),
                    "recent_penalty": recent_penalty,
                },
            )
        )

    ranked.sort(
        key=lambda item: (
            -item.score,
            item.resource.resource_type,
            item.resource.name.casefold(),
            item.resource.resource_id,
        )
    )
    return ranked[: max(1, min(top_k, 10))]
