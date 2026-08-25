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


__all__ = [
    "DATABASE_FOUNDATION_REVISION",
    "KNOWLEDGE_FABRIC_SCOPE_REVISION",
    "DatabaseFoundationMigration",
    "KnowledgeFabricScopeMigration",
]
