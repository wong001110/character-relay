"""Source-level enrichment for shared links and their complete media inventory.

Connector previews are deliberately treated as evidence, not as proof that a linked post's
asset inventory is complete. Platform-specific enrichers plug into this provider-neutral layer
and return one normalized manifest that Character media perception can consume lazily.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from time import monotonic
from typing import Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field

from echo_masque.content_resolver import ResolvedContentSource
from echo_masque.network_safety import PublicUrlGuard, PublicUrlRejected

AssetInventoryState = Literal["unknown", "partial", "complete"]
SharedAssetKind = Literal["image", "video"]
_SHARED_CONTENT_CACHE_SECONDS = 10 * 60
_FXTWITTER_API_BASE = "https://api.fxtwitter.com/2"
_MAX_SHARED_ASSETS = 12


class SharedContentAsset(BaseModel):
    """One source asset discovered while enriching a shared content item."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    asset_key: str = Field(min_length=1, max_length=500)
    kind: SharedAssetKind
    url: str = Field(min_length=1, max_length=4096)
    ordinal: int = Field(ge=1, le=100)
    label: str = Field(default="", max_length=300)
    width: int | None = Field(default=None, ge=0, le=100_000)
    height: int | None = Field(default=None, ge=0, le=100_000)
    role: Literal["source"] = "source"


