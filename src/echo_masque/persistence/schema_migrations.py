"""Database-foundation migrations shared by SQLite and PostgreSQL.

This is intentionally a small explicit runner rather than a second ORM schema
definition.  `Base.metadata.create_all()` remains the bootstrap mechanism for
the established product schema; each irreversible database capability is then
recorded in the ledger below.  New PostgreSQL/pgvector DDL must be introduced as
a named revision here, never as an untracked startup side effect.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.engine import Connection

from echo_masque.persistence.schema_migration_models import DatabaseSchemaMigrationRecord

if TYPE_CHECKING:
    from echo_masque.persistence.database import Database

DATABASE_FOUNDATION_REVISION = "database-foundation-v1"
KNOWLEDGE_FABRIC_SCOPE_REVISION = "knowledge-fabric-scope-v1"
KNOWLEDGE_FABRIC_CONTENT_REVISION = "knowledge-fabric-content-v1"
KNOWLEDGE_FABRIC_INTERPRETATION_REVISION = "knowledge-fabric-interpretation-v1"
KNOWLEDGE_FABRIC_INDEX_REVISION = "knowledge-fabric-index-v1"
KNOWLEDGE_FABRIC_PROJECTION_REVISION = "knowledge-fabric-projection-v1"
KNOWLEDGE_FABRIC_EXTERNAL_SYNC_REVISION = "knowledge-fabric-external-sync-v1"


class DatabaseFoundationMigration:
    """Install the minimum durable foundation required for PostgreSQL rollout."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def run(self) -> None:
        """Create pgvector where required and record the idempotent foundation revision."""

        dialect = self.database.engine.dialect.name
        if dialect == "postgresql":
            self._run_postgresql()
            return
        self._record_non_postgresql_revision(dialect)

    def _run_postgresql(self) -> None:
        # Advisory transaction lock prevents two application replicas from trying to
        # bootstrap the extension/revision at the same time.  The extension command is
        # idempotent but the lock also gives later revisions one predictable mechanism.
        with self.database.engine.begin() as connection:
            connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                {"key": DATABASE_FOUNDATION_REVISION},
            )
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            applied = connection.execute(
                text(
                    "SELECT 1 FROM database_schema_migrations "
                    "WHERE revision = :revision"
                ),
                {"revision": DATABASE_FOUNDATION_REVISION},
            ).scalar_one_or_none()
            if applied is None:
                connection.execute(
                    text(
                        "INSERT INTO database_schema_migrations "
                        "(revision, database_kind, applied_at) "
                        "VALUES (:revision, :database_kind, :applied_at)"
                    ),
                    {
                        "revision": DATABASE_FOUNDATION_REVISION,
                        "database_kind": "postgresql",
                        "applied_at": datetime.now(UTC),
                    },
                )

    def _record_non_postgresql_revision(self, dialect: str) -> None:
        with self.database.session() as session:
            record = session.get(DatabaseSchemaMigrationRecord, DATABASE_FOUNDATION_REVISION)
            if record is None:
                session.add(
                    DatabaseSchemaMigrationRecord(
                        revision=DATABASE_FOUNDATION_REVISION,
                        database_kind=dialect,
                    )
                )
                session.commit()


class KnowledgeFabricScopeMigration:
    """Record the additive Phase 2 scope/access schema after deterministic bootstrap."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def run(self) -> None:
        dialect = self.database.engine.dialect.name
        if dialect == "postgresql":
            with self.database.engine.begin() as connection:
                connection.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                    {"key": KNOWLEDGE_FABRIC_SCOPE_REVISION},
                )
                self._record(connection, database_kind="postgresql")
            return
        with self.database.session() as session:
            if session.get(DatabaseSchemaMigrationRecord, KNOWLEDGE_FABRIC_SCOPE_REVISION) is None:
                session.add(
                    DatabaseSchemaMigrationRecord(
                        revision=KNOWLEDGE_FABRIC_SCOPE_REVISION,
                        database_kind=dialect,
                    )
                )
                session.commit()

    @staticmethod
    def _record(connection: Connection, *, database_kind: str) -> None:
        applied = connection.execute(
            text(
                "SELECT 1 FROM database_schema_migrations "
                "WHERE revision = :revision"
            ),
            {"revision": KNOWLEDGE_FABRIC_SCOPE_REVISION},
        ).scalar_one_or_none()
        if applied is None:
            connection.execute(
                text(
                    "INSERT INTO database_schema_migrations "
                    "(revision, database_kind, applied_at) "
                    "VALUES (:revision, :database_kind, :applied_at)"
                ),
                {
                    "revision": KNOWLEDGE_FABRIC_SCOPE_REVISION,
                    "database_kind": database_kind,
                    "applied_at": datetime.now(UTC),
                },
                )


class KnowledgeFabricContentMigration:
    """Record the additive Phase 3 immutable-content schema after bootstrap."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def run(self) -> None:
        dialect = self.database.engine.dialect.name
        if dialect == "postgresql":
            with self.database.engine.begin() as connection:
                connection.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                    {"key": KNOWLEDGE_FABRIC_CONTENT_REVISION},
                )
                self._record(connection, database_kind="postgresql")
            return
        with self.database.session() as session:
            if (
                session.get(DatabaseSchemaMigrationRecord, KNOWLEDGE_FABRIC_CONTENT_REVISION)
                is None
            ):
                session.add(
                    DatabaseSchemaMigrationRecord(
                        revision=KNOWLEDGE_FABRIC_CONTENT_REVISION,
                        database_kind=dialect,
                    )
                )
                session.commit()

    @staticmethod
    def _record(connection: Connection, *, database_kind: str) -> None:
        applied = connection.execute(
            text(
                "SELECT 1 FROM database_schema_migrations "
                "WHERE revision = :revision"
            ),
            {"revision": KNOWLEDGE_FABRIC_CONTENT_REVISION},
        ).scalar_one_or_none()
        if applied is None:
            connection.execute(
                text(
                    "INSERT INTO database_schema_migrations "
                    "(revision, database_kind, applied_at) "
                    "VALUES (:revision, :database_kind, :applied_at)"
                ),
                {
                    "revision": KNOWLEDGE_FABRIC_CONTENT_REVISION,
                    "database_kind": database_kind,
                    "applied_at": datetime.now(UTC),
                },
            )


