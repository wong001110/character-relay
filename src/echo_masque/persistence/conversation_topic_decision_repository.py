"""Persistence for privacy-bounded Topic decision observations."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select

from echo_masque.persistence.conversation_topic_decision_models import (
    ConversationTopicDecisionRecord,
)
from echo_masque.persistence.database import Database


class ConversationTopicDecisionRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def record(
        self,
        *,
        owner_id: str,
        platform: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
        message_id: str,
        from_topic_id: str,
        to_topic_id: str,
        decision: str,
        reason: str,
        dense_score: float = 0.0,
        sparse_score: float = 0.0,
        continuation_score: float = 0.0,
        switch_score: float = 0.0,
        candidate_dense_score: float = 0.0,
        candidate_sparse_score: float = 0.0,
        idle_seconds: int = 0,
        now: datetime | None = None,
    ) -> ConversationTopicDecisionRecord:
        if decision not in {"continue", "switch", "resume", "create", "lifecycle"}:
            raise ValueError("Unsupported Topic decision type.")
        current = now or datetime.now(UTC)
        record = ConversationTopicDecisionRecord(
            id=str(uuid4()),
            owner_id=owner_id,
            platform=platform,
            connection_id=connection_id,
            guild_id=guild_id,
            channel_id=channel_id,
            thread_id=thread_id,
            message_id=message_id[:200],
            from_topic_id=from_topic_id[:64],
            to_topic_id=to_topic_id[:64],
            decision=decision,
            reason=reason[:120],
            dense_score=max(-1.0, min(1.0, dense_score)),
            sparse_score=max(0.0, min(1.0, sparse_score)),
            continuation_score=max(-1.0, min(1.0, continuation_score)),
            switch_score=max(-1.0, min(1.0, switch_score)),
            candidate_dense_score=max(-1.0, min(1.0, candidate_dense_score)),
            candidate_sparse_score=max(0.0, min(1.0, candidate_sparse_score)),
            idle_seconds=max(0, idle_seconds),
            created_at=current,
        )
        with self.database.session() as session:
            # Idempotent retries of the same message/decision must not create duplicate trace rows.
            existing = session.scalar(
                select(ConversationTopicDecisionRecord).where(
                    ConversationTopicDecisionRecord.owner_id == owner_id,
                    ConversationTopicDecisionRecord.message_id == message_id[:200],
                    ConversationTopicDecisionRecord.decision == decision,
                    ConversationTopicDecisionRecord.from_topic_id == from_topic_id[:64],
                    ConversationTopicDecisionRecord.to_topic_id == to_topic_id[:64],
                )
            )
            if existing is not None and message_id:
                return existing
            session.add(record)
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
        limit: int = 100,
    ) -> list[ConversationTopicDecisionRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(ConversationTopicDecisionRecord)
                    .where(
                        ConversationTopicDecisionRecord.owner_id == owner_id,
                        ConversationTopicDecisionRecord.platform == platform,
                        ConversationTopicDecisionRecord.connection_id == connection_id,
                        ConversationTopicDecisionRecord.guild_id == guild_id,
                        ConversationTopicDecisionRecord.channel_id == channel_id,
                        ConversationTopicDecisionRecord.thread_id == thread_id,
                    )
                    .order_by(ConversationTopicDecisionRecord.created_at.desc())
                    .limit(max(1, min(limit, 300)))
                )
            )

    def delete_topic(self, *, owner_id: str, topic_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                delete(ConversationTopicDecisionRecord).where(
                    ConversationTopicDecisionRecord.owner_id == owner_id,
                    (
                        (ConversationTopicDecisionRecord.from_topic_id == topic_id)
                        | (ConversationTopicDecisionRecord.to_topic_id == topic_id)
                    ),
                )
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)

    def delete_owner(self, owner_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                delete(ConversationTopicDecisionRecord).where(
                    ConversationTopicDecisionRecord.owner_id == owner_id
                )
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)


__all__ = ["ConversationTopicDecisionRepository"]
