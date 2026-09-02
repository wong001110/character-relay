import asyncio
from pathlib import Path

from cryptography.fernet import Fernet

from echo_masque.config import Settings
from echo_masque.knowledge_fabric_background_runtime import KnowledgeFabricBackgroundRuntime
from echo_masque.knowledge_fabric_worker import serve


def test_background_runtime_starts_and_stops_in_dependency_order() -> None:
    events: list[str] = []

    async def operation(name: str) -> None:
        events.append(name)

    runtime = KnowledgeFabricBackgroundRuntime(
        start_report_retention=lambda: operation("start-retention"),
        stop_report_retention=lambda: operation("stop-retention"),
        start_external_sync=lambda: operation("start-sync"),
        stop_external_sync=lambda: operation("stop-sync"),
        start_derived_work=lambda: operation("start-derived"),
        stop_derived_work=lambda: operation("stop-derived"),
    )

    async def scenario() -> None:
        await runtime.start()
        await runtime.start()
        await runtime.stop()

    asyncio.run(scenario())

    assert events == [
        "start-retention",
        "start-sync",
        "start-derived",
        "stop-derived",
        "stop-sync",
        "stop-retention",
    ]


def test_background_runtime_rolls_back_partial_startup() -> None:
    events: list[str] = []

    async def start_retention() -> None:
        events.append("start-retention")

    async def stop_retention() -> None:
        events.append("stop-retention")

    async def fail_sync() -> None:
        events.append("start-sync")
        raise RuntimeError("database unavailable")

    async def unused() -> None:
        events.append("unused")

    runtime = KnowledgeFabricBackgroundRuntime(
        start_report_retention=start_retention,
        stop_report_retention=stop_retention,
        start_external_sync=fail_sync,
        stop_external_sync=unused,
        start_derived_work=unused,
        stop_derived_work=unused,
    )

    async def scenario() -> None:
        try:
            await runtime.start()
        except RuntimeError as exc:
            assert str(exc) == "database unavailable"
        else:  # pragma: no cover - documents the expected failed startup path.
            raise AssertionError("expected startup to fail")

    asyncio.run(scenario())

    assert events == ["start-retention", "start-sync", "stop-retention"]


def test_dedicated_worker_runs_without_starting_an_http_server(tmp_path: Path) -> None:
    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'fabric-worker.db'}",
        legacy_local_user_enabled=False,
        credential_encryption_keys=Fernet.generate_key().decode("ascii"),
    )

    async def shutdown_immediately() -> None:
        return None

    asyncio.run(serve(settings, wait_for_shutdown=shutdown_immediately))
