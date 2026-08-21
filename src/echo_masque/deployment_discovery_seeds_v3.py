"""Topic-free Discovery seed construction from v3 conversation/entity/episode evidence."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from echo_masque.deployment_discovery_intelligence import (
    DeploymentDiscoverySeeds,
    DiscoverySeed,
)
from echo_masque.persistence.character_learned_state_event_models import (
    CharacterLearnedStateEventRecord,
)
from echo_masque.persistence.conversation_runtime_repository import (
    ConversationRuntimeRepository,
)
from echo_masque.persistence.conversation_structure_repository import (
    ConversationStructureRepository,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.entity_evidence_repository import (
    EntityEvidenceRepository,
    KnowledgeGapView,
)
from echo_masque.persistence.repository import Repository
from echo_masque.persistence.smart_participation_repository import decode_strings


class DeploymentDiscoverySeedBuilderV3:
    """Build curiosity/search seeds without Topic identity or global lived-state leakage."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.cards = Repository(database)
        self.structure = ConversationStructureRepository(database)
        self.runtime = ConversationRuntimeRepository(database)
        self.entities = EntityEvidenceRepository(database)

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @staticmethod
    def _clean_subject(value: str) -> str:
        normalized = " ".join(value.split())
        for prefix in ("concept:", "media:", "event:", "entity:"):
            if normalized.startswith(prefix):
                return normalized.removeprefix(prefix).replace("_", " ")
        return normalized.replace("_", " ")

    @staticmethod
    def _dedupe(seeds: list[DiscoverySeed], limit: int) -> tuple[DiscoverySeed, ...]:
        values: dict[str, DiscoverySeed] = {}
        for seed in seeds:
            key = " ".join(seed.text.casefold().split())
            if not key:
                continue
            previous = values.get(key)
            if previous is None or seed.weight > previous.weight:
                values[key] = seed
        return tuple(
            sorted(values.values(), key=lambda item: item.weight, reverse=True)[:limit]
        )

    def _deployment(
        self,
        *,
        owner_id: str,
        deployment_id: str,
    ) -> CharacterDeploymentRecord | None:
        with self.database.session() as session:
            record = session.get(CharacterDeploymentRecord, deployment_id)
        if record is None or record.owner_id != owner_id:
            return None
        return record

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
        deployment = self._deployment(owner_id=owner_id, deployment_id=deployment_id)
        if deployment is None:
            return None
        threads = self.structure.recent_threads_for_server(
            owner_id=owner_id,
            connection_id=deployment.connection_id,
            guild_id=deployment.workspace_id,
            limit=12,
            now=current,
        )
        episodes = self.runtime.recent_episodes(
            owner_id=owner_id,
            connection_id=deployment.connection_id,
            guild_id=deployment.workspace_id,
            limit=16,
        )
        entities = self.entities.recent_entities(
            owner_id=owner_id,
            connection_id=deployment.connection_id,
            guild_id=deployment.workspace_id,
            limit=20,
        )
        with self.database.session() as session:
            interest_events = list(
                session.scalars(
                    select(CharacterLearnedStateEventRecord)
                    .where(
                        CharacterLearnedStateEventRecord.owner_id == owner_id,
                        CharacterLearnedStateEventRecord.character_card_id
                        == deployment.character_card_id,
                        CharacterLearnedStateEventRecord.state_type == "interest",
                        CharacterLearnedStateEventRecord.connection_id
                        == deployment.connection_id,
                        CharacterLearnedStateEventRecord.guild_id == deployment.workspace_id,
                        CharacterLearnedStateEventRecord.recorded_at
                        >= current - timedelta(days=120),
                        CharacterLearnedStateEventRecord.subject_type.in_(
                            ("concept", "media", "event", "entity")
                        ),
                    )
                    .order_by(CharacterLearnedStateEventRecord.recorded_at.desc())
                    .limit(160)
                )
            )
        seeds: list[DiscoverySeed] = []
        for index, thread in enumerate(threads[:8]):
            age_days = max(
                0.0,
                (current - self._aware(thread.last_active_at)).total_seconds() / 86400.0,
            )
            recency = math.pow(0.5, age_days / 7.0)
            label = " ".join(thread.canonical_label.split())
            if label:
                seeds.append(
                    DiscoverySeed(
                        text=label,
                        weight=min(1.0, 0.72 + 0.22 * recency - index * 0.02),
                        source="conversation_thread",
                        evidence_ref=f"thread:{thread.id}",
                    )
                )
            active_entities = set(thread.active_entity_ids)
            for entity in entities:
                if entity.id not in active_entities:
                    continue
                seeds.append(
                    DiscoverySeed(
                        text=entity.canonical_name,
                        weight=min(0.95, 0.65 + 0.2 * recency),
                        source="thread_entity",
                        evidence_ref=f"entity:{entity.id}",
                    )
                )
        for index, episode in enumerate(episodes[:8]):
            summary = " ".join(episode.summary.split())[:300]
            if summary:
                seeds.append(
                    DiscoverySeed(
                        text=summary,
                        weight=max(0.35, 0.62 - index * 0.03),
                        source="episode",
                        evidence_ref=f"episode:{episode.id}",
                    )
                )
        for entity in entities[:10]:
            weight = 0.58 if entity.status == "canonical" else 0.5
            seeds.append(
                DiscoverySeed(
                    text=entity.canonical_name,
                    weight=weight,
                    source="entity",
                    evidence_ref=f"entity:{entity.id}",
                )
            )
        interest_scores: dict[tuple[str, str], float] = {}
        for event in interest_events:
            age_days = max(
                0.0,
                (current - self._aware(event.recorded_at)).total_seconds() / 86400.0,
            )
            decay = math.pow(0.5, age_days / 30.0)
            key = (event.subject_type, event.subject_key)
            interest_scores[key] = interest_scores.get(key, 0.0) + (
                float(event.delta) * float(event.evidence_confidence) * decay
            )
        for (subject_type, subject_key), score in sorted(
            interest_scores.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:12]:
            if score <= 0.05:
                continue
            text = self._clean_subject(subject_key)
            if text:
                seeds.append(
                    DiscoverySeed(
                        text=text,
                        weight=min(0.82, 0.42 + score),
                        source="server_learned_interest",
                        evidence_ref=f"{subject_type}:{subject_key}",
                    )
                )
        card = self.cards.get_character_card(deployment.character_card_id, owner_id)
        if card is not None:
            for value in (
                *decode_strings(card.tags_json),
                *decode_strings(card.traits_json),
            )[:8]:
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
        ranked = self._dedupe(seeds, bounded)
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

    def for_knowledge_gap(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        gap: KnowledgeGapView,
    ) -> DeploymentDiscoverySeeds | None:
        deployment = self._deployment(owner_id=owner_id, deployment_id=deployment_id)
        if deployment is None:
            return None
        entity = next(
            (
                item
                for item in self.entities.recent_entities(
                    owner_id=owner_id,
                    connection_id=deployment.connection_id,
                    guild_id=deployment.workspace_id,
                    limit=100,
                )
                if item.id == gap.entity_id
            ),
            None,
        )
        if entity is None:
            return None
        queries = tuple(
            dict.fromkeys(
                [
                    entity.canonical_name,
                    *(
                        f"{entity.canonical_name} {field.replace('_', ' ')}"
                        for field in gap.missing_fields[:4]
                    ),
                ]
            )
        )[:6]
        seeds = tuple(
            DiscoverySeed(
                text=query,
                weight=1.0 if index == 0 else 0.9,
                source="knowledge_gap",
                evidence_ref=f"knowledge_gap:{gap.id}",
            )
            for index, query in enumerate(queries)
        )
        semantic_text = "\n".join(
            f"Knowledge gap ({field}): {entity.canonical_name}"
            for field in gap.missing_fields
        )[:4000]
        return DeploymentDiscoverySeeds(
            deployment_id=deployment.id,
            owner_id=deployment.owner_id,
            character_card_id=deployment.character_card_id,
            connection_id=deployment.connection_id,
            guild_id=deployment.workspace_id,
            queries=queries,
            semantic_text=semantic_text,
            seeds=seeds,
        )


__all__ = ["DeploymentDiscoverySeedBuilderV3"]