class KnowledgeFabricInterpretationMigration:
    """Record the additive Phase 4 entity/assertion/event interpretation schema."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def run(self) -> None:
        dialect = self.database.engine.dialect.name
        if dialect == "postgresql":
            with self.database.engine.begin() as connection:
                connection.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                    {"key": KNOWLEDGE_FABRIC_INTERPRETATION_REVISION},
                )
                self._record(connection, database_kind="postgresql")
            return
        with self.database.session() as session:
            if (
                session.get(
                    DatabaseSchemaMigrationRecord,
                    KNOWLEDGE_FABRIC_INTERPRETATION_REVISION,
                )
                is None
            ):
                session.add(
                    DatabaseSchemaMigrationRecord(
                        revision=KNOWLEDGE_FABRIC_INTERPRETATION_REVISION,
                        database_kind=dialect,
                    )
                )
                session.commit()

    @staticmethod
    def _record(connection: Connection, *, database_kind: str) -> None:
        applied = connection.execute(
            text("SELECT 1 FROM database_schema_migrations WHERE revision = :revision"),
            {"revision": KNOWLEDGE_FABRIC_INTERPRETATION_REVISION},
        ).scalar_one_or_none()
        if applied is None:
            connection.execute(
                text(
                    "INSERT INTO database_schema_migrations "
                    "(revision, database_kind, applied_at) "
                    "VALUES (:revision, :database_kind, :applied_at)"
                ),
                {
                    "revision": KNOWLEDGE_FABRIC_INTERPRETATION_REVISION,
                    "database_kind": database_kind,
                    "applied_at": datetime.now(UTC),
                },
            )


class KnowledgeFabricIndexMigration:
    """Install PostgreSQL-only FTS and pgvector indexes over derived Evidence projections."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def run(self) -> None:
        dialect = self.database.engine.dialect.name
        if dialect == "postgresql":
            with self.database.engine.begin() as connection:
                connection.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                    {"key": KNOWLEDGE_FABRIC_INDEX_REVISION},
                )
                connection.execute(
                    text(
                        "ALTER TABLE knowledge_evidence_embeddings "
                        "ADD COLUMN IF NOT EXISTS embedding vector"
                    )
                )
                connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_knowledge_evidence_retrieval_entry_fts "
                        "ON knowledge_evidence_retrieval_entries "
                        "USING gin (to_tsvector('simple', retrieval_text))"
                    )
                )
                connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_knowledge_evidence_embedding_e5_384_hnsw "
                        "ON knowledge_evidence_embeddings USING hnsw "
                        "((embedding::vector(384)) vector_cosine_ops) "
                        "WHERE embedding IS NOT NULL "
                        "AND embedding_model = 'intfloat/multilingual-e5-small' "
                        "AND embedding_dimension = 384"
                    )
                )
                self._record(connection, database_kind="postgresql")
            return
        with self.database.session() as session:
            if session.get(DatabaseSchemaMigrationRecord, KNOWLEDGE_FABRIC_INDEX_REVISION) is None:
                session.add(
                    DatabaseSchemaMigrationRecord(
                        revision=KNOWLEDGE_FABRIC_INDEX_REVISION,
                        database_kind=dialect,
                    )
                )
                session.commit()

    @staticmethod
    def _record(connection: Connection, *, database_kind: str) -> None:
        applied = connection.execute(
            text("SELECT 1 FROM database_schema_migrations WHERE revision = :revision"),
            {"revision": KNOWLEDGE_FABRIC_INDEX_REVISION},
        ).scalar_one_or_none()
        if applied is None:
            connection.execute(
                text(
                    "INSERT INTO database_schema_migrations "
                    "(revision, database_kind, applied_at) "
                    "VALUES (:revision, :database_kind, :applied_at)"
                ),
                {
                    "revision": KNOWLEDGE_FABRIC_INDEX_REVISION,
                    "database_kind": database_kind,
                    "applied_at": datetime.now(UTC),
                },
            )


