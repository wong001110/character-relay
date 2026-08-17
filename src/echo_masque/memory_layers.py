"""Versioned Memory sidecars: Core revisions, synthesized freshness, and summaries."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, func, select, update

from echo_masque.persistence.core_memory_models import CharacterCoreMemoryRecord
from echo_masque.persistence.core_memory_repository import CoreMemoryRepository
from echo_masque.persistence.database import Database
from echo_masque.persistence.memory_layer_models import (
    CharacterCoreMemoryRevisionRecord,
    CharacterMemorySummaryRecord,
    SynthesizedMemoryFreshnessRecord,
)
from echo_masque.persistence.memory_vnext_models import ConversationMemoryVNextRecord

_FRESHNESS_SECONDS = {
    "event": 14 * 24 * 60 * 60,
    "goal": 21 * 24 * 60 * 60,
    "relationship": 45 * 24 * 60 * 60,
    "preference": 90 * 24 * 60 * 60,
    "other": 60 * 24 * 60 * 60,
    "fact": 180 * 24 * 60 * 60,
}


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _json(values: list[str] | tuple[str, ...]) -> str:
    return json.dumps(list(dict.fromkeys(values)), ensure_ascii=False, separators=(",", ":"))


class CoreMemoryRevisionRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def record(
        self,
        *,
        memory: CharacterCoreMemoryRecord,
        action: str,
        now: datetime | None = None,
    ) -> CharacterCoreMemoryRevisionRecord:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            latest = session.scalar(
                select(func.max(CharacterCoreMemoryRevisionRecord.revision_no)).where(
                    CharacterCoreMemoryRevisionRecord.owner_id == memory.owner_id,
                    CharacterCoreMemoryRevisionRecord.core_memory_id == memory.id,
                )
            )
            record = CharacterCoreMemoryRevisionRecord(
                id=str(uuid4()),
                owner_id=memory.owner_id,
                core_memory_id=memory.id,
                revision_no=int(latest or 0) + 1,
                action=action[:24],
                character_card_id=memory.character_card_id,
                connection_id=memory.connection_id,
                guild_id=memory.guild_id,
                scope_type=memory.scope_type,
                subject_user_id=memory.subject_user_id,
                memory_type=memory.memory_type,
                content=memory.content,
                priority=memory.priority,
                status=memory.status,
                source_memory_id=memory.source_memory_id,
                source_message_id=memory.source_message_id,
                created_at=current,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def list_history(
        self,
        *,
        owner_id: str,
        core_memory_id: str,
        limit: int = 100,
    ) -> tuple[CharacterCoreMemoryRevisionRecord, ...]:
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(CharacterCoreMemoryRevisionRecord)
                    .where(
                        CharacterCoreMemoryRevisionRecord.owner_id == owner_id,
                        CharacterCoreMemoryRevisionRecord.core_memory_id == core_memory_id,
                    )
                    .order_by(CharacterCoreMemoryRevisionRecord.revision_no.desc())
                    .limit(max(1, min(limit, 300)))
                )
            )
        return tuple(records)

    def get(
        self,
        *,
        owner_id: str,
        revision_id: str,
    ) -> CharacterCoreMemoryRevisionRecord | None:
        with self.database.session() as session:
            return session.scalar(
                select(CharacterCoreMemoryRevisionRecord).where(
                    CharacterCoreMemoryRevisionRecord.id == revision_id,
                    CharacterCoreMemoryRevisionRecord.owner_id == owner_id,
                )
            )

    def restore(
        self,
        *,
        owner_id: str,
        revision_id: str,
    ) -> CharacterCoreMemoryRecord:
        revision = self.get(owner_id=owner_id, revision_id=revision_id)
        if revision is None:
            raise KeyError("core_memory_revision")
        restored = CoreMemoryRepository(self.database).upsert(
            owner_id=owner_id,
            character_card_id=revision.character_card_id,
            connection_id=revision.connection_id,
            guild_id=revision.guild_id,
            scope_type=revision.scope_type,
            subject_user_id=revision.subject_user_id,
            memory_type=revision.memory_type,
            content=revision.content,
            priority=revision.priority,
            source_memory_id=revision.source_memory_id,
            source_message_id=revision.source_message_id,
        )
        return restored

    def delete_owner(self, owner_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                delete(CharacterCoreMemoryRevisionRecord).where(
                    CharacterCoreMemoryRevisionRecord.owner_id == owner_id
                )
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)

    def claim_owner(self, source_owner_id: str, target_owner_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                update(CharacterCoreMemoryRevisionRecord)
                .where(CharacterCoreMemoryRevisionRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)


class SynthesizedMemoryFreshnessRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def stale_after_seconds(memory_type: str) -> int:
        return _FRESHNESS_SECONDS.get(memory_type, _FRESHNESS_SECONDS["other"])

    def mark_confirmed(
        self,
        memory: ConversationMemoryVNextRecord,
        *,
        now: datetime | None = None,
    ) -> SynthesizedMemoryFreshnessRecord:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            record = session.get(SynthesizedMemoryFreshnessRecord, memory.id)
            if record is None:
                record = SynthesizedMemoryFreshnessRecord(
                    memory_id=memory.id,
                    owner_id=memory.owner_id,
                    character_card_id=memory.character_card_id,
                    connection_id=memory.connection_id,
                    guild_id=memory.guild_id,
                    memory_type=memory.memory_type,
                    freshness_status="fresh",
                    stale_after_seconds=self.stale_after_seconds(memory.memory_type),
                    last_confirmed_at=current,
                    last_checked_at=current,
                    updated_at=current,
                )
                session.add(record)
            else:
                record.memory_type = memory.memory_type
                record.freshness_status = "fresh"
                record.stale_after_seconds = self.stale_after_seconds(memory.memory_type)
                record.last_confirmed_at = current
                record.last_checked_at = current
                record.updated_at = current
            session.commit()
            session.refresh(record)
            return record

    def get(self, memory_id: str) -> SynthesizedMemoryFreshnessRecord | None:
        with self.database.session() as session:
            return session.get(SynthesizedMemoryFreshnessRecord, memory_id)

    def refresh_staleness(
        self,
        *,
        owner_id: str = "",
        now: datetime | None = None,
        limit: int = 1000,
    ) -> int:
        current = now or datetime.now(UTC)
        changed = 0
        with self.database.session() as session:
            query = select(SynthesizedMemoryFreshnessRecord)
            if owner_id:
                query = query.where(SynthesizedMemoryFreshnessRecord.owner_id == owner_id)
            records = list(session.scalars(query.limit(max(1, min(limit, 5000)))))
            for record in records:
                confirmed = _aware(record.last_confirmed_at)
                stale = current - confirmed >= timedelta(seconds=record.stale_after_seconds)
                status = "stale" if stale else "fresh"
                if record.freshness_status != status:
                    record.freshness_status = status
                    changed += 1
                record.last_checked_at = current
                record.updated_at = current
            session.commit()
        return changed

    def delete_memory(self, memory_id: str) -> None:
        with self.database.session() as session:
            session.execute(
                delete(SynthesizedMemoryFreshnessRecord).where(
                    SynthesizedMemoryFreshnessRecord.memory_id == memory_id
                )
            )
            session.commit()

    def delete_owner(self, owner_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                delete(SynthesizedMemoryFreshnessRecord).where(
                    SynthesizedMemoryFreshnessRecord.owner_id == owner_id
                )
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)

    def claim_owner(self, source_owner_id: str, target_owner_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                update(SynthesizedMemoryFreshnessRecord)
                .where(SynthesizedMemoryFreshnessRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)


class CharacterMemorySummaryService:
    """Build a compact versioned cache from explicit Core + current synthesized Memory."""

    def __init__(
        self,
        database: Database,
        freshness: SynthesizedMemoryFreshnessRepository | None = None,
    ) -> None:
        self.database = database
        self.core = CoreMemoryRepository(database)
        self.freshness = freshness or SynthesizedMemoryFreshnessRepository(database)

    def latest(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        connection_id: str,
        guild_id: str,
    ) -> CharacterMemorySummaryRecord | None:
        with self.database.session() as session:
            return session.scalar(
                select(CharacterMemorySummaryRecord)
                .where(
                    CharacterMemorySummaryRecord.owner_id == owner_id,
                    CharacterMemorySummaryRecord.character_card_id == character_card_id,
                    CharacterMemorySummaryRecord.connection_id == connection_id,
                    CharacterMemorySummaryRecord.guild_id == guild_id,
                )
                .order_by(CharacterMemorySummaryRecord.version.desc())
                .limit(1)
            )

    def history(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        connection_id: str,
        guild_id: str,
        limit: int = 20,
    ) -> tuple[CharacterMemorySummaryRecord, ...]:
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(CharacterMemorySummaryRecord)
                    .where(
                        CharacterMemorySummaryRecord.owner_id == owner_id,
                        CharacterMemorySummaryRecord.character_card_id == character_card_id,
                        CharacterMemorySummaryRecord.connection_id == connection_id,
                        CharacterMemorySummaryRecord.guild_id == guild_id,
                    )
                    .order_by(CharacterMemorySummaryRecord.version.desc())
                    .limit(max(1, min(limit, 100)))
                )
            )
        return tuple(records)

    def refresh(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        connection_id: str,
        guild_id: str,
        now: datetime | None = None,
    ) -> CharacterMemorySummaryRecord | None:
        current = now or datetime.now(UTC)
        core = self.core.list_for_character(
            owner_id=owner_id,
            character_card_id=character_card_id,
            connection_id=connection_id,
            guild_id=guild_id,
            status="active",
            limit=20,
        )
        with self.database.session() as session:
            synthesized = list(
                session.scalars(
                    select(ConversationMemoryVNextRecord)
                    .where(
                        ConversationMemoryVNextRecord.owner_id == owner_id,
                        ConversationMemoryVNextRecord.character_card_id == character_card_id,
                        ConversationMemoryVNextRecord.connection_id == connection_id,
                        ConversationMemoryVNextRecord.guild_id == guild_id,
                        ConversationMemoryVNextRecord.status == "active",
                        ConversationMemoryVNextRecord.scope_type.in_(
                            ("character_server", "character_private")
                        ),
                    )
                    .order_by(
                        ConversationMemoryVNextRecord.importance.desc(),
                        ConversationMemoryVNextRecord.confidence.desc(),
                    )
                    .limit(30)
                )
            )
        current_synthesized = [
            item
            for item in synthesized
            if (self.freshness.get(item.id) is None)
            or self.freshness.get(item.id).freshness_status != "stale"  # type: ignore[union-attr]
        ]
        lines: list[str] = []
        core_ids: list[str] = []
        memory_ids: list[str] = []
        for item in core[:12]:
            line = f"Core/{item.memory_type}: {item.content}"
            if sum(len(value) + 1 for value in lines) + len(line) > 3500:
                break
            lines.append(line)
            core_ids.append(item.id)
        for item in current_synthesized[:16]:
            line = (
                f"Synthesized/{item.memory_type} "
                f"(confidence {item.confidence:.2f}): {item.content}"
            )
            if sum(len(value) + 1 for value in lines) + len(line) > 3500:
                break
            lines.append(line)
            memory_ids.append(item.id)
        if not lines:
            return None
        summary_text = "\n".join(lines)
        source_hash = hashlib.sha256(
            json.dumps(
                {
                    "summary": summary_text,
                    "core": core_ids,
                    "synthesized": memory_ids,
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        latest = self.latest(
            owner_id=owner_id,
            character_card_id=character_card_id,
            connection_id=connection_id,
            guild_id=guild_id,
        )
        if latest is not None and latest.source_hash == source_hash:
            return latest
        version = 1 if latest is None else latest.version + 1
        record = CharacterMemorySummaryRecord(
            id=str(uuid4()),
            owner_id=owner_id,
            character_card_id=character_card_id,
            connection_id=connection_id,
            guild_id=guild_id,
            version=version,
            summary_text=summary_text,
            source_core_ids_json=_json(core_ids),
            source_memory_ids_json=_json(memory_ids),
            source_hash=source_hash,
            created_at=current,
        )
        with self.database.session() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def delete_owner(self, owner_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                delete(CharacterMemorySummaryRecord).where(
                    CharacterMemorySummaryRecord.owner_id == owner_id
                )
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)

    def claim_owner(self, source_owner_id: str, target_owner_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                update(CharacterMemorySummaryRecord)
                .where(CharacterMemorySummaryRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)


__all__ = [
    "CharacterMemorySummaryService",
    "CoreMemoryRevisionRepository",
    "SynthesizedMemoryFreshnessRepository",
]
