"""Explicit SQLite-to-PostgreSQL data migration for the database foundation phase."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import Integer, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from echo_masque.persistence.database import Database, normalize_postgresql_driver_url
from echo_masque.persistence.intelligence_v3_migration import (
    _LEGACY_TABLES_TO_DROP,
    _MIGRATION_LEDGER_ID,
)
from echo_masque.persistence.intelligence_v3_migration_models import (
    IntelligenceV3HardCutoverMigrationRecord,
)
from echo_masque.persistence.knowledge_fabric_hard_cutover import (
    KNOWLEDGE_FABRIC_HARD_CUTOVER_ID,
    LEGACY_KNOWLEDGE_TABLES_TO_DROP,
)
from echo_masque.persistence.knowledge_fabric_hard_cutover_models import (
    KnowledgeFabricHardCutoverMigrationRecord,
)
from echo_masque.persistence.models import Base
from echo_masque.persistence.schema_migration_models import DatabaseDataMigrationRecord

SQLITE_TO_POSTGRES_MIGRATION_ID = "sqlite-to-postgresql-v1"
_MIGRATION_TABLES = {"database_schema_migrations", "database_data_migrations"}
_COPY_BATCH_SIZE = 500


class SQLiteToPostgresMigrationError(RuntimeError):
    """Raised when an explicit source-to-target migration is unsafe to continue."""


def migrate_sqlite_to_postgres(
    source_url: str,
    target_url: str,
    *,
    backup_directory: Path | None = None,
) -> dict[str, object]:
    """Copy a current SQLite database into an empty PostgreSQL database once.

    The tool keeps SQLite as the source of truth until the copy completes.  It
    creates a file backup, never mutates or deletes the source, and refuses to
    merge into a non-empty target.  The SQLite source must already be at the
    current application schema; this avoids a migration tool silently changing
    the only rollback authority during a database cutover.
    """

    source = make_url(source_url)
    target_url = normalize_postgresql_driver_url(target_url)
    target = make_url(target_url)
    if source.get_backend_name() != "sqlite":
        raise SQLiteToPostgresMigrationError("The source database must be SQLite.")
    if target.get_backend_name() != "postgresql":
        raise SQLiteToPostgresMigrationError("The target database must be PostgreSQL.")
    if source.database in {None, "", ":memory:"}:
        raise SQLiteToPostgresMigrationError("The SQLite source must be a persistent file.")

    source_path = Path(str(source.database)).expanduser().resolve()
    if not source_path.exists():
        raise SQLiteToPostgresMigrationError("The SQLite source file does not exist.")
    backup_path = _backup_sqlite_source(source_path, backup_directory)
    source_fingerprint = _source_fingerprint(backup_path)

    source_database = Database(f"sqlite:///{backup_path}")
    _assert_source_schema_is_current(source_database)
    target_database = Database(target_url)
    target_database.initialize(
        run_legacy_migrations=False,
        allow_incomplete_data_migration=True,
    )

    completed_counts = _prepare_target_migration(target_database, source_fingerprint)
    if completed_counts is not None:
        source_database.engine.dispose()
        target_database.engine.dispose()
        return {
            "status": "already_completed",
            "backup_path": str(backup_path),
            "source_fingerprint": source_fingerprint,
            "table_counts": completed_counts,
        }

    try:
        table_counts = _copy_all_tables(source_database, target_database)
        target_database.initialize(allow_incomplete_data_migration=True)
        _mark_completed(target_database, table_counts)
    except Exception as error:
        _mark_failed(target_database, error)
        raise
    finally:
        source_database.engine.dispose()
        target_database.engine.dispose()

    return {
        "status": "completed",
        "backup_path": str(backup_path),
        "source_fingerprint": source_fingerprint,
        "table_counts": table_counts,
    }


def _backup_sqlite_source(source_path: Path, backup_directory: Path | None) -> Path:
    """Create a consistent SQLite snapshot, including committed WAL content."""

    destination_directory = (backup_directory or source_path.parent).expanduser().resolve()
    destination_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    destination = destination_directory / (
        f"{source_path.name}.postgresql-{timestamp}-{uuid4().hex[:12]}.bak"
    )
    with sqlite3.connect(source_path) as source_connection, sqlite3.connect(
        destination
    ) as destination_connection:
        source_connection.backup(destination_connection)
    return destination


def _source_fingerprint(snapshot_path: Path) -> str:
    """Fingerprint the exact consistent snapshot, never a location string."""

    digest = hashlib.sha256()
    with snapshot_path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _assert_source_schema_is_current(database: Database) -> None:
    inspector = inspect(database.engine)
    existing_tables = set(inspector.get_table_names())
    missing_tables: list[str] = []
    missing_columns: list[str] = []
    for table in Base.metadata.sorted_tables:
        if table.name in _MIGRATION_TABLES:
            continue
        if table.name not in existing_tables:
            missing_tables.append(table.name)
            continue
        existing_columns = {column["name"] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name not in existing_columns:
                missing_columns.append(f"{table.name}.{column.name}")
    if missing_tables or missing_columns:
        details = ", ".join(sorted(missing_tables + missing_columns)[:12])
        raise SQLiteToPostgresMigrationError(
            "The SQLite source is not at the current application schema. "
            "Start the current application against a verified copy of the source, "
            "then retry the PostgreSQL copy. Missing: " + details
        )

    _assert_source_intelligence_cutover_is_complete(database, existing_tables)
    _assert_source_knowledge_fabric_cutover_is_complete(database, existing_tables)
    _assert_source_legacy_tables_are_empty(database, existing_tables)


def _assert_source_intelligence_cutover_is_complete(
    database: Database, existing_tables: set[str]
) -> None:
    if "intelligence_v3_hard_cutover_migrations" not in existing_tables:
        return
    with database.session() as session:
        record = session.get(IntelligenceV3HardCutoverMigrationRecord, _MIGRATION_LEDGER_ID)
    if record is None or record.status != "completed":
        raise SQLiteToPostgresMigrationError(
            "The SQLite source Intelligence v3 hard-cutover is not completed. "
            "Repair or finish it on a verified source copy before PostgreSQL migration."
        )


def _assert_source_knowledge_fabric_cutover_is_complete(
    database: Database, existing_tables: set[str]
) -> None:
    legacy_tables = set(LEGACY_KNOWLEDGE_TABLES_TO_DROP).intersection(existing_tables)
    if not legacy_tables:
        return
    if "knowledge_fabric_hard_cutover_migrations" not in existing_tables:
        raise SQLiteToPostgresMigrationError(
            "The SQLite source still contains retired Knowledge Base or Server Wiki tables. "
            "Run the Knowledge Fabric hard cutover on a verified source copy before migration."
        )
    with database.session() as session:
        record = session.get(
            KnowledgeFabricHardCutoverMigrationRecord,
            KNOWLEDGE_FABRIC_HARD_CUTOVER_ID,
        )
    if record is None or record.status != "completed":
        raise SQLiteToPostgresMigrationError(
            "The SQLite source Knowledge Fabric hard cutover is not completed. "
            "Repair or finish it on a verified source copy before PostgreSQL migration."
        )
    raise SQLiteToPostgresMigrationError(
        "The SQLite source still contains retired Knowledge Base or Server Wiki tables after "
        "its completed Knowledge Fabric hard cutover: "
        + ", ".join(sorted(legacy_tables))
    )


def _assert_source_legacy_tables_are_empty(database: Database, existing_tables: set[str]) -> None:
    legacy_tables = sorted(set(_LEGACY_TABLES_TO_DROP).intersection(existing_tables))
    if not legacy_tables:
        return
    with database.engine.connect() as connection:
        populated = [
            table_name
            for table_name in legacy_tables
            if connection.exec_driver_sql(
                f'SELECT EXISTS(SELECT 1 FROM "{table_name}" LIMIT 1)'
            ).scalar()
        ]
    if populated:
        raise SQLiteToPostgresMigrationError(
            "The SQLite source still contains unmigrated legacy Intelligence tables: "
            + ", ".join(populated)
        )


def _prepare_target_migration(
    database: Database, source_fingerprint: str
) -> dict[str, int] | None:
    """Take one target lock, reject a dirty target, and claim this copy operation."""

    with database.engine.begin() as connection:
        if database.engine.dialect.name == "postgresql":
            connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                {"key": SQLITE_TO_POSTGRES_MIGRATION_ID},
            )
        session = Session(bind=connection, expire_on_commit=False)
        try:
            record = session.get(DatabaseDataMigrationRecord, SQLITE_TO_POSTGRES_MIGRATION_ID)
            if record is not None:
                if record.status == "completed" and record.source_fingerprint == source_fingerprint:
                    return {
                        str(name): int(count)
                        for name, count in json.loads(record.table_counts_json).items()
                    }
                raise SQLiteToPostgresMigrationError(
                    "The target already has a SQLite-to-PostgreSQL migration record. "
                    "Use a fresh target database instead of merging source data."
                )
            _assert_target_is_empty(connection)
            now = datetime.now(UTC)
            session.add(
                DatabaseDataMigrationRecord(
                    id=SQLITE_TO_POSTGRES_MIGRATION_ID,
                    source_fingerprint=source_fingerprint,
                    status="running",
                    table_counts_json="{}",
                    started_at=now,
                    updated_at=now,
                    completed_at=None,
                    last_error="",
                )
            )
            session.flush()
            return None
        finally:
            session.close()


def _assert_target_is_empty(connection: Any) -> None:
    inspector = inspect(connection)
    expected_tables = {table.name for table in Base.metadata.sorted_tables}
    actual_tables = set(inspector.get_table_names())
    unknown_tables = actual_tables - expected_tables
    views = set(inspector.get_view_names())
    if unknown_tables or views:
        unknown = sorted(unknown_tables | views)
        raise SQLiteToPostgresMigrationError(
            "The PostgreSQL target contains unexpected tables or views: " + ", ".join(unknown)
        )
    populated = [
        table.name
        for table in Base.metadata.sorted_tables
        if table.name not in _MIGRATION_TABLES
        and connection.execute(select(func.count()).select_from(table)).scalar_one() > 0
    ]
    if populated:
        raise SQLiteToPostgresMigrationError(
            "The PostgreSQL target contains product data and cannot be merged: "
            + ", ".join(sorted(populated))
        )


def _copy_all_tables(source: Database, target: Database) -> dict[str, int]:
    counts: dict[str, int] = {}
    with source.engine.connect() as source_connection, target.engine.begin() as target_connection:
        for table in Base.metadata.sorted_tables:
            if table.name in _MIGRATION_TABLES:
                continue
            copied = 0
            result = source_connection.execute(select(table)).mappings()
            while rows := result.fetchmany(_COPY_BATCH_SIZE):
                payload: list[dict[str, Any]] = [dict(row) for row in rows]
                target_connection.execute(table.insert(), payload)
                copied += len(payload)
            counts[table.name] = copied
        _reset_postgresql_sequences(target_connection)
    return counts


def _reset_postgresql_sequences(connection: Any) -> None:
    """Advance PostgreSQL integer identity sequences after preserving source IDs."""

    for table in Base.metadata.sorted_tables:
        if table.name in _MIGRATION_TABLES:
            continue
        primary_key = list(table.primary_key.columns)
        if len(primary_key) != 1:
            continue
        column = primary_key[0]
        if not isinstance(column.type, Integer) or not column.autoincrement:
            continue
        quoted_table = f'"{table.name}"'
        quoted_column = f'"{column.name}"'
        connection.execute(
            text(
                "SELECT setval(pg_get_serial_sequence(:table_name, :column_name), "
                f"COALESCE((SELECT MAX({quoted_column}) FROM {quoted_table}), 1), "
                f"(SELECT MAX({quoted_column}) IS NOT NULL FROM {quoted_table}))"
            ),
            {"table_name": table.name, "column_name": column.name},
        )


def _mark_completed(database: Database, table_counts: dict[str, int]) -> None:
    with database.session() as session:
        record = session.get(DatabaseDataMigrationRecord, SQLITE_TO_POSTGRES_MIGRATION_ID)
        if record is None:
            raise SQLiteToPostgresMigrationError("Migration ledger record disappeared.")
        now = datetime.now(UTC)
        record.status = "completed"
        record.table_counts_json = json.dumps(table_counts, sort_keys=True)
        record.updated_at = now
        record.completed_at = now
        record.last_error = ""
        session.commit()


def _mark_failed(database: Database, error: Exception) -> None:
    with database.session() as session:
        record = session.get(DatabaseDataMigrationRecord, SQLITE_TO_POSTGRES_MIGRATION_ID)
        if record is None or record.status == "completed":
            return
        record.status = "failed"
        record.updated_at = datetime.now(UTC)
        record.last_error = type(error).__name__[:120]
        session.commit()


__all__ = [
    "SQLITE_TO_POSTGRES_MIGRATION_ID",
    "SQLiteToPostgresMigrationError",
    "migrate_sqlite_to_postgres",
]
