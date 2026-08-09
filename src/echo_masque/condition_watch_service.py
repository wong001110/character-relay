"""Bounded event loop for Tool Calling V2 condition watches."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from echo_masque.persistence.condition_watch_models import ConditionWatchRecord
from echo_masque.persistence.condition_watch_repository import ConditionWatchRepository


@dataclass(frozen=True)
class ConditionWatchEvaluation:
    """Result of one bounded condition evaluation attempt."""

    triggered: bool
    summary: str = ""


ConditionEvaluator = Callable[[ConditionWatchRecord], Awaitable[ConditionWatchEvaluation]]
ConditionNotifier = Callable[[ConditionWatchRecord, ConditionWatchEvaluation], Awaitable[None]]
ConditionProcessor = Callable[[ConditionWatchRecord], Awaitable[None]]


class ConditionWatchService:
    """Poll persisted watches and transition them through a bounded lifecycle.

    The service remains the scheduling clock and `claim_due()` owner. A Phase 2 orchestration
    processor may take over one already-claimed attempt, while the legacy evaluator/notifier
    path remains available for parity testing and rollback.
    """

    def __init__(
        self,
        repository: ConditionWatchRepository,
        *,
        evaluator: ConditionEvaluator,
        notifier: ConditionNotifier,
        processor: ConditionProcessor | None = None,
        poll_seconds: int = 60,
        batch_size: int = 20,
    ) -> None:
        self.repository = repository
        self.evaluator = evaluator
        self.notifier = notifier
        self.processor = processor
        self.poll_seconds = max(60, poll_seconds)
        self.batch_size = min(max(batch_size, 1), 50)
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self.repository.purge_orphans()
        self._stop.clear()
        self._task = asyncio.create_task(
            self._run_loop(),
            name="character-relay-condition-watch",
        )

    async def stop(self) -> None:
        self._stop.set()
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def run_once(self) -> int:
        records = self.repository.claim_due(limit=self.batch_size)
        for record in records:
            await self._process(record)
        return len(records)

    async def _process(self, record: ConditionWatchRecord) -> None:
        try:
            if self.processor is not None:
                await self.processor(record)
                return
            evaluation = await self.evaluator(record)
            if not evaluation.triggered:
                self.repository.mark_not_met(record.id)
                return
            await self.notifier(record, evaluation)
            self.repository.mark_triggered(record.id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # The graph processor persists expected evaluation/notifier failures itself.
            # This remains a final safety net for orchestration/runtime failures.
            self.repository.mark_failure(record.id, str(exc))

    async def _run_loop(self) -> None:
        while not self._stop.is_set():
            await self.run_once()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.poll_seconds)
            except TimeoutError:
                continue


__all__ = [
    "ConditionEvaluator",
    "ConditionNotifier",
    "ConditionProcessor",
    "ConditionWatchEvaluation",
    "ConditionWatchService",
]
