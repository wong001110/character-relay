"""Independent background scheduler for Deployment browsing Activity Sessions."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from echo_masque.deployment_activity import DeploymentBrowsingActivityService

logger = logging.getLogger(__name__)


class DeploymentActivityScheduler:
    """Poll the Activity Runtime without coupling source failures to Presence sleep scheduling."""

    def __init__(
        self,
        service: DeploymentBrowsingActivityService,
        *,
        poll_seconds: int = 60,
    ) -> None:
        self.service = service
        self.poll_seconds = max(10, poll_seconds)
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        try:
            await self.service.run_once()
        except Exception:
            logger.exception("Initial Deployment Activity reconciliation failed.")
        self._task = asyncio.create_task(
            self._run(),
            name="character-relay-deployment-activity",
        )

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _run(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.poll_seconds)
                try:
                    await self.service.run_once()
                except Exception:
                    # One upstream Discovery/source failure must not kill future scheduling.
                    logger.exception("Deployment Activity scheduler iteration failed.")
        except asyncio.CancelledError:
            raise


__all__ = ["DeploymentActivityScheduler"]
