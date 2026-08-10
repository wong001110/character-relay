"""Provider-neutral Media Understanding runtime with shared cache reuse."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from functools import partial
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from echo_masque.media_singleflight import MediaAnalysisSingleFlight
from echo_masque.persistence.media_models import MediaAnalysisRecord
from echo_masque.persistence.media_repository import MediaAnalysisRepository

MediaType = Literal["image", "video", "audio"]


class MediaAsset(BaseModel):
    """Resolved media reference. Raw media retention is intentionally not required."""

    model_config = ConfigDict(frozen=True)

    media_key: str = Field(min_length=1, max_length=300)
    media_type: MediaType
    mime_type: str = Field(default="", max_length=120)
    filename: str = Field(default="", max_length=255)
    source_uri: str = Field(default="", max_length=4096)
    size_bytes: int | None = Field(default=None, ge=0)


class MediaAnalysis(BaseModel):
    """Objective media-derived context shared by every Character that inspects the content."""

    model_config = ConfigDict(frozen=True)

    summary: str = Field(min_length=1, max_length=12000)
    visible_text: str = Field(default="", max_length=16000)
    people: tuple[str, ...] = ()
    objects: tuple[str, ...] = ()
    notable_details: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()
    tone: str = Field(default="", max_length=160)


class MediaUnderstandingProvider(Protocol):
    @property
    def provider_id(self) -> str: ...

    @property
    def model(self) -> str: ...

    async def analyze(self, asset: MediaAsset) -> MediaAnalysis: ...


class MediaUnderstandingUnavailable(RuntimeError):
    """Raised when an in-flight shared analysis failed or could not finish safely."""


class MediaUnderstandingService:
    """Run Level-1 understanding once and share both in-flight and persisted results."""

    def __init__(
        self,
        repository: MediaAnalysisRepository,
        provider: MediaUnderstandingProvider,
        *,
        analysis_version: str = "general-v1",
        poll_interval_seconds: float = 0.75,
        wait_timeout_seconds: float = 300.0,
    ) -> None:
        self.repository = repository
        self.provider = provider
        self.analysis_version = analysis_version
        self.poll_interval_seconds = max(0.1, poll_interval_seconds)
        self.wait_timeout_seconds = max(1.0, wait_timeout_seconds)
        self.singleflight = MediaAnalysisSingleFlight(repository)
        self._inflight: dict[str, asyncio.Task[tuple[MediaAnalysis, bool]]] = {}
        self._inflight_lock = asyncio.Lock()

    def _identity(self, asset: MediaAsset) -> str:
        return "|".join(
            (
                asset.media_key,
                self.analysis_version,
                self.provider.provider_id,
                self.provider.model,
            )
        )

    async def analyze(self, asset: MediaAsset) -> tuple[MediaAnalysis, bool]:
        """Return objective analysis and whether existing/in-flight work was reused."""

        identity = self._identity(asset)
        joined_existing = False
        async with self._inflight_lock:
            task = self._inflight.get(identity)
            if task is None:
                task = asyncio.create_task(self._analyze_singleflight(asset))
                self._inflight[identity] = task
                task.add_done_callback(partial(self._schedule_clear, identity))
            else:
                joined_existing = True
        analysis, reused = await asyncio.shield(task)
        return analysis, reused or joined_existing

    def _schedule_clear(
        self,
        identity: str,
        completed: asyncio.Future[tuple[MediaAnalysis, bool]],
    ) -> None:
        asyncio.create_task(self._clear_inflight(identity, completed))

    async def _clear_inflight(
        self,
        identity: str,
        completed: asyncio.Future[tuple[MediaAnalysis, bool]],
    ) -> None:
        async with self._inflight_lock:
            if self._inflight.get(identity) is completed:
                self._inflight.pop(identity, None)

    @staticmethod
    def _parse_ready(record: MediaAnalysisRecord) -> MediaAnalysis | None:
        try:
            return MediaAnalysis.model_validate_json(record.result_json)
        except ValidationError:
            return None

    async def _analyze_singleflight(self, asset: MediaAsset) -> tuple[MediaAnalysis, bool]:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.wait_timeout_seconds
        while loop.time() < deadline:
            claim = self.singleflight.claim(
                media_key=asset.media_key,
                media_type=asset.media_type,
                analysis_version=self.analysis_version,
                provider=self.provider.provider_id,
                model=self.provider.model,
            )

            if claim.status == "ready":
                cached = self._parse_ready(claim.record)
                if cached is not None:
                    return cached, True
                self.singleflight.invalidate(claim.record.id)
                continue

            if claim.status == "failed":
                raise MediaUnderstandingUnavailable(
                    claim.record.error or "Shared Media Understanding failed recently."
                )

            if claim.status == "claimed":
                try:
                    analysis = await self.provider.analyze(asset)
                except Exception as exc:
                    self.singleflight.fail(
                        record_id=claim.record.id,
                        lease_token=claim.lease_token,
                        error=str(exc),
                    )
                    raise
                if not self.singleflight.complete(
                    record_id=claim.record.id,
                    lease_token=claim.lease_token,
                    result_json=analysis.model_dump_json(),
                ):
                    raise MediaUnderstandingUnavailable(
                        "Media Analysis lease expired before the provider result could be committed."
                    )
                self.repository.purge_expired(limit=100)
                return analysis, False

            # Another process owns the lease. This process waits without starting another
            # provider call; a stale lease can be reclaimed on the next loop iteration.
            await asyncio.sleep(self.poll_interval_seconds)
            state = self.singleflight.state(
                media_key=asset.media_key,
                analysis_version=self.analysis_version,
                provider=self.provider.provider_id,
                model=self.provider.model,
            )
            if state is None:
                continue
            if state.status == "ready":
                cached = self._parse_ready(state)
                if cached is not None and _not_expired(state):
                    return cached, True
                self.singleflight.invalidate(state.id)
            elif state.status == "failed" and _lease_is_future(state):
                raise MediaUnderstandingUnavailable(
                    state.error or "Shared Media Understanding failed recently."
                )

        raise MediaUnderstandingUnavailable("Timed out waiting for shared Media Understanding.")


def _not_expired(record: MediaAnalysisRecord) -> bool:
    value = record.expires_at
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC) > datetime.now(UTC)


def _lease_is_future(record: MediaAnalysisRecord) -> bool:
    value = record.lease_expires_at
    if value is None:
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC) > datetime.now(UTC)
