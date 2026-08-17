"""Targeted cleanup helpers for rebuildable Conversation Intelligence indexes."""

from __future__ import annotations

from sqlalchemy import delete, exists, select

from echo_masque.persistence.character_learned_state_event_models import (
    CharacterLearnedStateEventRecord,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.episodic_sql_rag_models import (
    CharacterEpisodeAccessRecord,
    ConversationEntityRecord,
    ConversationEpisodeEntityRecord,
)
from echo_masque.persistence.semantic_vector_models import SemanticVectorRecord

_EPISODE_VECTOR_NAMESPACES = ("internal-episode-recall",)
_SYNTHESIZED_MEMORY_VECTOR_NAMESPACES = ("internal-memory-vnext",)


class ConversationIntelligenceDerivedCleanup:
    """Delete indexes/projections without touching raw source evidence or explicit Core Memory."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def delete_episode_indexes(
        self,
        *,
        owner_id: str,
        episode_ids: tuple[str, ...],
    ) -> None:
        if not episode_ids:
            return
        with self.database.session() as session:
            session.execute(
                delete(CharacterEpisodeAccessRecord).where(
                    CharacterEpisodeAccessRecord.owner_id == owner_id,
                    CharacterEpisodeAccessRecord.episode_id.in_(episode_ids),
                )
            )
            session.execute(
                delete(ConversationEpisodeEntityRecord).where(
                    ConversationEpisodeEntityRecord.owner_id == owner_id,
                    ConversationEpisodeEntityRecord.episode_id.in_(episode_ids),
                )
            )
            session.execute(
                delete(SemanticVectorRecord).where(
                    SemanticVectorRecord.owner_id == owner_id,
                    SemanticVectorRecord.namespace.in_(_EPISODE_VECTOR_NAMESPACES),
                    SemanticVectorRecord.resource_id.in_(episode_ids),
                )
            )
            # Only remove entities no remaining Episode incidence references. Shared entities are
            # retained because another Episode may still use them for SQL expansion.
            orphan_ids = list(
                session.scalars(
                    select(ConversationEntityRecord.id).where(
                        ConversationEntityRecord.owner_id == owner_id,
                        ~exists().where(
                            ConversationEpisodeEntityRecord.entity_id
                            == ConversationEntityRecord.id
                        ),
                    )
                )
            )
            if orphan_ids:
                session.execute(
                    delete(ConversationEntityRecord).where(
                        ConversationEntityRecord.id.in_(orphan_ids)
                    )
                )
            session.commit()

    def delete_synthesized_memory_vectors(
        self,
        *,
        owner_id: str,
        memory_ids: tuple[str, ...],
    ) -> None:
        if not memory_ids:
            return
        with self.database.session() as session:
            session.execute(
                delete(SemanticVectorRecord).where(
                    SemanticVectorRecord.owner_id == owner_id,
                    SemanticVectorRecord.namespace.in_(_SYNTHESIZED_MEMORY_VECTOR_NAMESPACES),
                    SemanticVectorRecord.resource_id.in_(memory_ids),
                )
            )
            session.commit()

    def delete_topic_learned_history(
        self,
        *,
        owner_id: str,
        topic_id: str,
    ) -> None:
        with self.database.session() as session:
            session.execute(
                delete(CharacterLearnedStateEventRecord).where(
                    CharacterLearnedStateEventRecord.owner_id == owner_id,
                    (
                        (CharacterLearnedStateEventRecord.topic_id == topic_id)
                        | (
                            (CharacterLearnedStateEventRecord.subject_type == "topic")
                            & (
                                CharacterLearnedStateEventRecord.subject_key
                                == f"topic:{topic_id}"
                            )
                        )
                    ),
                )
            )
            session.commit()


__all__ = ["ConversationIntelligenceDerivedCleanup"]
