"""Persistence for derived Episode projections."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select

from echo_masque.persistence.conversation_episode_models import ConversationEpisodeRecord
from echo_masque.persistence.database import Database


class ConversationEpisodeRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _json(values: list[str]) -> str:
        return json.dumps(list(dict.fromkeys(item for item in values if item)), ensure_ascii=False)

    def upsert_projection(
        self,
        *,
        owner_id: str,
        platform: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
        episode_key: str,
        topic_id: str,
        burst_ids: list[str],
        source_message_ids: list[str],
        participant_refs: list[str],
        media_refs: list[str],
        summary: str,
        key_points: list[str],
        status: str = "active",
        now: datetime | None = None,
    ) -> ConversationEpisodeRecord:
        if status not in {"active", "closed"}:
            raise ValueError("Unsupported Episode status.")
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            record = session.scalar(
                select(ConversationEpisodeRecord).where(
                    ConversationEpisodeRecord.owner_id == owner_id,
                    ConversationEpisodeRecord.platform == platform,
                    ConversationEpisodeRecord.connection_id == connection_id,
                    ConversationEpisodeRecord.guild_id == guild_id,
                    ConversationEpisodeRecord.episode_key == episode_key,
                )
            )
            if record is None:
                record = ConversationEpisodeRecord(
                    id=str(uuid4()),
                    owner_id=owner_id,
                    platform=platform,
                    connection_id=connection_id,
                    guild_id=guild_id,
                    channel_id=channel_id,
                    thread_id=thread_id,
                    episode_key=episode_key[:120],
                    started_at=current,
                )
                session.add(record)
            record.topic_id = topic_id[:64]
            record.burst_ids_json = self._json(burst_ids[-12:])
            record.source_message_ids_json = self._json(source_message_ids[-40:])
            record.participant_refs_json = self._json(participant_refs[-30:])
            record.media_refs_json = self._json(media_refs[-20:])
            record.summary = " ".join(summary.split())[:800]
            record.key_points_json = self._json(
                [" ".join(item.split())[:300] for item in key_points[-8:]]
            )
            record.source_count = len(set(source_message_ids))
            record.status = status
            record.ended_at = current
            record.updated_at = current
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
        limit: int = 20,
    ) -> list[ConversationEpisodeRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(ConversationEpisodeRecord)
                    .where(
                        ConversationEpisodeRecord.owner_id == owner_id,
                        ConversationEpisodeRecord.platform == platform,
                        ConversationEpisodeRecord.connection_id == connection_id,
                        ConversationEpisodeRecord.guild_id == guild_id,
                        ConversationEpisodeRecord.channel_id == channel_id,
                        ConversationEpisodeRecord.thread_id == thread_id,
                    )
                    .order_by(ConversationEpisodeRecord.ended_at.desc())
                    .limit(max(1, min(limit, 100)))
                )
            )

    def recent_for_topic(
        self,
        *,
        owner_id: str,
        topic_id: str,
        limit: int = 20,
    ) -> list[ConversationEpisodeRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(ConversationEpisodeRecord)
                    .where(
                        ConversationEpisodeRecord.owner_id == owner_id,
                        ConversationEpisodeRecord.topic_id == topic_id,
                    )
                    .order_by(ConversationEpisodeRecord.ended_at.desc())
                    .limit(max(1, min(limit, 100)))
                )
            )

    def delete_owner(self, owner_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                delete(ConversationEpisodeRecord).where(
                    ConversationEpisodeRecord.owner_id == owner_id
                )
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)


__all__ = ["ConversationEpisodeRepository"]
