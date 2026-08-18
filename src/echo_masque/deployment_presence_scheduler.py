"""Background event loop for Deployment Presence rhythm transitions."""

from __future__ import annotations

import asyncio
import contextlib

from echo_masque.deployment_presence_rhythm import DeploymentPresenceRhythmService


class DeploymentPresenceScheduler:
    """Poll persisted rhythm state; intentionally has no provider/model dependencies."""

    def __init__(
        self,
        rhythm: DeploymentPresenceRhythmService,
        *,
        poll_seconds: int = 30,
    ) -> None:
        self.rhythm = rhythm
        self.poll_seconds = max(5, poll_seconds)
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        # Reconcile immediately so a restart inside a sleep window restores Runtime authority
        # before waiting for the first normal poll interval.
        self.rhythm.run_once()
        self._task = asyncio.create_task(
            self._run(),
            name="character-relay-deployment-presence",
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
                self.rhythm.run_once()
        except asyncio.CancelledError:
            raise


__all__ = ["DeploymentPresenceScheduler"]
