import sqlite3
from os import environ
from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import (
    CharacterDeploymentRecord,
)
from echo_masque.persistence.deployment_presence_models import DeploymentPresenceRecord
from echo_masque.persistence.intelligence_v3_migration_models import (
    IntelligenceV3HardCutoverMigrationRecord,
)
from echo_masque.persistence.knowledge_fabric_repository import KnowledgeFabricRepository
from echo_masque.persistence.models import TargetRecord
from echo_masque.persistence.schema_migration_models import (
    DatabaseDataMigrationRecord,
    DatabaseSchemaMigrationRecord,
)
from echo_masque.persistence.schema_migrations import (
    DATABASE_FOUNDATION_REVISION,
    KNOWLEDGE_FABRIC_CONTENT_REVISION,
    KNOWLEDGE_FABRIC_SCOPE_REVISION,
)
from echo_masque.persistence.sqlite_to_postgres_migration import (
    SQLiteToPostgresMigrationError,
    _assert_source_schema_is_current,
    _assert_target_is_empty,
    _backup_sqlite_source,
    _prepare_target_migration,
    _source_fingerprint,
    migrate_sqlite_to_postgres,
)


def _deployment(identifier: str, *, channel_id: str) -> CharacterDeploymentRecord:
    return CharacterDeploymentRecord(
        id=identifier,
        owner_id="owner-1",
        character_card_id="character-1",
        connection_id="connection-1",
        platform="discord",
        workspace_id="guild-1",
        workspace_name="Guild One",
        channel_id=channel_id,
        channel_name=f"#{channel_id}",
        thread_id="",
        thread_name="",
        participation_mode="mention_and_reply",
        memory_scope="channel_isolated",
        version_label="Current",
        sticker_count=0,
        status="paused",
    )


def _destructive_postgres_test_url() -> str:
    """Return the sole explicitly approved disposable database for schema-reset tests."""

    postgres_url = environ.get("ECHO_MASQUE_TEST_POSTGRES_URL")
    if not postgres_url:
        pytest.skip("ECHO_MASQUE_TEST_POSTGRES_URL is not configured")
    parsed = make_url(postgres_url)
    if parsed.get_backend_name() != "postgresql" or parsed.database != "echo_masque_test":
        pytest.fail(
            "PostgreSQL foundation tests only reset the dedicated echo_masque_test database."
        )
    if environ.get("ECHO_MASQUE_ALLOW_DESTRUCTIVE_POSTGRES_TESTS") != "yes":
        pytest.fail(
            "Set ECHO_MASQUE_ALLOW_DESTRUCTIVE_POSTGRES_TESTS=yes to reset the test schema."
        )
    return postgres_url


def test_sqlite_foundation_revision_is_idempotent(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'foundation.db'}")
    database.initialize()
    database.initialize()

    with database.session() as session:
        record = session.get(DatabaseSchemaMigrationRecord, DATABASE_FOUNDATION_REVISION)

    assert record is not None
    assert record.database_kind == "sqlite"


def test_sqlite_to_postgres_rejects_non_postgresql_target(tmp_path: Path) -> None:
    source_path = tmp_path / "source.db"
    with pytest.raises(SQLiteToPostgresMigrationError, match="target database must be PostgreSQL"):
        migrate_sqlite_to_postgres(
            f"sqlite:///{source_path}",
            f"sqlite:///{tmp_path / 'target.db'}",
        )


def test_destructive_postgres_test_guard_requires_dedicated_database_and_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "ECHO_MASQUE_TEST_POSTGRES_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5432/operator_database",
    )
    monkeypatch.setenv("ECHO_MASQUE_ALLOW_DESTRUCTIVE_POSTGRES_TESTS", "yes")
    with pytest.raises(pytest.fail.Exception, match="dedicated echo_masque_test database"):
        _destructive_postgres_test_url()

    monkeypatch.setenv(
        "ECHO_MASQUE_TEST_POSTGRES_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5432/echo_masque_test",
    )
    monkeypatch.delenv("ECHO_MASQUE_ALLOW_DESTRUCTIVE_POSTGRES_TESTS")
    with pytest.raises(pytest.fail.Exception, match="ALLOW_DESTRUCTIVE"):
        _destructive_postgres_test_url()


