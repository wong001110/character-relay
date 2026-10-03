"""Transactional room sources and immutable selection handoffs.

Room locking serializes observations across workers on PostgreSQL. SQLite's
process lock is only for local development; it is not a distributed authority.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from threading import RLock
from uuid import uuid4
from weakref import WeakKeyDictionary

from pydantic import ValidationError
from sqlalchemy import JSON, Engine, cast, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from echo_masque.persistence.conversation_media_models import ConversationMediaReferenceRecord
from echo_masque.persistence.database import Database
from echo_masque.persistence.note_models import CharacterNoteRecord
from echo_masque.persistence.room_models import (
    RoomDeliverySourceRecord,
    RoomRouteRecord,
    RoomSelectionRecord,
    RoomSourceRecord,
    RoomStateRecord,
)
from echo_masque.room_routing import RoomScope, SpeakerChoice
from echo_masque.room_sources import (
    FocusedContext,
    SourceMessage,
    SourceUnavailable,
    StoredSource,
    delivery_key,
    evidence_key,
    scope_key,
)
from echo_masque.sparse_retrieval import semantic_tokens

_LOCKS: WeakKeyDictionary[Engine, RLock] = WeakKeyDictionary()
_LOCKS_GUARD = RLock()


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _source_from_json(content_json: str) -> SourceMessage:
    try:
        return SourceMessage.model_validate_json(content_json)
    except ValidationError:
        raw = json.loads(content_json)
        if not isinstance(raw, dict) or not raw.get("deleted"):
            raise
        # Older tombstones could retain presentation-only metadata because model_copy()
        # preserved the previous message body. Sanitize that historical shape on read.
        raw.update(
            {
                "text": "",
                "attachments": [],
                "custom_emojis": [],
                "stickers": [],
                "mentions": [],
                "embeds": [],
                "poll": None,
                "reactions": [],
                "pinned": False,
                "has_unseen_media": False,
                "media_fingerprint": "",
            }
        )
        return SourceMessage.model_validate(raw)


def _stored(record: RoomSourceRecord) -> StoredSource:
    return StoredSource(
        _source_from_json(record.content_json),
        record.revision,
        record.room_revision,
    )


class RoomRepository:
    def __init__(self, database: Database) -> None:
        self.database = database
        with _LOCKS_GUARD:
            self._lock = _LOCKS.setdefault(database.engine, RLock())

    def _room(self, session: Session, scope: RoomScope) -> RoomStateRecord:
        insert = pg_insert if self.database.engine.dialect.name == "postgresql" else sqlite_insert
        session.execute(
            insert(RoomStateRecord)
            .values(
                id=scope_key(scope),
                scope_json=scope.model_dump_json(),
                revision=0,
                readable=True,
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )
        record = session.scalar(
            select(RoomStateRecord).where(RoomStateRecord.id == scope_key(scope)).with_for_update()
        )
        assert record is not None
        return record

    def observe(self, scope: RoomScope, messages: Sequence[SourceMessage]) -> int:
        """Reject cross-room/identity changes; edits are ordered and tombstones are sticky."""
        if len(messages) > 64 or any(not item.in_scope(scope) for item in messages):
            raise ValueError("source_scope_mismatch")
        with self._lock, self.database.session() as session:
            room = self._room(session, scope)
            if not room.readable:
                raise SourceUnavailable("room_access_revoked")
            for item in messages:
                record = session.get(RoomSourceRecord, evidence_key(scope, item.message_id))
                if record is not None:
                    old = _source_from_json(record.content_json)
                    if old.deleted:
                        continue
                    if item.deleted:
                        # Erase readable and presentation content. Reactions/media from a deleted
                        # message are not valid evidence and must not poison later Web snapshots.
                        item = old.model_copy(
                            update={
                                "deleted": True,
                                "text": "",
                                "attachments": (),
                                "custom_emojis": (),
                                "stickers": (),
                                "mentions": (),
                                "embeds": (),
                                "poll": None,
                                "reactions": (),
                                "pinned": False,
                                "has_unseen_media": False,
                                "media_fingerprint": "",
                            }
                        )
                    else:
                        if (
                            old.author_id != item.author_id
                            or old.author_is_bot != item.author_is_bot
                        ):
                            raise ValueError("source_author_conflict")
                        if old.author_deployment_id and item.author_deployment_id not in {
                            "",
                            old.author_deployment_id,
                        }:
                            raise ValueError("source_character_conflict")
                        if item.effective_time() < old.effective_time():
                            continue
                        if item.effective_time() == old.effective_time() and old.content_available:
                            # An equal-version enrichment cannot replace readable text.
                            item = item.model_copy(
                                update={
                                    "text": old.text,
                                    "content_available": old.content_available,
                                }
                            )
                        if not item.author_deployment_id and old.author_deployment_id:
                            item = item.model_copy(
                                update={"author_deployment_id": old.author_deployment_id}
                            )
                    # Presentation-only enrichment (avatar/name/pin/reaction counts) is visible
                    # to Web Room clients but must not advance Agent source versions or
                    # invalidate a generated Character draft.
                    if old.draft_fingerprint() == item.draft_fingerprint():
                        if not item.response_to_message_id and old.response_to_message_id:
                            item = item.model_copy(
                                update={
                                    "response_to_message_id": old.response_to_message_id,
                                    "response_delivery_complete": old.response_delivery_complete,
                                }
                            )
                        if old != item:
                            record.content_json = item.model_dump_json()
                            session.flush()
                        continue
                    if not item.response_to_message_id and old.response_to_message_id:
                        item = item.model_copy(
                            update={
                                "response_to_message_id": old.response_to_message_id,
                                "response_delivery_complete": old.response_delivery_complete,
                            }
                        )
                    if old == item:
                        continue
                session.execute(
                    delete(CharacterNoteRecord).where(
                        CharacterNoteRecord.scope_id == room.id,
                        CharacterNoteRecord.source_message_id == item.message_id,
                        CharacterNoteRecord.authored.is_(False),
                        CharacterNoteRecord.source_hash != item.draft_fingerprint(),
                    )
                )
                # Erase stale derived perception as well as notes. Other rooms/cards retain
                # their own source checks; no broad guild-level "any source visible" fallback.
                session.execute(delete(ConversationMediaReferenceRecord).where(
                    ConversationMediaReferenceRecord.owner_id == scope.owner_id,
                    ConversationMediaReferenceRecord.guild_id == scope.guild_id,
                    ConversationMediaReferenceRecord.channel_id == scope.channel_id,
                    ConversationMediaReferenceRecord.thread_id == scope.thread_id,
                    ConversationMediaReferenceRecord.message_id == item.message_id,
                    ConversationMediaReferenceRecord.context_json != "",
                    ConversationMediaReferenceRecord.source_fingerprint != item.draft_fingerprint(),
                ))
                room.revision += 1
                if record is None:
                    record = RoomSourceRecord(
                        id=evidence_key(scope, item.message_id),
                        scope_id=room.id,
                        message_id=item.message_id,
                        content_json=item.model_dump_json(),
                        revision=1,
                        room_revision=room.revision,
                        created_at=item.created_at or datetime.now(UTC),
                    )
                    session.add(record)
                else:
                    record.content_json = item.model_dump_json()
                    record.revision += 1
                    record.room_revision = room.revision
                session.flush()
            room.updated_at = datetime.now(UTC)
            session.commit()
            return room.revision

    def set_access(
        self, scope: RoomScope, *, readable: bool, checked_at: datetime | None = None
    ) -> None:
        """Only the authenticated adapter's fresh platform permission check calls this."""
        with self._lock, self.database.session() as session:
            room = self._room(session, scope)
            observed = checked_at or datetime.now(UTC)
            if observed.tzinfo is None:
                raise ValueError("permission_timestamp_requires_timezone")
            if room.permission_checked_at is not None:
                previous = _aware(room.permission_checked_at)
                # Late queued ingress cannot reopen access revoked by a newer platform check.
                if observed < previous or (observed == previous and not room.readable):
                    return
            room.permission_checked_at = observed
            if room.readable != readable:
                room.readable = readable
                room.revision += 1
            session.commit()

    def get(self, scope: RoomScope, message_id: str) -> StoredSource | None:
        with self._lock, self.database.session() as session:
            room = session.get(RoomStateRecord, scope_key(scope))
            if room is None or not room.readable:
                return None
            record = session.get(RoomSourceRecord, evidence_key(scope, message_id))
            return _stored(record) if record is not None else None

    def can_read(self, scope: RoomScope, *, max_age_seconds: int | None = None) -> bool:
        with self._lock, self.database.session() as session:
            room = session.get(RoomStateRecord, scope_key(scope))
            if room is None or not room.readable:
                return False
            return max_age_seconds is None or (
                room.permission_checked_at is not None
                and 0
                <= (datetime.now(UTC) - _aware(room.permission_checked_at)).total_seconds()
                <= max_age_seconds
            )

    def search(
        self, scope: RoomScope, query: str, *, candidate_limit: int = 240
    ) -> tuple[StoredSource, ...]:
        """SQL sparse prefilter of this exact room before bounded in-process ranking.

        Old evidence is searchable even after it leaves recent context. No automatic
        embedding, semantic Thread, Episode summary or all-room scan is involved.
        """
        if not 1 <= candidate_limit <= 240 or not query.strip() or len(query) > 800:
            raise ValueError("invalid_history_query")
        terms = tuple(dict.fromkeys(semantic_tokens(query)))[:16]
        if not terms:
            return ()
        with self._lock, self.database.session() as session:
            room = session.get(RoomStateRecord, scope_key(scope))
            if room is None or not room.readable:
                return ()
            text = (
                cast(RoomSourceRecord.content_json, JSON)["text"].as_string()
                if self.database.engine.dialect.name == "postgresql"
                else func.json_extract(RoomSourceRecord.content_json, "$.text")
            )
            rows = session.scalars(
                select(RoomSourceRecord)
                .where(
                    RoomSourceRecord.scope_id == room.id,
                    or_(
                        *(
                            func.lower(text).contains(term.casefold(), autoescape=True)
                            for term in terms
                        )
                    ),
                )
                .order_by(RoomSourceRecord.created_at.desc(), RoomSourceRecord.id)
                .limit(candidate_limit)
            ).all()
            return tuple(
                item
                for row in rows
                if not (item := _stored(row)).message.deleted and item.message.content_available
            )

    def recent(self, scope: RoomScope, *, limit: int = 24) -> tuple[StoredSource, ...]:
        if not 1 <= limit <= 64:
            raise ValueError("invalid_source_limit")
        with self._lock, self.database.session() as session:
            room = session.get(RoomStateRecord, scope_key(scope))
            if room is None or not room.readable:
                return ()
            records = session.scalars(
                select(RoomSourceRecord)
                .where(
                    RoomSourceRecord.scope_id == room.id,
                )
                .order_by(RoomSourceRecord.created_at.desc(), RoomSourceRecord.id.desc())
                .limit(limit)
            ).all()
            return tuple(_stored(record) for record in reversed(records))

    def focus(
        self,
        scope: RoomScope,
        target_message_id: str,
        *,
        recent_limit: int = 12,
        ancestor_limit: int = 8,
        char_limit: int = 24000,
    ) -> FocusedContext:
        if (
            not 0 <= recent_limit <= 20
            or not 0 <= ancestor_limit <= 8
            or not 10000 <= char_limit <= 32000
        ):
            raise ValueError("invalid_context_budget")
        with self._lock, self.database.session() as session:
            room = session.scalar(
                select(RoomStateRecord)
                .where(RoomStateRecord.id == scope_key(scope))
                .with_for_update()
            )
            if room is None or not room.readable:
                raise SourceUnavailable("room_unavailable")
            target = session.get(RoomSourceRecord, evidence_key(scope, target_message_id))
            if target is None:
                raise SourceUnavailable("target_unavailable")
            current = _stored(target)
            if current.message.deleted or not current.message.content_available:
                raise SourceUnavailable("target_unavailable")
            anchors = [current]
            missing: list[str] = []
            seen = {target_message_id}
            for _ in range(ancestor_limit):
                parent_id = (
                    current.message.reply_to_message_id or current.message.response_to_message_id
                )
                if not parent_id or parent_id in seen:
                    break
                seen.add(parent_id)
                parent = session.get(RoomSourceRecord, evidence_key(scope, parent_id))
                if parent is None:
                    missing.append(parent_id)
                    break
                current = _stored(parent)
                if current.message.deleted or not current.message.content_available:
                    missing.append(parent_id)
                    break
                anchors.append(current)
            # Anchor and closest ancestors take precedence over a recent unrelated burst.
            selected: dict[str, StoredSource] = {}
            chars = 0
            for source in anchors:
                if chars + len(source.message.text) > char_limit:
                    missing.append(source.message.message_id)
                    break
                selected[source.message.message_id] = source
                chars += len(source.message.text)
            records = session.scalars(
                select(RoomSourceRecord)
                .where(
                    RoomSourceRecord.scope_id == room.id,
                )
                .order_by(RoomSourceRecord.created_at.desc(), RoomSourceRecord.id.desc())
                .limit(recent_limit)
            ).all()
            for record in records:
                source = _stored(record)
                if source.message.deleted or not source.message.content_available:
                    continue
                if (
                    source.message.message_id in selected
                    or chars + len(source.message.text) > char_limit
                ):
                    continue
                selected[source.message.message_id] = source
                chars += len(source.message.text)
            sources = tuple(
                sorted(
                    selected.values(),
                    key=lambda source: (
                        source.message.created_at or datetime.min.replace(tzinfo=UTC),
                        source.message.message_id,
                    ),
                )
            )
            return FocusedContext(
                scope,
                target_message_id,
                sources,
                tuple(
                    source.message.message_id
                    for source in anchors
                    if source.message.message_id in selected
                ),
                tuple(missing),
                room.revision,
            )

    def select(
        self,
        scope: RoomScope,
        *,
        request_id: str,
        trigger_message_id: str,
        requester_id: str,
        requester_is_bot: bool,
        choice: SpeakerChoice,
        origin: str,
    ) -> RoomSelectionRecord:
        if origin not in {"direct", "ambient", "continuation", "context_action"}:
            raise ValueError("invalid_selection_origin")
        focus = self.focus(scope, choice.target_message_id)
        record = RoomSelectionRecord(
            id=str(uuid4()),
            scope_id=scope_key(scope),
            request_id=request_id,
            trigger_message_id=trigger_message_id,
            deployment_id=choice.speaker,
            requester_id=requester_id,
            requester_is_bot=requester_is_bot,
            target_message_id=choice.target_message_id,
            mode=choice.mode,
            origin=origin,
            focus_json=json.dumps(
                {
                    "fingerprint": focus.fingerprint,
                    "sources": [
                        [source.message.message_id, source.revision] for source in focus.sources
                    ],
                    "anchor_ids": focus.anchor_ids,
                    "room_revision": focus.room_revision,
                }
            ),
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )
        with self._lock, self.database.session() as session:
            session.add(record)
            session.commit()
        return record

    def selection(
        self, scope: RoomScope, selection_id: str, deployment_id: str
    ) -> RoomSelectionRecord:
        with self._lock, self.database.session() as session:
            record = session.get(RoomSelectionRecord, selection_id)
            if (
                record is None
                or record.scope_id != scope_key(scope)
                or record.deployment_id != deployment_id
                or _aware(record.expires_at) <= datetime.now(UTC)
            ):
                raise SourceUnavailable("selection_unavailable")
            return record

    def reserve_route(
        self,
        scope: RoomScope,
        *,
        request_id: str,
        input_hash: str,
        requester_id: str,
        optional: bool,
        cooldown_seconds: int = 15,
        window_seconds: int = 600,
        max_optional_attempts: int = 12,
    ) -> tuple[str, RoomRouteRecord | None]:
        """Reserve before awaiting a model, so repeated events cannot spend twice."""
        key = hashlib.sha256(json.dumps([scope_key(scope), request_id]).encode()).hexdigest()
        now = datetime.now(UTC)
        with self._lock, self.database.session() as session:
            room = self._room(session, scope)
            if not room.readable:
                return "room_access_revoked", None
            existing = session.get(RoomRouteRecord, key)
            if existing is not None:
                if existing.input_hash != input_hash or existing.requester_id != requester_id:
                    raise ValueError("routing_request_conflict")
                return "replay" if existing.result_json else "routing_in_progress", existing
            if optional:
                conditions = (
                    RoomRouteRecord.scope_id == room.id,
                    RoomRouteRecord.optional.is_(True),
                )
                last = session.scalar(
                    select(RoomRouteRecord)
                    .where(*conditions)
                    .order_by(RoomRouteRecord.created_at.desc())
                    .limit(1)
                )
                if (
                    last is not None
                    and _aware(last.created_at) + timedelta(seconds=cooldown_seconds) > now
                ):
                    return "room_cooldown", None
                count = (
                    session.scalar(
                        select(func.count())
                        .select_from(RoomRouteRecord)
                        .where(
                            *conditions,
                            RoomRouteRecord.created_at >= now - timedelta(seconds=window_seconds),
                        )
                    )
                    or 0
                )
                if count >= max_optional_attempts:
                    return "room_attempt_limit", None
            record = RoomRouteRecord(
                id=key,
                scope_id=room.id,
                request_id=request_id,
                input_hash=input_hash,
                requester_id=requester_id,
                optional=optional,
            )
            session.add(record)
            session.commit()
            return "reserved", record

    def finish_route(self, route_id: str, *, status: str, result_json: str) -> None:
        with self._lock, self.database.session() as session:
            record = session.get(RoomRouteRecord, route_id)
            if record is None or record.result_json:
                raise ValueError("routing_receipt_conflict")
            record.status = status
            record.result_json = result_json
            record.completed_at = datetime.now(UTC)
            session.commit()

    def delivery_source(self, scope: RoomScope, message_id: str) -> RoomDeliverySourceRecord | None:
        with self.database.session() as session:
            return session.get(RoomDeliverySourceRecord, delivery_key(scope, message_id))
