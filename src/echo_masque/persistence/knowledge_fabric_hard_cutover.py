"""One-way retirement of the pre-Fabric Knowledge Base and Server Wiki v3 stores."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from threading import Lock

from sqlalchemy import inspect, text

from echo_masque.knowledge_fabric_hard_cutover_policy import (
    LEGACY_KNOWLEDGE_TABLES_TO_DROP,
    LEGACY_VECTOR_NAMESPACE,
    has_legacy_knowledge_vectors,
    retired_knowledge_tables,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.knowledge_fabric_hard_cutover_models import (
    KnowledgeFabricHardCutoverMigrationRecord,
)

KNOWLEDGE_FABRIC_HARD_CUTOVER_ID = "knowledge-fabric-hard-cutover-v1"
_RUN_LOCK = Lock()


class KnowledgeFabricHardCutoverMigration:
    """Delete retired data exactly once and record the irreversible product decision."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def run(self) -> None:
        with _RUN_LOCK:
            if not self._claim_run():
                return
            try:
                counts, retired_tables = self._retire_legacy_storage()
            except Exception as error:
                self._fail_run(error)
                raise
            self._complete_run(counts, retired_tables)

    def _claim_run(self) -> bool:
        now = datetime.now(UTC)
        with self.database.session() as session:
            record = session.get(
                KnowledgeFabricHardCutoverMigrationRecord,
                KNOWLEDGE_FABRIC_HARD_CUTOVER_ID,
            )
            if record is not None and record.status == "completed":
                return False
            if record is None:
                session.add(
                    KnowledgeFabricHardCutoverMigrationRecord(
                        id=KNOWLEDGE_FABRIC_HARD_CUTOVER_ID,
                        status="running",
                        attempt_count=1,
                        started_at=now,
                        updated_at=now,
                    )
                )
            else:
                record.status = "running"
                record.attempt_count += 1
                record.last_error = ""
                record.started_at = now
                record.updated_at = now
                record.completed_at = None
            session.commit()
        return True

    def _retire_legacy_storage(self) -> tuple[dict[str, int], tuple[str, ...]]:
        with self.database.engine.begin() as connection:
            if self.database.engine.dialect.name == "postgresql":
                connection.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                    {"key": KNOWLEDGE_FABRIC_HARD_CUTOVER_ID},
                )
            existing = set(inspect(connection).get_table_names())
            counts: dict[str, int] = {}
            if has_legacy_knowledge_vectors(existing):
                result = connection.execute(
                    text("DELETE FROM semantic_vectors WHERE namespace = :namespace"),
                    {"namespace": LEGACY_VECTOR_NAMESPACE},
                )
                counts["semantic_vectors:knowledge-chunk"] = max(0, int(result.rowcount or 0))
            retired = retired_knowledge_tables(existing)
            for table_name in retired:
                connection.exec_driver_sql(f'DROP TABLE "{table_name}"')
            return counts, retired

    def _complete_run(self, counts: dict[str, int], retired_tables: tuple[str, ...]) -> None:
        now = datetime.now(UTC)
        with self.database.session() as session:
            record = session.get(
                KnowledgeFabricHardCutoverMigrationRecord,
                KNOWLEDGE_FABRIC_HARD_CUTOVER_ID,
            )
            if record is None:
                raise RuntimeError("Knowledge Fabric cutover ledger claim is missing")
            record.status = "completed"
            record.retired_tables_json = json.dumps(retired_tables)
            record.retired_row_counts_json = json.dumps(counts, sort_keys=True)
            record.last_error = ""
            record.updated_at = now
            record.completed_at = now
            session.commit()

    def _fail_run(self, error: Exception) -> None:
        with self.database.session() as session:
            record = session.get(
                KnowledgeFabricHardCutoverMigrationRecord,
                KNOWLEDGE_FABRIC_HARD_CUTOVER_ID,
            )
            if record is None:
                raise RuntimeError("Knowledge Fabric cutover ledger claim is missing") from error
            record.status = "failed"
            record.last_error = type(error).__name__[:120]
            record.updated_at = datetime.now(UTC)
            session.commit()


__all__ = [
    "KNOWLEDGE_FABRIC_HARD_CUTOVER_ID",
    "LEGACY_KNOWLEDGE_TABLES_TO_DROP",
    "KnowledgeFabricHardCutoverMigration",
]
