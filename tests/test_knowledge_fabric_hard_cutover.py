from __future__ import annotations

import json
from os import environ

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.engine import make_url

from echo_masque.persistence import Database
from echo_masque.persistence.intelligence_v3_migration_models import (
    IntelligenceV3HardCutoverMigrationRecord,
)
from echo_masque.persistence.knowledge_fabric_hard_cutover import (
    KNOWLEDGE_FABRIC_HARD_CUTOVER_ID,
    LEGACY_KNOWLEDGE_TABLES_TO_DROP,
    KnowledgeFabricHardCutoverMigration,
)
from echo_masque.persistence.knowledge_fabric_hard_cutover_models import (
    KnowledgeFabricHardCutoverMigrationRecord,
)
from echo_masque.persistence.semantic_vector_models import SemanticVectorRecord
from echo_masque.persistence.sqlite_to_postgres_migration import (
    SQLiteToPostgresMigrationError,
    _assert_source_schema_is_current,
)


def _legacy_fixture(database: Database) -> None:
    with database.engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE knowledge_bases (id VARCHAR(64) PRIMARY KEY NOT NULL)"
        )


        connection.exec_driver_sql(
            "CREATE TABLE knowledge_documents (id VARCHAR(64) PRIMARY KEY NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE knowledge_chunks (id VARCHAR(64) PRIMARY KEY NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE knowledge_wiki_pages ("
            "id VARCHAR(64) PRIMARY KEY NOT NULL, "
            "knowledge_base_id VARCHAR(64) NOT NULL REFERENCES knowledge_bases(id))"
        )
        connection.exec_driver_sql(
            "CREATE TABLE server_wiki_pages_v3 (id VARCHAR(64) PRIMARY KEY NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE knowledge_consolidation_checkpoints_v3 ("
            "id VARCHAR(64) PRIMARY KEY NOT NULL)"
        )
        connection.exec_driver_sql("INSERT INTO knowledge_bases (id) VALUES ('legacy-base')")
        connection.exec_driver_sql(
            "INSERT INTO knowledge_wiki_pages (id, knowledge_base_id) "
            "VALUES ('legacy-page', 'legacy-base')"
        )
    with database.session() as session:
        session.add_all(
            (
                SemanticVectorRecord(
                    id="legacy-vector",
                    owner_id="owner",
                    namespace="knowledge-chunk",
                    resource_id="chunk",
                    source_hash="hash",
                    semantic_text="old",
                    model_name="model",
                    dimension=1,
                    embedding_blob=b"\0",
                ),
                SemanticVectorRecord(
                    id="retained-vector",
                    owner_id="owner",
                    namespace="conversation",
                    resource_id="episode",
                    source_hash="hash",
                    semantic_text="keep",
                    model_name="model",
                    dimension=1,
                    embedding_blob=b"\0",
                ),
            )
        )
        session.commit()


def _destructive_postgres_test_url() -> str:
    postgres_url = environ.get("ECHO_MASQUE_TEST_POSTGRES_URL")
    if not postgres_url:
        pytest.skip("ECHO_MASQUE_TEST_POSTGRES_URL is not configured")
    parsed = make_url(postgres_url)
    if parsed.get_backend_name() != "postgresql" or parsed.database != "echo_masque_test":
        pytest.fail("PostgreSQL cutover tests only reset echo_masque_test.")
    if environ.get("ECHO_MASQUE_ALLOW_DESTRUCTIVE_POSTGRES_TESTS") != "yes":
        pytest.fail("Set ECHO_MASQUE_ALLOW_DESTRUCTIVE_POSTGRES_TESTS=yes.")
    return postgres_url


def test_hard_cutover_drops_legacy_tables_and_only_legacy_vectors() -> None:
    database = Database("sqlite://")
    database.initialize(run_legacy_migrations=False)
    _legacy_fixture(database)

    KnowledgeFabricHardCutoverMigration(database).run()

    tables = set(inspect(database.engine).get_table_names())
    assert not tables.intersection(LEGACY_KNOWLEDGE_TABLES_TO_DROP)
    with database.engine.connect() as connection:
        retained = connection.exec_driver_sql(
            "SELECT namespace FROM semantic_vectors ORDER BY id"
        ).scalars().all()
    assert retained == ["conversation"]
    with database.session() as session:
        record = session.get(
            KnowledgeFabricHardCutoverMigrationRecord,
            KNOWLEDGE_FABRIC_HARD_CUTOVER_ID,
        )
    assert record is not None
    assert record.status == "completed"
    assert set(json.loads(record.retired_tables_json)) == set(LEGACY_KNOWLEDGE_TABLES_TO_DROP)
    assert json.loads(record.retired_row_counts_json) == {"semantic_vectors:knowledge-chunk": 1}

    KnowledgeFabricHardCutoverMigration(database).run()
    with database.session() as session:
        replay = session.scalar(select(KnowledgeFabricHardCutoverMigrationRecord))
    assert replay is not None
    assert replay.attempt_count == 1


def test_postgresql_copy_preflight_rejects_uncut_legacy_knowledge_tables() -> None:
    database = Database("sqlite://")
    database.initialize(run_legacy_migrations=False)
    _legacy_fixture(database)
    with database.session() as session:
        session.add(
            IntelligenceV3HardCutoverMigrationRecord(
                id="intelligence-v3-hard-cutover-v1",
                status="completed",
                attempt_count=1,
            )
        )
        session.commit()

    with pytest.raises(SQLiteToPostgresMigrationError, match="hard cutover is not completed"):
        _assert_source_schema_is_current(database)


def test_hard_cutover_removes_legacy_storage_on_disposable_postgresql() -> None:
    database = Database(_destructive_postgres_test_url())
    with database.engine.begin() as connection:
        connection.exec_driver_sql("DROP SCHEMA public CASCADE")
        connection.exec_driver_sql("CREATE SCHEMA public")
    database.initialize(run_legacy_migrations=False)
    _legacy_fixture(database)

    KnowledgeFabricHardCutoverMigration(database).run()

    tables = set(inspect(database.engine).get_table_names())
    assert not tables.intersection(LEGACY_KNOWLEDGE_TABLES_TO_DROP)
    with database.engine.connect() as connection:
        namespaces = connection.exec_driver_sql(
            "SELECT namespace FROM semantic_vectors ORDER BY id"
        ).scalars().all()
    assert namespaces == ["conversation"]
