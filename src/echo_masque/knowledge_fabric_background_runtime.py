"""Lifecycle boundary for durable Knowledge Fabric maintenance work."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

type LifecycleOperation = Callable[[], Awaitable[None]]
type FailureWaiter = Callable[[], Awaitable[None]]


class KnowledgeFabricBackgroundRuntime:
    """Start and stop Fabric maintenance as one independently deployable unit.

    Acquisition, report retention, and derived index/projection rebuilding share a durable
    database lease protocol, but they must not share the HTTP API process by default.
    """

    def __init__(
        self,
        *,
        start_report_retention: LifecycleOperation,
        stop_report_retention: LifecycleOperation,
        start_external_sync: LifecycleOperation,
        stop_external_sync: LifecycleOperation,
        start_derived_work: LifecycleOperation,
        stop_derived_work: LifecycleOperation,
        failure_waiters: tuple[FailureWaiter, ...] = (),
    ) -> None:
        self._operations = (
            (start_report_retention, stop_report_retention),
            (start_external_sync, stop_external_sync),
            (start_derived_work, stop_derived_work),
        )
        self._failure_waiters = failure_waiters
        self._started: list[LifecycleOperation] = []

    async def start(self) -> None:
        """Start all maintenance loops, rolling back a partial startup on failure."""

        if self._started:
            return
        try:
            for start, stop in self._operations:
                await start()
                self._started.append(stop)
        except BaseException:
            await self.stop()
            raise

    async def stop(self) -> None:
        """Stop only loops that successfully started, in reverse dependency order."""

        while self._started:
            stop = self._started.pop()
            await stop()

    async def wait_for_failure(self) -> None:
        """Raise when a supervised worker loop exhausts its bounded retry budget."""

        if not self._failure_waiters:
            await asyncio.Future[None]()
        tasks: list[asyncio.Future[None]] = [
            asyncio.ensure_future(waiter()) for waiter in self._failure_waiters
        ]
        try:
            done, _pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                await task
            raise RuntimeError("Knowledge Fabric worker supervisor stopped unexpectedly.")
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


__all__ = ["KnowledgeFabricBackgroundRuntime"]
