"""Typed, revisable Message Relation contracts for Conversation Structure v3."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from sqlalchemy import select

from echo_masque.persistence.conversation_structure_models import MessageRelationRecord
from echo_masque.persistence.conversation_structure_repository import (
    ConversationStructureRepository,
    MessageRelationView,
)

InteractionRelationType = Literal[
    "REPLY_TO",
    "ADDRESSED_TO",
    "ANSWERS",
    "CLARIFIES",
    "REACTS_TO",
    "CONTINUES",
]
SemanticRelationType = Literal[
    "REFERS_TO",
    "EVALUATES",
    "INSULTS",
    "PRAISES",
    "AGREES_WITH",
    "DISAGREES_WITH",
    "DEPICTS",
]
RelationStatus = Literal["resolved", "unresolved", "rejected", "superseded"]
RelationTargetType = Literal[
    "message",
    "actor",
    "deployment",
    "media",
    "entity",
    "segment",
    "thread",
    "unknown",
]

INTERACTION_RELATIONS: frozenset[str] = frozenset(
    {
        "REPLY_TO",
        "ADDRESSED_TO",
        "ANSWERS",
        "CLARIFIES",
        "REACTS_TO",
        "CONTINUES",
    }
)
SEMANTIC_RELATIONS: frozenset[str] = frozenset(
    {
        "REFERS_TO",
        "EVALUATES",
        "INSULTS",
        "PRAISES",
        "AGREES_WITH",
        "DISAGREES_WITH",
        "DEPICTS",
    }
)


def _evidence_json(values: tuple[str, ...], *, limit: int = 16) -> str:
    clean = list(dict.fromkeys(item for item in values if item))[-limit:]
    return json.dumps(clean, ensure_ascii=False)


class ConversationRelationService:
    """Write and revise interpretation edges without rewriting source evidence."""

    def __init__(self, repository: ConversationStructureRepository) -> None:
        self.repository = repository
        self.database = repository.database

    @staticmethod
    def _class_for(relation_type: str) -> str:
        if relation_type in INTERACTION_RELATIONS:
            return "interaction"
        if relation_type in SEMANTIC_RELATIONS:
            return "semantic"
        raise ValueError(f"Unsupported Message Relation type: {relation_type}")

    def record(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        discord_thread_id: str,
        source_message_id: str,
        source_author_id: str = "",
        source_author_display_name: str = "",
        relation_type: InteractionRelationType | SemanticRelationType,
        target_ref_type: RelationTargetType,
        target_ref: str,
        target_author_id: str = "",
        target_author_display_name: str = "",
        confidence: float,
        source: str,
        evidence_refs: tuple[str, ...],
        status: RelationStatus = "resolved",
        now: datetime | None = None,
    ) -> MessageRelationView:
        if status == "superseded":
            raise ValueError("A new relation cannot be born superseded.")
        current = now or datetime.now(UTC)
        return self.repository.record_relation(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            channel_id=channel_id,
            discord_thread_id=discord_thread_id,
            source_message_id=source_message_id,
            source_author_id=source_author_id,
            source_author_display_name=source_author_display_name,
            relation_class=self._class_for(relation_type),
            relation_type=relation_type,
            target_ref_type=target_ref_type,
            target_ref=target_ref,
            target_author_id=target_author_id,
            target_author_display_name=target_author_display_name,
            confidence=confidence,
            source=source,
            evidence_refs=evidence_refs,
            status=status,
            now=current,
        )

    def revise(
        self,
        *,
        owner_id: str,
        relation_id: str,
        target_ref_type: RelationTargetType,
        target_ref: str,
        confidence: float,
        source: str,
        evidence_refs: tuple[str, ...],
        status: Literal["resolved", "unresolved"] = "resolved",
        now: datetime | None = None,
    ) -> MessageRelationView:
        """Supersede one interpretation with a new version and keep the old edge for provenance."""

        current = now or datetime.now(UTC)
        with self.database.session() as session:
            previous = session.get(MessageRelationRecord, relation_id)
            if previous is None or previous.owner_id != owner_id:
                raise KeyError("Message Relation not found.")
            if previous.status in {"rejected", "superseded"}:
                raise ValueError("Only an active relation interpretation can be revised.")
            previous.status = "superseded"
            previous.updated_at = current
            replacement = MessageRelationRecord(
                id=str(uuid4()),
                owner_id=previous.owner_id,
                connection_id=previous.connection_id,
                guild_id=previous.guild_id,
                channel_id=previous.channel_id,
                discord_thread_id=previous.discord_thread_id,
                source_message_id=previous.source_message_id,
                source_author_id=previous.source_author_id,
                source_author_display_name=previous.source_author_display_name,
                relation_class=previous.relation_class,
                relation_type=previous.relation_type,
                target_ref_type=target_ref_type,
                target_ref=target_ref[:240],
                target_author_id=previous.target_author_id,
                target_author_display_name=previous.target_author_display_name,
                confidence=max(0.0, min(float(confidence), 1.0)),
                source=source[:32],
                evidence_refs_json=_evidence_json(evidence_refs),
                status=status,
                supersedes_relation_id=previous.id,
                created_at=current,
                updated_at=current,
            )
            session.add(replacement)
            session.commit()
            session.refresh(replacement)
            return self.repository.relation_view(replacement)

    def reject(
        self,
        *,
        owner_id: str,
        relation_id: str,
        now: datetime | None = None,
    ) -> MessageRelationView:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            record = session.get(MessageRelationRecord, relation_id)
            if record is None or record.owner_id != owner_id:
                raise KeyError("Message Relation not found.")
            if record.status == "superseded":
                raise ValueError("Superseded relation history cannot be rejected in place.")
            record.status = "rejected"
            record.updated_at = current
            session.commit()
            session.refresh(record)
            return self.repository.relation_view(record)

    def history(
        self,
        *,
        owner_id: str,
        source_message_id: str,
        relation_type: InteractionRelationType | SemanticRelationType,
    ) -> tuple[MessageRelationView, ...]:
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(MessageRelationRecord)
                    .where(
                        MessageRelationRecord.owner_id == owner_id,
                        MessageRelationRecord.source_message_id == source_message_id,
                        MessageRelationRecord.relation_type == relation_type,
                    )
                    .order_by(MessageRelationRecord.created_at.asc())
                )
            )
        return tuple(self.repository.relation_view(item) for item in records)


__all__ = [
    "INTERACTION_RELATIONS",
    "SEMANTIC_RELATIONS",
    "ConversationRelationService",
    "InteractionRelationType",
    "RelationStatus",
    "RelationTargetType",
    "SemanticRelationType",
]
