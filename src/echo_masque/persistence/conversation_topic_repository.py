"""Persistence access for bounded conversation topic memory."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.sql.elements import ColumnElement

from echo_masque.conversation_topic_lifecycle import evaluate_topic_lifecycle
from echo_masque.persistence.conversation_topic_decision_repository import (
    ConversationTopicDecisionRepository,
)
from echo_masque.persistence.conversation_topic_models import ConversationTopicRecord
from echo_masque.persistence.database import Database
from echo_masque.persistence.semantic_vector_repository import SemanticVectorRepository

_TOPIC_VECTOR_NAMESPACE = "conversation-topic"


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class ConversationTopicRepository:
    """Store topic capsules under exact platform/server/channel/thread scope."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.semantic_vectors = SemanticVectorRepository(database)
        self.decisions = ConversationTopicDecisionRepository(database)

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

    def _advance_lifecycle(
        self,
        record: ConversationTopicRecord,
        *,
        now: datetime | None = None,
    ) -> ConversationTopicRecord:
        decision = evaluate_topic_lifecycle(record, now=now)
        if decision is None:
            return record
        return self.set_status(
            topic_id=record.id,
            owner_id=record.owner_id,
            status=decision.to_status,
            now=now,
            reason=decision.reason,
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
            record = session.scalar(
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
        if record is None:
            return None
        advanced = self._advance_lifecycle(record)
        return advanced if advanced.status == "active" else None

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
        current = _aware(now) if now is not None else datetime.now(UTC)
        scope = self._scope_conditions(
            owner_id=owner_id,
            platform=platform,
            connection_id=connection_id,
            guild_id=guild_id,
            channel_id=channel_id,
            thread_id=thread_id,
        )
        with self.database.session() as session:
            previous = session.scalar(
                select(ConversationTopicRecord)
                .where(*scope, ConversationTopicRecord.status == "active")
                .order_by(ConversationTopicRecord.last_active_at.desc())
                .limit(1)
            )
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
        self.decisions.record(
            owner_id=owner_id,
            platform=platform,
            connection_id=connection_id,
            guild_id=guild_id,
            channel_id=channel_id,
            thread_id=thread_id,
            message_id=last_message_id,
            from_topic_id=previous.id if previous is not None else "",
            to_topic_id=record.id,
            decision="create",
            reason="new_topic_created",
            idle_seconds=(
                max(0, int((current - _aware(previous.last_active_at)).total_seconds()))
                if previous is not None
                else 0
            ),
            now=current,
        )
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
        current = _aware(now) if now is not None else datetime.now(UTC)
        with self.database.session() as session:
            record = session.scalar(
                select(ConversationTopicRecord).where(
                    ConversationTopicRecord.id == topic_id,
                    ConversationTopicRecord.owner_id == owner_id,
                )
            )
            if record is None:
                raise KeyError("topic")
            previous_active = _aware(record.last_active_at)
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
        if increment_message_count and last_message_id:
            self.decisions.record(
                owner_id=record.owner_id,
                platform=record.platform,
                connection_id=record.connection_id,
                guild_id=record.guild_id,
                channel_id=record.channel_id,
                thread_id=record.thread_id,
                message_id=last_message_id,
                from_topic_id=record.id,
                to_topic_id=record.id,
                decision="continue",
                reason="topic_capsule_continued",
                idle_seconds=max(0, int((current - previous_active).total_seconds())),
                now=current,
            )
        return record

    def resume(
        self,
        *,
        topic_id: str,
        owner_id: str,
        platform: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
        summary: str,
        keywords_json: str,
        participants_json: str,
        last_message_id: str,
        now: datetime | None = None,
    ) -> ConversationTopicRecord:
        current = _aware(now) if now is not None else datetime.now(UTC)
        scope = self._scope_conditions(
            owner_id=owner_id,
            platform=platform,
            connection_id=connection_id,
            guild_id=guild_id,
            channel_id=channel_id,
            thread_id=thread_id,
        )
        with self.database.session() as session:
            previous = session.scalar(
                select(ConversationTopicRecord)
                .where(
                    *scope,
                    ConversationTopicRecord.status == "active",
                    ConversationTopicRecord.id != topic_id,
                )
                .order_by(ConversationTopicRecord.last_active_at.desc())
                .limit(1)
            )
            session.execute(
                update(ConversationTopicRecord)
                .where(
                    *scope,
                    ConversationTopicRecord.status == "active",
                    ConversationTopicRecord.id != topic_id,
                )
                .values(status="cooling", updated_at=current)
            )
            record = session.scalar(
                select(ConversationTopicRecord).where(
                    ConversationTopicRecord.id == topic_id,
                    ConversationTopicRecord.owner_id == owner_id,
                    *scope[1:],
                )
            )
            if record is None:
                raise KeyError("topic")
            idle_seconds = max(
                0,
                int((current - _aware(record.last_active_at)).total_seconds()),
            )
            record.status = "active"
            record.closed_at = None
            record.summary = summary
            record.keywords_json = keywords_json
            record.participants_json = participants_json
            record.last_message_id = last_message_id[:200]
            record.last_active_at = current
            record.updated_at = current
            record.message_count += 1
            record.capsule_version += 1
            session.commit()
            session.refresh(record)
        self.decisions.record(
            owner_id=owner_id,
            platform=platform,
            connection_id=connection_id,
            guild_id=guild_id,
            channel_id=channel_id,
            thread_id=thread_id,
            message_id=last_message_id,
            from_topic_id=previous.id if previous is not None else "",
            to_topic_id=record.id,
            decision="resume",
            reason="historical_topic_resumed",
            idle_seconds=idle_seconds,
            now=current,
        )
        return record

    def set_status(
        self,
        *,
        topic_id: str,
        owner_id: str,
        status: str,
        now: datetime | None = None,
        reason: str = "manual_status_change",
    ) -> ConversationTopicRecord:
        if status not in {"active", "cooling", "closed", "archived"}:
            raise ValueError("Unsupported conversation topic status.")
        current = _aware(now) if now is not None else datetime.now(UTC)
        with self.database.session() as session:
            record = session.scalar(
                select(ConversationTopicRecord).where(
                    ConversationTopicRecord.id == topic_id,
                    ConversationTopicRecord.owner_id == owner_id,
                )
            )
            if record is None:
                raise KeyError("topic")
            previous_status = record.status
            last_active = _aware(record.last_active_at)
            record.status = status
            record.updated_at = current
            if status in {"closed", "archived"}:
                record.closed_at = current
            session.commit()
            session.refresh(record)
        if previous_status != status:
            self.decisions.record(
                owner_id=record.owner_id,
                platform=record.platform,
                connection_id=record.connection_id,
                guild_id=record.guild_id,
                channel_id=record.channel_id,
                thread_id=record.thread_id,
                message_id="",
                from_topic_id=record.id,
                to_topic_id=record.id,
                decision="lifecycle",
                reason=f"{previous_status}_to_{status}:{reason}",
                idle_seconds=max(0, int((current - last_active).total_seconds())),
                now=current,
            )
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
            records = list(
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
        return [self._advance_lifecycle(record) for record in records]

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
        self.decisions.delete_owner(owner_id)
        return count


__all__ = ["ConversationTopicRepository"]
