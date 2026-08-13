"""Persistence access for bounded conversation topic memory."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.sql.elements import ColumnElement

from echo_masque.persistence.conversation_topic_models import ConversationTopicRecord
from echo_masque.persistence.database import Database
from echo_masque.persistence.semantic_vector_repository import SemanticVectorRepository

_TOPIC_VECTOR_NAMESPACE = "conversation-topic"


class ConversationTopicRepository:
    """Store topic capsules under exact platform/server/channel/thread scope."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.semantic_vectors = SemanticVectorRepository(database)

    @staticmethod
    def _scope_conditions(
        *,
        owner_id: str,
        platform: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
    ) -> tuple[ColumnElement[bool], ...]:
        return (
            ConversationTopicRecord.owner_id == owner_id,
            ConversationTopicRecord.platform == platform,
            ConversationTopicRecord.connection_id == connection_id,
            ConversationTopicRecord.guild_id == guild_id,
            ConversationTopicRecord.channel_id == channel_id,
            ConversationTopicRecord.thread_id == thread_id,
        )

    def active_for_scope(
        self,
        *,
        owner_id: str,
        platform: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
    ) -> ConversationTopicRecord | None:
        with self.database.session() as session:
            return session.scalar(
                select(ConversationTopicRecord)
                .where(
                    *self._scope_conditions(
                        owner_id=owner_id,
                        platform=platform,
                        connection_id=connection_id,
                        guild_id=guild_id,
                        channel_id=channel_id,
                        thread_id=thread_id,
                    ),
                    ConversationTopicRecord.status == "active",
                )
                .order_by(ConversationTopicRecord.last_active_at.desc())
                .limit(1)
            )

    def get(self, topic_id: str, owner_id: str) -> ConversationTopicRecord | None:
        with self.database.session() as session:
            return session.scalar(
                select(ConversationTopicRecord).where(
                    ConversationTopicRecord.id == topic_id,
                    ConversationTopicRecord.owner_id == owner_id,
                )
            )

    def create(
        self,
        *,
        owner_id: str,
        platform: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
        topic_label: str,
        summary: str,
        keywords_json: str,
        open_loops_json: str,
        pending_actions_json: str,
        participants_json: str,
        last_message_id: str,
        now: datetime | None = None,
    ) -> ConversationTopicRecord:
        current = now or datetime.now(UTC)
        scope = self._scope_conditions(
            owner_id=owner_id,
            platform=platform,
            connection_id=connection_id,
            guild_id=guild_id,
            channel_id=channel_id,
            thread_id=thread_id,
        )
        with self.database.session() as session:
            session.execute(
                update(ConversationTopicRecord)
                .where(*scope, ConversationTopicRecord.status == "active")
                .values(status="cooling", updated_at=current)
            )
            record = ConversationTopicRecord(
                id=str(uuid4()),
                owner_id=owner_id,
                platform=platform,
                connection_id=connection_id,
                guild_id=guild_id,
                channel_id=channel_id,
                thread_id=thread_id,
                topic_label=topic_label[:240],
                summary=summary,
                keywords_json=keywords_json,
                open_loops_json=open_loops_json,
                pending_actions_json=pending_actions_json,
                participants_json=participants_json,
                status="active",
                message_count=1 if last_message_id else 0,
                capsule_version=1,
                last_message_id=last_message_id[:200],
                started_at=current,
                last_active_at=current,
                updated_at=current,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def update_capsule(
        self,
        *,
        topic_id: str,
        owner_id: str,
        topic_label: str,
        summary: str,
        keywords_json: str,
        open_loops_json: str,
        pending_actions_json: str,
        participants_json: str,
        last_message_id: str,
        increment_message_count: bool,
        now: datetime | None = None,
    ) -> ConversationTopicRecord:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            record = session.scalar(
                select(ConversationTopicRecord).where(
                    ConversationTopicRecord.id == topic_id,
                    ConversationTopicRecord.owner_id == owner_id,
                )
            )
            if record is None:
                raise KeyError("topic")
            record.topic_label = topic_label[:240]
            record.summary = summary
            record.keywords_json = keywords_json
            record.open_loops_json = open_loops_json
            record.pending_actions_json = pending_actions_json
            record.participants_json = participants_json
            record.last_message_id = last_message_id[:200]
            record.last_active_at = current
            record.updated_at = current
            record.capsule_version += 1
            if increment_message_count:
                record.message_count += 1
            session.commit()
            session.refresh(record)
            return record

    def set_status(
        self,
        *,
        topic_id: str,
        owner_id: str,
        status: str,
        now: datetime | None = None,
    ) -> ConversationTopicRecord:
        if status not in {"active", "cooling", "closed", "archived"}:
            raise ValueError("Unsupported conversation topic status.")
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            record = session.scalar(
                select(ConversationTopicRecord).where(
                    ConversationTopicRecord.id == topic_id,
                    ConversationTopicRecord.owner_id == owner_id,
                )
            )
            if record is None:
                raise KeyError("topic")
            record.status = status
            record.updated_at = current
            if status in {"closed", "archived"}:
                record.closed_at = current
            session.commit()
            session.refresh(record)
            return record

    def recent_for_scope(
        self,
        *,
        owner_id: str,
        platform: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
        limit: int = 5,
    ) -> list[ConversationTopicRecord]:
        bounded = max(1, min(limit, 20))
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(ConversationTopicRecord)
                    .where(
                        *self._scope_conditions(
                            owner_id=owner_id,
                            platform=platform,
                            connection_id=connection_id,
                            guild_id=guild_id,
                            channel_id=channel_id,
                            thread_id=thread_id,
                        )
                    )
                    .order_by(ConversationTopicRecord.last_active_at.desc())
                    .limit(bounded)
                )
            )

    def claim_owner(self, source_owner_id: str, target_owner_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                update(ConversationTopicRecord)
                .where(ConversationTopicRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            session.commit()
            count = int(getattr(result, "rowcount", 0) or 0)
        self.semantic_vectors.delete_namespace(
            owner_id=source_owner_id,
            namespace=_TOPIC_VECTOR_NAMESPACE,
        )
        return count

    def delete_owner(self, owner_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                delete(ConversationTopicRecord).where(ConversationTopicRecord.owner_id == owner_id)
            )
            session.commit()
            count = int(getattr(result, "rowcount", 0) or 0)
        self.semantic_vectors.delete_namespace(
            owner_id=owner_id,
            namespace=_TOPIC_VECTOR_NAMESPACE,
        )
        return count


__all__ = ["ConversationTopicRepository"]
