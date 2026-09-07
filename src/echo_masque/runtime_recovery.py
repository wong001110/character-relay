"""Explicit, offline-only recovery for durable work interrupted after all workers stop."""

from __future__ import annotations

from echo_masque.config import Settings
from echo_masque.knowledge_object_storage import object_storage_from_settings
from echo_masque.persistence import (
    Database,
    DurableRuntimeRepository,
    MatrixRepository,
    inspect_storage,
)
from echo_masque.persistence.knowledge_fabric_content_repository import (
    KnowledgeFabricContentRepository,
)


def recover_after_all_workers_stopped(settings: Settings) -> dict[str, object]:
    """Recover interrupted records only during an operator-controlled offline window.

    This function deliberately has no startup caller.  The caller must first stop every API,
    connector, and Knowledge Fabric worker sharing this database; otherwise an active operation
    could be mistaken for an interrupted one.  Character delivery and side-effect claims are
    marked uncertain by the durable Runtime recovery and are never replayed automatically.
    """

    # The offline command has the same production database guard as every service entry point.
    inspect_storage(settings)
    database = Database(settings.database_url)
    database.initialize()
    runtime = DurableRuntimeRepository(database).recover_interrupted()
    matrices = MatrixRepository(database).recover_interrupted()
    content = KnowledgeFabricContentRepository(
        database,
        object_storage=object_storage_from_settings(settings),
    )
    ingestion_jobs = content.requeue_interrupted_ingestion_jobs()
    return {
        "runtime": runtime,
        "matrices_paused": matrices,
        "ingestion_jobs_requeued": ingestion_jobs,
    }


__all__ = ["recover_after_all_workers_stopped"]
