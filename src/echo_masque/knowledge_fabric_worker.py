"""Dedicated process entry point for Knowledge Fabric maintenance."""

from __future__ import annotations

import asyncio
import signal
from collections.abc import Awaitable, Callable
from contextlib import suppress

from echo_masque.api import create_app
from echo_masque.config import Settings, get_settings
from echo_masque.knowledge_fabric_background_runtime import KnowledgeFabricBackgroundRuntime


def _background_runtime(app: object) -> KnowledgeFabricBackgroundRuntime:
    """Compose only durable Fabric loops from an already initialized application."""

    state = app.state  # type: ignore[attr-defined]
    return KnowledgeFabricBackgroundRuntime(
        start_report_retention=state.knowledge_fabric_external_sync_report_retention.start,
        stop_report_retention=state.knowledge_fabric_external_sync_report_retention.stop,
        start_external_sync=state.knowledge_fabric_external_sync_scheduler.start,
        stop_external_sync=state.knowledge_fabric_external_sync_scheduler.stop,
        start_derived_work=state.knowledge_fabric_invalidation_worker.start,
        stop_derived_work=state.knowledge_fabric_invalidation_worker.stop,
    )


async def serve(
    settings: Settings | None = None,
    *,
    wait_for_shutdown: Callable[[], Awaitable[None]] | None = None,
) -> None:
    """Run Fabric maintenance until SIGTERM/SIGINT or an injected test shutdown."""

    app = create_app(settings or get_settings())
    runtime = _background_runtime(app)
    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()

    if wait_for_shutdown is None:
        for signum in (signal.SIGINT, signal.SIGTERM):
            with suppress(NotImplementedError):  # pragma: no cover - Windows lacks asyncio signals.
                loop.add_signal_handler(signum, shutdown.set)

        async def wait_for_signal() -> None:
            await shutdown.wait()

        wait_for_shutdown = wait_for_signal

    await app.state.browser_runtime.start()
    try:
        await runtime.start()
        await wait_for_shutdown()
    finally:
        await runtime.stop()
        await app.state.browser_runtime.stop()


def main() -> None:
    asyncio.run(serve())


if __name__ == "__main__":
    main()
