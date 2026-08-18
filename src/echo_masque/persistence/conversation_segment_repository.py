"""Repository for Burst segments and concurrent Semantic Threads."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from echo_masque.persistence.conversation_segment_models import (
    ConversationSegmentRecord,
    SemanticThreadRecord,
)
from echo_masque.persistence.database import Database


@dataclass(frozen=True, slots=True)
class SemanticThreadView:
    id: str
    label: str
    summary: str
    keywords: tuple[str, ...]
    status: str
    last_active_at: datetime


@dataclass(frozen=True, slots=True)
class ConversationSegmentView:
    id: str
    burst_id: str
    message_ids: tuple[str, ...]
    participant_ids: tuple[str, ...]
    kind: str
    summary: str
    semantic_thread_id: str
    thread_action: str
    thread_evidence: bool
    confidence: float
    source: str
    created_at: datetime


def _decode_strings(raw: str) -> tuple[str, ...]:
    try:
        value = json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError):
        return ()
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if isinstance(item, str) and item)


class ConversationSegmentRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @staticmethod
    def thread_view(record: SemanticThreadRecord) -> SemanticThreadView:
        return SemanticThreadView(
            id=record.id,
            label=record.label,
            summary=record.summary,
            keywords=_decode_strings(record.keywords_json),
            status=record.status,
            last_active_at=ConversationSegmentRepository._aware(record.last_active_at),
        )

    @staticmethod
    def segment_view(record: ConversationSegmentRecord) -> ConversationSegmentView:
        return ConversationSegmentView(
            id=record.id,
            burst_id=record.burst_id,
            message_ids=_decode_strings(record.message_ids_json),
            participant_ids=_decode_strings(record.participant_ids_json),
            kind=record.kind,
            summary=record.summary,
            semantic_thread_id=record.semantic_thread_id,
            thread_action=record.thread_action,
            thread_evidence=record.thread_evidence,
            confidence=record.confidence,
            source=record.source,
            created_at=ConversationSegmentRepository._aware(record.created_at),
        )

    def recent_threads(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        discord_thread_id: str,
        limit: int = 12,
        now: datetime | None = None,
    ) -> tuple[SemanticThreadView, ...]:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(SemanticThreadRecord)
                    .where(
                        SemanticThreadRecord.owner_id == owner_id,
                        SemanticThreadRecord.connection_id == connection_id,
                        SemanticThreadRecord.guild_id == guild_id,
                        SemanticThreadRecord.channel_id == channel_id,
                        SemanticThreadRecord.discord_thread_id == discord_thread_id,
                        SemanticThreadRecord.status != "archived",
                    )
                    .order_by(SemanticThreadRecord.last_active_at.desc())
                    .limit(max(1, min(limit, 50)))
                )
            )
            for record in records:
                age = current - self._aware(record.last_active_at)
                desired = "hot" if age <= timedelta(minutes=30) else "warm" if age <= timedelta(hours=6) else "dormant"
                if record.status != desired:
                    record.status = desired
                    record.updated_at = current
            session.commit()
        return tuple(self.thread_view(item) for item in records)

    def create_thread(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        discord_thread_id: str,
        label: str,
        summary: str,
        keywords: tuple[str, ...],
        now: datetime,
    ) -> SemanticThreadView:
        record = SemanticThreadRecord(
            id=str(uuid4()),
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            channel_id=channel_id,
            discord_thread_id=discord_thread_id,
            label=" ".join(label.split())[:240],
            summary=" ".join(summary.split())[:4000],
            keywords_json=json.dumps(list(dict.fromkeys(keywords))[:24], ensure_ascii=False),
            status="hot",
            last_active_at=now,
            created_at=now,
            updated_at=now,
        )
        with self.database.session() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
        return self.thread_view(record)

    def update_thread_evidence(
        self,
        *,
        owner_id: str,
        thread_id: str,
        summary: str,
        keywords: tuple[str, ...],
        now: datetime,
    ) -> SemanticThreadView | None:
        with self.database.session() as session:
            record = session.get(SemanticThreadRecord, thread_id)
            if record is None or record.owner_id != owner_id:
                return None
            compact = " ".join(summary.split())[:1000]
            if compact:
                existing = [item for item in record.summary.split("\n") if item.strip()]
                if not existing or existing[-1] != compact:
                    existing.append(compact)
                record.summary = "\n".join(existing[-4:])[-4000:]
            existing_keywords = list(_decode_strings(record.keywords_json))
            for keyword in keywords:
                clean = " ".join(keyword.split())[:120]
                if clean and clean not in existing_keywords:
                    existing_keywords.append(clean)
            record.keywords_json = json.dumps(existing_keywords[-24:], ensure_ascii=False)
            record.status = "hot"
            record.last_active_at = now
            record.updated_at = now
            session.commit()
            session.refresh(record)
            return self.thread_view(record)

    def touch_thread(
        self,
        *,
        owner_id: str,
        thread_id: str,
        now: datetime,
    ) -> None:
        with self.database.session() as session:
            record = session.get(SemanticThreadRecord, thread_id)
            if record is None or record.owner_id != owner_id:
                return
            record.status = "hot"
            record.last_active_at = now
            record.updated_at = now
            session.commit()

    def record_segments(
        self,
        *,
        owner_id: str,
        burst_id: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        discord_thread_id: str,
        segments: tuple[dict[str, object], ...],
        now: datetime,
    ) -> tuple[ConversationSegmentView, ...]:
        values: list[ConversationSegmentView] = []
        with self.database.session() as session:
            for index, item in enumerate(segments, start=1):
                segment_key = str(item.get("segment_key") or f"segment-{index}")[:120]
                existing = session.scalar(
                    select(ConversationSegmentRecord).where(
                        ConversationSegmentRecord.owner_id == owner_id,
                        ConversationSegmentRecord.burst_id == burst_id,
                        ConversationSegmentRecord.segment_key == segment_key,
                    )
                )
                if existing is not None:
                    values.append(self.segment_view(existing))
                    continue
                message_ids = tuple(str(value) for value in item.get("message_ids", ()) if str(value))
                participants = tuple(str(value) for value in item.get("participant_ids", ()) if str(value))
                record = ConversationSegmentRecord(
                    id=str(uuid4()),
                    owner_id=owner_id,
                    burst_id=burst_id,
                    segment_key=segment_key,
                    connection_id=connection_id,
                    guild_id=guild_id,
                    channel_id=channel_id,
                    discord_thread_id=discord_thread_id,
                    message_ids_json=json.dumps(list(message_ids), ensure_ascii=False),
                    participant_ids_json=json.dumps(list(participants), ensure_ascii=False),
                    kind=str(item.get("kind") or "discussion")[:32],
                    summary=str(item.get("summary") or "")[:4000],
                    semantic_thread_id=str(item.get("semantic_thread_id") or "")[:64],
                    thread_action=str(item.get("thread_action") or "create")[:32],
                    thread_evidence=bool(item.get("thread_evidence", True)),
                    confidence=max(0.0, min(float(item.get("confidence") or 0.0), 1.0)),
                    source=str(item.get("source") or "deterministic")[:32],
                    created_at=now,
                )
                session.add(record)
                session.flush()
                values.append(self.segment_view(record))
            session.commit()
        return tuple(values)

    def recent_segments(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        limit: int = 100,
    ) -> tuple[ConversationSegmentView, ...]:
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(ConversationSegmentRecord)
                    .where(
                        ConversationSegmentRecord.owner_id == owner_id,
                        ConversationSegmentRecord.connection_id == connection_id,
                        ConversationSegmentRecord.guild_id == guild_id,
                    )
                    .order_by(ConversationSegmentRecord.created_at.desc())
                    .limit(max(1, min(limit, 500)))
                )
            )
        return tuple(self.segment_view(item) for item in records)


__all__ = [
    "ConversationSegmentRepository",
    "ConversationSegmentView",
    "SemanticThreadView",
]