def test_sqlite_snapshot_includes_committed_wal_content_and_has_unique_backups(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "wal-source.db"
    with sqlite3.connect(source_path) as source:
        source.execute("PRAGMA journal_mode=WAL")
        source.execute("CREATE TABLE snapshot_probe (value TEXT NOT NULL)")
        source.execute("INSERT INTO snapshot_probe (value) VALUES ('present-in-wal')")
        source.commit()
        assert (tmp_path / "wal-source.db-wal").exists()

    first = _backup_sqlite_source(source_path, tmp_path / "backups")
    second = _backup_sqlite_source(source_path, tmp_path / "backups")

    assert first != second
    with sqlite3.connect(first) as snapshot:
        row = snapshot.execute("SELECT value FROM snapshot_probe").fetchone()
    assert row == ("present-in-wal",)
    assert _source_fingerprint(first) == _source_fingerprint(second)

    with sqlite3.connect(source_path) as source:
        source.execute("INSERT INTO snapshot_probe (value) VALUES ('changed-source')")
        source.commit()
    changed = _backup_sqlite_source(source_path, tmp_path / "backups")
    assert _source_fingerprint(changed) != _source_fingerprint(first)


def test_sqlite_source_rejects_unfinished_intelligence_cutover_and_legacy_data(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{tmp_path / 'legacy-source.db'}")
    database.initialize()

    with database.session() as session:
        record = session.get(
            IntelligenceV3HardCutoverMigrationRecord,
            "intelligence-v3-hard-cutover-v1",
        )
        assert record is not None
        record.status = "failed"
        session.commit()
    with pytest.raises(SQLiteToPostgresMigrationError, match="hard-cutover is not completed"):
        _assert_source_schema_is_current(database)

    with database.session() as session:
        record = session.get(
            IntelligenceV3HardCutoverMigrationRecord,
            "intelligence-v3-hard-cutover-v1",
        )
        assert record is not None
        record.status = "completed"
        session.commit()
    with database.engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE character_core_memories (id TEXT PRIMARY KEY)")
        connection.exec_driver_sql("INSERT INTO character_core_memories (id) VALUES ('legacy-1')")
    with pytest.raises(
        SQLiteToPostgresMigrationError,
        match="unmigrated legacy Intelligence tables",
    ):
        _assert_source_schema_is_current(database)


def test_target_preflight_rejects_unknown_table_and_claim_is_idempotent(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'target.db'}")
    database.initialize(run_legacy_migrations=False)
    with database.engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE unexpected_legacy_table (id TEXT PRIMARY KEY)")
        with pytest.raises(SQLiteToPostgresMigrationError, match="unexpected tables or views"):
            _assert_target_is_empty(connection)
        connection.exec_driver_sql("DROP TABLE unexpected_legacy_table")

    assert _prepare_target_migration(database, "fingerprint") is None
    with database.session() as session:
        record = session.get(DatabaseDataMigrationRecord, "sqlite-to-postgresql-v1")
        assert record is not None
        record.status = "completed"
        session.commit()
    assert _prepare_target_migration(database, "fingerprint") == {}


def test_database_initialize_rejects_incomplete_data_migration(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'incomplete-target.db'}")
    database.initialize(run_legacy_migrations=False)
    assert _prepare_target_migration(database, "fingerprint") is None

    with pytest.raises(RuntimeError, match="startup is blocked"):
        database.initialize()

    with database.session() as session:
        record = session.get(DatabaseDataMigrationRecord, "sqlite-to-postgresql-v1")
        assert record is not None
        record.status = "failed"
        session.commit()
    with pytest.raises(RuntimeError, match="'failed'"):
        database.initialize()

    database.initialize(allow_incomplete_data_migration=True)


def test_postgresql_foundation_when_explicit_test_database_is_available() -> None:
    """Exercise pgvector bootstrap and ported runtime invariants on disposable PostgreSQL."""

    postgres_url = _destructive_postgres_test_url()

    database = Database(postgres_url)
    with database.engine.begin() as connection:
        # The helper permits only the dedicated, explicitly opted-in test database.
        connection.exec_driver_sql("DROP SCHEMA public CASCADE")
        connection.exec_driver_sql("CREATE SCHEMA public")
    database.initialize()

    with database.engine.connect() as connection:
        assert connection.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        ).scalar_one() == "vector"
        inspector = inspect(connection)
        table_names = set(inspector.get_table_names())
        corpus_indexes = {index["name"] for index in inspector.get_indexes("knowledge_corpora")}
        grant_indexes = {
            index["name"] for index in inspector.get_indexes("knowledge_access_grants")
        }
    assert {
        "knowledge_server_scopes",
        "knowledge_server_administrators",
        "knowledge_corpora",
        "knowledge_sources",
        "knowledge_object_artifacts",
        "knowledge_source_versions",
        "knowledge_canonical_documents",
        "knowledge_canonical_sections",
        "knowledge_canonical_blocks",
        "knowledge_asset_references",
        "knowledge_evidence_units",
        "knowledge_ingestion_jobs",
        "knowledge_ingestion_checkpoints",
        "knowledge_dependency_invalidations",
        "knowledge_access_grants",
        "knowledge_overlay_policies",
    } <= table_names
    assert "ix_knowledge_corpora_owner_scope" in corpus_indexes
    assert "ix_knowledge_grant_grantee_access" in grant_indexes

    fabric = KnowledgeFabricRepository(database)
    scope = fabric.ensure_server_scope(
        platform="discord",
        connection_id="connection-fabric",
        workspace_id="guild-fabric",
    )
    corpus = fabric.create_system_global_corpus(
        name="PostgreSQL Fabric",
        description="",
        default_authority_profile="standard",
        status="active",
    )
    assert fabric.set_server_global_grant(
        server_scope_id=scope.id,
        corpus_id=corpus.id,
        enabled=True,
    ) is not None
    database.initialize()
    with database.session() as session:
        assert session.get(DatabaseSchemaMigrationRecord, KNOWLEDGE_FABRIC_SCOPE_REVISION)
        assert session.get(DatabaseSchemaMigrationRecord, KNOWLEDGE_FABRIC_CONTENT_REVISION)

    with database.session() as session:
        session.add(_deployment("deployment-a", channel_id="channel-a"))
        session.add(DeploymentPresenceRecord(deployment_id="deployment-a", owner_id="owner-1"))
        session.commit()

        session.add(_deployment("deployment-b", channel_id="channel-b"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        deployment = session.get(CharacterDeploymentRecord, "deployment-a")
        assert deployment is not None
        session.delete(deployment)
        session.commit()
        assert session.get(DeploymentPresenceRecord, "deployment-a") is None


def test_sqlite_to_postgres_migration_when_explicit_test_database_is_available(
    tmp_path: Path,
) -> None:
    postgres_url = _destructive_postgres_test_url()

    target = Database(postgres_url)
    with target.engine.begin() as connection:
        connection.exec_driver_sql("DROP SCHEMA public CASCADE")
        connection.exec_driver_sql("CREATE SCHEMA public")

    source_path = tmp_path / "production-source.db"
    source_url = f"sqlite:///{source_path}"
    source = Database(source_url)
    source.initialize()
    fabric = KnowledgeFabricRepository(source)
    scope = fabric.ensure_server_scope(
        platform="discord",
        connection_id="connection-fabric",
        workspace_id="guild-fabric",
    )
    corpus = fabric.create_system_global_corpus(
        name="Migrated Fabric",
        description="",
        default_authority_profile="standard",
        status="active",
    )
    assert fabric.set_server_global_grant(
        server_scope_id=scope.id,
        corpus_id=corpus.id,
        enabled=True,
    ) is not None
    with source.session() as session:
        session.add(TargetRecord(id="target-1", name="Migrated target", target_kind="stable"))
        session.commit()

    first = migrate_sqlite_to_postgres(
        source_url,
        postgres_url,
        backup_directory=tmp_path / "backups",
    )
    assert first["status"] == "completed"
    assert Path(str(first["backup_path"])).exists()
    assert first["table_counts"]["targets"] == 1

    migrated = Database(postgres_url)
    migrated.initialize()
    with migrated.session() as session:
        assert session.get(TargetRecord, "target-1") is not None
    migrated_fabric = KnowledgeFabricRepository(migrated)
    assert migrated_fabric.get_server_scope(scope.id) is not None
    assert migrated_fabric.get_corpus(corpus.id) is not None
    assert migrated_fabric.get_server_global_grant(
        server_scope_id=scope.id,
        corpus_id=corpus.id,
    ) is not None

    second = migrate_sqlite_to_postgres(
        source_url,
        postgres_url,
        backup_directory=tmp_path / "backups",
    )
    assert second["status"] == "already_completed"

    with source.session() as session:
        session.add(TargetRecord(id="target-2", name="Changed source", target_kind="stable"))
        session.commit()
    with pytest.raises(SQLiteToPostgresMigrationError, match="fresh target database"):
        migrate_sqlite_to_postgres(
            source_url,
            postgres_url,
            backup_directory=tmp_path / "backups",
        )
