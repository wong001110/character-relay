"""Background executor for regenerable Knowledge Fabric derived state."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from echo_masque.persistence.knowledge_fabric_index_repository import KnowledgeFabricIndexRepository
from echo_masque.persistence.knowledge_fabric_invalidation_repository import (
    KnowledgeDerivedWorkClaim,
    KnowledgeFabricInvalidationRepository,
)
from echo_masque.persistence.knowledge_fabric_projection_repository import (
    KnowledgeFabricProjectionRepository,
)

logger = logging.getLogger(__name__)
_MAX_CONSECUTIVE_LOOP_FAILURES = 3
_MAX_RETRY_SECONDS = 30.0


class KnowledgeFabricInvalidationWorker:
    """Consume only persisted derived-work invalidations; never acquire or publish Sources."""

    def __init__(
        self,
        *,
        invalidations: KnowledgeFabricInvalidationRepository,
        indexes: KnowledgeFabricIndexRepository,
        projections: KnowledgeFabricProjectionRepository,
        poll_seconds: float = 30,
        lease_seconds: int = 120,
    ) -> None:
        if poll_seconds <= 0:
            raise ValueError("Derived-work poll interval must be positive.")
        if lease_seconds < 30:
            raise ValueError("Derived-work lease duration must be at least 30 seconds.")
        self.invalidations = invalidations
        self.indexes = indexes
        self.projections = projections
        self.poll_seconds = poll_seconds
        self.lease_seconds = lease_seconds
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        if self._task is not None:
            with suppress(asyncio.CancelledError, Exception):
                self._task.result()
            self._task = None
        self._stopping.clear()
        # Only leases proven expired are released; an alive worker's claim remains untouched.
        await asyncio.to_thread(self.invalidations.recover_expired)
        self._task = asyncio.create_task(self._run(), name="knowledge-fabric-derived-work")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stopping.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Derived-work worker had already failed while stopping.")
        finally:
            self._task = None

    async def run_once(self) -> int:
        # Rebuilding an index or Projection can be materially slower than the work lease.  Claim
        # one item and run its synchronous repository work outside the API event loop.
        claims = await asyncio.to_thread(
            self.invalidations.claim_due,
            limit=1,
            lease_seconds=self.lease_seconds,
        )
        for claim in claims:
            renewal = asyncio.create_task(
                self._renew_claim_until_complete(claim),
                name=f"knowledge-fabric-derived-work-lease:{claim.invalidation_id}",
            )
            try:
                await asyncio.to_thread(self._run_claim, claim)
            finally:
                renewal.cancel()
                with suppress(asyncio.CancelledError):
                    await renewal
        return len(claims)

    async def _run(self) -> None:
        consecutive_failures = 0
        while not self._stopping.is_set():
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                consecutive_failures += 1
                logger.exception(
                    "Knowledge Fabric derived-work loop failed (%s/%s).",
                    consecutive_failures,
                    _MAX_CONSECUTIVE_LOOP_FAILURES,
                )
                if consecutive_failures >= _MAX_CONSECUTIVE_LOOP_FAILURES:
                    raise
                retry_seconds = min(2 ** (consecutive_failures - 1), _MAX_RETRY_SECONDS)
                with suppress(TimeoutError):
                    await asyncio.wait_for(self._stopping.wait(), timeout=retry_seconds)
                continue
            consecutive_failures = 0
            with suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=self.poll_seconds)

    async def wait_for_failure(self) -> None:
        """Wait for an exhausted retry budget so the process supervisor can restart us."""

        task = self._task
        if task is None:
            raise RuntimeError("Derived-work worker has not started.")
        await asyncio.shield(task)
        if not self._stopping.is_set():
            raise RuntimeError("Derived-work worker stopped unexpectedly.")

    def _run_claim(self, claim: KnowledgeDerivedWorkClaim) -> None:
        try:
            if claim.dependency_type == "indexes":
                self.indexes.rebuild_entries_for_source_version(claim.source_version_id)
            elif claim.dependency_type == "projections":
                self.projections.rebuild_existing_source_overview(
                    source_version_id=claim.source_version_id
                )
            else:
                self.invalidations.fail(claim=claim, error_code="unsupported_dependency")
                return
        except Exception:
            self.invalidations.fail(claim=claim, error_code="derived_work_failed")
            return
        self.invalidations.complete(claim=claim)

    async def _renew_claim_until_complete(self, claim: KnowledgeDerivedWorkClaim) -> None:
        """Renew a durable fence while synchronous rebuild work runs in a worker thread."""

        interval = min(30.0, self.lease_seconds / 2)
        while True:
            await asyncio.sleep(interval)
            current = await asyncio.to_thread(
                self.invalidations.renew_claim,
                claim=claim,
                lease_seconds=self.lease_seconds,
            )
            if not current:
                return


__all__ = ["KnowledgeFabricInvalidationWorker"]
