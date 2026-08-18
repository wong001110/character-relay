"""Shadow-only social association for Deployment-scoped Character Discovery."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from echo_masque.discovery_contracts import DiscoveryDecision, DiscoveryMode
from echo_masque.persistence.character_learned_state_event_models import (
    CharacterLearnedStateEventRecord,
)
from echo_masque.persistence.conversation_topic_models import ConversationTopicRecord
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.discovery_models import (
    DeploymentDiscoveryExposureRecord,
    DiscoveryItemRecord,
)
from echo_masque.persistence.discovery_repository import DiscoveryRepository


@dataclass(frozen=True, slots=True)
class DiscoveryTopicAssociation:
    topic_id: str
    status: str
    score: float


@dataclass(frozen=True, slots=True)
class DiscoveryRelationshipAssociation:
    subject_type: str
    subject_key: str
    score: float
    topic_id: str


@dataclass(frozen=True, slots=True)
class DiscoverySocialAssociationResult:
    deployment_id: str
    discovery_item_id: str
    topic: DiscoveryTopicAssociation | None
    relationship: DiscoveryRelationshipAssociation | None
    would_share: bool
    motivation: str
    confidence: float


class DiscoverySocialAssociationService:
    """Derive explainable Shadow social intent from Deployment-safe conversation evidence."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.discovery = DiscoveryRepository(database)

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @staticmethod
    def _tokens(value: str) -> set[str]:
        normalized = " ".join(value.casefold().split())
        return {
            token.strip(".,!?;:()[]{}\"'")
            for token in normalized.split()
            if len(token.strip(".,!?;:()[]{}\"'")) >= 2
        }

    @staticmethod
    def _keywords(raw: str) -> tuple[str, ...]:
        try:
            decoded = json.loads(raw or "[]")
        except (json.JSONDecodeError, TypeError):
            return ()
        if not isinstance(decoded, list):
            return ()
        return tuple(
            value
            for item in decoded[:12]
            if (value := " ".join(str(item).split()))
        )

    @classmethod
    def _topic_score(
        cls,
        *,
        content_text: str,
        topic: ConversationTopicRecord,
        now: datetime,
    ) -> float:
        content = content_text.casefold()
        content_tokens = cls._tokens(content_text)
        label = " ".join(topic.topic_label.split())
        phrases = (label, *cls._keywords(topic.keywords_json))
        lexical = 0.0
        for phrase in phrases:
            query = phrase.casefold().strip()
            if not query:
                continue
            if query in content:
                lexical = max(lexical, 1.0)
                continue
            query_tokens = cls._tokens(query)
            if query_tokens:
                lexical = max(
                    lexical,
                    len(query_tokens & content_tokens) / len(query_tokens),
                )
        age_days = max(
            0.0,
            (now - cls._aware(topic.last_active_at)).total_seconds() / 86400.0,
        )
        recency = math.pow(0.5, age_days / 14.0)
        status_weight = {
            "active": 1.0,
            "cooling": 0.9,
            "closed": 0.65,
            "archived": 0.45,
        }.get(topic.status, 0.5)
        return max(0.0, min(1.0, lexical * 0.8 + recency * status_weight * 0.2))

    def _best_topic(
        self,
        *,
        owner_id: str,
        deployment: CharacterDeploymentRecord,
        content_text: str,
        now: datetime,
    ) -> DiscoveryTopicAssociation | None:
        with self.database.session() as session:
            topics = list(
                session.scalars(
                    select(ConversationTopicRecord)
                    .where(
                        ConversationTopicRecord.owner_id == owner_id,
                        ConversationTopicRecord.platform == "discord",
                        ConversationTopicRecord.connection_id == deployment.connection_id,
                        ConversationTopicRecord.guild_id == deployment.workspace_id,
                        ConversationTopicRecord.last_active_at >= now - timedelta(days=90),
                    )
                    .order_by(ConversationTopicRecord.last_active_at.desc())
                    .limit(80)
                )
            )
        best: DiscoveryTopicAssociation | None = None
        for topic in topics:
            score = self._topic_score(content_text=content_text, topic=topic, now=now)
            if best is None or score > best.score:
                best = DiscoveryTopicAssociation(
                    topic_id=topic.id,
                    status=topic.status,
                    score=round(score, 6),
                )
        if best is None or best.score < 0.28:
            return None
        return best

    def _relationship_for_topic(
        self,
        *,
        owner_id: str,
        deployment: CharacterDeploymentRecord,
        topic_id: str,
        now: datetime,
    ) -> DiscoveryRelationshipAssociation | None:
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
                        CharacterLearnedStateEventRecord.topic_id == topic_id,
                        CharacterLearnedStateEventRecord.recorded_at
                        >= now - timedelta(days=120),
                    )
                    .order_by(CharacterLearnedStateEventRecord.recorded_at.desc())
                    .limit(160)
                )
            )
        scores: dict[tuple[str, str], float] = {}
        for event in events:
            age_days = max(
                0.0,
                (now - self._aware(event.recorded_at)).total_seconds() / 86400.0,
            )
            decay = math.pow(0.5, age_days / 45.0)
            contribution = float(event.delta) * float(event.evidence_confidence) * decay
            key = (event.subject_type, event.subject_key)
            scores[key] = scores.get(key, 0.0) + contribution
        if not scores:
            return None
        (subject_type, subject_key), score = max(scores.items(), key=lambda item: item[1])
        normalized = max(0.0, min(1.0, score))
        if normalized < 0.2:
            return None
        return DiscoveryRelationshipAssociation(
            subject_type=subject_type,
            subject_key=subject_key,
            score=round(normalized, 6),
            topic_id=topic_id,
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
            content_text = "\n".join(
                value
                for value in (item.title, item.creator, item.description[:4000])
                if value.strip()
            )
            base_interest = max(0.0, min(float(exposure.interest_score), 1.0))

        topic = self._best_topic(
            owner_id=owner_id,
            deployment=deployment,
            content_text=content_text,
            now=current,
        )
        relationship = (
            self._relationship_for_topic(
                owner_id=owner_id,
                deployment=deployment,
                topic_id=topic.topic_id,
                now=current,
            )
            if topic is not None
            else None
        )

        if relationship is not None and topic is not None:
            motivation = "REMIND_ME_OF_SOMEONE"
            context_score = max(topic.score, relationship.score)
        elif topic is not None:
            motivation = (
                "RELATED_TO_CURRENT_TOPIC"
                if topic.status in {"active", "cooling"}
                else "RELATED_TO_PAST_CONVERSATION"
            )
            context_score = topic.score
        else:
            motivation = "INTERESTING"
            context_score = 0.0

        confidence = max(0.0, min(1.0, base_interest * 0.65 + context_score * 0.35))
        would_share = bool(
            base_interest >= 0.62
            and (
                context_score >= 0.34
                or (exposure.attention_level == "engage" and base_interest >= 0.78)
            )
        )
        result = DiscoverySocialAssociationResult(
            deployment_id=deployment_id,
            discovery_item_id=discovery_item_id,
            topic=topic,
            relationship=relationship,
            would_share=would_share,
            motivation=motivation,
            confidence=round(confidence, 6),
        )
        if persist:
            self.discovery.record_decision(
                owner_id=owner_id,
                deployment_id=deployment_id,
                discovery_item_id=discovery_item_id,
                mode=DiscoveryMode.SHADOW,
                decision=(
                    DiscoveryDecision.WOULD_SHARE
                    if would_share
                    else DiscoveryDecision.REMEMBER
                ),
                motivation=motivation,
                confidence=result.confidence,
                scores={
                    "interest": round(base_interest, 6),
                    "topic": round(topic.score, 6) if topic is not None else 0.0,
                    "relationship": (
                        round(relationship.score, 6) if relationship is not None else 0.0
                    ),
                },
                evidence={
                    "attention_level": exposure.attention_level,
                    "topic_id": topic.topic_id if topic is not None else "",
                    "relationship_subject_type": (
                        relationship.subject_type if relationship is not None else ""
                    ),
                    "relationship_subject_key": (
                        relationship.subject_key if relationship is not None else ""
                    ),
                    "side_effects": False,
                },
                now=current,
            )
        return result


__all__ = [
    "DiscoveryRelationshipAssociation",
    "DiscoverySocialAssociationResult",
    "DiscoverySocialAssociationService",
    "DiscoveryTopicAssociation",
]