class KnowledgeFabricProjectionMigration:
    """Record the additive Projection schema after deterministic ORM bootstrap."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def run(self) -> None:
        dialect = self.database.engine.dialect.name
        if dialect == "postgresql":
            with self.database.engine.begin() as connection:
                connection.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                    {"key": KNOWLEDGE_FABRIC_PROJECTION_REVISION},
                )
                self._record(connection, database_kind="postgresql")
            return
        with self.database.session() as session:
            if (
                session.get(
                    DatabaseSchemaMigrationRecord,
                    KNOWLEDGE_FABRIC_PROJECTION_REVISION,
                )
                is None
            ):
                session.add(
                    DatabaseSchemaMigrationRecord(
                        revision=KNOWLEDGE_FABRIC_PROJECTION_REVISION,
                        database_kind=dialect,
                    )
                )
                session.commit()

    @staticmethod
    def _record(connection: Connection, *, database_kind: str) -> None:
        applied = connection.execute(
            text("SELECT 1 FROM database_schema_migrations WHERE revision = :revision"),
            {"revision": KNOWLEDGE_FABRIC_PROJECTION_REVISION},
        ).scalar_one_or_none()
        if applied is None:
            connection.execute(
                text(
                    "INSERT INTO database_schema_migrations "
                    "(revision, database_kind, applied_at) "
                    "VALUES (:revision, :database_kind, :applied_at)"
                ),
                {
                    "revision": KNOWLEDGE_FABRIC_PROJECTION_REVISION,
                    "database_kind": database_kind,
                    "applied_at": datetime.now(UTC),
                },
            )


class KnowledgeFabricExternalSyncMigration:
    """Record the additive external Source sync-state schema after ORM bootstrap."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def run(self) -> None:
        dialect = self.database.engine.dialect.name
        if dialect == "postgresql":
            with self.database.engine.begin() as connection:
                connection.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                    {"key": KNOWLEDGE_FABRIC_EXTERNAL_SYNC_REVISION},
                )
                self._record(connection, database_kind="postgresql")
            return
        with self.database.session() as session:
            if (
                session.get(
                    DatabaseSchemaMigrationRecord,
                    KNOWLEDGE_FABRIC_EXTERNAL_SYNC_REVISION,
                )
                is None
            ):
                session.add(
                    DatabaseSchemaMigrationRecord(
                        revision=KNOWLEDGE_FABRIC_EXTERNAL_SYNC_REVISION,
                        database_kind=dialect,
                    )
                )
                session.commit()

    @staticmethod
    def _record(connection: Connection, *, database_kind: str) -> None:
        applied = connection.execute(
            text("SELECT 1 FROM database_schema_migrations WHERE revision = :revision"),
            {"revision": KNOWLEDGE_FABRIC_EXTERNAL_SYNC_REVISION},
        ).scalar_one_or_none()
        if applied is None:
            connection.execute(
                text(
                    "INSERT INTO database_schema_migrations "
                    "(revision, database_kind, applied_at) "
                    "VALUES (:revision, :database_kind, :applied_at)"
                ),
                {
                    "revision": KNOWLEDGE_FABRIC_EXTERNAL_SYNC_REVISION,
                    "database_kind": database_kind,
                    "applied_at": datetime.now(UTC),
                },
            )


__all__ = [
    "DATABASE_FOUNDATION_REVISION",
    "KNOWLEDGE_FABRIC_CONTENT_REVISION",
    "KNOWLEDGE_FABRIC_EXTERNAL_SYNC_REVISION",
    "KNOWLEDGE_FABRIC_INDEX_REVISION",
    "KNOWLEDGE_FABRIC_INTERPRETATION_REVISION",
    "KNOWLEDGE_FABRIC_PROJECTION_REVISION",
    "KNOWLEDGE_FABRIC_SCOPE_REVISION",
    "DatabaseFoundationMigration",
    "KnowledgeFabricContentMigration",
    "KnowledgeFabricExternalSyncMigration",
    "KnowledgeFabricIndexMigration",
    "KnowledgeFabricInterpretationMigration",
    "KnowledgeFabricProjectionMigration",
    "KnowledgeFabricScopeMigration",
]
