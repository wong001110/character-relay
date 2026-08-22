"""Unified evidence graph projector for Conversation Structure, Episodes, Entities, and Media."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from echo_masque.persistence.conversation_runtime_repository import ConversationEpisodeV3View
from echo_masque.persistence.conversation_structure_repository import (
    ConversationSegmentView,
    MessageRelationView,
    ThreadMembershipView,
)
from echo_masque.persistence.entity_evidence_repository import (
    EntityEvidenceRepository,
    EvidenceEdgeV3View,
)

logger = logging.getLogger(__name__)


class EvidenceGraphService:
    """Project typed interpretations into one provenance graph without creating truth authority."""

    def __init__(self, repository: EntityEvidenceRepository) -> None:
        self.repository = repository

    def project_message_relation(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        relation: MessageRelationView,
        now: datetime | None = None,
    ) -> EvidenceEdgeV3View:
        current = now or datetime.now(UTC)
        status = {
            "resolved": "active",
            "unresolved": "unresolved",
            "rejected": "rejected",
            "superseded": "superseded",
        }.get(relation.status, "unresolved")
        return self.repository.add_edge(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            source_ref_type="message",
            source_ref=relation.source_message_id,
            relation_type=relation.relation_type,
            target_ref_type=relation.target_ref_type,
            target_ref=relation.target_ref,
            confidence=relation.confidence,
            authority_class=(
                "explicit_message_relation"
                if relation.source == "discord_explicit"
                else "conversation_interpretation"
            ),
            source_kind=relation.source,
            evidence_refs=(*relation.evidence_refs, f"message_relation:{relation.id}"),
            status=status,
            producer="message_relation_v3",
            valid_from=relation.created_at,
            valid_to=(
                relation.updated_at if relation.status in {"rejected", "superseded"} else None
            ),
            now=current,
        )

    def project_membership(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        segment: ConversationSegmentView,
        membership: ThreadMembershipView,
        now: datetime | None = None,
    ) -> EvidenceEdgeV3View:
        current = now or datetime.now(UTC)
        status = "active" if membership.status == "active" else "superseded"
        return self.repository.add_edge(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            source_ref_type="segment",
            source_ref=segment.id,
            relation_type=membership.relation.upper(),
            target_ref_type="thread" if membership.thread_id else "unknown",
            target_ref=membership.thread_id,
            confidence=membership.confidence,
            authority_class="conversation_structure",
            source_kind=membership.source,
            evidence_refs=(*segment.message_ids, f"thread_membership:{membership.id}"),
            status=status if membership.thread_id else "unresolved",
            producer="conversation_structure_v3",
            valid_from=membership.created_at,
            valid_to=membership.superseded_at,
            now=current,
        )

    def project_episode(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        episode: ConversationEpisodeV3View,
        now: datetime | None = None,
    ) -> tuple[EvidenceEdgeV3View, ...]:
        current = now or datetime.now(UTC)
        values: list[EvidenceEdgeV3View] = []
        for segment_id in episode.segment_ids:
            edge = self._project_episode_edge(
                self.repository.add_edge,
                owner_id=owner_id,
                connection_id=connection_id,
                guild_id=guild_id,
                source_ref_type="episode",
                source_ref=episode.id,
                relation_type="HAS_SEGMENT",
                target_ref_type="segment",
                target_ref=segment_id,
                confidence=1.0,
                authority_class="projection",
                source_kind="episode_v3",
                evidence_refs=(f"episode:{episode.id}", f"segment:{segment_id}"),
                status="active",
                producer="episode_v3",
                valid_from=episode.started_at,
                now=current,
            )
            if edge is not None:
                values.append(edge)
        if episode.conversation_thread_id:
            edge = self._project_episode_edge(
                self.repository.add_edge,
                owner_id=owner_id,
                connection_id=connection_id,
                guild_id=guild_id,
                source_ref_type="episode",
                source_ref=episode.id,
                relation_type="OCCURRED_IN_THREAD",
                target_ref_type="thread",
                target_ref=episode.conversation_thread_id,
                confidence=1.0,
                authority_class="projection",
                source_kind="episode_v3",
                evidence_refs=(
                    f"episode:{episode.id}",
                    f"thread:{episode.conversation_thread_id}",
                ),
                status="active",
                producer="episode_v3",
                valid_from=episode.started_at,
                now=current,
            )
            if edge is not None:
                values.append(edge)
        for entity_id in episode.entity_ids:
            edge = self._project_episode_edge(
                self.repository.add_edge,
                owner_id=owner_id,
                connection_id=connection_id,
                guild_id=guild_id,
                source_ref_type="episode",
                source_ref=episode.id,
                relation_type="INVOLVES_ENTITY",
                target_ref_type="entity",
                target_ref=entity_id,
                confidence=0.9,
                authority_class="projection",
                source_kind="episode_v3",
                evidence_refs=(f"episode:{episode.id}", f"entity:{entity_id}"),
                status="active",
                producer="episode_v3",
                valid_from=episode.started_at,
                now=current,
            )
            if edge is not None:
                values.append(edge)
        return tuple(values)

    @staticmethod
    def _project_episode_edge(
        operation: Callable[..., EvidenceEdgeV3View],
        /,
        **kwargs: object,
    ) -> EvidenceEdgeV3View | None:
        try:
            return operation(**kwargs)
        except Exception as exc:
            logger.warning(
                "Intelligence v3 Episode edge projection failed",
                extra={"projection_kind": "episode_edge", "error_type": type(exc).__name__},
            )
            return None

    def reject_interpretation(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        edge_id: str,
        now: datetime | None = None,
    ) -> EvidenceEdgeV3View:
        return self.repository.reject_edge(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            edge_id=edge_id,
            now=now,
        )


__all__ = ["EvidenceGraphService"]
