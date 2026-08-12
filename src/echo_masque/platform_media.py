"""yt-dlp-backed public platform resolver for reusable video metadata and transcripts."""

from __future__ import annotations

import asyncio
import html
import json
import re
import shutil
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
_SAFE_MEDIA_HEADER_NAMES = {
    "accept": "Accept",
    "accept-language": "Accept-Language",
    "origin": "Origin",
    "referer": "Referer",
    "user-agent": "User-Agent",
}


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
    media_headers: tuple[tuple[str, str], ...] = ()
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
        return any(
            host == suffix or host.endswith(f".{suffix}")
            for suffix in _PLATFORM_HOST_SUFFIXES
        )

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
        media_url, media_ext, media_headers = await self._select_media_url(info)
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
            media_headers=media_headers,
            transcript=transcript,
            transcript_language=transcript_language,
            transcript_source=transcript_source,
        )

    @classmethod
    def _extract_info(cls, url: str) -> dict[str, Any]:
        import yt_dlp

        options = cls._yt_dlp_options()
        try:
            return cls._extract_with_options(yt_dlp, url, options)
        except Exception as exc:
            if not cls._should_retry_bilibili_with_impersonation(url, exc):
                raise

        retry_options = dict(options)
        retry_options["impersonate"] = "chrome"
        try:
            return cls._extract_with_options(yt_dlp, url, retry_options)
        except Exception:
            # Bilibili currently returns HTTP 412 from its playurl API for some server
            # environments even when yt-dlp itself is otherwise correctly configured.
            # The caller deliberately falls back to page/Jina context instead of making
            # the entire Character turn fail.
            return {}

    @staticmethod
    def _yt_dlp_options() -> dict[str, Any]:
        node_path = shutil.which("node")
        deno_path = shutil.which("deno")
        js_runtimes: dict[str, dict[str, str | None]] = {}
        if deno_path:
            js_runtimes["deno"] = {"path": deno_path}
        if node_path:
            js_runtimes["node"] = {"path": node_path}

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
        }
        if js_runtimes:
            options["js_runtimes"] = js_runtimes
        return options

    @staticmethod
    def _extract_with_options(
        yt_dlp_module: Any,
        url: str,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        with yt_dlp_module.YoutubeDL(options) as ydl:
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

    @staticmethod
    def _should_retry_bilibili_with_impersonation(url: str, exc: Exception) -> bool:
        host = (urlparse(url).hostname or "").casefold().rstrip(".")
        is_bilibili = host == "bilibili.com" or host.endswith(".bilibili.com")
        return is_bilibili and "412" in str(exc)

    async def _select_media_url(
        self,
        info: dict[str, Any],
    ) -> tuple[str, str, tuple[tuple[str, str], ...]]:
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
            direct_http = (
                protocol.startswith("http")
                and "m3u8" not in protocol
                and "dash" not in protocol
            )
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
            headers = self._safe_media_headers(
                info.get("http_headers"),
                item.get("http_headers"),
            )
            return validated, self._text(item.get("ext"), 20), headers
        return "", "", ()

    @classmethod
    def _safe_media_headers(cls, *raw_headers: object) -> tuple[tuple[str, str], ...]:
        values: dict[str, tuple[str, str]] = {}
        for raw in raw_headers:
            if not isinstance(raw, dict):
                continue
            for raw_name, raw_value in raw.items():
                name = cls._text(raw_name, 80)
                canonical = _SAFE_MEDIA_HEADER_NAMES.get(name.casefold())
                if canonical is None:
                    continue
                value = cls._text(raw_value, 1000).replace("\r", " ").replace("\n", " ").strip()
                if value:
                    values[canonical.casefold()] = (canonical, value)
        return tuple(values[key] for key in sorted(values))

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

    @classmethod
    def _preferred_language(cls, values: dict[str, Any]) -> str:
        available = [str(key) for key in values]
        for preferred in _LANGUAGE_PRIORITY:
            exact = next(
                (item for item in available if item.casefold() == preferred.casefold()),
                None,
            )
            if exact:
                return exact
        for preferred in _LANGUAGE_PRIORITY:
            prefix = preferred.split("-", 1)[0].casefold()
            match = next(
                (item for item in available if item.casefold().split("-", 1)[0] == prefix),
                None,
            )
            if match:
                return match
        return available[0] if available else ""

    @staticmethod
    def _subtitle_format_score(ext: str) -> int:
        return {"json3": 6, "srv3": 5, "vtt": 4, "ttml": 3, "srt": 2}.get(ext.casefold(), 1)

    async def _fetch_transcript(self, candidate: _SubtitleCandidate) -> str:
        try:
            validated = await self.url_guard.validate(candidate.url)
        except PublicUrlRejected:
            return ""
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(20.0),
                transport=self.http_transport,
                follow_redirects=False,
            ) as client:
                response = await client.get(validated, headers={"Accept": "*/*"})
        except httpx.HTTPError:
            return ""
        if response.is_redirect:
            location = response.headers.get("location", "").strip()
            if not location:
                return ""
            redirected = urljoin(validated, location)
            try:
                redirected = await self.url_guard.validate(redirected)
            except PublicUrlRejected:
                return ""
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(20.0),
                    transport=self.http_transport,
                    follow_redirects=False,
                ) as client:
                    response = await client.get(redirected, headers={"Accept": "*/*"})
            except httpx.HTTPError:
                return ""
        if response.is_error:
            return ""
        content = response.content[: _MAX_SUBTITLE_BYTES + 1]
        if len(content) > _MAX_SUBTITLE_BYTES:
            return ""
        return self._subtitle_text(content, candidate.ext)

    @classmethod
    def _subtitle_text(cls, content: bytes, ext: str) -> str:
        try:
            text = content.decode("utf-8", errors="replace")
        except Exception:
            return ""
        normalized = ext.casefold()
        if normalized == "json3":
            return cls._json3_text(text)
        if normalized in {"srv1", "srv2", "srv3"}:
            text = re.sub(r"<[^>]+>", " ", text)
        elif normalized in {"vtt", "srt", "ttml"}:
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"^WEBVTT.*$", " ", text, flags=re.MULTILINE)
            text = re.sub(r"^\d+$", " ", text, flags=re.MULTILINE)
            text = re.sub(
                r"^\s*\d{1,2}:\d{2}:\d{2}[.,]\d{3}\s*-->.*$",
                " ",
                text,
                flags=re.MULTILINE,
            )
            text = re.sub(
                r"^\s*\d{1,2}:\d{2}[.,]\d{3}\s*-->.*$",
                " ",
                text,
                flags=re.MULTILINE,
            )
        return cls._clean_transcript(text)

    @classmethod
    def _json3_text(cls, text: str) -> str:
        try:
            body = json.loads(text)
        except json.JSONDecodeError:
            return ""
        if not isinstance(body, dict):
            return ""
        events = body.get("events")
        if not isinstance(events, list):
            return ""
        parts: list[str] = []
        for event in events:
            if not isinstance(event, dict):
                continue
            segs = event.get("segs")
            if not isinstance(segs, list):
                continue
            phrase = "".join(
                str(segment.get("utf8") or "")
                for segment in segs
                if isinstance(segment, dict)
            )
            if phrase.strip():
                parts.append(phrase.strip())
        return cls._clean_transcript(" ".join(parts))

    @staticmethod
    def _clean_transcript(text: str) -> str:
        cleaned = html.unescape(text)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned[:_MAX_TRANSCRIPT_CHARS]

    @staticmethod
    def _text(value: object, maximum: int) -> str:
        if value is None:
            return ""
        text = str(value).replace("\x00", "").strip()
        return text[:maximum]

    @staticmethod
    def _duration(value: object) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)) and value >= 0:
            return int(value)
        return None
