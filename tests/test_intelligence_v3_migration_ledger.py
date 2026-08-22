from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from echo_masque.persistence.belief_models import BeliefV3Record
from echo_masque.persistence.database import Database
from echo_masque.persistence.intelligence_v3_migration import IntelligenceV3HardCutoverMigration
from echo_masque.persistence.intelligence_v3_migration_models import (
    IntelligenceV3HardCutoverMigrationRecord,
)
from echo_masque.persistence.models import Base


def _legacy_core_memory_name() -> str:
    return "character_core_" + "memories"


def _add_legacy_core_memory(database: Database) -> None:
    table = _legacy_core_memory_name()
    with database.engine.begin() as connection:
        connection.exec_driver_sql(
            f"""
            CREATE TABLE {table} (
                id VARCHAR(64) PRIMARY KEY,
                status VARCHAR(32),
                owner_id VARCHAR(120),
                character_card_id VARCHAR(64),
                connection_id VARCHAR(64),
                guild_id VARCHAR(200),
                subject_user_id VARCHAR(240),
                memory_type VARCHAR(160),
                content TEXT,
                scope_type VARCHAR(40),
                priority FLOAT
            )
            """
        )
        connection.exec_driver_sql(
            f"""
            INSERT INTO {table} (
                id, status, owner_id, character_card_id, connection_id, guild_id,
                subject_user_id, memory_type, content, scope_type, priority
            ) VALUES (
                'legacy-core-1', 'active', 'owner-1', 'card-1', 'connection-1', 'guild-1',
                'user-1', 'profile', 'Confirmed durable evidence.', 'server', 0.8
            )
            """
        )


def _add_outdated_discovery_share_table(database: Database) -> None:
    with database.engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE deployment_discovery_shares (
                id VARCHAR(64) PRIMARY KEY,
                owner_id VARCHAR(120) NOT NULL,
                deployment_id VARCHAR(64) NOT NULL,
                discovery_item_id VARCHAR(64) NOT NULL,
                source_decision_id VARCHAR(64) NOT NULL,
                mode VARCHAR(24) NOT NULL,
                status VARCHAR(32) NOT NULL,
                motivation VARCHAR(64) NOT NULL,
                confidence FLOAT NOT NULL,
                relationship_subject_key VARCHAR(320) NOT NULL,
                channel_id VARCHAR(200) NOT NULL,
                thread_id VARCHAR(200) NOT NULL,
                draft_text TEXT NOT NULL,
                discord_message_id VARCHAR(200) NOT NULL,
                attempt_count INTEGER NOT NULL,
                next_attempt_at DATETIME,
                last_error TEXT NOT NULL,
                approved_at DATETIME,
                rejected_at DATETIME,
                queued_at DATETIME,
                delivered_at DATETIME,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """
        )
def _ledger(database: Database) -> IntelligenceV3HardCutoverMigrationRecord:
    with database.session() as session:
        record = session.scalar(select(IntelligenceV3HardCutoverMigrationRecord))
        assert record is not None
        return record


def test_fresh_database_records_completed_cutover_once(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'fresh.db'}"
    database = Database(url)
    database.initialize()

    first = _ledger(database)
    assert first.status == "completed"
    assert first.attempt_count == 1
    assert first.completed_at is not None

    restarted = Database(url)
    restarted.initialize()
    second = _ledger(restarted)
    assert second.status == "completed"
    assert second.attempt_count == 1


def test_legacy_cutover_is_repeat_safe_after_restart(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    database = Database(url)
    _add_outdated_discovery_share_table(database)
    Base.metadata.create_all(database.engine)
    _add_legacy_core_memory(database)

    database.initialize()

    assert _legacy_core_memory_name() not in inspect(database.engine).get_table_names()
    with database.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    with database.session() as session:
        assert len(list(session.scalars(select(BeliefV3Record)))) == 1
    assert _ledger(database).status == "completed"

    restarted = Database(url)
    restarted.initialize()
    with restarted.session() as session:
        assert len(list(session.scalars(select(BeliefV3Record)))) == 1
    assert _ledger(restarted).attempt_count == 1


def test_interrupted_cutover_retries_from_persisted_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = f"sqlite:///{tmp_path / 'interrupted.db'}"
    database = Database(url)
    Base.metadata.create_all(database.engine)
    _add_legacy_core_memory(database)
    migration = IntelligenceV3HardCutoverMigration(database)

    def interrupt() -> int:
        raise RuntimeError("injected interruption")

    monkeypatch.setattr(migration, "_migrate_core_memory", interrupt)
    with pytest.raises(RuntimeError, match="injected interruption"):
        migration.run()

    interrupted = _ledger(database)
    assert interrupted.status == "failed"
    assert interrupted.attempt_count == 1
    assert interrupted.last_error == "RuntimeError"
    assert _legacy_core_memory_name() in inspect(database.engine).get_table_names()

    restarted = Database(url)
    restarted.initialize()
    completed = _ledger(restarted)
    assert completed.status == "completed"
    assert completed.attempt_count == 2
    with restarted.session() as session:
        assert len(list(session.scalars(select(BeliefV3Record)))) == 1


def test_sqlite_connections_enable_foreign_key_checks(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'foreign-keys.db'}")
    database.initialize()

    with database.engine.connect() as first, database.engine.connect() as second:
        assert first.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert second.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
    with pytest.raises(IntegrityError), database.engine.begin() as connection:
        connection.exec_driver_sql(
            """
            INSERT INTO character_key_group_assignments (
                id, owner_id, character_card_id, capability, key_group_id,
                model_override, created_at, updated_at
            ) VALUES ('invalid-assignment', 'missing-owner', 'missing-card', 'character',
                'missing-group', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
    with database.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []


def test_concurrent_initialization_runs_cutover_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = f"sqlite:///{tmp_path / 'concurrent.db'}"
    seed = Database(url)
    Base.metadata.create_all(seed.engine)
    calls = 0
    calls_lock = Lock()
    original = IntelligenceV3HardCutoverMigration._migrate_core_memory

    def count_runner(migration: IntelligenceV3HardCutoverMigration) -> int:
        nonlocal calls
        with calls_lock:
            calls += 1
        return original(migration)

    monkeypatch.setattr(IntelligenceV3HardCutoverMigration, "_migrate_core_memory", count_runner)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(Database(url).initialize) for _ in range(2)]
        for future in futures:
            future.result()

    assert calls == 1
    assert _ledger(Database(url)).attempt_count == 1
