"""Supervised bounded maintenance for completed diagnostic Runtime records."""

from __future__ import annotations

import asyncio
import logging

from echo_masque.persistence.runtime_durability_repository import DurableRuntimeRepository

logger = logging.getLogger(__name__)


class RuntimeMaintenance:
    def __init__(self, repository: DurableRuntimeRepository) -> None:
        self.repository = repository
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="runtime-maintenance")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def _run(self) -> None:
        while True:
            try:
                work = asyncio.create_task(asyncio.to_thread(self.repository.prune))
                try:
                    await asyncio.shield(work)
                except asyncio.CancelledError:
                    await work
                    raise
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Runtime diagnostic maintenance failed; retrying next interval")
            await asyncio.sleep(60)
