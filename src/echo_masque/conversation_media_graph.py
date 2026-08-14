"""Conversation Media ↔ Graph projection without duplicating media epistemic authority."""

from __future__ import annotations

from dataclasses import dataclass

from echo_masque.live_media import LiveMediaContext
from echo_masque.persistence.conversation_graph_repository import (
    ConversationGraphRepository,
    ConversationGraphScope,
)
from echo_masque.persistence.conversation_media_models import ConversationMediaReferenceRecord
from echo_masque.persistence.conversation_topic_repository import ConversationTopicRepository

_MEDIA_GRAPH_TTL = 30 * 24 * 60 * 60


@dataclass(frozen=True, slots=True)
class MediaGraphProjection:
    observed: bool
    media_node_id: str = ""
    edge_count: int = 0


class ConversationMediaGraphService:
    """Project only Runtime-proven media perception into an owner-private graph overlay."""

    def __init__(
        self,
        graph: ConversationGraphRepository,
        topics: ConversationTopicRepository,
    ) -> None:
        self.graph = graph
        self.topics = topics

    @staticmethod
    def media_key(source_key: str) -> str:
        return f"media:{' '.join(source_key.casefold().split())[:220]}"

    @staticmethod
    def _scope(
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
    ) -> ConversationGraphScope:
        return ConversationGraphScope(
            scope_owner_id=owner_id,
            platform="discord",
            connection_id=connection_id,
            guild_id=guild_id,
            channel_id=channel_id,
            thread_id=thread_id,
        )

    def project_perceived(
        self,
        *,
        record: ConversationMediaReferenceRecord,
        context: LiveMediaContext,
        connection_id: str,
    ) -> MediaGraphProjection:
        """Record PERCEIVED; never infer INSPECTED or SKIPPED from missing metadata."""

        if not record.owner_id or not record.character_card_id or not record.source_key:
            return MediaGraphProjection(False)
        scope = self._scope(
            owner_id=record.owner_id,
            connection_id=connection_id,
            guild_id=record.guild_id,
            channel_id=record.channel_id,
            thread_id=record.thread_id,
        )
        character = self.graph.upsert_node(
            scope=scope,
            node_type="Character",
            canonical_key=f"character:{record.character_card_id}",
            label=record.character_card_id,
            payload={"character_card_id": record.character_card_id},
            ttl_seconds=_MEDIA_GRAPH_TTL,
        )
        media = self.graph.upsert_node(
            scope=scope,
            node_type="Media",
            canonical_key=self.media_key(record.source_key),
            label=context.label or context.kind,
            summary=context.summary[:1200],
            payload={
                "source_key": record.source_key[:500],
                "kind": record.kind,
                "message_id": record.message_id,
                "reference_id": record.id,
            },
            ttl_seconds=_MEDIA_GRAPH_TTL,
        )
        self.graph.upsert_edge(
            scope=scope,
            source_node_id=character.id,
            relation="PERCEIVED",
            target_node_id=media.id,
            confidence=1.0,
            source_type="media_reference",
            source_message_id=record.message_id,
            provenance={"reference_id": record.id},
            ttl_seconds=_MEDIA_GRAPH_TTL,
        )
        edge_count = 1

        topic = self.topics.active_for_scope(
            owner_id=record.owner_id,
            platform="discord",
            connection_id=connection_id,
            guild_id=record.guild_id,
            channel_id=record.channel_id,
            thread_id=record.thread_id,
        )
        if topic is not None:
            topic_node = self.graph.upsert_node(
                scope=scope,
                node_type="Topic",
                canonical_key=f"topic:{topic.id}",
                label=topic.topic_label,
                payload={"topic_id": topic.id, "capsule_version": topic.capsule_version},
                ttl_seconds=_MEDIA_GRAPH_TTL,
            )
            self.graph.upsert_edge(
                scope=scope,
                source_node_id=topic_node.id,
                relation="REFERENCES",
                target_node_id=media.id,
                confidence=0.85,
                source_type="media_reference",
                source_message_id=record.message_id,
                provenance={"reference_id": record.id, "topic_id": topic.id},
                ttl_seconds=_MEDIA_GRAPH_TTL,
            )
            edge_count += 1
        return MediaGraphProjection(True, media.id, edge_count)

    def active_topic_media_keys(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
    ) -> frozenset[str]:
        """Return graph-linked Media identities for candidate narrowing only."""

        topic = self.topics.active_for_scope(
            owner_id=owner_id,
            platform="discord",
            connection_id=connection_id,
            guild_id=guild_id,
            channel_id=channel_id,
            thread_id=thread_id,
        )
        if topic is None:
            return frozenset()
        scope = self._scope(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            channel_id=channel_id,
            thread_id=thread_id,
        )
        topic_node = self.graph.find_node(
            scope=scope,
            node_type="Topic",
            canonical_key=f"topic:{topic.id}",
        )
        if topic_node is None:
            return frozenset()
        return frozenset(
            neighbor.node.canonical_key
            for neighbor in self.graph.neighbors(
                scope=scope,
                node_id=topic_node.id,
                relations=("REFERENCES",),
                limit=24,
            )
            if neighbor.node.node_type == "Media"
        )


__all__ = ["ConversationMediaGraphService", "MediaGraphProjection"]
