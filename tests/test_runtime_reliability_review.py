from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from echo_masque.api import create_app
from echo_masque.config import Settings
from echo_masque.knowledge_fabric_external_sync_scheduler import (
    KnowledgeFabricExternalSyncScheduler,
)
from echo_masque.knowledge_fabric_invalidation_worker import KnowledgeFabricInvalidationWorker
from echo_masque.knowledge_fabric_worker import compose_worker_runtime
from echo_masque.knowledge_object_storage import object_storage_from_settings
from echo_masque.persistence import Database, DurableRuntimeRepository, UnsafeProductionStorageError
from echo_masque.persistence.knowledge_fabric_content_repository import (
    KnowledgeFabricContentRepository,
)
from echo_masque.persistence.knowledge_fabric_repository import KnowledgeFabricRepository
from echo_masque.persistence.models import ExperimentMatrixRecord
from echo_masque.runtime_recovery import recover_after_all_workers_stopped


def _settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        credential_encryption_keys=Fernet.generate_key().decode("ascii"),
    )


def test_api_construction_preserves_active_runtime_matrix_and_ingestion_work(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path / "shared.db")
    database = Database(settings.database_url)
    database.initialize()
    runtime = DurableRuntimeRepository(database)
    operation = runtime.claim_social_operation(
        operation_id="operation-1",
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="",
        source_message_id="message-1",
        initial_deployment_ids=["deployment-1"],
        available_deployment_ids=["deployment-1"],
        continuation_budget=0,
        max_depth=0,
    )
    _, step = runtime.prepare_social_step(
        operation_id=operation.operation_id,
        step_index=0,
        deployment_id="deployment-1",
        request_hash="request-1",
    )
    storage = object_storage_from_settings(settings)
    fabric = KnowledgeFabricRepository(database, object_storage=storage)
    corpus = fabric.create_system_global_corpus(
        name="Global", description="", default_authority_profile="standard", status="active"
    )
    source = fabric.create_source(
        corpus_id=corpus.id,
        source_type="manual_text",
        locator="https://docs.example.test/source",
        access_profile_json="{}",
        parser_profile_json="{}",
        sync_policy_json="{}",
        freshness_policy_json="{}",
        authority_profile="standard",
    )
    content = KnowledgeFabricContentRepository(
        database,
        object_storage=storage,
    )
    job = content.get_or_create_ingestion_job(
        source_id=source.id, job_type="source_snapshot", idempotency_key="delivery-1"
    )
    content.claim_ingestion_job(job.id)
    with database.session() as session:
        session.add(
            ExperimentMatrixRecord(
                id="matrix-1",
                owner_id="owner-1",
                name="active matrix",
                status="running",
                definition_json="{}",
            )
        )
        session.commit()

    create_app(settings)

    assert runtime.get_operation(operation.operation_id).status == "active"  # type: ignore[union-attr]
    with database.session() as session:
        assert session.get(type(step), step.step_id).status == "generating"  # type: ignore[union-attr]
        assert session.get(type(job), job.id).status == "running"  # type: ignore[union-attr]
        assert session.get(ExperimentMatrixRecord, "matrix-1").status == "running"  # type: ignore[union-attr]


def test_health_rejects_a_current_database_failure_without_provider_calls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = create_app(_settings(tmp_path / "unavailable.db"))

    def unavailable() -> object:
        raise OperationalError("SELECT 1", {}, ConnectionError("database host unavailable"))

    monkeypatch.setattr(app.state.database.engine, "connect", unavailable)

    response = TestClient(app).get("/health")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database readiness check failed."}


def test_worker_rejects_production_sqlite_before_creating_database_side_effects(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "production-worker.db"
    settings = Settings(
        environment="production",
        database_url=f"sqlite:///{database_path}",
        legacy_local_user_enabled=False,
        credential_encryption_keys=Fernet.generate_key().decode("ascii"),
    )

    with pytest.raises(UnsafeProductionStorageError, match="requires PostgreSQL \\+ pgvector"):
        compose_worker_runtime(settings)
    with pytest.raises(UnsafeProductionStorageError, match="requires PostgreSQL \\+ pgvector"):
        recover_after_all_workers_stopped(settings)

    assert not database_path.exists()


class _FailingScheduleRepository:
    def recover_expired(self) -> int:
        return 0


class _FailingInvalidations:
    def recover_expired(self) -> int:
        return 0


def test_background_loops_exhaust_a_bounded_retry_budget_then_are_restartable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import echo_masque.knowledge_fabric_external_sync_scheduler as scheduler_module
    import echo_masque.knowledge_fabric_invalidation_worker as invalidation_module

    monkeypatch.setattr(scheduler_module, "_MAX_RETRY_SECONDS", 0)
    monkeypatch.setattr(invalidation_module, "_MAX_RETRY_SECONDS", 0)

    class FailingScheduler(KnowledgeFabricExternalSyncScheduler):
        async def run_once(self) -> int:
            raise OSError("database temporarily unavailable")

    class FailingInvalidationWorker(KnowledgeFabricInvalidationWorker):
        async def run_once(self) -> int:
            raise OSError("database temporarily unavailable")

    scheduler = FailingScheduler(
        schedule_repository=_FailingScheduleRepository(),  # type: ignore[arg-type]
        sync_by_source_type={},
    )
    invalidations = FailingInvalidationWorker(
        invalidations=_FailingInvalidations(),  # type: ignore[arg-type]
        indexes=object(),  # type: ignore[arg-type]
        projections=object(),  # type: ignore[arg-type]
    )

    async def scenario() -> None:
        await scheduler.start()
        await invalidations.start()
        with pytest.raises(OSError, match="database temporarily unavailable"):
            await scheduler.wait_for_failure()
        with pytest.raises(OSError, match="database temporarily unavailable"):
            await invalidations.wait_for_failure()

        # A controlled caller can start a new loop after a supervisor has observed a failure.
        await scheduler.start()
        await invalidations.start()
        await scheduler.stop()
        await invalidations.stop()

    asyncio.run(scenario())
