"""Serialized per-user/room/participant reading progress over existing current sources."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, cast, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement, Select

from echo_masque.agent_reading import (
    AgentReadingBatch,
    AgentReadingItem,
    AgentReadingReference,
    AgentReadingStatus,
)
from echo_masque.persistence.agent_reading_models import AgentReadingCursorRecord
from echo_masque.persistence.models import AuthSessionRecord, UserRecord
from echo_masque.persistence.room_models import RoomSourceRecord, RoomStateRecord
from echo_masque.persistence.room_repository import _aware, _source_from_json
from echo_masque.persistence.web_room_models import WebProfileRecord, WebRoomRecord
from echo_masque.persistence.web_room_repository import WebRoomRepository
from echo_masque.public_demo import is_public_demo_email
from echo_masque.room_sources import SourceMessage, scope_key
from echo_masque.web_room_message import message_summary, web_message_view
from echo_masque.web_rooms import WebRoomError, room_scope


class AgentReadingRepository:
    def __init__(self, rooms: WebRoomRepository) -> None:
        self.rooms = rooms
        self.database = rooms.database

    @contextmanager
    def _scoped(
        self,
        room_id: str,
        user_id: str,
        profile_id: str,
        session_id: str,
    ) -> Iterator[tuple[Session, RoomStateRecord, AgentReadingCursorRecord | None]]:
        # Shared with observe(): SQLite serialization and PostgreSQL room row ordering.
        with self.rooms.sources._lock, self.database.session() as session:
            room = session.scalar(
                select(WebRoomRecord).where(WebRoomRecord.id == room_id).with_for_update()
            )
            if room is None:
                raise WebRoomError("room_unavailable", 404)
            state = session.scalar(
                select(RoomStateRecord)
                .where(
                    RoomStateRecord.id == scope_key(room_scope(room)),
                )
                .with_for_update()
            )
            user = session.get(UserRecord, user_id)
            auth = session.get(AuthSessionRecord, session_id)
            now = datetime.now(UTC)
            if (
                user is None
                or not user.is_active
                or auth is None
                or auth.user_id != user_id
                or auth.revoked_at is not None
                or _aware(auth.expires_at) <= now
            ):
                raise WebRoomError("session_unavailable", 401)
            if is_public_demo_email(user.email):
                raise WebRoomError("agent_reading_demo_unavailable", 403)
            if not self.rooms._access(session, room, user_id):
                raise WebRoomError("room_unavailable", 404)
            profile = session.scalar(
                select(WebProfileRecord)
                .where(
                    WebProfileRecord.id == profile_id,
                )
                .with_for_update()
            )
            if profile is None or profile.owner_id != user_id:
                raise WebRoomError("profile_unavailable", 404)
            if (
                state is None
                or not state.readable
                or state.permission_checked_at is None
                or not 0 <= (now - _aware(state.permission_checked_at)).total_seconds() <= 90
            ):
                raise WebRoomError("room_connection_unavailable", 503)
            cursor = session.scalar(
                select(AgentReadingCursorRecord).where(
                    AgentReadingCursorRecord.user_id == user_id,
                    AgentReadingCursorRecord.room_id == room_id,
                    AgentReadingCursorRecord.profile_id == profile_id,
                )
            )
            yield session, state, cursor

    @staticmethod
    def _create(
        session: Session, room_id: str, user_id: str, profile_id: str
    ) -> AgentReadingCursorRecord:
        record = AgentReadingCursorRecord(
            id=hashlib.sha256(json.dumps([user_id, room_id, profile_id]).encode()).hexdigest(),
            user_id=user_id,
            room_id=room_id,
            profile_id=profile_id,
            cursor_revision=0,
            gap_generation=1,
            completed_gap_generation=0,
            last_gap_event_id="",
            batch_id="",
            batch_from_revision=0,
            batch_to_revision=0,
            batch_gap_generation=0,
            batch_needs_reread=0,
            batch_references_json="[]",
            last_completed_batch_id="",
        )
        session.add(record)
        return record

    def _eligible(self, state: RoomStateRecord, profile_id: str) -> ColumnElement[bool]:
        # Filter verified provenance in SQL, never by display name. COUNT can scan the
        # scoped index, but each response materializes at most 64 source bodies.
        external = (
            cast(RoomSourceRecord.content_json, JSON)["author_external_id"].as_string()
            if self.database.engine.dialect.name == "postgresql"
            else func.json_extract(RoomSourceRecord.content_json, "$.author_external_id")
        )
        return (RoomSourceRecord.scope_id == state.id) & (func.coalesce(external, "") != profile_id)

    @staticmethod
    def _rows(
        session: Session, statement: Select[tuple[RoomSourceRecord]]
    ) -> list[tuple[RoomSourceRecord, SourceMessage]]:
        return [
            (record, _source_from_json(record.content_json))
            for record in session.scalars(statement)
        ]

    @staticmethod
    def _reference(row: RoomSourceRecord, message: SourceMessage) -> AgentReadingReference:
        return AgentReadingReference(
            message_id=row.message_id,
            source_revision=row.revision,
            room_revision=row.room_revision,
            change="deleted"
            if message.deleted
            else "unavailable"
            if not message.content_available
            else "new"
            if row.revision == 1
            else "edited",
        )

    def _status(
        self,
        session: Session,
        state: RoomStateRecord,
        room_id: str,
        profile_id: str,
        cursor: AgentReadingCursorRecord | None,
    ) -> AgentReadingStatus:
        revision = cursor.cursor_revision if cursor else 0
        batch = None
        if cursor is not None and cursor.batch_id:
            items: list[AgentReadingItem] = []
            references = [
                AgentReadingReference.model_validate(item)
                for item in json.loads(cursor.batch_references_json)
            ]
            rows = self._rows(
                session,
                select(RoomSourceRecord)
                .where(
                    self._eligible(state, profile_id),
                    RoomSourceRecord.message_id.in_([entry.message_id for entry in references]),
                )
                .limit(64),
            )
            live = {record.message_id: (record, message) for record, message in rows}
            for ref in references:
                current = live.get(ref.message_id)
                if current is None or current[1].deleted:
                    items.append(
                        AgentReadingItem(**ref.model_dump(), state="removed", message=None)
                    )
                    continue
                row, message = current
                if row.revision != ref.source_revision or row.room_revision != ref.room_revision:
                    items.append(
                        AgentReadingItem(**ref.model_dump(), state="changed", message=None)
                    )
                    continue
                if not message.content_available:
                    items.append(
                        AgentReadingItem(
                            **ref.model_dump(),
                            state="current",
                            message=None,
                        )
                    )
                    continue
                reply_id = message.reply_to_message_id or message.response_to_message_id
                # Reply summaries are limited to this fixed batch's captured references.
                # A later parent edit must not leak newer text into an earlier batch.
                reply_ref = next(
                    (entry for entry in references if entry.message_id == reply_id), None
                )
                reply_current = live.get(reply_id)
                reply_message = reply_current[1] if reply_current else None
                available = bool(
                    reply_ref
                    and reply_current
                    and reply_message
                    and reply_current[0].revision == reply_ref.source_revision
                    and reply_current[0].room_revision == reply_ref.room_revision
                    and not reply_message.deleted
                    and reply_message.content_available
                )
                preview: dict[str, object] | None = None
                if reply_id:
                    preview = {
                        "message_id": reply_id,
                        "available": available,
                        "in_snapshot": reply_ref is not None,
                        "display_name": reply_message.author_display_name
                        if available and reply_message
                        else "",
                        "summary": message_summary(reply_message) if available else "",
                    }
                reactions = [
                    {
                        "key": entry.key,
                        "resource_id": entry.resource_id,
                        "name": entry.name,
                        "animated": entry.animated,
                        "asset_url": entry.asset_url,
                        "discord_count": entry.count,
                        "web_count": 0,
                        "mine": False,
                        "mine_profile_ids": [],
                        "count": entry.count,
                    }
                    for entry in message.reactions
                ]
                items.append(
                    AgentReadingItem(
                        **ref.model_dump(),
                        state="current",
                        message=web_message_view(
                            message, reply_id=reply_id, reply_preview=preview, reactions=reactions
                        ),
                    )
                )
            batch = AgentReadingBatch(
                id=cursor.batch_id,
                from_revision=cursor.batch_from_revision,
                to_revision=cursor.batch_to_revision,
                gap_generation=cursor.batch_gap_generation,
                needs_reread=bool(cursor.batch_needs_reread),
                items=items,
            )
        return AgentReadingStatus(
            room_id=room_id,
            profile_id=profile_id,
            cursor_revision=revision,
            observed_revision=state.revision,
            pending_count=session.scalar(
                select(func.count())
                .select_from(RoomSourceRecord)
                .where(
                    self._eligible(state, profile_id),
                    RoomSourceRecord.room_revision > revision,
                )
            )
            or 0,
            needs_reread=cursor is None or cursor.gap_generation > cursor.completed_gap_generation,
            gap_generation=cursor.gap_generation if cursor else 1,
            batch=batch,
        )

    def status(
        self, room_id: str, user_id: str, profile_id: str, *, session_id: str
    ) -> AgentReadingStatus:
        with self._scoped(room_id, user_id, profile_id, session_id) as (session, state, cursor):
            return self._status(session, state, room_id, profile_id, cursor)

    def gap(
        self, room_id: str, user_id: str, profile_id: str, *, session_id: str, event_id: str
    ) -> AgentReadingStatus:
        with self._scoped(room_id, user_id, profile_id, session_id) as (session, state, cursor):
            cursor = cursor or self._create(session, room_id, user_id, profile_id)
            if event_id != cursor.last_gap_event_id:
                cursor.gap_generation += 1
                cursor.last_gap_event_id = event_id
            result = self._status(session, state, room_id, profile_id, cursor)
            session.commit()
            return result

    def batch(
        self, room_id: str, user_id: str, profile_id: str, *, session_id: str
    ) -> AgentReadingStatus:
        with self._scoped(room_id, user_id, profile_id, session_id) as (session, state, cursor):
            cursor = cursor or self._create(session, room_id, user_id, profile_id)
            if not cursor.batch_id:
                pending = self._rows(
                    session,
                    select(RoomSourceRecord)
                    .where(
                        self._eligible(state, profile_id),
                        RoomSourceRecord.room_revision > cursor.cursor_revision,
                    )
                    .order_by(RoomSourceRecord.room_revision, RoomSourceRecord.id)
                    .limit(65),
                )
                chosen = pending[:64]
                cutoff = chosen[-1][0].room_revision if len(pending) > 64 else state.revision
                reread = cursor.gap_generation > cursor.completed_gap_generation
                if reread and len(chosen) < 64:
                    selected_ids = {row.id for row, _ in chosen}
                    context = self._rows(
                        session,
                        select(RoomSourceRecord)
                        .where(
                            self._eligible(state, profile_id),
                            RoomSourceRecord.id.not_in(selected_ids),
                            RoomSourceRecord.room_revision <= cutoff,
                        )
                        .order_by(RoomSourceRecord.created_at.desc(), RoomSourceRecord.id.desc())
                        .limit(64 - len(chosen)),
                    )
                    chosen += context[: 64 - len(chosen)]
                cursor.batch_id = uuid4().hex
                cursor.batch_from_revision = cursor.cursor_revision
                cursor.batch_to_revision = cutoff
                cursor.batch_gap_generation = cursor.gap_generation
                cursor.batch_needs_reread = int(reread)
                cursor.batch_references_json = json.dumps(
                    [self._reference(row, message).model_dump() for row, message in chosen]
                )
            result = self._status(session, state, room_id, profile_id, cursor)
            session.commit()
            return result

    def complete(
        self, room_id: str, user_id: str, profile_id: str, *, session_id: str, batch_id: str
    ) -> AgentReadingStatus:
        with self._scoped(room_id, user_id, profile_id, session_id) as (session, state, cursor):
            if (
                not batch_id
                or cursor is None
                or batch_id not in {cursor.batch_id, cursor.last_completed_batch_id}
            ):
                raise WebRoomError("agent_reading_batch_conflict", 409)
            if batch_id == cursor.batch_id:
                cursor.cursor_revision = cursor.batch_to_revision
                cursor.completed_gap_generation = max(
                    cursor.completed_gap_generation, cursor.batch_gap_generation
                )
                cursor.last_completed_batch_id = cursor.batch_id
                cursor.batch_id = ""
                cursor.batch_references_json = "[]"
            result = self._status(session, state, room_id, profile_id, cursor)
            session.commit()
            return result
