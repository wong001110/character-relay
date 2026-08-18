"""Perception-safe social association for Deployment Character Discovery."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from echo_masque.config import Settings
from echo_masque.discovery_contracts import DiscoveryDecision, DiscoveryMode
from echo_masque.persistence.character_learned_state_event_models import (
    CharacterLearnedStateEventRecord,
)
from echo_masque.persistence.conversation_episode_models import ConversationEpisodeRecord
from echo_masque.persistence.conversation_topic_models import ConversationTopicRecord
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.discovery_models import (
    DeploymentDiscoveryExposureRecord,
    DiscoveryItemRecord,
)
from echo_masque.persistence.discovery_repository import DiscoveryRepository
from echo_masque.persistence.discord_identity_repository import DiscordIdentityRepository
from echo_masque.persistence.episodic_sql_rag_repository import EpisodicSqlRagRepository
from echo_masque.persistence.semantic_vector_repository import SemanticVectorRepository
from echo_masque.semantic_participation import (
    FastEmbedSemanticEncoder,
    SemanticEmbeddingUnavailable,
    SemanticEncoder,
    _cosine,
)

_EPISODE_VECTOR_NAMESPACE = "discovery-association-episode-v1"


@dataclass(frozen=True, slots=True)
class DiscoveryTopicAssociation:
    topic_id: str
    label: str
    status: str
    channel_id: str
    thread_id: str
    score: float


@dataclass(frozen=True, slots=True)
class DiscoveryEpisodeAssociation:
    episode_id: str
    score: float
    expanded_episode_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DiscoveryRelationshipAssociation:
    subject_key: str
    label: str
    score: float


@dataclass(frozen=True, slots=True)
class DiscoverySocialAssociationResult:
    deployment_id: str
    discovery_item_id: str
    topic: DiscoveryTopicAssociation | None
    episode: DiscoveryEpisodeAssociation | None
    relationship: DiscoveryRelationshipAssociation | None
    would_share: bool
    motivation: str
    confidence: float


class DiscoverySocialAssociationService:
    """Link external content only to Topics/Episodes the Deployment's Character could know."""

    def __init__(
        self,
        database: Database,
        settings: Settings,
        *,
        encoder: SemanticEncoder | None = None,
    ) -> None:
        self.database = database
        self.settings = settings
        self.discovery = DiscoveryRepository(database)
        self.episodes = EpisodicSqlRagRepository(database)
        self.vectors = SemanticVectorRepository(database)
        self.identities = DiscordIdentityRepository(database)
        self.encoder = encoder
        if self.encoder is None and settings.semantic_embedding_runtime_enabled:
            self.encoder = FastEmbedSemanticEncoder(
                model_name=settings.semantic_embedding_model,
                model_file=settings.semantic_embedding_model_file,
                cache_dir=settings.semantic_embedding_cache_dir,
                dimension=settings.semantic_embedding_dimension,
            )

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @staticmethod
    def _tokens(value: str) -> set[str]:
        return {
            token.strip(".,!?;:()[]{}\"'")
            for token in " ".join(value.casefold().split()).split()
            if len(token.strip(".,!?;:()[]{}\"'")) >= 2
        }

    @classmethod
    def _sparse(cls, query: str, text: str) -> float:
        left = cls._tokens(query)
        right = cls._tokens(text)
        if not left or not right:
            return 0.0
        return len(left & right) / max(1, len(left | right))

    @staticmethod
    def _decode_strings(raw: str) -> tuple[str, ...]:
        try:
            value = json.loads(raw or "[]")
        except (json.JSONDecodeError, TypeError):
            return ()
        if not isinstance(value, list):
            return ()
        return tuple(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))

    @staticmethod
    def _episode_text(record: ConversationEpisodeRecord) -> str:
        return f"{record.summary}\n{record.key_points_json}"[:8000]

    def _vector(
        self,
        *,
        owner_id: str,
        record: ConversationEpisodeRecord,
        encoder: SemanticEncoder,
    ) -> list[float] | None:
        text = self._episode_text(record)
        source_hash = self.vectors.source_hash(text, encoder.model_name, encoder.dimension)
        cached = self.vectors.get(
            owner_id=owner_id,
            namespace=_EPISODE_VECTOR_NAMESPACE,
            resource_id=record.id,
            model_name=encoder.model_name,
            dimension=encoder.dimension,
            source_hash=source_hash,
        )
        if cached is not None:
            return cached
        try:
            vector = encoder.embed_passage(text)
        except SemanticEmbeddingUnavailable:
            return None
        self.vectors.upsert(
            owner_id=owner_id,
            namespace=_EPISODE_VECTOR_NAMESPACE,
            resource_id=record.id,
            semantic_text=text,
            model_name=encoder.model_name,
            dimension=encoder.dimension,
            vector=vector,
        )
        return vector

    def _best_episode(
        self,
        *,
        owner_id: str,
        deployment: CharacterDeploymentRecord,
        query: str,
    ) -> DiscoveryEpisodeAssociation | None:
        accessible = self.episodes.accessible_episodes(
            owner_id=owner_id,
            character_card_id=deployment.character_card_id,
            connection_id=deployment.connection_id,
            guild_id=deployment.workspace_id,
            limit=160,
        )
        if not accessible:
            return None
        query_vector: list[float] | None = None
        if self.encoder is not None:
            try:
                query_vector = self.encoder.embed_query(query)
            except SemanticEmbeddingUnavailable:
                query_vector = None
        scored: list[tuple[float, ConversationEpisodeRecord]] = []
        for record in accessible:
            score = self._sparse(query, self._episode_text(record))
            if query_vector is not None and self.encoder is not None:
                vector = self._vector(owner_id=owner_id, record=record, encoder=self.encoder)
                if vector is not None:
                    score = max(0.0, _cosine(query_vector, vector))
            if score >= 0.28:
                scored.append((score, record))
        if not scored:
            return None
        scored.sort(key=lambda item: item[0], reverse=True)
        seed_ids = tuple(record.id for _, record in scored[:2])
        expanded = self.episodes.expand_episode_ids(
            owner_id=owner_id,
            character_card_id=deployment.character_card_id,
            seed_episode_ids=seed_ids,
            connection_id=deployment.connection_id,
            guild_id=deployment.workspace_id,
            max_entity_degree=48,
            limit=12,
        )
        return DiscoveryEpisodeAssociation(
            episode_id=scored[0][1].id,
            score=round(max(0.0, min(scored[0][0], 1.0)), 6),
            expanded_episode_ids=expanded[:12],
        )

    def _topic_for_episode(
        self,
        *,
        owner_id: str,
        episode: ConversationEpisodeRecord,
        episode_score: float,
    ) -> DiscoveryTopicAssociation | None:
        if not episode.topic_id:
            return None
        with self.database.session() as session:
            topic = session.get(ConversationTopicRecord, episode.topic_id)
            if topic is None or topic.owner_id != owner_id:
                return None
        return DiscoveryTopicAssociation(
            topic_id=topic.id,
            label=topic.topic_label,
            status=topic.status,
            channel_id=episode.channel_id,
            thread_id=episode.thread_id,
            score=episode_score,
        )

    def _relationship_for_episode(
        self,
        *,
        owner_id: str,
        deployment: CharacterDeploymentRecord,
        episode: ConversationEpisodeRecord,
        now: datetime,
    ) -> DiscoveryRelationshipAssociation | None:
        participant_ids = self._decode_strings(episode.participant_refs_json)
        actor_keys = {f"actor:{value}" for value in participant_ids if value}
        if not actor_keys:
            return None
        with self.database.session() as session:
            events = list(
                session.scalars(
                    select(CharacterLearnedStateEventRecord)
                    .where(
                        CharacterLearnedStateEventRecord.owner_id == owner_id,
                        CharacterLearnedStateEventRecord.character_card_id
                        == deployment.character_card_id,
                        CharacterLearnedStateEventRecord.state_type == "relationship",
                        CharacterLearnedStateEventRecord.connection_id == deployment.connection_id,
                        CharacterLearnedStateEventRecord.guild_id == deployment.workspace_id,
                        CharacterLearnedStateEventRecord.subject_key.in_(actor_keys),
                        CharacterLearnedStateEventRecord.recorded_at
                        >= now - timedelta(days=180),
                    )
                    .order_by(CharacterLearnedStateEventRecord.recorded_at.desc())
                    .limit(240)
                )
            )
        totals: dict[str, float] = {}
        for event in events:
            age_days = max(
                0.0,
                (now - self._aware(event.recorded_at)).total_seconds() / 86400.0,
            )
            contribution = (
                float(event.delta)
                * float(event.evidence_confidence)
                * math.pow(0.5, age_days / 60.0)
            )
            totals[event.subject_key] = totals.get(event.subject_key, 0.0) + contribution
        if not totals:
            return None
        subject_key, raw_score = max(totals.items(), key=lambda item: item[1])
        score = max(0.0, min(raw_score, 1.0))
        if score < 0.12:
            return None
        user_id = subject_key.removeprefix("actor:")
        identity = self.identities.get_guild_actor_identity(
            owner_id=owner_id,
            connection_id=deployment.connection_id,
            guild_id=deployment.workspace_id,
            user_id=user_id,
        )
        label = user_id
        if identity is not None:
            label = (
                identity.guild_display_name.strip()
                or identity.global_display_name.strip()
                or identity.username.strip()
                or user_id
            )
        return DiscoveryRelationshipAssociation(
            subject_key=subject_key,
            label=label,
            score=round(score, 6),
        )

    def evaluate(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        discovery_item_id: str,
        now: datetime | None = None,
        persist: bool = True,
    ) -> DiscoverySocialAssociationResult | None:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        with self.database.session() as session:
            deployment = session.get(CharacterDeploymentRecord, deployment_id)
            item = session.get(DiscoveryItemRecord, discovery_item_id)
            exposure = session.scalar(
                select(DeploymentDiscoveryExposureRecord).where(
                    DeploymentDiscoveryExposureRecord.owner_id == owner_id,
                    DeploymentDiscoveryExposureRecord.deployment_id == deployment_id,
                    DeploymentDiscoveryExposureRecord.discovery_item_id == discovery_item_id,
                )
            )
            if (
                deployment is None
                or deployment.owner_id != owner_id
                or item is None
                or exposure is None
            ):
                return None
            if exposure.attention_level not in {"watch", "engage"}:
                return None
            query = "\n".join(
                value
                for value in (item.title, item.creator, item.description[:5000])
                if value.strip()
            )
            interest = max(0.0, min(float(exposure.interest_score), 1.0))

        episode_assoc = self._best_episode(
            owner_id=owner_id,
            deployment=deployment,
            query=query,
        )
        episode_record: ConversationEpisodeRecord | None = None
        if episode_assoc is not None:
            records = self.episodes.episodes_by_ids(
                owner_id=owner_id,
                character_card_id=deployment.character_card_id,
                connection_id=deployment.connection_id,
                guild_id=deployment.workspace_id,
                episode_ids=(episode_assoc.episode_id,),
            )
            episode_record = records[0] if records else None
        topic = (
            self._topic_for_episode(
                owner_id=owner_id,
                episode=episode_record,
                episode_score=episode_assoc.score,
            )
            if episode_record is not None and episode_assoc is not None
            else None
        )
        relationship = (
            self._relationship_for_episode(
                owner_id=owner_id,
                deployment=deployment,
                episode=episode_record,
                now=current,
            )
            if episode_record is not None
            else None
        )
        context_score = episode_assoc.score if episode_assoc is not None else 0.0
        if relationship is not None:
            context_score = max(context_score, relationship.score)
            motivation = "REMIND_ME_OF_SOMEONE"
        elif topic is not None:
            motivation = (
                "RELATED_TO_CURRENT_TOPIC"
                if topic.status in {"active", "cooling"}
                else "RELATED_TO_PAST_CONVERSATION"
            )
        else:
            motivation = "INTERESTING"
        confidence = max(0.0, min(1.0, interest * 0.68 + context_score * 0.32))
        would_share = bool(
            interest >= 0.62
            and (
                context_score >= 0.34
                or (exposure.attention_level == "engage" and interest >= 0.78)
            )
        )
        result = DiscoverySocialAssociationResult(
            deployment_id=deployment_id,
            discovery_item_id=discovery_item_id,
            topic=topic,
            episode=episode_assoc,
            relationship=relationship,
            would_share=would_share,
            motivation=motivation,
            confidence=round(confidence, 6),
        )
        if persist:
            profile = self.discovery.get_profile(owner_id=owner_id, deployment_id=deployment_id)
            mode = profile.mode if profile is not None else DiscoveryMode.SHADOW
            self.discovery.record_decision(
                owner_id=owner_id,
                deployment_id=deployment_id,
                discovery_item_id=discovery_item_id,
                mode=mode,
                decision=(
                    DiscoveryDecision.WOULD_SHARE
                    if would_share
                    else DiscoveryDecision.REMEMBER
                ),
                motivation=motivation,
                confidence=result.confidence,
                scores={
                    "interest": round(interest, 6),
                    "episode": episode_assoc.score if episode_assoc is not None else 0.0,
                    "relationship": relationship.score if relationship is not None else 0.0,
                },
                evidence={
                    "side_effects": False,
                    "attention_level": exposure.attention_level,
                    "episode_id": episode_assoc.episode_id if episode_assoc is not None else "",
                    "expanded_episode_ids": (
                        list(episode_assoc.expanded_episode_ids)
                        if episode_assoc is not None
                        else []
                    ),
                    "topic_id": topic.topic_id if topic is not None else "",
                    "relationship_subject_key": (
                        relationship.subject_key if relationship is not None else ""
                    ),
                },
                now=current,
            )
        return result


__all__ = [
    "DiscoveryEpisodeAssociation",
    "DiscoveryRelationshipAssociation",
    "DiscoverySocialAssociationResult",
    "DiscoverySocialAssociationService",
    "DiscoveryTopicAssociation",
]
