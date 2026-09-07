"""Bounded diagnostic batching; never used for delivery/side-effect authority."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import replace
from datetime import datetime
from threading import Lock

from echo_masque.persistence.runtime_durability_repository import DurableRuntimeRepository
from echo_masque.runtime_trace import RuntimeTraceEvent

logger = logging.getLogger(__name__)


class BufferedRuntimeTraceSink:
    def __init__(self, repository: DurableRuntimeRepository, *, capacity: int = 2048) -> None:
        self.repository = repository
        self.capacity = max(64, capacity)
        self._pending: deque[RuntimeTraceEvent] = deque()
        self._lock = Lock()
        self._task: asyncio.Task[None] | None = None
        self.dropped_events = 0
        self._starts: dict[tuple[str, str], datetime] = {}

    def emit(self, event: RuntimeTraceEvent) -> None:
        if self._task is None:
            self.repository.emit(event)
            return
        with self._lock:
            if len(self._pending) >= self.capacity:
                self.dropped_events += 1
                return
            key = (event.graph_run_id, event.node_name)
            if event.status == "started":
                if len(self._starts) >= self.capacity:
                    self._starts.pop(next(iter(self._starts)))
                self._starts[key] = event.occurred_at
            else:
                started = self._starts.pop(key, None)
                if started is not None:
                    milliseconds = max(0, int((event.occurred_at - started).total_seconds() * 1000))
                    event = replace(
                        event, metadata=(*event.metadata, ("duration_ms", str(milliseconds)))
                    )
            self._pending.append(event)

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="runtime-trace-buffer")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        await self.flush()

    async def flush(self) -> None:
        while True:
            with self._lock:
                batch = [self._pending.popleft() for _ in range(min(128, len(self._pending)))]
            if not batch:
                return
            try:
                # Shield a started transaction from cancellation so stop cannot start a
                # second transaction against the same batch before it has finished.
                write = asyncio.create_task(asyncio.to_thread(self.repository.emit_batch, batch))
                try:
                    await asyncio.shield(write)
                except asyncio.CancelledError:
                    await write
                    raise
            except asyncio.CancelledError:
                raise
            except Exception:
                self.dropped_events += len(batch)
                logger.exception("Diagnostic trace batch could not be persisted")

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(0.25)
            await self.flush()


__all__ = ["BufferedRuntimeTraceSink"]
