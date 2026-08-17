"""Persistence for explicit user-controlled Character Core Memory."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select

from echo_masque.persistence.core_memory_models import CharacterCoreMemoryRecord
from echo_masque.persistence.database import Database

_CORE_SCOPES = {"character_global", "character_server", "character_user"}
_CORE_STATUSES = {"active", "archived"}


def _compact(value: str, maximum: int) -> str:
    return " ".join(value.split())[:maximum]


def _normalized_key(content: str) -> str:
    normalized = " ".join(content.casefold().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:64]


class CoreMemoryRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def upsert(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        content: str,
        scope_type: str = "character_global",
        connection_id: str = "",
        guild_id: str = "",
        subject_user_id: str = "",
        memory_type: str = "other",
        priority: float = 0.75,
        source_memory_id: str = "",
        source_message_id: str = "",
        now: datetime | None = None,
    ) -> CharacterCoreMemoryRecord:
        if scope_type not in _CORE_SCOPES:
            raise ValueError("Unsupported Core Memory scope.")
        clean = _compact(content, 2000)
        if not clean:
            raise ValueError("Core Memory content is required.")
        if scope_type == "character_server" and (not connection_id or not guild_id):
            raise ValueError("Server-scoped Core Memory requires connection and guild.")
        if scope_type == "character_user" and not subject_user_id:
            raise ValueError("User-scoped Core Memory requires subject_user_id.")
        current = now or datetime.now(UTC)
        key = _normalized_key(clean)
        with self.database.session() as session:
            record = session.scalar(
                select(CharacterCoreMemoryRecord).where(
                    CharacterCoreMemoryRecord.owner_id == owner_id,
                    CharacterCoreMemoryRecord.character_card_id == character_card_id,
                    CharacterCoreMemoryRecord.connection_id == connection_id[:64],
                    CharacterCoreMemoryRecord.guild_id == guild_id[:200],
                    CharacterCoreMemoryRecord.scope_type == scope_type,
                    CharacterCoreMemoryRecord.subject_user_id == subject_user_id[:200],
                    CharacterCoreMemoryRecord.normalized_key == key,
                )
            )
            if record is None:
                record = CharacterCoreMemoryRecord(
                    id=str(uuid4()),
                    owner_id=owner_id[:120],
                    character_card_id=character_card_id[:64],
                    connection_id=connection_id[:64],
                    guild_id=guild_id[:200],
                    scope_type=scope_type,
                    subject_user_id=subject_user_id[:200],
                    memory_type=memory_type[:40] or "other",
                    content=clean,
                    normalized_key=key,
                    priority=max(0.0, min(1.0, priority)),
                    status="active",
                    source_memory_id=source_memory_id[:36],
                    source_message_id=source_message_id[:200],
                    created_at=current,
                    updated_at=current,
                )
                session.add(record)
            else:
                record.content = clean
                record.memory_type = memory_type[:40] or record.memory_type
                record.priority = max(record.priority, max(0.0, min(1.0, priority)))
                record.status = "active"
                if source_memory_id:
                    record.source_memory_id = source_memory_id[:36]
                if source_message_id:
                    record.source_message_id = source_message_id[:200]
                record.updated_at = current
            session.commit()
            session.refresh(record)
            return record

    def get(self, *, owner_id: str, memory_id: str) -> CharacterCoreMemoryRecord | None:
        with self.database.session() as session:
            return session.scalar(
                select(CharacterCoreMemoryRecord).where(
                    CharacterCoreMemoryRecord.id == memory_id,
                    CharacterCoreMemoryRecord.owner_id == owner_id,
                )
            )

    def list_for_character(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        connection_id: str = "",
        guild_id: str = "",
        subject_user_id: str = "",
        status: str = "active",
        limit: int = 100,
    ) -> tuple[CharacterCoreMemoryRecord, ...]:
        if status and status not in _CORE_STATUSES:
            raise ValueError("Unsupported Core Memory status.")
        with self.database.session() as session:
            query = select(CharacterCoreMemoryRecord).where(
                CharacterCoreMemoryRecord.owner_id == owner_id,
                CharacterCoreMemoryRecord.character_card_id == character_card_id,
            )
            if status:
                query = query.where(CharacterCoreMemoryRecord.status == status)
            if connection_id and guild_id:
                query = query.where(
                    (
                        CharacterCoreMemoryRecord.scope_type == "character_global"
                    )
                    | (
                        (CharacterCoreMemoryRecord.connection_id == connection_id)
                        & (CharacterCoreMemoryRecord.guild_id == guild_id)
                    )
                )
            else:
                query = query.where(CharacterCoreMemoryRecord.scope_type == "character_global")
            if subject_user_id:
                query = query.where(
                    (CharacterCoreMemoryRecord.scope_type != "character_user")
                    | (CharacterCoreMemoryRecord.subject_user_id == subject_user_id)
                )
            else:
                query = query.where(CharacterCoreMemoryRecord.scope_type != "character_user")
            records = list(
                session.scalars(
                    query.order_by(
                        CharacterCoreMemoryRecord.priority.desc(),
                        CharacterCoreMemoryRecord.updated_at.desc(),
                    ).limit(max(1, min(limit, 500)))
                )
            )
        return tuple(records)

    def update(
        self,
        *,
        owner_id: str,
        memory_id: str,
        content: str | None = None,
        memory_type: str | None = None,
        priority: float | None = None,
        status: str | None = None,
    ) -> CharacterCoreMemoryRecord:
        with self.database.session() as session:
            record = session.scalar(
                select(CharacterCoreMemoryRecord).where(
                    CharacterCoreMemoryRecord.id == memory_id,
                    CharacterCoreMemoryRecord.owner_id == owner_id,
                )
            )
            if record is None:
                raise KeyError("core_memory")
            if content is not None:
                clean = _compact(content, 2000)
                if not clean:
                    raise ValueError("Core Memory content is required.")
                record.content = clean
                record.normalized_key = _normalized_key(clean)
            if memory_type is not None:
                record.memory_type = memory_type[:40] or "other"
            if priority is not None:
                record.priority = max(0.0, min(1.0, priority))
            if status is not None:
                if status not in _CORE_STATUSES:
                    raise ValueError("Unsupported Core Memory status.")
                record.status = status
            record.updated_at = datetime.now(UTC)
            session.commit()
            session.refresh(record)
            return record

    def mark_used(self, memory_ids: tuple[str, ...]) -> None:
        if not memory_ids:
            return
        now = datetime.now(UTC)
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(CharacterCoreMemoryRecord).where(
                        CharacterCoreMemoryRecord.id.in_(memory_ids)
                    )
                )
            )
            for record in records:
                record.use_count += 1
                record.last_used_at = now
            session.commit()

    def delete(self, *, owner_id: str, memory_id: str) -> bool:
        with self.database.session() as session:
            record = session.scalar(
                select(CharacterCoreMemoryRecord).where(
                    CharacterCoreMemoryRecord.id == memory_id,
                    CharacterCoreMemoryRecord.owner_id == owner_id,
                )
            )
            if record is None:
                return False
            session.delete(record)
            session.commit()
            return True

    def delete_owner(self, owner_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                delete(CharacterCoreMemoryRecord).where(
                    CharacterCoreMemoryRecord.owner_id == owner_id
                )
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)


__all__ = ["CoreMemoryRepository"]
