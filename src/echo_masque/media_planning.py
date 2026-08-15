"""Planner-only lightweight media descriptors for admission and Topic routing."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from time import monotonic
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from echo_masque.api.connector_schemas import DiscordAttachmentContent, DiscordEmbedContent
from echo_masque.content_resolver import resolve_static_url
from echo_masque.network_safety import PublicUrlRejected
from echo_masque.platform_media import YtDlpMediaResolver

_URL_PATTERN = re.compile(r"https?://[^\s<>\]\[(){}\"']+", re.IGNORECASE)
_DESCRIPTOR_TTL_SECONDS = 60 * 60
_MAX_PLANNING_TEXT = 2200
_MAX_SUMMARY = 900


class MediaPlanningRequest(BaseModel):
    """Discord-visible media evidence supplied before any Character is selected."""

    model_config = ConfigDict(extra="forbid")

    connection_id: str = Field(min_length=1, max_length=64)
    guild_id: str = Field(min_length=1, max_length=200)
    channel_id: str = Field(min_length=1, max_length=200)
    thread_id: str = Field(default="", max_length=200)
    message_id: str = Field(min_length=1, max_length=200)
    text: str = Field(default="", max_length=10_000)
    attachments: list[DiscordAttachmentContent] = Field(default_factory=list, max_length=10)
    embeds: list[DiscordEmbedContent] = Field(default_factory=list, max_length=10)


class MediaPlanningDescriptor(BaseModel):
    """Objective routing evidence that must never imply Character perception."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    available: bool
    kind: str = Field(default="", max_length=40)
    platform: str = Field(default="", max_length=80)
    title: str = Field(default="", max_length=500)
    summary: str = Field(default="", max_length=_MAX_SUMMARY)
    planning_text: str = Field(default="", max_length=_MAX_PLANNING_TEXT)
    source: str = Field(default="", max_length=80)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    descriptor: MediaPlanningDescriptor
    expires_at: float


def _compact(value: object, maximum: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.replace("\x00", " ").split())[:maximum]


def _urls(text: str, embeds: list[DiscordEmbedContent]) -> tuple[str, ...]:
    values = [match.rstrip(".,!?;:，。！？；：") for match in _URL_PATTERN.findall(text)]
    values.extend(item.url.strip() for item in embeds if item.url.strip())
    return tuple(dict.fromkeys(value for value in values if value))


def _attachment_kind(item: DiscordAttachmentContent) -> str:
    content_type = item.content_type.casefold()
    filename = item.filename.casefold()
    if content_type.startswith("video/"):
        return "video"
    if content_type.startswith("image/"):
        return "image"
    if content_type.startswith("audio/"):
        return "audio"
    if filename.endswith((".mp4", ".webm", ".mov", ".mkv")):
        return "video"
    if filename.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif")):
        return "image"
    return "attachment"


