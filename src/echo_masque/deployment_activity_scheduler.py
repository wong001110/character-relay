"""Independent background scheduler for complete Deployment Discovery Activity."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from echo_masque.deployment_activity import DeploymentBrowsingActivityService
from echo_masque.discovery_runtime import (
    build_discovery_share_delivery,
    upgrade_discovery_activity_service,
)
from echo_masque.discovery_share import DiscoveryShareDeliveryService

logger = logging.getLogger(__name__)


class DeploymentActivityScheduler:
    """Poll Discovery activity and its durable share outbox as one bounded module."""

    def __init__(
        self,
        service: DeploymentBrowsingActivityService,
        *,
        poll_seconds: int = 60,
    ) -> None:
        self.service = upgrade_discovery_activity_service(service)
        self.share_delivery: DiscoveryShareDeliveryService | None = (
            build_discovery_share_delivery(self.service)
        )
        self.poll_seconds = max(10, poll_seconds)
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        if self.share_delivery is not None:
            self.share_delivery.recover_interrupted()
        await self._run_once_safely(initial=True)
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

    async def _run_once_safely(self, *, initial: bool = False) -> None:
        try:
            await self.service.run_once()
        except Exception:
            logger.exception(
                "%s Deployment Discovery reconciliation failed.",
                "Initial" if initial else "Scheduled",
            )
        if self.share_delivery is not None:
            try:
                await self.share_delivery.deliver_due_once()
            except Exception:
                logger.exception("Deployment Discovery share delivery iteration failed.")

    async def _run(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.poll_seconds)
                await self._run_once_safely()
        except asyncio.CancelledError:
            raise


__all__ = ["DeploymentActivityScheduler"]
