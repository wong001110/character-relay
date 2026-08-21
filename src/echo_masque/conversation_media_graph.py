"""Project Character media perception into the unified v3 Evidence Graph."""

from __future__ import annotations

from dataclasses import dataclass

from echo_masque.live_media import LiveMediaContext
from echo_masque.persistence.conversation_media_models import ConversationMediaReferenceRecord
from echo_masque.persistence.conversation_structure_repository import ConversationStructureRepository
from echo_masque.persistence.entity_evidence_repository import EntityEvidenceRepository


@dataclass(frozen=True, slots=True)
class MediaGraphProjection:
    observed: bool
    media_node_id: str = ""
    edge_count: int = 0


class ConversationMediaGraphService:
    """Write perception provenance without creating a second media truth store."""

    def __init__(
        self,
        evidence: EntityEvidenceRepository,
        structure: ConversationStructureRepository,
    ) -> None:
        self.evidence = evidence
        self.structure = structure

    @staticmethod
    def media_key(source_key: str) -> str:
        return f"media:{' '.join(source_key.casefold().split())[:220]}"

    def project_perceived(
        self,
        *,
        record: ConversationMediaReferenceRecord,
        context: LiveMediaContext,
        connection_id: str,
    ) -> MediaGraphProjection:
        if not record.owner_id or not record.character_card_id or not record.source_key:
            return MediaGraphProjection(False)
        media_ref = self.media_key(record.source_key)
        evidence_refs = tuple(
            item
            for item in (f"message:{record.message_id}", f"media_reference:{record.id}")
            if item
        )
        self.evidence.add_edge(
            owner_id=record.owner_id,
            connection_id=connection_id,
            guild_id=record.guild_id,
            source_ref_type="character",
            source_ref=record.character_card_id,
            relation_type="PERCEIVED",
            target_ref_type="media",
            target_ref=media_ref,
            confidence=1.0,
            authority_class="direct_perception",
            source_kind="media_reference",
            evidence_refs=evidence_refs,
            status="active",
            producer="conversation_media_v3",
        )
        edge_count = 1
        thread = self.structure.thread_for_message(
            owner_id=record.owner_id,
            connection_id=connection_id,
            guild_id=record.guild_id,
            channel_id=record.channel_id,
            discord_thread_id=record.thread_id,
            message_id=record.message_id,
        )
        if thread is not None:
            self.evidence.add_edge(
                owner_id=record.owner_id,
                connection_id=connection_id,
                guild_id=record.guild_id,
                source_ref_type="thread",
                source_ref=thread.id,
                relation_type="REFERENCES",
                target_ref_type="media",
                target_ref=media_ref,
                confidence=0.9,
                authority_class="conversation_structure",
                source_kind="media_reference",
                evidence_refs=evidence_refs,
                status="active",
                producer="conversation_media_v3",
            )
            edge_count += 1
        return MediaGraphProjection(True, media_ref, edge_count)

    def active_thread_media_keys(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
    ) -> frozenset[str]:
        """Return media evidence linked to the most recent live Conversation Thread."""

        threads = self.structure.recent_threads(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            channel_id=channel_id,
            discord_thread_id=thread_id,
            limit=1,
        )
        if not threads or threads[0].status not in {"hot", "warm"}:
            return frozenset()
        active = threads[0]
        edges = self.evidence.edges_for_ref(
            owner_id=owner_id,
            ref_type="thread",
            ref=active.id,
            active_only=True,
            limit=48,
        )
        return frozenset(
            edge.target_ref
            for edge in edges
            if edge.source_ref_type == "thread"
            and edge.source_ref == active.id
            and edge.relation_type == "REFERENCES"
            and edge.target_ref_type == "media"
        )


__all__ = ["ConversationMediaGraphService", "MediaGraphProjection"]
