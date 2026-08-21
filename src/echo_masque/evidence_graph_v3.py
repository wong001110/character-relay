"""Unified evidence graph projector for Conversation Structure, Episodes, Entities, and Media."""

from __future__ import annotations

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
            evidence_refs=relation.evidence_refs,
            status=status,
            producer="message_relation_v3",
            valid_from=current,
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
            evidence_refs=segment.message_ids,
            status=status if membership.thread_id else "unresolved",
            producer="conversation_structure_v3",
            valid_from=current,
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
            values.append(
                self.repository.add_edge(
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
                    evidence_refs=episode.source_message_ids,
                    status="active",
                    producer="episode_v3",
                    valid_from=current,
                    now=current,
                )
            )
        if episode.conversation_thread_id:
            values.append(
                self.repository.add_edge(
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
                    evidence_refs=episode.segment_ids,
                    status="active",
                    producer="episode_v3",
                    valid_from=current,
                    now=current,
                )
            )
        for entity_id in episode.entity_ids:
            values.append(
                self.repository.add_edge(
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
                    evidence_refs=episode.segment_ids,
                    status="active",
                    producer="episode_v3",
                    valid_from=current,
                    now=current,
                )
            )
        return tuple(values)

    def reject_interpretation(
        self,
        *,
        owner_id: str,
        edge_id: str,
        now: datetime | None = None,
    ) -> EvidenceEdgeV3View:
        return self.repository.reject_edge(owner_id=owner_id, edge_id=edge_id, now=now)


__all__ = ["EvidenceGraphService"]
