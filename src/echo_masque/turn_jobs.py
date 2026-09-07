"""Lifespan-supervised executor for already-accepted Discord turn jobs."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from echo_masque.persistence.turn_job_repository import TurnJobRepository
from echo_masque.turn_progress import bind_turn_progress

TurnRunner = Callable[[str, str], Awaitable[str]]


class TurnJobManager:
    def __init__(
        self,
        repository: TurnJobRepository,
        runner: TurnRunner,
        *,
        max_queue: int = 20,
        max_concurrency: int = 2,
        deadline_seconds: int = 300,
    ) -> None:
        self.repository = repository
        self.runner = runner
        self.max_queue = max(1, min(max_queue, 200))
        self.max_concurrency = max(1, min(max_concurrency, 16))
        self.deadline_seconds = max(30, min(deadline_seconds, 900))
        self._queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=self.max_queue)
        self._workers: list[asyncio.Task[None]] = []
        self._maintenance_task: asyncio.Task[None] | None = None
        self._owned_job_ids: set[str] = set()

    async def start(self) -> None:
        if self._workers:
            return
        self.repository.cleanup()
        self.repository.expire_deadlines()
        self._maintenance_task = asyncio.create_task(self._maintain(), name="turn-job-maintenance")
        self._workers = [
            asyncio.create_task(self._worker(), name=f"turn-job-{index}")
            for index in range(self.max_concurrency)
        ]

    async def stop(self) -> None:
        workers, self._workers = self._workers, []
        if self._maintenance_task is not None:
            self._maintenance_task.cancel()
            await asyncio.gather(self._maintenance_task, return_exceptions=True)
            self._maintenance_task = None
        for worker in workers:
            worker.cancel()
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)
        self.repository.stop_jobs(self._owned_job_ids)
        self._owned_job_ids.clear()

    def submit(self, job_id: str) -> bool:
        if not self._workers or self._queue.full():
            return False
        self._owned_job_ids.add(job_id)
        self._queue.put_nowait(job_id)
        return True

    def can_accept(self) -> bool:
        return bool(self._workers) and not self._queue.full()

    async def _worker(self) -> None:
        while True:
            job_id = await self._queue.get()
            try:
                if job_id is None:
                    return
                active_job_id: str = job_id
                job = self.repository.mark_running(active_job_id)
                if job is None or job.status != "running":
                    continue

                async def progress(text: str, *, target_id: str = active_job_id) -> bool:
                    return self.repository.publish_progress(target_id, text)

                try:
                    with bind_turn_progress(progress):
                        deadline = job.deadline_at
                        now = datetime.now(UTC)
                        if deadline.tzinfo is None:
                            now = now.replace(tzinfo=None)
                        result = await asyncio.wait_for(
                            self.runner(job.kind, job.request_json),
                            timeout=max(0.01, (deadline - now).total_seconds()),
                        )
                except TimeoutError:
                    self.repository.fail(job_id, status="timed_out", error_code="deadline_exceeded")
                except asyncio.CancelledError:
                    self.repository.fail(job_id, status="stopped", error_code="service_stopped")
                    raise
                except Exception as exc:
                    self.repository.fail(job_id, status="failed", error_code=type(exc).__name__)
                else:
                    field = "reply" if job.kind == "message" else "social_step"
                    self.repository.complete(job_id, field=field, value=result)
            finally:
                if job_id is not None:
                    self._owned_job_ids.discard(job_id)
                self._queue.task_done()
                self.repository.cleanup()

    async def _maintain(self) -> None:
        while True:
            await asyncio.sleep(60)
            self.repository.expire_deadlines()
            self.repository.cleanup()


def encode_payload(value: object) -> str:
    """Serialize a validated Pydantic payload without recording arbitrary runtime state."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