class MediaPlanningDescriptorService:
    """Resolve only enough objective evidence to plan a media-only Discord turn."""

    def __init__(self, platform_resolver: YtDlpMediaResolver | None = None) -> None:
        self.platform_resolver = platform_resolver or YtDlpMediaResolver()
        self._cache: dict[str, _CacheEntry] = {}

    async def describe(self, request: MediaPlanningRequest) -> MediaPlanningDescriptor:
        cache_key = f"{request.connection_id}:{request.guild_id}:{request.message_id}"
        now = monotonic()
        cached = self._cache.get(cache_key)
        if cached is not None and cached.expires_at > now:
            return cached.descriptor

        descriptor = self._from_discord_preview(request)
        if not descriptor.available:
            descriptor = await self._from_platform_metadata(request)
        if not descriptor.available:
            descriptor = self._from_attachment_label(request)

        self._cache[cache_key] = _CacheEntry(
            descriptor=descriptor,
            expires_at=now + _DESCRIPTOR_TTL_SECONDS,
        )
        if len(self._cache) > 1000:
            self._cache = {
                key: value for key, value in self._cache.items() if value.expires_at > now
            }
        return descriptor

    @staticmethod
    def _from_discord_preview(request: MediaPlanningRequest) -> MediaPlanningDescriptor:
        for embed in request.embeds:
            title = _compact(embed.title, 500)
            summary = _compact(embed.description, _MAX_SUMMARY)
            provider = _compact(embed.provider_name, 80).casefold()
            if not title and not summary:
                continue
            kind = "video" if embed.embed_type.casefold() in {"video", "rich"} else "link"
            planning = MediaPlanningDescriptorService._planning_text(
                kind=kind,
                platform=provider,
                title=title,
                summary=summary,
            )
            return MediaPlanningDescriptor(
                available=bool(planning),
                kind=kind,
                platform=provider,
                title=title,
                summary=summary,
                planning_text=planning,
                source="discord_preview",
                confidence=0.78,
            )
        return MediaPlanningDescriptor(available=False)

    async def _from_platform_metadata(
        self,
        request: MediaPlanningRequest,
    ) -> MediaPlanningDescriptor:
        for raw_url in _urls(request.text, request.embeds):
            try:
                source = resolve_static_url(raw_url)
            except ValueError:
                continue
            if source.kind != "video" or not self.platform_resolver.supports(source.canonical_url):
                continue
            try:
                validated = await self.platform_resolver.url_guard.validate(source.canonical_url)
                info = await asyncio.to_thread(self.platform_resolver._extract_info, validated)
            except (PublicUrlRejected, RuntimeError, ValueError):
                continue
            if not info:
                continue
            title = _compact(info.get("title"), 500)
            summary = _compact(info.get("description"), _MAX_SUMMARY)
            platform = _compact(
                info.get("extractor_key") or info.get("extractor") or source.platform,
                80,
            ).casefold()
            if not title and not summary:
                continue
            planning = self._planning_text(
                kind="video",
                platform=platform or source.platform,
                title=title,
                summary=summary,
            )
            return MediaPlanningDescriptor(
                available=bool(planning),
                kind="video",
                platform=platform or source.platform,
                title=title,
                summary=summary,
                planning_text=planning,
                source="platform_metadata",
                confidence=0.84,
            )
        return MediaPlanningDescriptor(available=False)

    @staticmethod
    def _from_attachment_label(request: MediaPlanningRequest) -> MediaPlanningDescriptor:
        for attachment in request.attachments:
            kind = _attachment_kind(attachment)
            filename = _compact(attachment.filename, 255)
            if not filename:
                continue
            stem = filename.rsplit(".", maxsplit=1)[0].replace("_", " ").replace("-", " ")
            semantic = " ".join(stem.split())
            if len(semantic) < 4 or re.fullmatch(r"(?:img|vid|image|video)?\s*\d+", semantic, re.I):
                continue
            planning = MediaPlanningDescriptorService._planning_text(
                kind=kind,
                platform="discord",
                title=semantic,
                summary="",
            )
            return MediaPlanningDescriptor(
                available=bool(planning),
                kind=kind,
                platform="discord",
                title=semantic,
                planning_text=planning,
                source="attachment_label",
                confidence=0.45,
            )
        return MediaPlanningDescriptor(available=False)

    @staticmethod
    def _planning_text(*, kind: str, platform: str, title: str, summary: str) -> str:
        parts = ["Planner-only objective media descriptor.", f"Kind: {kind or 'media'}." ]
        if platform:
            parts.append(f"Platform: {platform}.")
        if title:
            parts.append(f"Title/topic: {title}.")
        if summary:
            parts.append(f"Rough description: {summary}.")
        return " ".join(parts)[:_MAX_PLANNING_TEXT]


__all__ = [
    "MediaPlanningDescriptor",
    "MediaPlanningDescriptorService",
    "MediaPlanningRequest",
]
