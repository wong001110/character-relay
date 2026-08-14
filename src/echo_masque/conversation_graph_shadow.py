"""Low-cost Graph shadow observation for conversation bursts.

This layer records only relations that are directly authoritative from the connector payload. It
must not infer interests, relationships, topics, or speaker intent. Those derived relations are
added by later V4 phases after their own evidence contracts are validated.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from echo_masque.api.smart_participation_v4_schemas import SmartParticipationResolveRequest
from echo_masque.persistence.conversation_graph_repository import (
    ConversationGraphRepository,
    ConversationGraphScope,
)

_BURST_TTL_SECONDS = 7 * 24 * 60 * 60
_ACTOR_TTL_SECONDS = 90 * 24 * 60 * 60


@dataclass(frozen=True, slots=True)
class GraphShadowObservation:
    observed: bool
    burst_id: str
    node_count: int
    edge_count: int


class ConversationGraphShadowService:
    """Persist directly observed Burst/Actor relations without affecting runtime decisions."""

    def __init__(self, repository: ConversationGraphRepository) -> None:
        self.repository = repository

    @staticmethod
    def _scope(payload: SmartParticipationResolveRequest) -> ConversationGraphScope:
        return ConversationGraphScope(
            scope_owner_id="",
            platform="discord",
            connection_id=payload.connection_id,
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            thread_id=payload.thread_id,
        )

    @staticmethod
    def _burst_id(payload: SmartParticipationResolveRequest) -> str:
        explicit = " ".join(payload.burst_id.split())[:80]
        if explicit:
            return explicit
        message_ids = [item.message_id for item in payload.burst_messages if item.message_id]
        if payload.message_id:
            message_ids.append(payload.message_id)
        seed = "|".join(dict.fromkeys(message_ids))
        if not seed:
            seed = "|".join(
                (
                    payload.connection_id,
                    payload.guild_id,
                    payload.channel_id,
                    payload.thread_id,
                    payload.author_id,
                    hashlib.sha256(payload.message.encode("utf-8")).hexdigest(),
                )
            )
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:40]

    @staticmethod
    def _actors(
        payload: SmartParticipationResolveRequest,
    ) -> tuple[tuple[str, str, str], ...]:
        """Return (author_id, display_name, source_message_id) in first-seen order."""

        values: dict[str, tuple[str, str, str]] = {}
        for item in payload.burst_messages:
            if not item.author_id or item.author_id in values:
                continue
            values[item.author_id] = (
                item.author_id,
                item.author_display_name,
                item.message_id,
            )
        if payload.author_id and payload.author_id not in values:
            values[payload.author_id] = (
                payload.author_id,
                "",
                payload.message_id,
            )
        return tuple(values.values())

    def observe(self, payload: SmartParticipationResolveRequest) -> GraphShadowObservation:
        if not payload.connection_id or not (payload.channel_id or payload.thread_id):
            return GraphShadowObservation(False, "", 0, 0)
        burst_id = self._burst_id(payload)
        scope = self._scope(payload)
        source_ids = list(
            dict.fromkeys(
                [item.message_id for item in payload.burst_messages if item.message_id]
                + ([payload.message_id] if payload.message_id else [])
            )
        )[:5]
        burst = self.repository.upsert_node(
            scope=scope,
            node_type="ConversationBurst",
            canonical_key=f"burst:{burst_id}",
            label="Conversation burst",
            payload={
                "burst_id": burst_id,
                "source_message_ids": source_ids,
                "message_count": len(payload.burst_messages) or (1 if payload.message else 0),
            },
            ttl_seconds=_BURST_TTL_SECONDS,
        )
        node_count = 1
        edge_count = 0
        for author_id, display_name, source_message_id in self._actors(payload):
            actor = self.repository.upsert_node(
                scope=scope,
                node_type="Actor",
                canonical_key=f"actor:{author_id}",
                label=display_name,
                payload={"platform_user_id": author_id},
                ttl_seconds=_ACTOR_TTL_SECONDS,
            )
            node_count += 1
            self.repository.upsert_edge(
                scope=scope,
                source_node_id=actor.id,
                relation="PARTICIPATED_IN",
                target_node_id=burst.id,
                confidence=1.0,
                source_type="conversation_burst",
                source_message_id=source_message_id,
                source_burst_id=burst_id,
                provenance={
                    "source": "discord_connector",
                    "kind": "authored_message_in_burst",
                },
                ttl_seconds=_BURST_TTL_SECONDS,
            )
            edge_count += 1
        return GraphShadowObservation(True, burst_id, node_count, edge_count)


__all__ = ["ConversationGraphShadowService", "GraphShadowObservation"]
