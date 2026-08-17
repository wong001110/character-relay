"""Persistence and one-time dirty-data reset for Memory vNext."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, or_, select, update

from echo_masque.persistence.database import Database
from echo_masque.persistence.memory_intelligence_models import ConversationMemoryRecord
from echo_masque.persistence.memory_vnext_models import (
    ConversationMemoryVNextRecord,
    MemoryVNextStateRecord,
)

_SCHEMA_VERSION = "memory-vnext.1"
_VALID_SCOPES = {"character_user", "character_server", "character_private", "topic_local"}


class MemoryVNextRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _json(values: list[str] | tuple[str, ...]) -> str:
        bounded = list(dict.fromkeys(item.strip() for item in values if item.strip()))
        return json.dumps(bounded, ensure_ascii=False, separators=(",", ":"))

    def reset_legacy_dirty_data_once(self) -> int:
        """Delete old derived Memory once; raw conversation/source tables are untouched."""

        now = datetime.now(UTC)
        with self.database.session() as session:
            state = session.get(MemoryVNextStateRecord, "default")
            if (
                state is not None
                and state.schema_version == _SCHEMA_VERSION
                and state.legacy_reset_at
            ):
                return 0
            result = session.execute(delete(ConversationMemoryRecord))
            if state is None:
                state = MemoryVNextStateRecord(
                    id="default",
                    schema_version=_SCHEMA_VERSION,
                    legacy_reset_at=now,
                    updated_at=now,
                )
                session.add(state)
            else:
                state.schema_version = _SCHEMA_VERSION
                state.legacy_reset_at = now
                state.updated_at = now
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)

    def create(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        connection_id: str,
        guild_id: str,
        scope_type: str,
        memory_type: str,
        content: str,
        subject_user_id: str = "",
        topic_id: str = "",
        confidence: float = 0.7,
        importance: float = 0.5,
        provenance_episode_ids: tuple[str, ...] = (),
        source_message_ids: tuple[str, ...] = (),
        supersedes_memory_id: str = "",
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
    ) -> ConversationMemoryVNextRecord:
        if scope_type not in _VALID_SCOPES:
            raise ValueError("Unsupported Memory vNext scope.")
        if scope_type == "character_user" and not subject_user_id:
            raise ValueError("character_user Memory requires subject_user_id.")
        if scope_type == "topic_local" and not topic_id:
            raise ValueError("topic_local Memory requires topic_id.")
        record = ConversationMemoryVNextRecord(
            id=str(uuid4()),
            owner_id=owner_id,
            character_card_id=character_card_id,
            connection_id=connection_id,
            guild_id=guild_id,
            scope_type=scope_type,
            subject_user_id=subject_user_id[:200],
            topic_id=topic_id[:64],
            memory_type=memory_type[:40],
            content=" ".join(content.split())[:1600],
            confidence=max(0.0, min(1.0, confidence)),
            importance=max(0.0, min(1.0, importance)),
            provenance_episode_ids_json=self._json(provenance_episode_ids[-20:]),
            source_message_ids_json=self._json(source_message_ids[-40:]),
            supersedes_memory_id=supersedes_memory_id[:36],
            valid_from=valid_from,
            valid_to=valid_to,
        )
        with self.database.session() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def get(
        self,
        memory_id: str,
        owner_id: str = "",
    ) -> ConversationMemoryVNextRecord | None:
        with self.database.session() as session:
            record = session.get(ConversationMemoryVNextRecord, memory_id)
            if record is None:
                return None
            if owner_id and record.owner_id != owner_id:
                return None
            return record

    def active_candidates(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        connection_id: str,
        guild_id: str,
        subject_user_id: str,
        topic_id: str,
        limit: int = 200,
    ) -> list[ConversationMemoryVNextRecord]:
        now = datetime.now(UTC)
        with self.database.session() as session:
            scope_visibility = or_(
                ConversationMemoryVNextRecord.scope_type.in_(
                    ["character_server", "character_private"]
                ),
                (
                    (ConversationMemoryVNextRecord.scope_type == "character_user")
                    & (ConversationMemoryVNextRecord.subject_user_id == subject_user_id)
                ),
                (
                    (ConversationMemoryVNextRecord.scope_type == "topic_local")
                    & (ConversationMemoryVNextRecord.topic_id == topic_id)
                ),
            )
            return list(
                session.scalars(
                    select(ConversationMemoryVNextRecord)
                    .where(
                        ConversationMemoryVNextRecord.owner_id == owner_id,
                        ConversationMemoryVNextRecord.character_card_id == character_card_id,
                        ConversationMemoryVNextRecord.connection_id == connection_id,
                        ConversationMemoryVNextRecord.guild_id == guild_id,
                        ConversationMemoryVNextRecord.status == "active",
                        or_(
                            ConversationMemoryVNextRecord.valid_from.is_(None),
                            ConversationMemoryVNextRecord.valid_from <= now,
                        ),
                        or_(
                            ConversationMemoryVNextRecord.valid_to.is_(None),
                            ConversationMemoryVNextRecord.valid_to > now,
                        ),
                        scope_visibility,
                    )
                    .order_by(
                        ConversationMemoryVNextRecord.importance.desc(),
                        ConversationMemoryVNextRecord.updated_at.desc(),
                    )
                    .limit(max(1, min(limit, 500)))
                )
            )

    def mark_used(self, memory_ids: tuple[str, ...]) -> None:
        if not memory_ids:
            return
        now = datetime.now(UTC)
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(ConversationMemoryVNextRecord).where(
                        ConversationMemoryVNextRecord.id.in_(memory_ids)
                    )
                )
            )
            for record in records:
                record.use_count += 1
                record.last_used_at = now
            session.commit()

    def delete_owner(self, owner_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                delete(ConversationMemoryVNextRecord).where(
                    ConversationMemoryVNextRecord.owner_id == owner_id
                )
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)

    def claim_owner(self, source_owner_id: str, target_owner_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                update(ConversationMemoryVNextRecord)
                .where(ConversationMemoryVNextRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)

    def supersede(self, old_id: str, new_id: str) -> None:
        with self.database.session() as session:
            old = session.get(ConversationMemoryVNextRecord, old_id)
            new = session.get(ConversationMemoryVNextRecord, new_id)
            if old is None or new is None or old.owner_id != new.owner_id:
                raise KeyError("memory")
            old.status = "superseded"
            old.valid_to = datetime.now(UTC)
            new.supersedes_memory_id = old.id
            session.commit()


__all__ = ["MemoryVNextRepository"]
