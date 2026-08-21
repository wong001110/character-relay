"""Shared Discovery seed contracts and cheap-first candidate ranking."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select

from echo_masque.config import Settings
from echo_masque.discovery_contracts import DiscoveryCandidate
from echo_masque.persistence.database import Database
from echo_masque.persistence.discovery_models import DeploymentDiscoveryExposureRecord
from echo_masque.persistence.discovery_repository import DiscoveryRepository
from echo_masque.persistence.semantic_vector_repository import SemanticVectorRepository
from echo_masque.semantic_participation import (
    FastEmbedSemanticEncoder,
    SemanticEmbeddingUnavailable,
    SemanticEncoder,
    _cosine,
)

_DISCOVERY_VECTOR_NAMESPACE = "discovery_item_v1"


@dataclass(frozen=True, slots=True)
class DiscoverySeed:
    text: str
    weight: float
    source: str
    evidence_ref: str


@dataclass(frozen=True, slots=True)
class DeploymentDiscoverySeeds:
    deployment_id: str
    owner_id: str
    character_card_id: str
    connection_id: str
    guild_id: str
    queries: tuple[str, ...]
    semantic_text: str
    seeds: tuple[DiscoverySeed, ...]


@dataclass(frozen=True, slots=True)
class RankedDiscoveryCandidate:
    discovery_item_id: str
    candidate: DiscoveryCandidate
    semantic_relevance: float
    sparse_relevance: float
    freshness: float
    novelty: float
    exploration: float
    final_score: float
    reason: str


class DiscoveryCandidateRanker:
    """Rank external candidates with shared E5 + cheap deterministic secondary signals."""

    def __init__(
        self,
        database: Database,
        settings: Settings,
        *,
        encoder: SemanticEncoder | None = None,
    ) -> None:
        self.database = database
        self.settings = settings
        self.items = DiscoveryRepository(database)
        self.vectors = SemanticVectorRepository(database)
        self.encoder = encoder
        if self.encoder is None and settings.semantic_embedding_runtime_enabled:
            self.encoder = FastEmbedSemanticEncoder(
                model_name=settings.semantic_embedding_model,
                model_file=settings.semantic_embedding_model_file,
                cache_dir=settings.semantic_embedding_cache_dir,
                dimension=settings.semantic_embedding_dimension,
            )

    @staticmethod
    def _candidate_text(candidate: DiscoveryCandidate) -> str:
        return "\n".join(
            part
            for part in (
                candidate.title.strip(),
                candidate.creator.strip(),
                candidate.description.strip()[:3000],
            )
            if part
        )[:4000]

    @staticmethod
    def _tokens(value: str) -> set[str]:
        normalized = " ".join(value.casefold().split())
        tokens = {part.strip(".,!?;:()[]{}\"'") for part in normalized.split()}
        return {token for token in tokens if len(token) >= 2}

    @classmethod
    def _sparse(cls, seeds: DeploymentDiscoverySeeds, candidate: DiscoveryCandidate) -> float:
        content = " ".join(
            (candidate.title, candidate.creator, candidate.description[:1500])
        ).casefold()
        if not content.strip() or not seeds.seeds:
            return 0.0
        best = 0.0
        content_tokens = cls._tokens(content)
        for seed in seeds.seeds:
            query = seed.text.casefold().strip()
            if not query:
                continue
            if query in content:
                best = max(best, min(1.0, 0.7 + seed.weight * 0.3))
                continue
            query_tokens = cls._tokens(query)
            if query_tokens and content_tokens:
                overlap = len(query_tokens & content_tokens) / len(query_tokens)
                best = max(best, overlap * seed.weight)
        return max(0.0, min(1.0, best))

    @staticmethod
    def _freshness(candidate: DiscoveryCandidate, now: datetime) -> float:
        if candidate.published_at is None:
            return 0.35
        published = candidate.published_at
        if published.tzinfo is None:
            published = published.replace(tzinfo=UTC)
        age_days = max(0.0, (now - published.astimezone(UTC)).total_seconds() / 86400.0)
        return max(0.05, min(1.0, math.pow(0.5, age_days / 14.0)))

    @staticmethod
    def _exploration(deployment_id: str, canonical_key: str, now: datetime) -> float:
        digest = hashlib.sha256(
            f"{deployment_id}|{canonical_key}|{now.date().isoformat()}".encode()
        ).digest()
        return int.from_bytes(digest[:4], "big") / float(2**32 - 1)

    def _semantic_vector(
        self,
        *,
        owner_id: str,
        item_id: str,
        text: str,
    ) -> list[float] | None:
        if self.encoder is None or not text:
            return None
        source_hash = self.vectors.source_hash(
            text,
            self.encoder.model_name,
            self.encoder.dimension,
        )
        cached = self.vectors.get(
            owner_id=owner_id,
            namespace=_DISCOVERY_VECTOR_NAMESPACE,
            resource_id=item_id,
            model_name=self.encoder.model_name,
            dimension=self.encoder.dimension,
            source_hash=source_hash,
        )
        if cached is not None:
            return cached
        try:
            vector = self.encoder.embed_passage(text)
        except SemanticEmbeddingUnavailable:
            return None
        self.vectors.upsert(
            owner_id=owner_id,
            namespace=_DISCOVERY_VECTOR_NAMESPACE,
            resource_id=item_id,
            semantic_text=text,
            model_name=self.encoder.model_name,
            dimension=self.encoder.dimension,
            vector=vector,
        )
        return vector

    def rank(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        seeds: DeploymentDiscoverySeeds,
        candidates: Iterable[DiscoveryCandidate],
        limit: int = 10,
        now: datetime | None = None,
    ) -> tuple[RankedDiscoveryCandidate, ...]:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        bounded_limit = max(1, min(limit, 30))
        query_vector: list[float] | None = None
        if self.encoder is not None and seeds.semantic_text.strip():
            try:
                query_vector = self.encoder.embed_query(seeds.semantic_text)
            except SemanticEmbeddingUnavailable:
                query_vector = None

        unique_candidates = {
            candidate.canonical_key: candidate
            for candidate in candidates
            if candidate.canonical_key.strip()
        }
        stored: list[tuple[DiscoveryCandidate, str]] = []
        for candidate in unique_candidates.values():
            item = self.items.upsert_item(candidate)
            stored.append((candidate, item.id))
        item_ids = [item_id for _, item_id in stored]
        with self.database.session() as session:
            exposed_ids = (
                set(
                    session.scalars(
                        select(DeploymentDiscoveryExposureRecord.discovery_item_id).where(
                            DeploymentDiscoveryExposureRecord.deployment_id == deployment_id,
                            DeploymentDiscoveryExposureRecord.discovery_item_id.in_(item_ids),
                        )
                    )
                )
                if item_ids
                else set()
            )

        ranked: list[RankedDiscoveryCandidate] = []
        for candidate, item_id in stored:
            text = self._candidate_text(candidate)
            semantic = 0.0
            if query_vector is not None:
                candidate_vector = self._semantic_vector(
                    owner_id=owner_id,
                    item_id=item_id,
                    text=text,
                )
                if candidate_vector is not None:
                    semantic = max(0.0, _cosine(query_vector, candidate_vector))
            sparse = self._sparse(seeds, candidate)
            freshness = self._freshness(candidate, current)
            novelty = 0.15 if item_id in exposed_ids else 1.0
            exploration = self._exploration(deployment_id, candidate.canonical_key, current)
            score = (
                semantic * 0.68
                + sparse * 0.12
                + freshness * 0.10
                + novelty * 0.07
                + exploration * 0.03
            )
            if query_vector is None:
                score = (
                    sparse * 0.65
                    + freshness * 0.15
                    + novelty * 0.12
                    + exploration * 0.08
                )
            ranked.append(
                RankedDiscoveryCandidate(
                    discovery_item_id=item_id,
                    candidate=candidate,
                    semantic_relevance=round(semantic, 6),
                    sparse_relevance=round(sparse, 6),
                    freshness=round(freshness, 6),
                    novelty=round(novelty, 6),
                    exploration=round(exploration, 6),
                    final_score=round(max(0.0, min(1.0, score)), 6),
                    reason=(
                        "e5_ranked"
                        if query_vector is not None
                        else "sparse_fallback_embedding_unavailable"
                    ),
                )
            )

        normal = sorted(
            ranked,
            key=lambda item: (
                item.final_score,
                item.semantic_relevance,
                item.freshness,
            ),
            reverse=True,
        )
        if len(normal) <= bounded_limit:
            return tuple(normal)

        exploration_slots = max(1, round(bounded_limit * 0.2)) if bounded_limit >= 5 else 0
        primary_count = bounded_limit - exploration_slots
        selected = normal[:primary_count]
        selected_ids = {item.discovery_item_id for item in selected}
        exploration_pool = sorted(
            (
                item
                for item in normal[primary_count:]
                if item.discovery_item_id not in selected_ids and item.novelty >= 0.9
            ),
            key=lambda item: (item.exploration, item.freshness),
            reverse=True,
        )
        selected.extend(exploration_pool[:exploration_slots])
        if len(selected) < bounded_limit:
            selected_ids = {item.discovery_item_id for item in selected}
            selected.extend(
                item for item in normal if item.discovery_item_id not in selected_ids
            )
        return tuple(selected[:bounded_limit])


__all__ = [
    "DeploymentDiscoverySeeds",
    "DiscoveryCandidateRanker",
    "DiscoverySeed",
    "RankedDiscoveryCandidate",
]
