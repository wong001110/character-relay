"""Repository for Intelligence Core v3 Conversation Structure."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from echo_masque.persistence.conversation_structure_models import (
    ConversationSegmentV3Record,
    ConversationThreadRecord,
    MessageRelationRecord,
    ThreadMembershipRecord,
)
from echo_masque.persistence.database import Database


@dataclass(frozen=True, slots=True)
class ConversationThreadView:
    id: str
    canonical_label: str
    anchor_summary: str
    working_summary: str
    representative_segment_ids: tuple[str, ...]
    participant_ids: tuple[str, ...]
    active_entity_ids: tuple[str, ...]
    status: str
    last_active_at: datetime

    @property
    def label(self) -> str:
        """Temporary source-compatibility alias; canonical_label is the v3 contract."""

        return self.canonical_label

    @property
    def summary(self) -> str:
        """Temporary source-compatibility alias used only by ranking consumers."""

        return self.working_summary or self.anchor_summary

    @property
    def keywords(self) -> tuple[str, ...]:
        """v3 does not persist Thread keywords as identity authority."""

        return ()


@dataclass(frozen=True, slots=True)
class ThreadMembershipView:
    id: str
    segment_id: str
    thread_id: str
    relation: str
    confidence: float
    source: str
    reason: str
    version: int
    status: str
    superseded_at: datetime | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ConversationSegmentView:
    id: str
    burst_id: str
    message_ids: tuple[str, ...]
    participant_ids: tuple[str, ...]
    kind: str
    summary: str
    thread_id: str
    membership_relation: str
    membership_confidence: float
    confidence: float
    source: str
    created_at: datetime

    @property
    def semantic_thread_id(self) -> str:
        """Computed compatibility alias; membership, not Segment storage, is authoritative."""

        return self.thread_id

    @property
    def thread_action(self) -> str:
        if self.membership_relation == "unresolved":
            return "unresolved"
        if self.membership_relation in {"context_of", "reaction_to"}:
            return "context_only"
        return "attach" if self.thread_id else "unresolved"

    @property
    def thread_evidence(self) -> bool:
        return self.membership_relation == "belongs_to" and bool(self.thread_id)


@dataclass(frozen=True, slots=True)
class MessageRelationView:
    id: str
    source_message_id: str
    relation_class: str
    relation_type: str
    target_ref_type: str
    target_ref: str
    confidence: float
    source: str
    evidence_refs: tuple[str, ...]
    status: str
    supersedes_relation_id: str
    created_at: datetime
    updated_at: datetime


def _decode_strings(raw: str) -> tuple[str, ...]:
    try:
        value = json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError):
        return ()
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if isinstance(item, str) and item)


def _encode_strings(values: tuple[str, ...] | list[str], *, limit: int) -> str:
    clean = [str(item) for item in values if str(item)]
    return json.dumps(list(dict.fromkeys(clean))[-limit:], ensure_ascii=False)


def _string_items(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(item) for item in value if str(item))


def _bounded_float(value: object) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return max(0.0, min(float(value), 1.0))
    return 0.0


class ConversationStructureRepository:
    """Persist structure interpretations without making Segment→Thread assignment irreversible."""

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _aware(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @classmethod
    def thread_view(cls, record: ConversationThreadRecord) -> ConversationThreadView:
        return ConversationThreadView(
            id=record.id,
            canonical_label=record.canonical_label,
            anchor_summary=record.anchor_summary,
            working_summary=record.working_summary,
            representative_segment_ids=_decode_strings(record.representative_segment_ids_json),
            participant_ids=_decode_strings(record.participant_ids_json),
            active_entity_ids=_decode_strings(record.active_entity_ids_json),
            status=record.status,
            last_active_at=cls._aware(record.last_active_at) or record.last_active_at,
        )

    @classmethod
    def membership_view(cls, record: ThreadMembershipRecord) -> ThreadMembershipView:
        return ThreadMembershipView(
            id=record.id,
            segment_id=record.segment_id,
            thread_id=record.thread_id,
            relation=record.relation,
            confidence=record.confidence,
            source=record.source,
            reason=record.reason,
            version=record.version,
            status=record.status,
            superseded_at=cls._aware(record.superseded_at),
            created_at=cls._aware(record.created_at) or record.created_at,
        )

    @classmethod
    def relation_view(cls, record: MessageRelationRecord) -> MessageRelationView:
        return MessageRelationView(
            id=record.id,
            source_message_id=record.source_message_id,
            relation_class=record.relation_class,
            relation_type=record.relation_type,
            target_ref_type=record.target_ref_type,
            target_ref=record.target_ref,
            confidence=record.confidence,
            source=record.source,
            evidence_refs=_decode_strings(record.evidence_refs_json),
            status=record.status,
            supersedes_relation_id=record.supersedes_relation_id,
            created_at=cls._aware(record.created_at) or record.created_at,
            updated_at=cls._aware(record.updated_at) or record.updated_at,
        )

    @classmethod
    def segment_view(
        cls,
        record: ConversationSegmentV3Record,
        membership: ThreadMembershipRecord | None = None,
    ) -> ConversationSegmentView:
        return ConversationSegmentView(
            id=record.id,
            burst_id=record.burst_id,
            message_ids=_decode_strings(record.message_ids_json),
            participant_ids=_decode_strings(record.participant_ids_json),
            kind=record.kind,
            summary=record.summary,
            thread_id=membership.thread_id if membership is not None else "",
            membership_relation=membership.relation if membership is not None else "unresolved",
            membership_confidence=membership.confidence if membership is not None else 0.0,
            confidence=record.confidence,
            source=record.source,
            created_at=cls._aware(record.created_at) or record.created_at,
        )

    @staticmethod
    def _current_membership_record(
        session: Session, segment_id: str
    ) -> ThreadMembershipRecord | None:
        return session.scalar(
            select(ThreadMembershipRecord)
            .where(
                ThreadMembershipRecord.segment_id == segment_id,
                ThreadMembershipRecord.status == "active",
            )
            .order_by(ThreadMembershipRecord.version.desc())
            .limit(1)
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
    ) -> tuple[ConversationThreadView, ...]:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(ConversationThreadRecord)
                    .where(
                        ConversationThreadRecord.owner_id == owner_id,
                        ConversationThreadRecord.connection_id == connection_id,
                        ConversationThreadRecord.guild_id == guild_id,
                        ConversationThreadRecord.channel_id == channel_id,
                        ConversationThreadRecord.discord_thread_id == discord_thread_id,
                        ConversationThreadRecord.status != "archived",
                    )
                    .order_by(ConversationThreadRecord.last_active_at.desc())
                    .limit(max(1, min(limit, 50)))
                )
            )
            for record in records:
                age = current - (self._aware(record.last_active_at) or current)
                desired = (
                    "hot"
                    if age <= timedelta(minutes=30)
                    else "warm"
                    if age <= timedelta(hours=6)
                    else "dormant"
                )
                if record.status != desired:
                    record.status = desired
                    record.updated_at = current
            session.commit()
        return tuple(self.thread_view(item) for item in records)

    def recent_threads_for_server(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        limit: int = 20,
        now: datetime | None = None,
    ) -> tuple[ConversationThreadView, ...]:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(ConversationThreadRecord)
                    .where(
                        ConversationThreadRecord.owner_id == owner_id,
                        ConversationThreadRecord.connection_id == connection_id,
                        ConversationThreadRecord.guild_id == guild_id,
                        ConversationThreadRecord.status != "archived",
                    )
                    .order_by(ConversationThreadRecord.last_active_at.desc())
                    .limit(max(1, min(limit, 100)))
                )
            )
            for record in records:
                age = current - (self._aware(record.last_active_at) or current)
                desired = (
                    "hot"
                    if age <= timedelta(minutes=30)
                    else "warm"
                    if age <= timedelta(hours=6)
                    else "dormant"
                )
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
        canonical_label: str,
        anchor_summary: str,
        working_summary: str,
        now: datetime,
    ) -> ConversationThreadView:
        anchor = " ".join(anchor_summary.split())[:4000]
        record = ConversationThreadRecord(
            id=str(uuid4()),
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            channel_id=channel_id,
            discord_thread_id=discord_thread_id,
            canonical_label=" ".join(canonical_label.split())[:240] or "Conversation thread",
            anchor_summary=anchor,
            working_summary=" ".join(working_summary.split())[:4000] or anchor,
            representative_segment_ids_json="[]",
            participant_ids_json="[]",
            active_entity_ids_json="[]",
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

    def update_thread_working_state(
        self,
        *,
        owner_id: str,
        thread_id: str,
        working_summary: str,
        participant_ids: tuple[str, ...] = (),
        active_entity_ids: tuple[str, ...] = (),
        representative_segment_id: str = "",
        now: datetime,
    ) -> ConversationThreadView | None:
        with self.database.session() as session:
            record = session.get(ConversationThreadRecord, thread_id)
            if record is None or record.owner_id != owner_id:
                return None
            compact = " ".join(working_summary.split())[:4000]
            if compact:
                record.working_summary = compact
            if participant_ids:
                values = list(_decode_strings(record.participant_ids_json)) + list(participant_ids)
                record.participant_ids_json = _encode_strings(values, limit=64)
            if active_entity_ids:
                values = list(_decode_strings(record.active_entity_ids_json)) + list(
                    active_entity_ids
                )
                record.active_entity_ids_json = _encode_strings(values, limit=32)
            if representative_segment_id:
                values = list(_decode_strings(record.representative_segment_ids_json))
                values.append(representative_segment_id)
                record.representative_segment_ids_json = _encode_strings(values, limit=8)
            record.status = "hot"
            record.last_active_at = now
            record.updated_at = now
            session.commit()
            session.refresh(record)
            return self.thread_view(record)

    def touch_thread(self, *, owner_id: str, thread_id: str, now: datetime) -> None:
        with self.database.session() as session:
            record = session.get(ConversationThreadRecord, thread_id)
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
                    select(ConversationSegmentV3Record).where(
                        ConversationSegmentV3Record.owner_id == owner_id,
                        ConversationSegmentV3Record.burst_id == burst_id,
                        ConversationSegmentV3Record.segment_key == segment_key,
                    )
                )
                if existing is not None:
                    membership = self._current_membership_record(session, existing.id)
                    values.append(self.segment_view(existing, membership))
                    continue
                message_ids = _string_items(item.get("message_ids"))
                participants = _string_items(item.get("participant_ids"))
                record = ConversationSegmentV3Record(
                    id=str(uuid4()),
                    owner_id=owner_id,
                    burst_id=burst_id,
                    segment_key=segment_key,
                    connection_id=connection_id,
                    guild_id=guild_id,
                    channel_id=channel_id,
                    discord_thread_id=discord_thread_id,
                    message_ids_json=_encode_strings(list(message_ids), limit=32),
                    participant_ids_json=_encode_strings(list(participants), limit=32),
                    kind=str(item.get("kind") or "discussion")[:32],
                    summary=str(item.get("summary") or "")[:4000],
                    confidence=_bounded_float(item.get("confidence")),
                    source=str(item.get("source") or "deterministic")[:32],
                    created_at=now,
                )
                session.add(record)
                session.flush()
                values.append(self.segment_view(record, None))
            session.commit()
        return tuple(values)

    def assign_membership(
        self,
        *,
        owner_id: str,
        segment_id: str,
        thread_id: str,
        relation: str,
        confidence: float,
        source: str,
        reason: str,
        now: datetime,
    ) -> ThreadMembershipView:
        allowed = {"belongs_to", "context_of", "reaction_to", "unresolved"}
        normalized_relation = relation if relation in allowed else "unresolved"
        normalized_thread = thread_id if normalized_relation != "unresolved" else ""
        with self.database.session() as session:
            segment = session.get(ConversationSegmentV3Record, segment_id)
            if segment is None or segment.owner_id != owner_id:
                raise KeyError("Conversation Segment not found.")
            current = self._current_membership_record(session, segment_id)
            version = 1
            if current is not None:
                if (
                    current.thread_id == normalized_thread
                    and current.relation == normalized_relation
                    and current.status == "active"
                ):
                    return self.membership_view(current)
                version = current.version + 1
                current.status = "superseded"
                current.superseded_at = now
            if normalized_thread:
                thread = session.get(ConversationThreadRecord, normalized_thread)
                if thread is None or thread.owner_id != owner_id:
                    normalized_thread = ""
                    normalized_relation = "unresolved"
            record = ThreadMembershipRecord(
                id=str(uuid4()),
                owner_id=owner_id,
                segment_id=segment_id,
                thread_id=normalized_thread,
                relation=normalized_relation,
                confidence=max(0.0, min(float(confidence), 1.0)),
                source=str(source)[:32],
                reason=" ".join(reason.split())[:500],
                version=version,
                status="active",
                created_at=now,
            )
            session.add(record)
            if normalized_thread:
                thread = session.get(ConversationThreadRecord, normalized_thread)
                if thread is not None:
                    reps = list(_decode_strings(thread.representative_segment_ids_json))
                    reps.append(segment_id)
                    thread.representative_segment_ids_json = _encode_strings(reps, limit=8)
                    participants = list(_decode_strings(thread.participant_ids_json))
                    participants.extend(_decode_strings(segment.participant_ids_json))
                    thread.participant_ids_json = _encode_strings(participants, limit=64)
                    thread.status = "hot"
                    thread.last_active_at = now
                    thread.updated_at = now
            session.commit()
            session.refresh(record)
            return self.membership_view(record)

    def membership_history(
        self,
        *,
        owner_id: str,
        segment_id: str,
    ) -> tuple[ThreadMembershipView, ...]:
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(ThreadMembershipRecord)
                    .where(
                        ThreadMembershipRecord.owner_id == owner_id,
                        ThreadMembershipRecord.segment_id == segment_id,
                    )
                    .order_by(ThreadMembershipRecord.version.asc())
                )
            )
        return tuple(self.membership_view(item) for item in records)

    def current_membership(
        self,
        *,
        owner_id: str,
        segment_id: str,
    ) -> ThreadMembershipView | None:
        with self.database.session() as session:
            record = session.scalar(
                select(ThreadMembershipRecord)
                .where(
                    ThreadMembershipRecord.owner_id == owner_id,
                    ThreadMembershipRecord.segment_id == segment_id,
                    ThreadMembershipRecord.status == "active",
                )
                .order_by(ThreadMembershipRecord.version.desc())
                .limit(1)
            )
        return self.membership_view(record) if record is not None else None

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
                    select(ConversationSegmentV3Record)
                    .where(
                        ConversationSegmentV3Record.owner_id == owner_id,
                        ConversationSegmentV3Record.connection_id == connection_id,
                        ConversationSegmentV3Record.guild_id == guild_id,
                    )
                    .order_by(ConversationSegmentV3Record.created_at.desc())
                    .limit(max(1, min(limit, 500)))
                )
            )
            values = [
                self.segment_view(item, self._current_membership_record(session, item.id))
                for item in records
            ]
        return tuple(values)

    def thread_for_message(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        discord_thread_id: str,
        message_id: str,
        limit: int = 250,
    ) -> ConversationThreadView | None:
        """Resolve a prior message through Segment→current ThreadMembership provenance."""

        if not message_id:
            return None
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(ConversationSegmentV3Record)
                    .where(
                        ConversationSegmentV3Record.owner_id == owner_id,
                        ConversationSegmentV3Record.connection_id == connection_id,
                        ConversationSegmentV3Record.guild_id == guild_id,
                        ConversationSegmentV3Record.channel_id == channel_id,
                        ConversationSegmentV3Record.discord_thread_id == discord_thread_id,
                    )
                    .order_by(ConversationSegmentV3Record.created_at.desc())
                    .limit(max(1, min(limit, 1000)))
                )
            )
            for segment in records:
                if message_id not in _decode_strings(segment.message_ids_json):
                    continue
                membership = self._current_membership_record(session, segment.id)
                if (
                    membership is None
                    or not membership.thread_id
                    or membership.relation == "unresolved"
                ):
                    return None
                thread = session.get(ConversationThreadRecord, membership.thread_id)
                if thread is None or thread.owner_id != owner_id or thread.status == "archived":
                    return None
                return self.thread_view(thread)
        return None

    def record_relation(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        discord_thread_id: str,
        source_message_id: str,
        relation_class: str,
        relation_type: str,
        target_ref_type: str,
        target_ref: str,
        confidence: float,
        source: str,
        evidence_refs: tuple[str, ...],
        status: str,
        now: datetime,
    ) -> MessageRelationView:
        with self.database.session() as session:
            existing = session.scalar(
                select(MessageRelationRecord)
                .where(
                    MessageRelationRecord.owner_id == owner_id,
                    MessageRelationRecord.connection_id == connection_id,
                    MessageRelationRecord.guild_id == guild_id,
                    MessageRelationRecord.channel_id == channel_id,
                    MessageRelationRecord.discord_thread_id == discord_thread_id,
                    MessageRelationRecord.source_message_id == source_message_id,
                    MessageRelationRecord.relation_type == relation_type,
                    MessageRelationRecord.target_ref_type == target_ref_type,
                    MessageRelationRecord.target_ref == target_ref,
                    MessageRelationRecord.status == status,
                )
                .order_by(MessageRelationRecord.created_at.desc())
                .limit(1)
            )
            if existing is not None:
                return self.relation_view(existing)
            record = MessageRelationRecord(
                id=str(uuid4()),
                owner_id=owner_id,
                connection_id=connection_id,
                guild_id=guild_id,
                channel_id=channel_id,
                discord_thread_id=discord_thread_id,
                source_message_id=source_message_id,
                relation_class=relation_class[:24],
                relation_type=relation_type[:40],
                target_ref_type=target_ref_type[:32],
                target_ref=target_ref[:240],
                confidence=max(0.0, min(float(confidence), 1.0)),
                source=source[:32],
                evidence_refs_json=_encode_strings(list(evidence_refs), limit=16),
                status=status[:24],
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return self.relation_view(record)

    def recent_relations(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        limit: int = 200,
    ) -> tuple[MessageRelationView, ...]:
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(MessageRelationRecord)
                    .where(
                        MessageRelationRecord.owner_id == owner_id,
                        MessageRelationRecord.connection_id == connection_id,
                        MessageRelationRecord.guild_id == guild_id,
                    )
                    .order_by(MessageRelationRecord.created_at.desc())
                    .limit(max(1, min(limit, 500)))
                )
            )
        return tuple(self.relation_view(item) for item in records)

    def merge_threads(
        self,
        *,
        owner_id: str,
        source_thread_id: str,
        target_thread_id: str,
        reason: str,
        now: datetime,
    ) -> int:
        """Move active memberships to the target while preserving versioned history."""

        if source_thread_id == target_thread_id:
            return 0
        with self.database.session() as session:
            source = session.get(ConversationThreadRecord, source_thread_id)
            target = session.get(ConversationThreadRecord, target_thread_id)
            if (
                source is None
                or target is None
                or source.owner_id != owner_id
                or target.owner_id != owner_id
            ):
                raise KeyError("Conversation Thread not found.")
            segment_ids = list(
                session.scalars(
                    select(ThreadMembershipRecord.segment_id).where(
                        ThreadMembershipRecord.owner_id == owner_id,
                        ThreadMembershipRecord.thread_id == source_thread_id,
                        ThreadMembershipRecord.status == "active",
                    )
                )
            )
        for segment_id in segment_ids:
            current = self.current_membership(owner_id=owner_id, segment_id=segment_id)
            if current is None:
                continue
            self.assign_membership(
                owner_id=owner_id,
                segment_id=segment_id,
                thread_id=target_thread_id,
                relation=current.relation,
                confidence=current.confidence,
                source="thread_merge",
                reason=reason,
                now=now,
            )
        with self.database.session() as session:
            source = session.get(ConversationThreadRecord, source_thread_id)
            if source is not None and source.owner_id == owner_id:
                source.status = "archived"
                source.updated_at = now
                session.commit()
        return len(segment_ids)

    def split_thread(
        self,
        *,
        owner_id: str,
        source_thread_id: str,
        segment_ids: tuple[str, ...],
        canonical_label: str,
        anchor_summary: str,
        reason: str,
        now: datetime,
    ) -> ConversationThreadView:
        with self.database.session() as session:
            source = session.get(ConversationThreadRecord, source_thread_id)
            if source is None or source.owner_id != owner_id:
                raise KeyError("Conversation Thread not found.")
            scope = (
                source.connection_id,
                source.guild_id,
                source.channel_id,
                source.discord_thread_id,
            )
        created = self.create_thread(
            owner_id=owner_id,
            connection_id=scope[0],
            guild_id=scope[1],
            channel_id=scope[2],
            discord_thread_id=scope[3],
            canonical_label=canonical_label,
            anchor_summary=anchor_summary,
            working_summary=anchor_summary,
            now=now,
        )
        for segment_id in segment_ids:
            current = self.current_membership(owner_id=owner_id, segment_id=segment_id)
            if current is None or current.thread_id != source_thread_id:
                continue
            self.assign_membership(
                owner_id=owner_id,
                segment_id=segment_id,
                thread_id=created.id,
                relation=current.relation,
                confidence=current.confidence,
                source="thread_split",
                reason=reason,
                now=now,
            )
        return created


__all__ = [
    "ConversationSegmentView",
    "ConversationStructureRepository",
    "ConversationThreadView",
    "MessageRelationView",
    "ThreadMembershipView",
]
