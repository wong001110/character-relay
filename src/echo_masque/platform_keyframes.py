"""Bounded local keyframe sampling for public platform videos."""

from __future__ import annotations

import asyncio
import base64
import shutil
from dataclasses import dataclass
from time import monotonic

from pydantic import BaseModel, ConfigDict, Field

from echo_masque.platform_media import PlatformMediaResolution

_MAX_KEYFRAME_DATA_URI_CHARS = 1_500_000


class PlatformKeyframes(BaseModel):
    """Chronological JPEG samples extracted locally from one public platform video."""

    model_config = ConfigDict(frozen=True)

    source_key: str = Field(min_length=1, max_length=500)
    frame_data_uris: tuple[str, ...] = ()
    timestamps_seconds: tuple[float, ...] = ()


@dataclass(frozen=True)
class _KeyframeCacheEntry:
    value: PlatformKeyframes
    expires_at: float


class PlatformKeyframeExtractor:
    """Use local ffmpeg to sample video frames without exposing CDN URLs to providers."""

    def __init__(
        self,
        *,
        ffmpeg_path: str | None = None,
        timeout_seconds: float = 20.0,
        max_frames: int = 5,
        max_frame_bytes: int = 1_000_000,
        cache_seconds: float = 60 * 60,
    ) -> None:
        self.ffmpeg_path = (
            ffmpeg_path if ffmpeg_path is not None else (shutil.which("ffmpeg") or "")
        )
        self.timeout_seconds = max(1.0, timeout_seconds)
        self.max_frames = min(max(max_frames, 1), 6)
        self.max_frame_bytes = min(max(max_frame_bytes, 64 * 1024), 2 * 1024 * 1024)
        self.cache_seconds = max(60.0, cache_seconds)
        self._cache: dict[str, _KeyframeCacheEntry] = {}
        self._tasks: dict[str, asyncio.Task[PlatformKeyframes | None]] = {}
        self._lock = asyncio.Lock()

    async def extract(self, resolution: PlatformMediaResolution) -> PlatformKeyframes | None:
        if not self.ffmpeg_path or not resolution.media_url:
            return None
        now = monotonic()
        cached = self._cache.get(resolution.source_key)
        if cached is not None and cached.expires_at > now:
            return cached.value

        async with self._lock:
            task = self._tasks.get(resolution.source_key)
            if task is None:
                task = asyncio.create_task(self._extract_uncached(resolution))
                self._tasks[resolution.source_key] = task
        try:
            value = await asyncio.shield(task)
            if value is not None and value.frame_data_uris:
                self._cache[resolution.source_key] = _KeyframeCacheEntry(
                    value=value,
                    expires_at=monotonic() + self.cache_seconds,
                )
            return value
        finally:
            if task.done():
                async with self._lock:
                    if self._tasks.get(resolution.source_key) is task:
                        self._tasks.pop(resolution.source_key, None)

    async def _extract_uncached(
        self,
        resolution: PlatformMediaResolution,
    ) -> PlatformKeyframes | None:
        timestamps = self._sample_timestamps(resolution.duration_seconds, self.max_frames)
        semaphore = asyncio.Semaphore(2)

        async def sample(timestamp: float) -> tuple[float, bytes | None]:
            async with semaphore:
                frame = await self._extract_frame(resolution, timestamp)
            return timestamp, frame

        sampled = await asyncio.gather(*(sample(value) for value in timestamps))
        frames: list[str] = []
        kept_timestamps: list[float] = []
        for timestamp, frame in sampled:
            if not frame or len(frame) > self.max_frame_bytes:
                continue
            encoded = base64.b64encode(frame).decode("ascii")
            data_uri = f"data:image/jpeg;base64,{encoded}"
            if len(data_uri) > _MAX_KEYFRAME_DATA_URI_CHARS:
                continue
            frames.append(data_uri)
            kept_timestamps.append(timestamp)

        if not frames:
            return None
        return PlatformKeyframes(
            source_key=resolution.source_key,
            frame_data_uris=tuple(frames),
            timestamps_seconds=tuple(kept_timestamps),
        )

    async def _extract_frame(
        self,
        resolution: PlatformMediaResolution,
        timestamp: float,
    ) -> bytes | None:
        if not self.ffmpeg_path:
            return None
        command = [
            self.ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-rw_timeout",
            "15000000",
        ]
        header_blob = self._ffmpeg_headers(resolution.media_headers)
        if header_blob:
            command.extend(("-headers", header_blob))
        command.extend(
            (
                "-ss",
                f"{timestamp:.3f}",
                "-i",
                resolution.media_url,
                "-frames:v",
                "1",
                "-an",
                "-vf",
                "scale=min(1024\\,iw):-2",
                "-q:v",
                "5",
                "-f",
                "image2pipe",
                "-vcodec",
                "mjpeg",
                "pipe:1",
            )
        )
        process: asyncio.subprocess.Process | None = None
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout_seconds,
            )
        except (OSError, TimeoutError):
            if process is not None:
                try:
                    process.kill()
                    await process.communicate()
                except OSError:
                    pass
            return None
        if process.returncode != 0 or not stdout:
            return None
        return stdout[: self.max_frame_bytes + 1]

    @staticmethod
    def _sample_timestamps(duration_seconds: int | None, maximum: int) -> tuple[float, ...]:
        if duration_seconds is None or duration_seconds <= 0:
            defaults = (0.0, 5.0, 15.0, 30.0, 60.0)
            return defaults[:maximum]
        if duration_seconds <= 3:
            return (0.0,)
        fractions = (0.10, 0.30, 0.50, 0.70, 0.90)[:maximum]
        upper = max(float(duration_seconds) - 0.25, 0.0)
        values: list[float] = []
        for fraction in fractions:
            value = round(min(float(duration_seconds) * fraction, upper), 3)
            if value not in values:
                values.append(value)
        return tuple(values) or (0.0,)

    @staticmethod
    def _ffmpeg_headers(headers: tuple[tuple[str, str], ...]) -> str:
        values: list[str] = []
        for name, value in headers:
            clean_name = name.replace("\r", "").replace("\n", "").strip()
            clean_value = value.replace("\r", "").replace("\n", "").strip()
            if clean_name and clean_value:
                values.append(f"{clean_name}: {clean_value}")
        return "\r\n".join(values) + ("\r\n" if values else "")


__all__ = ["PlatformKeyframeExtractor", "PlatformKeyframes"]
