"""Owner-scoped Graph Shadow projection of authoritative Conversation Topic Memory."""

from __future__ import annotations

from dataclasses import dataclass

from echo_masque.api.smart_participation_v4_schemas import SmartParticipationResolveRequest
from echo_masque.persistence.conversation_graph_repository import (
    ConversationGraphRepository,
    ConversationGraphScope,
)
from echo_masque.persistence.conversation_topic_repository import ConversationTopicRepository

_BURST_TTL_SECONDS = 24 * 60 * 60
_TOPIC_EDGE_TTL_SECONDS = 24 * 60 * 60


@dataclass(frozen=True, slots=True)
class TopicGraphShadowObservation:
    observed: bool
    owner_count: int
    topic_count: int
    node_count: int
    edge_count: int


def _burst_id(payload: SmartParticipationResolveRequest) -> str:
    explicit = payload.burst_id.strip()
    if explicit:
        return explicit[:80]
    message_id = payload.message_id.strip()
    return f"message:{message_id}"[:80] if message_id else ""


class ConversationGraphTopicShadowService:
    """Project active Topic Memory references into private Graph overlays.

    Topic Memory remains authoritative. This service performs no semantic classification and stores
    no Topic summary copy; it only references the active Topic row and the current burst identity.
    """

    def __init__(
        self,
        graph_repository: ConversationGraphRepository,
        topic_repository: ConversationTopicRepository,
    ) -> None:
        self.graph_repository = graph_repository
        self.topic_repository = topic_repository

    def observe(
        self,
        payload: SmartParticipationResolveRequest,
        *,
        owner_ids: list[str],
    ) -> TopicGraphShadowObservation:
        burst_id = _burst_id(payload)
        owners = list(dict.fromkeys(item.strip() for item in owner_ids if item.strip()))
        if (
            not burst_id
            or not owners
            or not payload.connection_id
            or not payload.channel_id
        ):
            return TopicGraphShadowObservation(False, 0, 0, 0, 0)

        source_message_ids = [item.message_id for item in payload.burst_messages]
        if not source_message_ids and payload.message_id:
            source_message_ids = [payload.message_id]
        source_message_id = payload.message_id or (source_message_ids[-1] if source_message_ids else "")

        topic_count = 0
        node_count = 0
        edge_count = 0
        owner_count = 0
        for owner_id in owners:
            topic = self.topic_repository.active_for_scope(
                owner_id=owner_id,
                platform="discord",
                connection_id=payload.connection_id,
                guild_id=payload.guild_id,
                channel_id=payload.channel_id,
                thread_id=payload.thread_id,
            )
            if topic is None:
                continue

            scope = ConversationGraphScope(
                scope_owner_id=owner_id,
                platform="discord",
                connection_id=payload.connection_id,
                guild_id=payload.guild_id,
                channel_id=payload.channel_id,
                thread_id=payload.thread_id,
            )
            burst = self.graph_repository.upsert_node(
                scope=scope,
                node_type="ConversationBurst",
                canonical_key=f"burst:{burst_id}",
                label="Conversation Burst",
                payload={
                    "burst_id": burst_id,
                    "source_message_ids": source_message_ids,
                    "public_graph_reference": True,
                },
                ttl_seconds=_BURST_TTL_SECONDS,
            )
            topic_node = self.graph_repository.upsert_node(
                scope=scope,
                node_type="Topic",
                canonical_key=f"topic:{topic.id}",
                label=topic.topic_label,
                payload={
                    "topic_id": topic.id,
                    "topic_status": topic.status,
                    "capsule_version": topic.capsule_version,
                },
                ttl_seconds=_TOPIC_EDGE_TTL_SECONDS,
            )
            self.graph_repository.upsert_edge(
                scope=scope,
                source_node_id=topic_node.id,
                relation="ACTIVE_IN_BURST",
                target_node_id=burst.id,
                confidence=1.0,
                source_type="topic_memory",
                source_message_id=source_message_id,
                source_burst_id=burst_id,
                provenance={
                    "topic_id": topic.id,
                    "topic_status": topic.status,
                    "capsule_version": topic.capsule_version,
                },
                ttl_seconds=_TOPIC_EDGE_TTL_SECONDS,
            )
            owner_count += 1
            topic_count += 1
            node_count += 2
            edge_count += 1

        return TopicGraphShadowObservation(
            observed=topic_count > 0,
            owner_count=owner_count,
            topic_count=topic_count,
            node_count=node_count,
            edge_count=edge_count,
        )


__all__ = ["ConversationGraphTopicShadowService", "TopicGraphShadowObservation"]
