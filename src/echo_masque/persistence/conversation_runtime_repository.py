"""Repositories for Episode v3, ThreadWorkingState, and standalone PendingAction."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from echo_masque.persistence.conversation_runtime_models import (
    ConversationEpisodeV3Record,
    PendingActionV3Record,
    ThreadWorkingStateRecord,
)
from echo_masque.persistence.database import Database


def _decode_list(raw: str) -> tuple[str, ...]:
    try:
        value = json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError):
        return ()
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if isinstance(item, str) and item)


def _encode_list(values: tuple[str, ...] | list[str], *, limit: int) -> str:
    clean = [str(item) for item in values if str(item)]
    return json.dumps(list(dict.fromkeys(clean))[-limit:], ensure_ascii=False)


def _decode_dict(raw: str) -> dict[str, str]:
    try:
        value = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items() if str(key)}


def _encode_dict(value: dict[str, str]) -> str:
    return json.dumps({str(key): str(item) for key, item in value.items()}, ensure_ascii=False)


@dataclass(frozen=True, slots=True)
class ConversationEpisodeV3View:
    id: str
    conversation_thread_id: str
    segment_ids: tuple[str, ...]
    source_message_ids: tuple[str, ...]
    participant_ids: tuple[str, ...]
    entity_ids: tuple[str, ...]
    media_refs: tuple[str, ...]
    summary: str
    key_events: tuple[str, ...]
    segment_count: int
    status: str
    checkpoint_reason: str
    started_at: datetime
    ended_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ThreadWorkingStateView:
    thread_id: str
    current_object_ref: str
    active_entity_ids: tuple[str, ...]
    open_questions: tuple[str, ...]
    waiting_states: tuple[str, ...]
    referenced_media: tuple[str, ...]
    state: dict[str, str]
    status: str
    expires_at: datetime | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PendingActionV3View:
    id: str
    source_message_id: str
    source_segment_id: str
    conversation_thread_id: str
    requested_by_user_id: str
    target_character_card_id: str
    deployment_id: str
    tool_id: str
    intent_summary: str
    state: str
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ConversationRuntimeRepository:
    """Own short-lived Thread state and durable Segment-based Episode/Action projections."""

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _aware(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @classmethod
    def episode_view(cls, record: ConversationEpisodeV3Record) -> ConversationEpisodeV3View:
        return ConversationEpisodeV3View(
            id=record.id,
            conversation_thread_id=record.conversation_thread_id,
            segment_ids=_decode_list(record.segment_ids_json),
            source_message_ids=_decode_list(record.source_message_ids_json),
            participant_ids=_decode_list(record.participant_ids_json),
            entity_ids=_decode_list(record.entity_ids_json),
            media_refs=_decode_list(record.media_refs_json),
            summary=record.summary,
            key_events=_decode_list(record.key_events_json),
            segment_count=record.segment_count,
            status=record.status,
            checkpoint_reason=record.checkpoint_reason,
            started_at=cls._aware(record.started_at) or record.started_at,
            ended_at=cls._aware(record.ended_at) or record.ended_at,
            updated_at=cls._aware(record.updated_at) or record.updated_at,
        )

    @classmethod
    def working_state_view(cls, record: ThreadWorkingStateRecord) -> ThreadWorkingStateView:
        return ThreadWorkingStateView(
            thread_id=record.thread_id,
            current_object_ref=record.current_object_ref,
            active_entity_ids=_decode_list(record.active_entity_ids_json),
            open_questions=_decode_list(record.open_questions_json),
            waiting_states=_decode_list(record.waiting_states_json),
            referenced_media=_decode_list(record.referenced_media_json),
            state=_decode_dict(record.state_json),
            status=record.status,
            expires_at=cls._aware(record.expires_at),
            updated_at=cls._aware(record.updated_at) or record.updated_at,
        )

    @classmethod
    def pending_action_view(cls, record: PendingActionV3Record) -> PendingActionV3View:
        return PendingActionV3View(
            id=record.id,
            source_message_id=record.source_message_id,
            source_segment_id=record.source_segment_id,
            conversation_thread_id=record.conversation_thread_id,
            requested_by_user_id=record.requested_by_user_id,
            target_character_card_id=record.target_character_card_id,
            deployment_id=record.deployment_id,
            tool_id=record.tool_id,
            intent_summary=record.intent_summary,
            state=record.state,
            expires_at=cls._aware(record.expires_at),
            created_at=cls._aware(record.created_at) or record.created_at,
            updated_at=cls._aware(record.updated_at) or record.updated_at,
        )

    def upsert_working_state(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        discord_thread_id: str,
        thread_id: str,
        current_object_ref: str = "",
        active_entity_ids: tuple[str, ...] = (),
        open_questions: tuple[str, ...] = (),
        waiting_states: tuple[str, ...] = (),
        referenced_media: tuple[str, ...] = (),
        state: dict[str, str] | None = None,
        expires_at: datetime | None = None,
        now: datetime | None = None,
    ) -> ThreadWorkingStateView:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            record = session.get(ThreadWorkingStateRecord, thread_id)
            if record is None:
                record = ThreadWorkingStateRecord(
                    thread_id=thread_id,
                    owner_id=owner_id,
                    connection_id=connection_id,
                    guild_id=guild_id,
                    channel_id=channel_id,
                    discord_thread_id=discord_thread_id,
                    created_at=current,
                    updated_at=current,
                )
                session.add(record)
            elif record.owner_id != owner_id:
                raise KeyError("Thread Working State not found.")
            if current_object_ref:
                record.current_object_ref = current_object_ref[:320]
            if active_entity_ids:
                merged = list(_decode_list(record.active_entity_ids_json)) + list(active_entity_ids)
                record.active_entity_ids_json = _encode_list(merged, limit=48)
            if open_questions:
                merged = list(_decode_list(record.open_questions_json)) + list(open_questions)
                record.open_questions_json = _encode_list(merged, limit=24)
            if waiting_states:
                merged = list(_decode_list(record.waiting_states_json)) + list(waiting_states)
                record.waiting_states_json = _encode_list(merged, limit=24)
            if referenced_media:
                merged = list(_decode_list(record.referenced_media_json)) + list(referenced_media)
                record.referenced_media_json = _encode_list(merged, limit=24)
            if state:
                merged_state = _decode_dict(record.state_json)
                merged_state.update({str(key): str(value) for key, value in state.items()})
                record.state_json = _encode_dict(merged_state)
            record.status = "active"
            record.expires_at = expires_at
            record.updated_at = current
            session.commit()
            session.refresh(record)
            return self.working_state_view(record)

    def working_state(self, *, owner_id: str, thread_id: str) -> ThreadWorkingStateView | None:
        with self.database.session() as session:
            record = session.get(ThreadWorkingStateRecord, thread_id)
        if record is None or record.owner_id != owner_id:
            return None
        return self.working_state_view(record)

    def archive_working_state(
        self,
        *,
        owner_id: str,
        thread_id: str,
        now: datetime | None = None,
    ) -> ThreadWorkingStateView | None:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            record = session.get(ThreadWorkingStateRecord, thread_id)
            if record is None or record.owner_id != owner_id:
                return None
            record.status = "archived"
            record.updated_at = current
            session.commit()
            session.refresh(record)
            return self.working_state_view(record)

    def expire_working_states(self, *, now: datetime | None = None) -> int:
        current = now or datetime.now(UTC)
        changed = 0
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(ThreadWorkingStateRecord).where(
                        ThreadWorkingStateRecord.status == "active",
                        ThreadWorkingStateRecord.expires_at.is_not(None),
                        ThreadWorkingStateRecord.expires_at <= current,
                    )
                )
            )
            for record in records:
                record.status = "archived"
                record.updated_at = current
                changed += 1
            session.commit()
        return changed

    def active_episode(
        self,
        *,
        owner_id: str,
        conversation_thread_id: str,
    ) -> ConversationEpisodeV3View | None:
        if not conversation_thread_id:
            return None
        with self.database.session() as session:
            record = session.scalar(
                select(ConversationEpisodeV3Record)
                .where(
                    ConversationEpisodeV3Record.owner_id == owner_id,
                    ConversationEpisodeV3Record.conversation_thread_id == conversation_thread_id,
                    ConversationEpisodeV3Record.status == "active",
                )
                .order_by(ConversationEpisodeV3Record.updated_at.desc())
                .limit(1)
            )
        return self.episode_view(record) if record is not None else None

    def append_episode_segment(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        discord_thread_id: str,
        conversation_thread_id: str,
        segment_id: str,
        source_message_ids: tuple[str, ...],
        participant_ids: tuple[str, ...],
        entity_ids: tuple[str, ...] = (),
        media_refs: tuple[str, ...] = (),
        summary: str = "",
        key_events: tuple[str, ...] = (),
        max_segments: int = 12,
        now: datetime | None = None,
    ) -> ConversationEpisodeV3View:
        current = now or datetime.now(UTC)
        normalized_thread = conversation_thread_id[:64]
        with self.database.session() as session:
            record: ConversationEpisodeV3Record | None = None
            if normalized_thread:
                record = session.scalar(
                    select(ConversationEpisodeV3Record)
                    .where(
                        ConversationEpisodeV3Record.owner_id == owner_id,
                        ConversationEpisodeV3Record.conversation_thread_id == normalized_thread,
                        ConversationEpisodeV3Record.status == "active",
                    )
                    .order_by(ConversationEpisodeV3Record.updated_at.desc())
                    .limit(1)
                )
            if record is None:
                episode_id = str(uuid4())
                episode_key = (
                    f"thread:{normalized_thread}:{episode_id}"
                    if normalized_thread
                    else f"segment:{segment_id}:{episode_id}"
                )
                record = ConversationEpisodeV3Record(
                    id=episode_id,
                    owner_id=owner_id,
                    connection_id=connection_id,
                    guild_id=guild_id,
                    channel_id=channel_id,
                    discord_thread_id=discord_thread_id,
                    conversation_thread_id=normalized_thread,
                    episode_key=episode_key[:160],
                    started_at=current,
                    ended_at=current,
                    updated_at=current,
                )
                session.add(record)
            segments = list(_decode_list(record.segment_ids_json))
            if segment_id not in segments:
                segments.append(segment_id)
            messages = list(_decode_list(record.source_message_ids_json)) + list(source_message_ids)
            participants = list(_decode_list(record.participant_ids_json)) + list(participant_ids)
            entities = list(_decode_list(record.entity_ids_json)) + list(entity_ids)
            media = list(_decode_list(record.media_refs_json)) + list(media_refs)
            events = list(_decode_list(record.key_events_json)) + list(key_events)
            record.segment_ids_json = _encode_list(segments, limit=64)
            record.source_message_ids_json = _encode_list(messages, limit=160)
            record.participant_ids_json = _encode_list(participants, limit=64)
            record.entity_ids_json = _encode_list(entities, limit=64)
            record.media_refs_json = _encode_list(media, limit=64)
            record.key_events_json = _encode_list(events, limit=48)
            compact = " ".join(summary.split())[:4000]
            if compact:
                record.summary = compact
            record.segment_count = len(_decode_list(record.segment_ids_json))
            record.ended_at = current
            record.updated_at = current
            if not normalized_thread:
                record.status = "closed"
                record.checkpoint_reason = "unresolved_segment"
            elif record.segment_count >= max(1, max_segments):
                record.status = "closed"
                record.checkpoint_reason = "size_checkpoint"
            session.commit()
            session.refresh(record)
            return self.episode_view(record)

    def close_episode(
        self,
        *,
        owner_id: str,
        conversation_thread_id: str,
        reason: str,
        now: datetime | None = None,
    ) -> ConversationEpisodeV3View | None:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            record = session.scalar(
                select(ConversationEpisodeV3Record)
                .where(
                    ConversationEpisodeV3Record.owner_id == owner_id,
                    ConversationEpisodeV3Record.conversation_thread_id == conversation_thread_id,
                    ConversationEpisodeV3Record.status == "active",
                )
                .order_by(ConversationEpisodeV3Record.updated_at.desc())
                .limit(1)
            )
            if record is None:
                return None
            record.status = "closed"
            record.checkpoint_reason = reason[:40]
            record.ended_at = current
            record.updated_at = current
            session.commit()
            session.refresh(record)
            return self.episode_view(record)

    def recent_episodes(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        limit: int = 40,
    ) -> tuple[ConversationEpisodeV3View, ...]:
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(ConversationEpisodeV3Record)
                    .where(
                        ConversationEpisodeV3Record.owner_id == owner_id,
                        ConversationEpisodeV3Record.connection_id == connection_id,
                        ConversationEpisodeV3Record.guild_id == guild_id,
                    )
                    .order_by(ConversationEpisodeV3Record.ended_at.desc())
                    .limit(max(1, min(limit, 200)))
                )
            )
        return tuple(self.episode_view(record) for record in records)

    def create_pending_action(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        discord_thread_id: str,
        source_message_id: str,
        source_segment_id: str,
        conversation_thread_id: str,
        requested_by_user_id: str,
        target_character_card_id: str,
        deployment_id: str,
        tool_id: str,
        intent_summary: str,
        state: str = "pending",
        expires_at: datetime | None = None,
        now: datetime | None = None,
    ) -> PendingActionV3View:
        current = now or datetime.now(UTC)
        record = PendingActionV3Record(
            id=str(uuid4()),
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            channel_id=channel_id,
            discord_thread_id=discord_thread_id,
            source_message_id=source_message_id[:200],
            source_segment_id=source_segment_id[:64],
            conversation_thread_id=conversation_thread_id[:64],
            requested_by_user_id=requested_by_user_id[:200],
            target_character_card_id=target_character_card_id[:64],
            deployment_id=deployment_id[:64],
            tool_id=tool_id[:160],
            intent_summary=" ".join(intent_summary.split())[:2000],
            state=state[:32],
            expires_at=expires_at,
            created_at=current,
            updated_at=current,
        )
        with self.database.session() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
        return self.pending_action_view(record)

    def active_pending_actions(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        requested_by_user_id: str = "",
        target_character_card_id: str = "",
        deployment_id: str = "",
        conversation_thread_id: str = "",
        now: datetime | None = None,
        limit: int = 20,
    ) -> tuple[PendingActionV3View, ...]:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            statement = select(PendingActionV3Record).where(
                PendingActionV3Record.owner_id == owner_id,
                PendingActionV3Record.connection_id == connection_id,
                PendingActionV3Record.guild_id == guild_id,
                PendingActionV3Record.state.in_(("pending", "in_progress", "blocked_unavailable")),
            )
            if requested_by_user_id:
                statement = statement.where(
                    PendingActionV3Record.requested_by_user_id == requested_by_user_id
                )
            if target_character_card_id:
                statement = statement.where(
                    PendingActionV3Record.target_character_card_id == target_character_card_id
                )
            if deployment_id:
                statement = statement.where(PendingActionV3Record.deployment_id == deployment_id)
            if conversation_thread_id:
                statement = statement.where(
                    PendingActionV3Record.conversation_thread_id == conversation_thread_id
                )
            records = list(
                session.scalars(
                    statement.order_by(PendingActionV3Record.updated_at.desc()).limit(
                        max(1, min(limit, 100))
                    )
                )
            )
            changed = False
            active: list[PendingActionV3Record] = []
            for record in records:
                expires = self._aware(record.expires_at)
                if expires is not None and expires <= current:
                    record.state = "expired"
                    record.updated_at = current
                    changed = True
                else:
                    active.append(record)
            if changed:
                session.commit()
        return tuple(self.pending_action_view(record) for record in active)

    def pending_action(self, *, owner_id: str, action_id: str) -> PendingActionV3View | None:
        with self.database.session() as session:
            record = session.get(PendingActionV3Record, action_id)
        if record is None or record.owner_id != owner_id:
            return None
        return self.pending_action_view(record)

    def update_pending_action_state(
        self,
        *,
        owner_id: str,
        action_id: str,
        state: str,
        now: datetime | None = None,
    ) -> PendingActionV3View | None:
        current = now or datetime.now(UTC)
        allowed = {
            "pending",
            "in_progress",
            "blocked_unavailable",
            "completed",
            "cancelled",
            "expired",
        }
        normalized = state if state in allowed else "pending"
        with self.database.session() as session:
            record = session.get(PendingActionV3Record, action_id)
            if record is None or record.owner_id != owner_id:
                return None
            record.state = normalized
            record.updated_at = current
            session.commit()
            session.refresh(record)
            return self.pending_action_view(record)


__all__ = [
    "ConversationEpisodeV3View",
    "ConversationRuntimeRepository",
    "PendingActionV3View",
    "ThreadWorkingStateView",
]
