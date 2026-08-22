"""One-way Intelligence Core v3 hard-cutover migration and legacy table cleanup.

Useful durable evidence is projected into v3 stores. Unreliable historical conversation identity is
not migrated; raw messages and migrated Episodes remain the historical evidence boundary.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from threading import Lock
from typing import Any, cast
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import MetaData, Table, inspect, select
from sqlalchemy.engine import Connection

from echo_masque.persistence.belief_models import BeliefV3Record
from echo_masque.persistence.character_learned_state_event_models import (
    CharacterLearnedStateEventRecord,
)
from echo_masque.persistence.conversation_runtime_models import ConversationEpisodeV3Record
from echo_masque.persistence.database import Database
from echo_masque.persistence.discovery_share_models import DeploymentDiscoveryShareRecord
from echo_masque.persistence.intelligence_v3_migration_models import (
    IntelligenceV3HardCutoverMigrationRecord,
)

_LEGACY_TABLES_TO_DROP = (
    "conversation_" + "topics",
    "conversation_" + "topic_" + "decisions",
    "semantic_threads",
    "conversation_segments",
    "conversation_consolidation_checkpoints",
    "server_wiki_pages",
    "conversation_authority_edges",
    "conversation_graph_edges",
    "conversation_graph_nodes",
    "character_core_memory_revisions",
    "synthesized_memory_freshness",
    "character_memory_summaries",
    "character_core_memories",
    "conversation_memory_v2",
    "conversation_memory_vnext",
    "memory_vnext_state",
    "conversation_episodes",
)

_ALLOWED_BELIEF_STATUSES = {
    "active",
    "provisional",
    "disputed",
    "superseded",
    "rejected",
    "expired",
}

_MIGRATION_LEDGER_ID = "intelligence-v3-hard-cutover-v1"
_RUN_LOCK = Lock()


def _json_strings(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, str):
        return ()
    try:
        value = json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError):
        return ()
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if isinstance(item, str) and item)


def _json(values: tuple[str, ...], *, limit: int = 96) -> str:
    return json.dumps(list(dict.fromkeys(values))[-limit:], ensure_ascii=False)


def _dt(value: object, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return fallback


def _nullable_dt(value: object) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _legacy_id(kind: str, old_id: object) -> str:
    return str(uuid5(NAMESPACE_URL, f"character-relay:intelligence-v3:{kind}:{old_id}"))


def _reflect(database: Database, table_name: str) -> Table | None:
    if table_name not in set(inspect(database.engine).get_table_names()):
        return None
    return Table(table_name, MetaData(), autoload_with=database.engine)


def _rowcount(result: object) -> int:
    value = getattr(result, "rowcount", 0)
    return int(value) if isinstance(value, int) and value > 0 else 0


def _safe_column_name(value: str) -> bool:
    return bool(value) and value.replace("_", "").isalnum()


def _disable_sqlite_foreign_keys(connection: Connection) -> None:
    """Temporarily disable checks outside the rebuild transaction."""

    connection.commit()
    connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    connection.commit()


def _restore_sqlite_foreign_keys(connection: Connection) -> None:
    connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    connection.commit()


def _assert_sqlite_foreign_key_check(connection: Connection) -> None:
    violations = connection.exec_driver_sql("PRAGMA foreign_key_check").all()
    if violations:
        tables = ", ".join(sorted({str(row[0]) for row in violations}))
        raise RuntimeError(f"SQLite foreign-key check failed after v3 migration: {tables}")


class IntelligenceV3HardCutoverMigration:
    """Idempotently migrate useful legacy evidence and physically remove retired structures."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def _claim_run(self) -> bool:
        """Persist a resumable attempt, unless this exact cutover has completed."""

        now = datetime.now(UTC)
        with self.database.session() as session:
            record = session.get(IntelligenceV3HardCutoverMigrationRecord, _MIGRATION_LEDGER_ID)
            if record is not None and record.status == "completed":
                return False
            if record is None:
                record = IntelligenceV3HardCutoverMigrationRecord(
                    id=_MIGRATION_LEDGER_ID,
                    status="running",
                    attempt_count=1,
                    last_error="",
                    started_at=now,
                    updated_at=now,
                    completed_at=None,
                )
                session.add(record)
            else:
                record.status = "running"
                record.attempt_count += 1
                record.started_at = now
                record.updated_at = now
                record.completed_at = None
                record.last_error = ""
            session.commit()
        return True

    def _complete_run(self) -> None:
        now = datetime.now(UTC)
        with self.database.session() as session:
            record = session.get(IntelligenceV3HardCutoverMigrationRecord, _MIGRATION_LEDGER_ID)
            if record is None:
                raise RuntimeError("Intelligence v3 migration ledger claim is missing")
            record.status = "completed"
            record.updated_at = now
            record.completed_at = now
            record.last_error = ""
            session.commit()

    def _fail_run(self, error: Exception) -> None:
        now = datetime.now(UTC)
        with self.database.session() as session:
            record = session.get(IntelligenceV3HardCutoverMigrationRecord, _MIGRATION_LEDGER_ID)
            if record is None:
                raise RuntimeError("Intelligence v3 migration ledger claim is missing") from error
            record.status = "failed"
            record.updated_at = now
            record.last_error = type(error).__name__[:120]
            session.commit()

    def _migrate_core_memory(self) -> int:
        table = _reflect(self.database, "character_core_memories")
        if table is None:
            return 0
        now = datetime.now(UTC)
        migrated = 0
        with self.database.session() as session:
            for row in session.execute(select(table)).mappings():
                if str(row.get("status") or "active") != "active":
                    continue
                belief_id = _legacy_id("core", row.get("id"))
                if session.get(BeliefV3Record, belief_id) is not None:
                    continue
                source_message = str(row.get("source_message_id") or "")
                source_memory = str(row.get("source_memory_id") or "")
                evidence = tuple(item for item in (source_message, source_memory) if item)
                current = _dt(row.get("updated_at"), now)
                session.add(
                    BeliefV3Record(
                        id=belief_id,
                        owner_id=str(row.get("owner_id") or ""),
                        character_card_id=str(row.get("character_card_id") or "")[:64],
                        connection_id=str(row.get("connection_id") or "")[:64],
                        guild_id=str(row.get("guild_id") or "")[:200],
                        subject_entity_id="",
                        subject_ref=str(row.get("subject_user_id") or "")[:240],
                        predicate=str(row.get("memory_type") or "memory")[:160],
                        value_text=str(row.get("content") or "")[:8000],
                        scope=str(row.get("scope_type") or "character_global")[:40],
                        authority_class="authored",
                        authority_score=1.0,
                        origin="core_memory_migration",
                        confidence=1.0,
                        importance=max(0.0, min(float(row.get("priority") or 0.75), 1.0)),
                        status="active",
                        supersedes_belief_id="",
                        evidence_refs_json=_json(evidence),
                        authored=True,
                        valid_from=_dt(row.get("created_at"), current),
                        valid_to=None,
                        last_confirmed_at=current,
                        stale_after=None,
                        created_at=_dt(row.get("created_at"), current),
                        updated_at=current,
                    )
                )
                migrated += 1
            session.commit()
        return migrated

    def _migrate_memory_vnext(self) -> int:
        table = _reflect(self.database, "conversation_memory_vnext")
        if table is None:
            return 0
        now = datetime.now(UTC)
        migrated = 0
        with self.database.session() as session:
            for row in session.execute(select(table)).mappings():
                raw_status = str(row.get("status") or "provisional")
                if raw_status not in {"active", "provisional", "disputed", "superseded"}:
                    continue
                belief_id = _legacy_id("memory-vnext", row.get("id"))
                if session.get(BeliefV3Record, belief_id) is not None:
                    continue
                status = raw_status if raw_status in _ALLOWED_BELIEF_STATUSES else "provisional"
                source_messages = _json_strings(row.get("source_message_ids_json"))
                source_episodes = _json_strings(row.get("provenance_episode_ids_json"))
                evidence = tuple(f"message:{item}" for item in source_messages) + tuple(
                    f"episode:{item}" for item in source_episodes
                )
                confidence = max(0.0, min(float(row.get("confidence") or 0.7), 1.0))
                current = _dt(row.get("updated_at"), now)
                supersedes_old = str(row.get("supersedes_memory_id") or "")
                supersedes = _legacy_id("memory-vnext", supersedes_old) if supersedes_old else ""
                session.add(
                    BeliefV3Record(
                        id=belief_id,
                        owner_id=str(row.get("owner_id") or ""),
                        character_card_id=str(row.get("character_card_id") or "")[:64],
                        connection_id=str(row.get("connection_id") or "")[:64],
                        guild_id=str(row.get("guild_id") or "")[:200],
                        subject_entity_id="",
                        subject_ref=str(row.get("subject_user_id") or "")[:240],
                        predicate=str(row.get("memory_type") or "memory")[:160],
                        value_text=str(row.get("content") or "")[:8000],
                        scope=str(row.get("scope_type") or "server")[:40],
                        authority_class="conversation",
                        authority_score=max(0.35, min(confidence, 0.85)),
                        origin="memory_vnext_migration",
                        confidence=confidence,
                        importance=max(0.0, min(float(row.get("importance") or 0.5), 1.0)),
                        status=status,
                        supersedes_belief_id=supersedes[:64],
                        evidence_refs_json=_json(evidence),
                        authored=False,
                        valid_from=_nullable_dt(row.get("valid_from"))
                        or _dt(row.get("created_at"), current),
                        valid_to=_nullable_dt(row.get("valid_to")),
                        last_confirmed_at=current if status == "active" else None,
                        stale_after=None,
                        created_at=_dt(row.get("created_at"), current),
                        updated_at=current,
                    )
                )
                migrated += 1
            session.commit()
        return migrated

    def _migrate_episodes(self) -> int:
        table = _reflect(self.database, "conversation_episodes")
        if table is None:
            return 0
        now = datetime.now(UTC)
        migrated = 0
        with self.database.session() as session:
            for row in session.execute(select(table)).mappings():
                episode_id = _legacy_id("episode", row.get("id"))
                if session.get(ConversationEpisodeV3Record, episode_id) is not None:
                    continue
                old_id = str(row.get("id") or "")
                source_messages = _json_strings(row.get("source_message_ids_json"))
                participants = _json_strings(row.get("participant_refs_json"))
                media = _json_strings(row.get("media_refs_json"))
                key_events = _json_strings(row.get("key_points_json"))
                started = _dt(row.get("started_at"), now)
                ended = _dt(row.get("ended_at"), started)
                session.add(
                    ConversationEpisodeV3Record(
                        id=episode_id,
                        owner_id=str(row.get("owner_id") or ""),
                        platform=str(row.get("platform") or "discord")[:24],
                        connection_id=str(row.get("connection_id") or "")[:64],
                        guild_id=str(row.get("guild_id") or "")[:200],
                        channel_id=str(row.get("channel_id") or "")[:200],
                        discord_thread_id=str(row.get("thread_id") or "")[:200],
                        conversation_thread_id="",
                        episode_key=f"legacy:{old_id}"[:160],
                        segment_ids_json="[]",
                        source_message_ids_json=_json(source_messages),
                        participant_ids_json=_json(participants),
                        entity_ids_json="[]",
                        media_refs_json=_json(media),
                        summary=str(row.get("summary") or "")[:12000],
                        key_events_json=_json(key_events),
                        segment_count=0,
                        status="archived",
                        checkpoint_reason="legacy_migration",
                        started_at=started,
                        ended_at=ended,
                        updated_at=_dt(row.get("updated_at"), ended),
                    )
                )
                migrated += 1
            session.commit()
        return migrated

    def _purge_invalid_behavior_rows(self) -> int:
        table = _reflect(self.database, "character_learned_states")
        if table is None:
            return 0
        with self.database.engine.begin() as connection:
            result = connection.exec_driver_sql(
                "DELETE FROM character_learned_states "
                "WHERE state_type = 'relationship' OR subject_type = 'topic'"
            )
        return _rowcount(result)

    def _rebuild_sqlite_table(self, table: Table, expected: Table) -> int:
        with self.database.engine.connect() as connection:
            rows = list(connection.execute(select(table)).mappings())
        expected_names = {column.name for column in expected.columns}
        with self.database.engine.connect() as connection:
            _disable_sqlite_foreign_keys(connection)
            try:
                with connection.begin():
                    connection.exec_driver_sql(f'DROP TABLE IF EXISTS "{table.name}"')
                    expected.create(bind=connection, checkfirst=True)
                    for row in rows:
                        values = {
                            name: row.get(name)
                            for name in expected_names
                            if name in row and row.get(name) is not None
                        }
                        if "conversation_thread_id" in expected_names:
                            values.setdefault("conversation_thread_id", "")
                        if "source_segment_id" in expected_names:
                            values.setdefault("source_segment_id", "")
                        connection.execute(expected.insert().values(**values))
            finally:
                _restore_sqlite_foreign_keys(connection)
            _assert_sqlite_foreign_key_check(connection)
        return len(rows)

    def _migrate_behavior_event_schema(self) -> dict[str, int]:
        aggregate_removed = self._purge_invalid_behavior_rows()
        table = _reflect(self.database, "character_learned_state_events")
        if table is None:
            return {"aggregate_removed": aggregate_removed, "events_removed": 0}
        expected = cast(Table, CharacterLearnedStateEventRecord.__table__)
        columns = {column.name for column in table.columns}
        expected_columns = {column.name for column in expected.columns}
        if columns == expected_columns:
            with self.database.engine.begin() as connection:
                result = connection.exec_driver_sql(
                    "DELETE FROM character_learned_state_events "
                    "WHERE state_type = 'relationship' OR subject_type = 'topic'"
                )
            return {"aggregate_removed": aggregate_removed, "events_removed": _rowcount(result)}
        if self.database.engine.dialect.name == "sqlite":
            with self.database.engine.connect() as connection:
                rows = list(connection.execute(select(table)).mappings())
            preserved = [
                row
                for row in rows
                if str(row.get("state_type") or "") != "relationship"
                and str(row.get("subject_type") or "") != "topic"
            ]
            expected_names = {column.name for column in expected.columns}
            with self.database.engine.connect() as connection:
                _disable_sqlite_foreign_keys(connection)
                try:
                    with connection.begin():
                        connection.exec_driver_sql(
                            'DROP TABLE IF EXISTS "character_learned_state_events"'
                        )
                        expected.create(bind=connection, checkfirst=True)
                        for row in preserved:
                            values = {
                                name: row.get(name)
                                for name in expected_names
                                if name in row and row.get(name) is not None
                            }
                            values.setdefault("conversation_thread_id", "")
                            values.setdefault("source_segment_id", "")
                            connection.execute(expected.insert().values(**values))
                finally:
                    _restore_sqlite_foreign_keys(connection)
                _assert_sqlite_foreign_key_check(connection)
            return {
                "aggregate_removed": aggregate_removed,
                "events_removed": len(rows) - len(preserved),
            }
        with self.database.engine.begin() as connection:
            for column in sorted(expected_columns - columns):
                if not _safe_column_name(column):
                    continue
                connection.exec_driver_sql(
                    f'ALTER TABLE character_learned_state_events ADD COLUMN "{column}" VARCHAR(200)'
                )
            result = connection.exec_driver_sql(
                "DELETE FROM character_learned_state_events "
                "WHERE state_type = 'relationship' OR subject_type = 'topic'"
            )
            for column in sorted(columns - expected_columns):
                if _safe_column_name(column):
                    connection.exec_driver_sql(
                        f'ALTER TABLE character_learned_state_events DROP COLUMN "{column}"'
                    )
        return {"aggregate_removed": aggregate_removed, "events_removed": _rowcount(result)}

    def _migrate_discovery_share_schema(self) -> int:
        table = _reflect(self.database, "deployment_discovery_shares")
        if table is None:
            return 0
        expected = cast(Table, DeploymentDiscoveryShareRecord.__table__)
        columns = {column.name for column in table.columns}
        expected_columns = {column.name for column in expected.columns}
        if columns == expected_columns:
            return 0
        if self.database.engine.dialect.name == "sqlite":
            return self._rebuild_sqlite_table(table, expected)
        with self.database.engine.begin() as connection:
            for column in sorted(expected_columns - columns):
                if column == "conversation_thread_id":
                    connection.exec_driver_sql(
                        "ALTER TABLE deployment_discovery_shares "
                        "ADD COLUMN conversation_thread_id VARCHAR(64) NOT NULL DEFAULT ''"
                    )
            for column in sorted(columns - expected_columns):
                if _safe_column_name(column):
                    connection.exec_driver_sql(
                        f'ALTER TABLE deployment_discovery_shares DROP COLUMN "{column}"'
                    )
        return 1

    def _drop_legacy_tables(self) -> tuple[str, ...]:
        existing = set(inspect(self.database.engine).get_table_names())
        dropped: list[str] = []
        if self.database.engine.dialect.name != "sqlite":
            with self.database.engine.begin() as connection:
                for table_name in _LEGACY_TABLES_TO_DROP:
                    if table_name not in existing:
                        continue
                    connection.exec_driver_sql(f'DROP TABLE IF EXISTS "{table_name}"')
                    dropped.append(table_name)
            return tuple(dropped)
        with self.database.engine.connect() as connection:
            _disable_sqlite_foreign_keys(connection)
            try:
                with connection.begin():
                    for table_name in _LEGACY_TABLES_TO_DROP:
                        if table_name not in existing:
                            continue
                        connection.exec_driver_sql(f'DROP TABLE IF EXISTS "{table_name}"')
                        dropped.append(table_name)
            finally:
                _restore_sqlite_foreign_keys(connection)
            _assert_sqlite_foreign_key_check(connection)
        return tuple(dropped)

    def run(self) -> dict[str, Any]:
        # SQLite is deployed as one application replica. This lock provides one runner inside
        # that process; the persistent ledger makes an interrupted attempt resumable after restart.
        with _RUN_LOCK:
            if not self._claim_run():
                return {"already_completed": True}
            try:
                result: dict[str, Any] = {
                    "core_memories_migrated": self._migrate_core_memory(),
                    "memory_vnext_migrated": self._migrate_memory_vnext(),
                    "episodes_migrated": self._migrate_episodes(),
                    "behavior_state": self._migrate_behavior_event_schema(),
                    "discovery_share_schema_rebuilt": self._migrate_discovery_share_schema(),
                }
                result["dropped_tables"] = self._drop_legacy_tables()
                self._complete_run()
                return result
            except Exception as error:
                self._fail_run(error)
                raise


__all__ = ["IntelligenceV3HardCutoverMigration"]
