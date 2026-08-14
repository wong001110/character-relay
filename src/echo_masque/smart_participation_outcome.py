"""Project authoritative Smart Participation outcomes into derived/durable V4 state."""

from __future__ import annotations

from dataclasses import dataclass

from echo_masque.api.smart_participation_outcome_schemas import SmartParticipationOutcomeObservation
from echo_masque.character_learned_state import CharacterLearnedStateService, LearnedStateEvidence
from echo_masque.persistence import DeploymentRepository, Repository
from echo_masque.persistence.conversation_graph_repository import (
    ConversationGraphRepository,
    ConversationGraphScope,
)
from echo_masque.persistence.conversation_topic_repository import ConversationTopicRepository
from echo_masque.smart_participation_durable_state import SmartParticipationDurableStateService

_PUBLIC_BURST_TTL = 24 * 60 * 60
_PRIVATE_TOPIC_TTL = 7 * 24 * 60 * 60


@dataclass(frozen=True, slots=True)
class SmartParticipationOutcomeProjection:
    recorded: bool
    selected_count: int
    graph_edge_count: int
    learned_evidence_count: int
    durable_recorded: bool


class SmartParticipationOutcomeService:
    """Use admission facts as evidence without treating model prose as truth."""

    def __init__(self, deployments: DeploymentRepository) -> None:
        self.deployments = deployments
        self.database = deployments.database
        self.repository = Repository(self.database)
        self.graph = ConversationGraphRepository(self.database)
        self.topics = ConversationTopicRepository(self.database)
        self.learned = CharacterLearnedStateService(self.database)
        self.durable = SmartParticipationDurableStateService(self.database)

    @staticmethod
    def _burst_key(payload: SmartParticipationOutcomeObservation) -> str:
        burst = payload.burst_id.strip()
        if burst:
            return burst[:80]
        return f"message:{payload.message_id}"[:80] if payload.message_id else ""

    def _character_label(self, *, owner_id: str, character_card_id: str) -> str:
        card = self.repository.get_character_card(character_card_id, owner_id)
        return card.display_name if card is not None else character_card_id

    def record(
        self,
        payload: SmartParticipationOutcomeObservation,
    ) -> SmartParticipationOutcomeProjection:
        selected_ids = tuple(
            dict.fromkeys(item for item in payload.selected_deployment_ids if item)
        )
        if not selected_ids:
            return SmartParticipationOutcomeProjection(False, 0, 0, 0, False)
        records = self.deployments.list_connector_deployments(
            platform="discord",
            connection_id=payload.connection_id,
        )
        record_by_id = {item.id: item for item in records if item.id in selected_ids}
        selected = [record_by_id[item] for item in selected_ids if item in record_by_id]
        if not selected:
            return SmartParticipationOutcomeProjection(False, 0, 0, 0, False)

        self.durable.record_admission(
            connection_id=payload.connection_id,
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            thread_id=payload.thread_id,
            deployment_ids=tuple(item.id for item in selected),
            window_seconds=600,
        )
        burst_key = self._burst_key(payload)
        graph_edges = 0
        learned_count = 0

        if burst_key and payload.channel_id:
            public_scope = ConversationGraphScope(
                platform="discord",
                connection_id=payload.connection_id,
                guild_id=payload.guild_id,
                channel_id=payload.channel_id,
                thread_id=payload.thread_id,
            )
            burst = self.graph.upsert_node(
                scope=public_scope,
                node_type="ConversationBurst",
                canonical_key=f"burst:{burst_key}",
                label="Conversation Burst",
                payload={"burst_id": burst_key, "message_id": payload.message_id},
                ttl_seconds=_PUBLIC_BURST_TTL,
            )
            for record in selected:
                label = self._character_label(
                    owner_id=record.owner_id,
                    character_card_id=record.character_card_id,
                )
                character = self.graph.upsert_node(
                    scope=public_scope,
                    node_type="Character",
                    canonical_key=f"deployment:{record.id}",
                    label=label,
                    payload={
                        "deployment_id": record.id,
                        "character_card_id": record.character_card_id,
                    },
                    ttl_seconds=_PUBLIC_BURST_TTL,
                )
                self.graph.upsert_edge(
                    scope=public_scope,
                    source_node_id=character.id,
                    relation="RESPONDED_TO",
                    target_node_id=burst.id,
                    confidence=1.0,
                    source_type="runtime_admission",
                    source_message_id=payload.message_id,
                    source_burst_id=burst_key,
                    provenance={"deployment_id": record.id},
                    ttl_seconds=_PUBLIC_BURST_TTL,
                )
                graph_edges += 1

        scope_key = ":".join(
            (payload.connection_id, payload.guild_id, payload.channel_id, payload.thread_id)
        )
        for record in selected:
            evidence_base = dict(
                owner_id=record.owner_id,
                character_card_id=record.character_card_id,
                source_type="runtime_admission",
                source_message_id=payload.message_id,
                source_burst_id=burst_key,
            )
            self.learned.record_evidence(
                LearnedStateEvidence(
                    state_type="participation_fatigue",
                    subject_type="concept",
                    subject_key=f"scope:{scope_key}",
                    delta=1.0,
                    confidence=0.9,
                    reason_code="selected_smart_participation",
                    **evidence_base,
                )
            )
            learned_count += 1
            if payload.author_id:
                self.learned.record_evidence(
                    LearnedStateEvidence(
                        state_type="relationship",
                        subject_type="actor",
                        subject_key=f"actor:{payload.author_id}",
                        delta=0.20,
                        confidence=0.55,
                        reason_code="direct_group_interaction",
                        **evidence_base,
                    )
                )
                learned_count += 1

            topic = self.topics.active_for_scope(
                owner_id=record.owner_id,
                platform="discord",
                connection_id=payload.connection_id,
                guild_id=payload.guild_id,
                channel_id=payload.channel_id,
                thread_id=payload.thread_id,
            )
            if topic is None:
                continue
            topic_key = f"topic:{topic.id}"
            for state_type, delta, confidence, reason in (
                ("interest", 0.22, 0.55, "voluntary_topic_participation"),
                ("salience", 0.45, 0.75, "recent_active_topic"),
                ("conversation_ownership", 0.55, 0.75, "selected_to_answer_topic"),
            ):
                self.learned.record_evidence(
                    LearnedStateEvidence(
                        state_type=state_type,  # type: ignore[arg-type]
                        subject_type="topic",
                        subject_key=topic_key,
                        delta=delta,
                        confidence=confidence,
                        reason_code=reason,
                        **evidence_base,
                    )
                )
                learned_count += 1

            private_scope = ConversationGraphScope(
                scope_owner_id=record.owner_id,
                platform="discord",
                connection_id=payload.connection_id,
                guild_id=payload.guild_id,
                channel_id=payload.channel_id,
                thread_id=payload.thread_id,
            )
            label = self._character_label(
                owner_id=record.owner_id,
                character_card_id=record.character_card_id,
            )
            character = self.graph.upsert_node(
                scope=private_scope,
                node_type="Character",
                canonical_key=f"character:{record.character_card_id}",
                label=label,
                payload={"character_card_id": record.character_card_id},
                ttl_seconds=_PRIVATE_TOPIC_TTL,
            )
            topic_node = self.graph.upsert_node(
                scope=private_scope,
                node_type="Topic",
                canonical_key=topic_key,
                label=topic.topic_label,
                payload={"topic_id": topic.id, "capsule_version": topic.capsule_version},
                ttl_seconds=_PRIVATE_TOPIC_TTL,
            )
            self.graph.upsert_edge(
                scope=private_scope,
                source_node_id=character.id,
                relation="PARTICIPATED_IN",
                target_node_id=topic_node.id,
                confidence=0.8,
                source_type="runtime_admission",
                source_message_id=payload.message_id,
                source_burst_id=burst_key,
                provenance={"deployment_id": record.id, "topic_id": topic.id},
                ttl_seconds=_PRIVATE_TOPIC_TTL,
            )
            graph_edges += 1

        return SmartParticipationOutcomeProjection(
            True,
            len(selected),
            graph_edges,
            learned_count,
            True,
        )


__all__ = ["SmartParticipationOutcomeProjection", "SmartParticipationOutcomeService"]
