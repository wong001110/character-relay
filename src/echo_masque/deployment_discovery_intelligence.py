"""Server-scoped Discovery seed construction and cheap-first candidate ranking."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from echo_masque.config import Settings
from echo_masque.discovery_contracts import DiscoveryCandidate
from echo_masque.persistence.character_learned_state_event_models import (
    CharacterLearnedStateEventRecord,
)
from echo_masque.persistence.conversation_topic_models import ConversationTopicRecord
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.discovery_models import DeploymentDiscoveryExposureRecord
from echo_masque.persistence.discovery_repository import DiscoveryRepository
from echo_masque.persistence.repository import Repository
from echo_masque.persistence.semantic_vector_repository import SemanticVectorRepository
from echo_masque.persistence.smart_participation_repository import decode_strings
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


class DeploymentDiscoverySeedBuilder:
    """Build seeds from one Deployment's server evidence without using global Learned aggregates."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.cards = Repository(database)

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @staticmethod
    def _decode_keywords(raw: str) -> tuple[str, ...]:
        try:
            decoded = json.loads(raw or "[]")
        except (json.JSONDecodeError, TypeError):
            return ()
        if not isinstance(decoded, list):
            return ()
        return tuple(
            dict.fromkeys(
                " ".join(str(item).split())
                for item in decoded
                if " ".join(str(item).split())
            )
        )[:12]

    @staticmethod
    def _clean_subject(value: str) -> str:
        normalized = " ".join(value.split())
        for prefix in ("concept:", "media:", "event:"):
            if normalized.startswith(prefix):
                return normalized.removeprefix(prefix).replace("_", " ")
        return normalized.replace("_", " ")

    def build(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        now: datetime | None = None,
        limit: int = 8,
    ) -> DeploymentDiscoverySeeds | None:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        bounded = max(1, min(limit, 12))
        with self.database.session() as session:
            deployment = session.get(CharacterDeploymentRecord, deployment_id)
            if deployment is None or deployment.owner_id != owner_id:
                return None
            topics = list(
                session.scalars(
                    select(ConversationTopicRecord)
                    .where(
                        ConversationTopicRecord.owner_id == owner_id,
                        ConversationTopicRecord.platform == "discord",
                        ConversationTopicRecord.connection_id == deployment.connection_id,
                        ConversationTopicRecord.guild_id == deployment.workspace_id,
                        ConversationTopicRecord.status.in_(("active", "cooling")),
                    )
                    .order_by(ConversationTopicRecord.last_active_at.desc())
                    .limit(12)
                )
            )
            events = list(
                session.scalars(
                    select(CharacterLearnedStateEventRecord)
                    .where(
                        CharacterLearnedStateEventRecord.owner_id == owner_id,
                        CharacterLearnedStateEventRecord.character_card_id
                        == deployment.character_card_id,
                        CharacterLearnedStateEventRecord.state_type == "interest",
                        CharacterLearnedStateEventRecord.connection_id == deployment.connection_id,
                        CharacterLearnedStateEventRecord.guild_id == deployment.workspace_id,
                        CharacterLearnedStateEventRecord.recorded_at
                        >= current - timedelta(days=120),
                    )
                    .order_by(CharacterLearnedStateEventRecord.recorded_at.desc())
                    .limit(160)
                )
            )

        topic_by_id = {topic.id: topic for topic in topics}
        seeds: list[DiscoverySeed] = []

        # Recent active/cooling server Topics are the strongest immediate curiosity source.
        for index, topic in enumerate(topics[:8]):
            age_days = max(
                0.0,
                (current - self._aware(topic.last_active_at)).total_seconds() / 86400.0,
            )
            recency = math.pow(0.5, age_days / 7.0)
            label = " ".join(topic.topic_label.split())
            if label:
                seeds.append(
                    DiscoverySeed(
                        text=label,
                        weight=min(1.0, 0.75 + 0.2 * recency - index * 0.02),
                        source="topic",
                        evidence_ref=f"topic:{topic.id}",
                    )
                )
            for keyword in self._decode_keywords(topic.keywords_json)[:4]:
                seeds.append(
                    DiscoverySeed(
                        text=keyword,
                        weight=min(0.9, 0.55 + 0.2 * recency),
                        source="topic_keyword",
                        evidence_ref=f"topic:{topic.id}",
                    )
                )

        # Aggregate only this server's append-only interest evidence. Do not read the global
        # CharacterLearnedStateRecord aggregate because one Character Card may live independently
        # in multiple Discord servers.
        interest_scores: dict[tuple[str, str], float] = {}
        for event in events:
            age_days = max(
                0.0,
                (current - self._aware(event.recorded_at)).total_seconds() / 86400.0,
            )
            decay = math.pow(0.5, age_days / 30.0)
            score = float(event.delta) * float(event.evidence_confidence) * decay
            interest_key = (event.subject_type, event.subject_key)
            interest_scores[interest_key] = interest_scores.get(interest_key, 0.0) + score

        for (subject_type, subject_key), score in sorted(
            interest_scores.items(),
            key=lambda item: item[1],
            reverse=True,
        ):
            if score <= 0.05:
                continue
            if subject_type == "topic" and subject_key.startswith("topic:"):
                matched_topic = topic_by_id.get(subject_key.removeprefix("topic:"))
                text = (
                    " ".join(matched_topic.topic_label.split())
                    if matched_topic is not None
                    else ""
                )
            elif subject_type in {"concept", "media", "event"}:
                text = self._clean_subject(subject_key)
            else:
                text = ""
            if not text:
                continue
            seeds.append(
                DiscoverySeed(
                    text=text,
                    weight=min(0.85, 0.45 + max(0.0, score)),
                    source="server_learned_interest",
                    evidence_ref=f"{subject_type}:{subject_key}",
                )
            )
            if len(seeds) >= bounded * 3:
                break

        # Character Card remains a reusable definition, but its existing tags/traits can provide
        # a weak cold-start prior without adding new cross-server lived state to the Card.
        card = self.cards.get_character_card(deployment.character_card_id, owner_id)
        if card is not None:
            for value in (*decode_strings(card.tags_json), *decode_strings(card.traits_json))[:8]:
                text = " ".join(value.split())
                if text:
                    seeds.append(
                        DiscoverySeed(
                            text=text,
                            weight=0.25,
                            source="character_definition_prior",
                            evidence_ref=f"character:{card.id}",
                        )
                    )

        deduped: dict[str, DiscoverySeed] = {}
        for seed in seeds:
            seed_key = seed.text.casefold()
            previous = deduped.get(seed_key)
            if previous is None or seed.weight > previous.weight:
                deduped[seed_key] = seed
        ranked = tuple(
            sorted(deduped.values(), key=lambda item: item.weight, reverse=True)[:bounded]
        )
        queries = tuple(seed.text for seed in ranked[:6])
        semantic_text = "\n".join(
            f"Interest ({seed.source}, weight={seed.weight:.2f}): {seed.text}"
            for seed in ranked
        )[:4000]
        return DeploymentDiscoverySeeds(
            deployment_id=deployment.id,
            owner_id=deployment.owner_id,
            character_card_id=deployment.character_card_id,
            connection_id=deployment.connection_id,
            guild_id=deployment.workspace_id,
            queries=queries,
            semantic_text=semantic_text,
            seeds=ranked,
        )


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
            # Semantic relevance is authoritative for normal ranking; secondary signals can move
            # near-ties but cannot turn a semantically unrelated item into the main feed.
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
                item
                for item in normal
                if item.discovery_item_id not in selected_ids
            )
        return tuple(selected[:bounded_limit])


__all__ = [
    "DeploymentDiscoverySeedBuilder",
    "DeploymentDiscoverySeeds",
    "DiscoveryCandidateRanker",
    "DiscoverySeed",
    "RankedDiscoveryCandidate",
]
