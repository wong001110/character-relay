"""Periodic bounded cleanup for TTL-backed media persistence."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass
from typing import Protocol

from echo_masque.persistence import (
    ConversationMediaReferenceRepository,
    Database,
    GeneratedMediaArtifactRepository,
    MediaAnalysisRepository,
)

logger = logging.getLogger(__name__)


class ExpiringMediaRepository(Protocol):
    def purge_expired(self, *, limit: int = ...) -> int: ...


@dataclass(frozen=True, slots=True)
class MediaRetentionResult:
    media_analysis: int = 0
    conversation_media: int = 0
    generated_media: int = 0

    @property
    def total(self) -> int:
        return self.media_analysis + self.conversation_media + self.generated_media


class MediaRetentionService:
    """Keep TTL-backed media tables bounded without adding cleanup work to request paths."""

    def __init__(
        self,
        media_analysis_repository: MediaAnalysisRepository,
        conversation_media_repository: ConversationMediaReferenceRepository,
        generated_media_repository: GeneratedMediaArtifactRepository,
        *,
        interval_seconds: int = 3600,
        max_batches_per_table: int = 5,
    ) -> None:
        self.media_analysis_repository = media_analysis_repository
        self.conversation_media_repository = conversation_media_repository
        self.generated_media_repository = generated_media_repository
        self.interval_seconds = max(60, interval_seconds)
        self.max_batches_per_table = max(1, min(max_batches_per_table, 20))
        self._task: asyncio.Task[None] | None = None

    @classmethod
    def for_database(
        cls,
        database: Database,
        *,
        interval_seconds: int = 3600,
    ) -> MediaRetentionService:
        return cls(
            MediaAnalysisRepository(database),
            ConversationMediaReferenceRepository(database),
            GeneratedMediaArtifactRepository(database),
            interval_seconds=interval_seconds,
        )

    async def start(self) -> None:
        if self._task is not None:
            return
        self.purge_once()
        self._task = asyncio.create_task(
            self._run(),
            name="character-relay-media-retention",
        )

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    def purge_once(self) -> MediaRetentionResult:
        result = MediaRetentionResult(
            media_analysis=self._purge_bounded(
                "media_analysis",
                self.media_analysis_repository,
                batch_size=500,
            ),
            conversation_media=self._purge_bounded(
                "conversation_media",
                self.conversation_media_repository,
                batch_size=500,
            ),
            generated_media=self._purge_bounded(
                "generated_media",
                self.generated_media_repository,
                batch_size=200,
            ),
        )
        if result.total:
            logger.info(
                "Purged expired media persistence: analysis=%s conversation=%s generated=%s",
                result.media_analysis,
                result.conversation_media,
                result.generated_media,
            )
        return result

    def _purge_bounded(
        self,
        label: str,
        repository: ExpiringMediaRepository,
        *,
        batch_size: int,
    ) -> int:
        deleted = 0
        try:
            for _ in range(self.max_batches_per_table):
                count = repository.purge_expired(limit=batch_size)
                deleted += count
                if count < batch_size:
                    break
        except Exception as exc:
            logger.warning("Media retention cleanup failed for %s: %s", label, exc)
        return deleted

    async def _run(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.interval_seconds)
                self.purge_once()
        except asyncio.CancelledError:
            raise


__all__ = ["MediaRetentionResult", "MediaRetentionService"]
