"""Lifespan-supervised maintenance for transient Conversation Runtime state."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import UTC, datetime

from echo_masque.conversation_runtime import ConversationRuntimeCoordinator
from echo_masque.persistence.conversation_runtime_repository import ConversationRuntimeRepository

logger = logging.getLogger(__name__)


class ConversationRuntimeMaintenanceService:
    """Checkpoint inactive Episodes and archive expired ThreadWorkingState records.

    Episode checkpoints remain owner-scoped even when this service runs across all owners.
    Repeated runs are safe: only active, old Episodes transition to ``closed`` and only active,
    expired scratch state transitions to ``archived``.
    """

    def __init__(
        self,
        coordinator: ConversationRuntimeCoordinator,
        runtime: ConversationRuntimeRepository,
        *,
        interval_seconds: int = 60,
    ) -> None:
        self.coordinator = coordinator
        self.runtime = runtime
        self.interval_seconds = max(30, min(interval_seconds, 3600))
        self._task: asyncio.Task[None] | None = None
        self._maintenance_task: asyncio.Task[dict[str, int]] | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        await self._run_once()
        self._task = asyncio.create_task(
            self._run(), name="conversation-runtime-maintenance"
        )

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    def maintain_once(self, *, now: datetime | None = None) -> dict[str, int]:
        """Apply one idempotent maintenance pass and return transition counts."""

        current = (now or datetime.now(UTC)).astimezone(UTC)
        checkpointed = 0
        archived = 0
        try:
            owner_ids = set(self.runtime.owners_with_active_episodes())
            owner_ids.update(self.runtime.owners_with_expired_working_states(now=current))
            for owner_id in owner_ids:
                archived += self.runtime.expired_working_state_count(
                    owner_id=owner_id, now=current
                )
                checkpointed += len(
                    self.coordinator.checkpoint_inactive(owner_id=owner_id, now=current)
                )
        except Exception as exc:
            logger.warning("Conversation Runtime maintenance failed: %s", exc)
            return {"episodes_checkpointed": checkpointed, "working_states_archived": 0}
        if checkpointed or archived:
            logger.info(
                "Conversation Runtime maintenance checkpointed=%s archived_working_states=%s",
                checkpointed,
                archived,
            )
        return {"episodes_checkpointed": checkpointed, "working_states_archived": archived}

    async def _run(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.interval_seconds)
                await self._run_once()
        except asyncio.CancelledError:
            raise

    async def _run_once(self) -> dict[str, int]:
        """Run synchronous DB work without abandoning it during lifespan cancellation.

        Cancelling ``asyncio.to_thread`` only cancels its awaiter; the database thread can still
        be mutating state.  The service therefore shields and joins the tracked task before
        reporting shutdown complete, preserving a quiescent lifecycle boundary.
        """

        task = asyncio.create_task(asyncio.to_thread(self.maintain_once))
        self._maintenance_task = task
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            await asyncio.shield(task)
            raise
        finally:
            if self._maintenance_task is task:
                self._maintenance_task = None


__all__ = ["ConversationRuntimeMaintenanceService"]
