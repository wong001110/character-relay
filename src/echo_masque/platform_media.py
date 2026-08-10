"""yt-dlp-backed public platform resolver for reusable video metadata and transcripts."""

from __future__ import annotations

import asyncio
import html
import json
import re
from dataclasses import dataclass
from time import monotonic
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field

from echo_masque.network_safety import PublicUrlGuard, PublicUrlRejected

_MAX_SUBTITLE_BYTES = 2 * 1024 * 1024
_MAX_TRANSCRIPT_CHARS = 14_000
_MAX_DESCRIPTION_CHARS = 2500
_RESOLUTION_TTL_SECONDS = 60 * 60
_PLATFORM_HOST_SUFFIXES = (
    "youtube.com",
    "youtu.be",
    "bilibili.com",
    "b23.tv",
    "tiktok.com",
    "x.com",
    "twitter.com",
    "facebook.com",
    "fb.watch",
    "instagram.com",
    "vimeo.com",
    "twitch.tv",
    "dailymotion.com",
)
_LANGUAGE_PRIORITY = (
    "zh-Hans",
    "zh-CN",
    "zh-SG",
    "zh-Hant",
    "zh-TW",
    "zh-HK",
    "zh",
    "en-US",
    "en-GB",
    "en",
)


class PlatformMediaResolution(BaseModel):
    """Normalized result of one yt-dlp extraction pass."""

    model_config = ConfigDict(frozen=True)

    source_key: str = Field(min_length=1, max_length=500)
    canonical_url: str = Field(min_length=1, max_length=4096)
    platform: str = Field(default="", max_length=80)
    media_id: str = Field(default="", max_length=300)
    title: str = Field(default="", max_length=500)
    uploader: str = Field(default="", max_length=300)
    description: str = Field(default="", max_length=_MAX_DESCRIPTION_CHARS)
    duration_seconds: int | None = Field(default=None, ge=0)
    media_url: str = Field(default="", max_length=4096)
    media_ext: str = Field(default="", max_length=20)
    transcript: str = Field(default="", max_length=_MAX_TRANSCRIPT_CHARS)
    transcript_language: str = Field(default="", max_length=80)
    transcript_source: str = Field(default="", max_length=40)

    @property
    def has_context(self) -> bool:
        return bool(self.title or self.description or self.transcript)


@dataclass(frozen=True)
class _SubtitleCandidate:
    url: str
    ext: str
    language: str
    source: str


@dataclass(frozen=True)
class _ResolutionCacheEntry:
    value: PlatformMediaResolution
    expires_at: float


