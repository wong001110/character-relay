"""Scoped, versioned explicit notes with source checks before storage and disclosure.

A member can save an exact excerpt from their own readable message, not somebody
else's assertion or a model's inferred psychology. Operator-authored background is
an explicit separate operation. Notes are never a grant or a participation signal.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import uuid4

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from echo_masque.notes import NoteAccessDenied, NoteConflict, NoteInput, NoteView
from echo_masque.persistence.database import Database
from echo_masque.persistence.models import CharacterCardRecord
from echo_masque.persistence.note_models import CharacterNoteRecord, NoteCreationReceiptRecord
from echo_masque.persistence.room_models import RoomSourceRecord, RoomStateRecord
from echo_masque.persistence.room_repository import RoomRepository
from echo_masque.room_routing import RoomScope
from echo_masque.room_sources import SourceMessage, evidence_key, scope_key


def _view(record: CharacterNoteRecord) -> NoteView:
    return NoteView(
        id=record.id,
        character_card_id=record.character_card_id,
        scope=RoomScope.model_validate_json(record.scope_json) if record.scope_json else None,
        subject_ref=record.subject_ref,
        kind=cast(Literal["note", "relationship"], record.kind),
        text=record.text,
        authored=record.authored,
        actor_id=record.actor_id,
        source_message_id=record.source_message_id,
        version=record.version,
        updated_at=record.updated_at,
    )


class CharacterNoteRepository:
    def __init__(self, database: Database) -> None:
        self.database = database
        # The room lock is only a SQLite/local-process aid; PG serializes on the card row.
        self._rooms = RoomRepository(database)

    @staticmethod
    def _card(session: Session, owner_id: str, card_id: str) -> None:
        card = session.scalar(
            select(CharacterCardRecord)
            .where(CharacterCardRecord.id == card_id, CharacterCardRecord.owner_id == owner_id)
            .with_for_update()
        )
        if card is None:
            raise NoteAccessDenied("character_unavailable")

    @staticmethod
    def _source(
        session: Session, scope: RoomScope, actor_id: str, source_id: str, text: str
    ) -> str:
        room = session.get(RoomStateRecord, scope_key(scope))
        source = session.get(RoomSourceRecord, evidence_key(scope, source_id))
        if room is None or not room.readable or source is None:
            raise NoteAccessDenied("note_source_unavailable")
        message = SourceMessage.model_validate_json(source.content_json)
        if (
            message.deleted
            or not message.content_available
            or message.author_is_bot
            or message.author_id != actor_id
        ):
            raise NoteAccessDenied("note_source_not_actor")
        if text not in message.text:
            raise NoteConflict("note_must_quote_explicit_source")
        return message.draft_fingerprint()

    @staticmethod
    def _current_source(session: Session, record: CharacterNoteRecord) -> bool:
        if not record.source_message_id:
            return record.authored
        scope = RoomScope.model_validate_json(record.scope_json)
        source = session.get(RoomSourceRecord, evidence_key(scope, record.source_message_id))
        if source is None:
            return False
        message = SourceMessage.model_validate_json(source.content_json)
        return (
            not message.deleted
            and message.content_available
            and not message.author_is_bot
            and message.author_id == record.actor_id
            and message.draft_fingerprint() == record.source_hash
        )

    def create(
        self,
        *,
        owner_id: str,
        card_id: str,
        payload: NoteInput,
        scope: RoomScope | None = None,
        actor_id: str = "",
        source_message_id: str = "",
        request_id: str = "",
        authored: bool = False,
    ) -> NoteView:
        if scope is not None and scope.owner_id != owner_id:
            raise NoteAccessDenied("note_scope_mismatch")
        if authored:
            if source_message_id:
                raise NoteConflict("authored_note_has_no_member_source")
            actor_id = owner_id
        elif (
            scope is None
            or not actor_id
            or not source_message_id
            or not request_id
            or payload.subject_ref != f"user:{actor_id}"
        ):
            raise NoteAccessDenied("explicit_own_note_required")
        identity = (
            hashlib.sha256(
                json.dumps(
                    [owner_id, card_id, scope_key(scope) if scope else "", actor_id, request_id],
                    ensure_ascii=False,
                ).encode()
            ).hexdigest()
            if request_id
            else uuid4().hex
        )
        with self._rooms._lock, self.database.session() as session:
            self._card(session, owner_id, card_id)
            source_hash = ""
            if not authored:
                assert scope is not None
                source_hash = self._source(
                    session, scope, actor_id, source_message_id, payload.text
                )
            existing = session.get(CharacterNoteRecord, identity)
            if existing is not None:
                if (
                    existing.text != payload.text
                    or existing.subject_ref != payload.subject_ref
                    or existing.kind != payload.kind
                    or existing.authored != authored
                    or existing.source_message_id != source_message_id
                ):
                    raise NoteConflict("note_request_reused")
                return _view(existing)
            if session.get(NoteCreationReceiptRecord, identity) is not None:
                raise NoteConflict("note_request_retired")
            count = (
                session.scalar(
                    select(func.count())
                    .select_from(CharacterNoteRecord)
                    .where(
                        CharacterNoteRecord.owner_id == owner_id,
                        CharacterNoteRecord.character_card_id == card_id,
                    )
                )
                or 0
            )
            if count >= 256:
                raise NoteConflict("character_note_capacity")
            record = CharacterNoteRecord(
                id=identity,
                owner_id=owner_id,
                character_card_id=card_id,
                scope_id=scope_key(scope) if scope else "",
                scope_json=scope.model_dump_json() if scope else "",
                subject_ref=payload.subject_ref,
                kind=payload.kind,
                text=payload.text,
                authored=authored,
                actor_id=actor_id,
                source_message_id=source_message_id,
                source_hash=source_hash,
                version=1,
            )
            session.add(record)
            session.add(
                NoteCreationReceiptRecord(
                    id=identity,
                    owner_id=owner_id,
                    character_card_id=card_id,
                )
            )
            session.flush()
            result = _view(record)
            session.commit()
            return result

    def list(
        self,
        *,
        owner_id: str,
        card_id: str,
        scope: RoomScope | None = None,
        subjects: tuple[str, ...] | None = None,
        include_background: bool = True,
        limit: int = 64,
    ) -> tuple[NoteView, ...]:
        if not 1 <= limit <= 256 or (subjects is not None and len(subjects) > 24):
            raise ValueError("note_query_budget")
        if scope is not None and scope.owner_id != owner_id:
            raise NoteAccessDenied("note_scope_mismatch")
        with self._rooms._lock, self.database.session() as session:
            self._card(session, owner_id, card_id)
            if scope is not None:
                room = session.get(RoomStateRecord, scope_key(scope))
                if room is None or not room.readable:
                    return ()
            conditions = [CharacterNoteRecord.scope_id == (scope_key(scope) if scope else "")]
            if scope is not None and include_background:
                conditions.append(
                    (CharacterNoteRecord.scope_id == "") & CharacterNoteRecord.authored.is_(True)
                )
            query = select(CharacterNoteRecord).where(
                CharacterNoteRecord.owner_id == owner_id,
                CharacterNoteRecord.character_card_id == card_id,
                or_(*conditions),
            )
            if subjects is not None:
                query = query.where(CharacterNoteRecord.subject_ref.in_(("self", *subjects)))
            records = session.scalars(
                query.order_by(
                    CharacterNoteRecord.authored.desc(),
                    CharacterNoteRecord.updated_at.desc(),
                    CharacterNoteRecord.id,
                ).limit(256)
            ).all()
            return tuple(_view(item) for item in records if self._current_source(session, item))[
                :limit
            ]

    def change(
        self,
        *,
        owner_id: str,
        card_id: str,
        note_id: str,
        expected_version: int,
        payload: NoteInput | None,
        operator: bool = False,
        actor_id: str = "",
        scope: RoomScope | None = None,
        source_message_id: str = "",
    ) -> NoteView | None:
        """None payload physically forgets. No hidden history or vector copy is retained."""
        if expected_version < 1:
            raise NoteConflict("note_version_required")
        with self._rooms._lock, self.database.session() as session:
            self._card(session, owner_id, card_id)
            record = session.get(CharacterNoteRecord, note_id)
            if record is None or record.owner_id != owner_id or record.character_card_id != card_id:
                raise NoteAccessDenied("note_unavailable")
            if record.version != expected_version:
                raise NoteConflict("note_version_conflict")
            if not operator and (
                record.authored
                or scope is None
                or scope.owner_id != owner_id
                or record.scope_id != scope_key(scope)
                or record.actor_id != actor_id
                or record.subject_ref != f"user:{actor_id}"
                or (payload is not None and payload.subject_ref != record.subject_ref)
            ):
                raise NoteAccessDenied("note_actor_mismatch")
            source_hash = record.source_hash
            authored = record.authored
            if payload is not None:
                if operator:
                    # An operator edit becomes attributed author content, not a forged self-report.
                    authored, actor_id, source_message_id, source_hash = True, owner_id, "", ""
                else:
                    assert scope is not None
                    source_hash = self._source(
                        session, scope, actor_id, source_message_id, payload.text
                    )
            predicate = (
                CharacterNoteRecord.id == note_id,
                CharacterNoteRecord.version == expected_version,
                CharacterNoteRecord.owner_id == owner_id,
                CharacterNoteRecord.character_card_id == card_id,
            )
            if payload is None:
                changed = session.scalar(
                    delete(CharacterNoteRecord).where(*predicate).returning(CharacterNoteRecord.id)
                )
                if changed is None:
                    raise NoteConflict("note_version_conflict")
                session.commit()
                return None
            changed = session.scalar(
                update(CharacterNoteRecord)
                .where(*predicate)
                .values(
                    text=payload.text,
                    subject_ref=payload.subject_ref,
                    kind=payload.kind,
                    authored=authored,
                    actor_id=actor_id,
                    source_message_id=source_message_id,
                    source_hash=source_hash,
                    version=expected_version + 1,
                    updated_at=datetime.now(UTC),
                )
                .returning(CharacterNoteRecord.id)
            )
            if changed is None:
                raise NoteConflict("note_version_conflict")
            session.refresh(record)
            result = _view(record)
            session.commit()
            return result

    def delete_for_card(self, owner_id: str, card_id: str) -> int:
        with self._rooms._lock, self.database.session() as session:
            rows = session.scalars(
                delete(CharacterNoteRecord)
                .where(
                    CharacterNoteRecord.owner_id == owner_id,
                    CharacterNoteRecord.character_card_id == card_id,
                )
                .returning(CharacterNoteRecord.id)
            ).all()
            session.execute(
                delete(NoteCreationReceiptRecord).where(
                    NoteCreationReceiptRecord.owner_id == owner_id,
                    NoteCreationReceiptRecord.character_card_id == card_id,
                )
            )
            session.commit()
            return len(rows)