class SharedContentManifest(BaseModel):
    """Normalized source content plus the best-known source asset inventory."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_key: str = Field(min_length=1, max_length=500)
    canonical_url: str = Field(min_length=1, max_length=4096)
    platform: str = Field(default="web", max_length=80)
    author: str = Field(default="", max_length=500)
    text: str = Field(default="", max_length=12_000)
    assets: tuple[SharedContentAsset, ...] = ()
    inventory_state: AssetInventoryState = "unknown"
    expected_asset_count: int | None = Field(default=None, ge=0, le=100)
    resolver: str = Field(default="", max_length=120)

    @property
    def discovered_asset_count(self) -> int:
        return len(self.assets)


class SharedContentEnricher(Protocol):
    """Platform adapter capable of expanding one normalized source identity."""

    def supports(self, source: ResolvedContentSource) -> bool: ...

    async def enrich(self, source: ResolvedContentSource) -> SharedContentManifest | None: ...


@dataclass(frozen=True)
class _ManifestCacheEntry:
    value: SharedContentManifest
    expires_at: float


@dataclass(slots=True)
class SharedContentResolver:
    """Run source enrichers with short-lived cache and single-flight deduplication."""

    enrichers: tuple[SharedContentEnricher, ...]
    cache_seconds: int = _SHARED_CONTENT_CACHE_SECONDS
    _cache: dict[str, _ManifestCacheEntry] = field(default_factory=dict, init=False, repr=False)
    _tasks: dict[str, asyncio.Task[SharedContentManifest]] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    async def resolve(self, source: ResolvedContentSource) -> SharedContentManifest:
        now = monotonic()
        cached = self._cache.get(source.source_key)
        if cached is not None and cached.expires_at > now:
            return cached.value

        async with self._lock:
            task = self._tasks.get(source.source_key)
            if task is None:
                task = asyncio.create_task(self._resolve_uncached(source))
                self._tasks[source.source_key] = task
        try:
            value = await asyncio.shield(task)
            self._cache[source.source_key] = _ManifestCacheEntry(
                value=value,
                expires_at=monotonic() + max(30, self.cache_seconds),
            )
            return value
        finally:
            if task.done():
                async with self._lock:
                    if self._tasks.get(source.source_key) is task:
                        self._tasks.pop(source.source_key, None)

    async def _resolve_uncached(self, source: ResolvedContentSource) -> SharedContentManifest:
        for enricher in self.enrichers:
            if not enricher.supports(source):
                continue
            try:
                manifest = await enricher.enrich(source)
            except Exception:
                manifest = None
            if manifest is not None:
                return manifest
        return SharedContentManifest(
            source_key=source.source_key,
            canonical_url=source.canonical_url,
            platform=source.platform,
            inventory_state="unknown",
        )


@dataclass(slots=True)
class FxTwitterSharedContentEnricher:
    """Resolve X/Twitter posts through FxTwitter into a complete source asset manifest."""

    url_guard: PublicUrlGuard
    http_transport: httpx.AsyncBaseTransport | None = None
    api_base: str = _FXTWITTER_API_BASE

    def supports(self, source: ResolvedContentSource) -> bool:
        return source.platform == "x" and source.source_key.startswith("x:")

    async def enrich(self, source: ResolvedContentSource) -> SharedContentManifest | None:
        status_id = source.source_key.removeprefix("x:").strip()
        if not status_id.isdigit():
            return None
        endpoint = f"{self.api_base.rstrip('/')}/status/{status_id}"
        try:
            endpoint = await self.url_guard.validate(endpoint)
        except PublicUrlRejected:
            return None
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(12.0),
                transport=self.http_transport,
                follow_redirects=False,
                headers={"User-Agent": "Character-Relay/SharedContentResolver"},
            ) as client:
                response = await client.get(endpoint, headers={"Accept": "application/json"})
        except httpx.HTTPError:
            return None
        if response.is_error or response.is_redirect:
            return None
        try:
            body = response.json()
        except ValueError:
            return None
        if not isinstance(body, dict):
            return None
        code = body.get("code")
        if isinstance(code, (int, float)) and int(code) != 200:
            return None
        status = body.get("status")
        if not isinstance(status, dict):
            status = body.get("tweet")
        if not isinstance(status, dict):
            return None
        if status.get("type") not in {None, "status"}:
            return None

        text = self._text(status.get("text"), 12_000)
        author = self._author(status.get("author") or body.get("author"))
        assets = self._assets(source, status)
        return SharedContentManifest(
            source_key=source.source_key,
            canonical_url=source.canonical_url,
            platform="x",
            author=author,
            text=text,
            assets=assets,
            inventory_state="complete",
            expected_asset_count=len(assets),
            resolver="fxtwitter-v2",
        )

    @classmethod
    def _assets(
        cls,
        source: ResolvedContentSource,
        status: dict[str, object],
    ) -> tuple[SharedContentAsset, ...]:
        media = status.get("media")
        if not isinstance(media, dict):
            return ()
        ordered = media.get("all")
        values: list[dict[str, object]] = []
        if isinstance(ordered, list):
            values = [item for item in ordered if isinstance(item, dict)]
        else:
            for key in ("photos", "videos"):
                raw = media.get(key)
                if isinstance(raw, list):
                    values.extend(item for item in raw if isinstance(item, dict))

        assets: list[SharedContentAsset] = []
        seen_urls: set[str] = set()
        for raw in values[:_MAX_SHARED_ASSETS]:
            media_type = cls._text(raw.get("type"), 40).casefold()
            if media_type == "mosaic_photo":
                continue
            url = cls._text(raw.get("url"), 4096)
            if not url or url in seen_urls:
                continue
            kind: SharedAssetKind = (
                "video"
                if media_type in {"video", "gif", "animated_gif"}
                or cls._text(raw.get("format"), 80).casefold().startswith("video/")
                else "image"
            )
            seen_urls.add(url)
            ordinal = len(assets) + 1
            raw_id = cls._text(raw.get("id"), 160)
            asset_id = raw_id or str(ordinal)
            assets.append(
                SharedContentAsset(
                    asset_key=f"{source.source_key}:{kind}:{asset_id}",
                    kind=kind,
                    url=url,
                    ordinal=ordinal,
                    label=f"X post {kind} {ordinal}",
                    width=cls._integer(raw.get("width")),
                    height=cls._integer(raw.get("height")),
                )
            )
        return tuple(assets)

    @classmethod
    def _author(cls, value: object) -> str:
        if not isinstance(value, dict):
            return ""
        name = cls._text(value.get("name"), 300)
        screen_name = cls._text(value.get("screen_name"), 200).lstrip("@")
        if name and screen_name:
            return f"{name} (@{screen_name})"[:500]
        return (name or (f"@{screen_name}" if screen_name else ""))[:500]

    @staticmethod
    def _text(value: object, maximum: int) -> str:
        return str(value).strip()[:maximum] if isinstance(value, str) else ""

    @staticmethod
    def _integer(value: object) -> int | None:
        return int(value) if isinstance(value, (int, float)) and value >= 0 else None


def default_shared_content_resolver(
    *,
    url_guard: PublicUrlGuard,
    http_transport: httpx.AsyncBaseTransport | None = None,
) -> SharedContentResolver:
    return SharedContentResolver(
        (
            FxTwitterSharedContentEnricher(
                url_guard=url_guard,
                http_transport=http_transport,
            ),
        )
    )


__all__ = [
    "AssetInventoryState",
    "FxTwitterSharedContentEnricher",
    "SharedContentAsset",
    "SharedContentEnricher",
    "SharedContentManifest",
    "SharedContentResolver",
    "default_shared_content_resolver",
]