class YtDlpMediaResolver:
    """Extract public platform metadata without downloading the full video."""

    def __init__(
        self,
        *,
        url_guard: PublicUrlGuard | None = None,
        http_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.url_guard = url_guard or PublicUrlGuard()
        self.http_transport = http_transport
        self._cache: dict[str, _ResolutionCacheEntry] = {}
        self._tasks: dict[str, asyncio.Task[PlatformMediaResolution | None]] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def supports(url: str) -> bool:
        host = (urlparse(url).hostname or "").casefold().rstrip(".")
        return any(host == suffix or host.endswith(f".{suffix}") for suffix in _PLATFORM_HOST_SUFFIXES)

    async def resolve(
        self,
        url: str,
        *,
        source_key: str,
    ) -> PlatformMediaResolution | None:
        if not self.supports(url):
            return None
        try:
            validated = await self.url_guard.validate(url.strip())
        except PublicUrlRejected:
            return None

        now = monotonic()
        cached = self._cache.get(source_key)
        if cached is not None and cached.expires_at > now:
            return cached.value

        async with self._lock:
            task = self._tasks.get(source_key)
            if task is None:
                task = asyncio.create_task(
                    self._resolve_uncached(validated, source_key=source_key)
                )
                self._tasks[source_key] = task
        try:
            value = await asyncio.shield(task)
            if value is not None:
                self._cache[source_key] = _ResolutionCacheEntry(
                    value=value,
                    expires_at=monotonic() + _RESOLUTION_TTL_SECONDS,
                )
            return value
        finally:
            if task.done():
                async with self._lock:
                    if self._tasks.get(source_key) is task:
                        self._tasks.pop(source_key, None)

    async def _resolve_uncached(
        self,
        url: str,
        *,
        source_key: str,
    ) -> PlatformMediaResolution | None:
        try:
            info = await asyncio.to_thread(self._extract_info, url)
        except Exception:
            return None
        if not info:
            return None

        canonical_url = self._text(info.get("webpage_url"), 4096) or url
        platform = self._text(
            info.get("extractor_key") or info.get("extractor") or urlparse(url).hostname,
            80,
        ).casefold()
        title = self._text(info.get("title"), 500)
        uploader = self._text(
            info.get("uploader") or info.get("channel") or info.get("creator"),
            300,
        )
        description = self._text(info.get("description"), _MAX_DESCRIPTION_CHARS)
        media_id = self._text(info.get("id"), 300)
        duration = self._duration(info.get("duration"))
        media_url, media_ext = await self._select_media_url(info)
        subtitle = self._select_subtitle(info)
        transcript = ""
        transcript_language = ""
        transcript_source = ""
        if subtitle is not None:
            transcript = await self._fetch_transcript(subtitle)
            if transcript:
                transcript_language = subtitle.language
                transcript_source = subtitle.source

        return PlatformMediaResolution(
            source_key=source_key,
            canonical_url=canonical_url,
            platform=platform,
            media_id=media_id,
            title=title,
            uploader=uploader,
            description=description,
            duration_seconds=duration,
            media_url=media_url,
            media_ext=media_ext,
            transcript=transcript,
            transcript_language=transcript_language,
            transcript_source=transcript_source,
        )

    @staticmethod
    def _extract_info(url: str) -> dict[str, Any]:
        import yt_dlp

        options: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "socket_timeout": 15,
            "retries": 2,
            "extractor_retries": 2,
            "fragment_retries": 1,
            "ignore_no_formats_error": True,
            "js_runtimes": {"node": {}},
        }
        with yt_dlp.YoutubeDL(options) as ydl:
            raw = ydl.extract_info(url, download=False)
            sanitized = ydl.sanitize_info(raw)
        if not isinstance(sanitized, dict):
            return {}
        entries = sanitized.get("entries")
        if isinstance(entries, list):
            for item in entries:
                if isinstance(item, dict):
                    return {str(key): value for key, value in item.items()}
        return {str(key): value for key, value in sanitized.items()}

    async def _select_media_url(self, info: dict[str, Any]) -> tuple[str, str]:
        candidates: list[dict[str, Any]] = []
        formats = info.get("formats")
        if isinstance(formats, list):
            candidates.extend(item for item in formats if isinstance(item, dict))
        if isinstance(info.get("url"), str):
            candidates.append(info)

        def score(item: dict[str, Any]) -> tuple[int, int, int, int]:
            protocol = self._text(item.get("protocol"), 40).casefold()
            url = self._text(item.get("url"), 4096)
            vcodec = self._text(item.get("vcodec"), 80).casefold()
            acodec = self._text(item.get("acodec"), 80).casefold()
            ext = self._text(item.get("ext"), 20).casefold()
            height_raw = item.get("height")
            height = int(height_raw) if isinstance(height_raw, (int, float)) else 0
            has_video = bool(url and vcodec and vcodec != "none")
            has_audio = bool(acodec and acodec != "none")
            direct_http = protocol.startswith("http") and "m3u8" not in protocol and "dash" not in protocol
            reasonable_height = min(height or 480, 1080)
            return (
                int(has_video and has_audio and direct_http),
                int(has_video and direct_http),
                int(ext in {"mp4", "webm"}),
                reasonable_height,
            )

        for item in sorted(candidates, key=score, reverse=True):
            url = self._text(item.get("url"), 4096)
            if not url:
                continue
            try:
                validated = await self.url_guard.validate(url)
            except PublicUrlRejected:
                continue
            if len(validated) > 4096:
                continue
            return validated, self._text(item.get("ext"), 20)
        return "", ""

    @classmethod
    def _select_subtitle(cls, info: dict[str, Any]) -> _SubtitleCandidate | None:
        for field, source in (("subtitles", "manual"), ("automatic_captions", "automatic")):
            raw = info.get(field)
            if not isinstance(raw, dict):
                continue
            language = cls._preferred_language(raw)
            if not language:
                continue
            entries = raw.get(language)
            if not isinstance(entries, list):
                continue
            preferred = sorted(
                (item for item in entries if isinstance(item, dict)),
                key=lambda item: cls._subtitle_format_score(cls._text(item.get("ext"), 20)),
                reverse=True,
            )
            for item in preferred:
                url = cls._text(item.get("url"), 4096)
                if url:
                    return _SubtitleCandidate(
                        url=url,
                        ext=cls._text(item.get("ext"), 20),
                        language=language,
                        source=source,
                    )
        return None

    @staticmethod
    def _preferred_language(values: dict[str, Any]) -> str:
        available = [key for key in values if isinstance(key, str) and key != "live_chat"]
        for preferred in _LANGUAGE_PRIORITY:
            for language in available:
                if language.casefold() == preferred.casefold():
                    return language
        for prefix in ("zh", "en"):
            for language in available:
                if language.casefold().startswith(prefix):
                    return language
        return available[0] if available else ""

    @staticmethod
    def _subtitle_format_score(ext: str) -> int:
        order = {"json3": 5, "vtt": 4, "srt": 3, "ttml": 2, "srv3": 1}
        return order.get(ext.casefold(), 0)

    async def _fetch_transcript(self, subtitle: _SubtitleCandidate) -> str:
        try:
            current = await self.url_guard.validate(subtitle.url)
        except PublicUrlRejected:
            return ""
        headers = {"User-Agent": "CharacterRelay/0.4 SubtitleResolver"}
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(15.0),
                transport=self.http_transport,
                follow_redirects=False,
                headers=headers,
            ) as client:
                for _ in range(4):
                    response = await client.get(current)
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location", "").strip()
                        if not location:
                            return ""
                        current = await self.url_guard.validate(urljoin(current, location))
                        continue
                    if response.is_error or len(response.content) > _MAX_SUBTITLE_BYTES:
                        return ""
                    return self._parse_subtitle(response.content, subtitle.ext)
        except (httpx.HTTPError, PublicUrlRejected, ValueError):
            return ""
        return ""

    @classmethod
    def _parse_subtitle(cls, content: bytes, ext: str) -> str:
        text = content.decode("utf-8", errors="replace")
        if ext.casefold() == "json3":
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                return ""
            lines: list[str] = []
            events = data.get("events") if isinstance(data, dict) else None
            if isinstance(events, list):
                for event in events:
                    if not isinstance(event, dict):
                        continue
                    segments = event.get("segs")
                    if not isinstance(segments, list):
                        continue
                    line = "".join(
                        str(segment.get("utf8", ""))
                        for segment in segments
                        if isinstance(segment, dict)
                    ).strip()
                    if line:
                        lines.append(line)
            return cls._normalize_transcript(lines)

        cleaned = re.sub(r"<[^>]+>", "", text)
        lines = []
        for raw in cleaned.splitlines():
            line = html.unescape(raw).strip()
            if not line:
                continue
            if line.startswith(("WEBVTT", "Kind:", "Language:")):
                continue
            if re.fullmatch(r"\d+", line):
                continue
            if "-->" in line:
                continue
            if line.startswith("NOTE"):
                continue
            lines.append(line)
        return cls._normalize_transcript(lines)

    @staticmethod
    def _normalize_transcript(lines: list[str]) -> str:
        normalized: list[str] = []
        previous = ""
        for raw in lines:
            line = re.sub(r"\s+", " ", raw).strip()
            if not line or line == previous:
                continue
            previous = line
            normalized.append(line)
            if sum(len(item) + 1 for item in normalized) >= _MAX_TRANSCRIPT_CHARS:
                break
        return "\n".join(normalized)[:_MAX_TRANSCRIPT_CHARS]

    @staticmethod
    def _duration(value: Any) -> int | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return max(0, int(value))

    @staticmethod
    def _text(value: Any, limit: int) -> str:
        return value.strip()[:limit] if isinstance(value, str) else ""
