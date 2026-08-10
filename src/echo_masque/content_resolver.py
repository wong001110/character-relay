"""Provider-neutral URL classification and canonical source identities."""

from __future__ import annotations

import re
from typing import Literal, Protocol
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from pydantic import BaseModel, ConfigDict, Field

ContentKind = Literal["article", "image", "video", "audio", "social_post", "unknown"]
ContentResolutionStatus = Literal["available", "partial", "unsupported", "auth_required"]

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif"}
_VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".mkv", ".m4v"}
_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"}
_TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


class ResolvedContentSource(BaseModel):
    """Cheap URL-level identity before any expensive extraction or media inference."""

    model_config = ConfigDict(frozen=True)

    source_url: str = Field(min_length=1, max_length=4096)
    canonical_url: str = Field(min_length=1, max_length=4096)
    source_key: str = Field(min_length=1, max_length=500)
    kind: ContentKind
    status: ContentResolutionStatus = "available"
    platform: str = Field(default="web", max_length=80)
    media_type: Literal["image", "video", "audio"] | None = None


class ContentSourceResolver(Protocol):
    async def resolve(self, url: str) -> ResolvedContentSource: ...


def canonicalize_public_url(url: str) -> str:
    """Normalize a public HTTP(S) URL without performing network I/O."""

    parsed = urlparse(url.strip())
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Content URL must be an absolute HTTP(S) URL.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Content URL must not contain embedded credentials.")
    host = parsed.hostname.casefold().rstrip(".")
    port = parsed.port
    netloc = host
    if port is not None and not (
        (parsed.scheme.casefold() == "http" and port == 80)
        or (parsed.scheme.casefold() == "https" and port == 443)
    ):
        netloc = f"{host}:{port}"
    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_") and key.casefold() not in _TRACKING_QUERY_KEYS
    ]
    query = urlencode(sorted(query_items))
    return urlunparse((parsed.scheme.casefold(), netloc, parsed.path or "/", "", query, ""))


def _extension_kind(path: str) -> tuple[ContentKind, Literal["image", "video", "audio"] | None]:
    lowered = path.casefold()
    for extension in _IMAGE_EXTENSIONS:
        if lowered.endswith(extension):
            return "image", "image"
    for extension in _VIDEO_EXTENSIONS:
        if lowered.endswith(extension):
            return "video", "video"
    for extension in _AUDIO_EXTENSIONS:
        if lowered.endswith(extension):
            return "audio", "audio"
    return "unknown", None


def resolve_static_url(url: str) -> ResolvedContentSource:
    """Resolve identities available from the URL itself; redirects/extraction happen later."""

    canonical = canonicalize_public_url(url)
    parsed = urlparse(canonical)
    host = (parsed.hostname or "").casefold()
    path = parsed.path
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))

    if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}:
        video_id = query.get("v", "").strip()
        if not video_id:
            match = re.match(r"^/(?:shorts|live|embed)/([^/?#]+)", path)
            video_id = match.group(1) if match else ""
        if video_id:
            return ResolvedContentSource(
                source_url=url,
                canonical_url=canonical,
                source_key=f"youtube:{video_id}",
                kind="video",
                platform="youtube",
                media_type="video",
            )
    if host == "youtu.be":
        video_id = path.strip("/").split("/", 1)[0]
        if video_id:
            return ResolvedContentSource(
                source_url=url,
                canonical_url=canonical,
                source_key=f"youtube:{video_id}",
                kind="video",
                platform="youtube",
                media_type="video",
            )

    if host.endswith("bilibili.com"):
        match = re.search(r"/(BV[0-9A-Za-z]+)", path, re.IGNORECASE)
        if match:
            bvid = match.group(1)
            return ResolvedContentSource(
                source_url=url,
                canonical_url=canonical,
                source_key=f"bilibili:{bvid}",
                kind="video",
                platform="bilibili",
                media_type="video",
            )
    if host == "b23.tv":
        return ResolvedContentSource(
            source_url=url,
            canonical_url=canonical,
            source_key=f"url:{canonical}",
            kind="unknown",
            status="partial",
            platform="bilibili",
        )

    if host in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
        match = re.search(r"/status/(\d+)", path)
        if match:
            return ResolvedContentSource(
                source_url=url,
                canonical_url=canonical,
                source_key=f"x:{match.group(1)}",
                kind="social_post",
                platform="x",
            )

    if host.endswith("tiktok.com"):
        match = re.search(r"/video/(\d+)", path)
        if match:
            return ResolvedContentSource(
                source_url=url,
                canonical_url=canonical,
                source_key=f"tiktok:{match.group(1)}",
                kind="video",
                platform="tiktok",
                media_type="video",
            )

    extension_kind, media_type = _extension_kind(path)
    if extension_kind != "unknown":
        return ResolvedContentSource(
            source_url=url,
            canonical_url=canonical,
            source_key=f"url:{canonical}",
            kind=extension_kind,
            platform="web",
            media_type=media_type,
        )

    # Generic HTTP(S) documents are treated as articles until an extractor reports otherwise.
    return ResolvedContentSource(
        source_url=url,
        canonical_url=canonical,
        source_key=f"url:{canonical}",
        kind="article",
        platform="web",
    )
