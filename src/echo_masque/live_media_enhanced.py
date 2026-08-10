"""Resilient live-media extensions for Discord connector turns."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import SecretStr

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.browser_runtime import BrowserCapabilityManager, BrowserToolUnavailable
from echo_masque.content_resolver import ResolvedContentSource
from echo_masque.jina_reader import JinaReaderClient, JinaReaderUnavailable
from echo_masque.live_media import (
    DiscordAttachment,
    LiveMediaContext,
    LiveMediaContextService,
    _ResolvedAsset,
)
from echo_masque.media_runtime import MediaAnalysis, MediaAsset
from echo_masque.platform_media import PlatformMediaResolution, YtDlpMediaResolver
from echo_masque.provider_credentials import ResolvedProviderCredential
from echo_masque.tool_external import ExternalToolFailed

_ARTICLE_MAX_CHARS = 14_000
_ARTICLE_ANALYSIS_VERSION = "article-v3"
_ARTICLE_PROVIDER = "jina-reader"
_ARTICLE_MODEL = "readerlm-v2"
_ARTICLE_TTL = timedelta(days=7)
_HTTP_FALLBACK_VERSION = "article-http-v1"
_HTTP_FALLBACK_PROVIDER = "content-extractor"
_HTTP_FALLBACK_MODEL = "http-browser-v1"
_MIN_USEFUL_HTTP_CHARS = 300


class EnhancedLiveMediaContextService(LiveMediaContextService):
    """Prefer connector metadata, yt-dlp platform extraction, and Jina Reader articles."""

    def __init__(
        self,
        *args: Any,
        browser_runtime: BrowserCapabilityManager | None = None,
        jina_api_key: SecretStr | None = None,
        jina_reader: JinaReaderClient | None = None,
        platform_resolver: YtDlpMediaResolver | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.browser_runtime = browser_runtime
        self.jina_reader = jina_reader or JinaReaderClient(
            api_key=jina_api_key,
            url_guard=self.url_guard,
            http_transport=self.http_transport,
        )
        self.platform_resolver = platform_resolver or YtDlpMediaResolver(
            url_guard=self.url_guard,
            http_transport=self.http_transport,
        )
        self._platform_context: dict[str, PlatformMediaResolution] = {}

    @classmethod
    def from_service(
        cls,
        service: LiveMediaContextService,
        *,
        browser_runtime: BrowserCapabilityManager | None,
        jina_api_key: SecretStr | None = None,
    ) -> EnhancedLiveMediaContextService:
        """Rebuild a just-created base service while preserving configured dependencies."""

        return cls(
            media_repository=service.media_repository,
            credential_resolver=service.credential_resolver,
            discord_bot_token=service.discord_bot_token,
            provider_factory=service.provider_factory,
            http_transport=service.http_transport,
            url_guard=service.url_guard,
            browser_runtime=browser_runtime,
            jina_api_key=jina_api_key,
        )

    async def _discord_attachments(
        self,
        payload: DiscordInboundMessage,
    ) -> list[DiscordAttachment]:
        """Trust connector-supplied metadata first; backend Discord REST remains fallback."""

        if payload.attachments:
            values: list[DiscordAttachment] = []
            for item in payload.attachments[:10]:
                url = item.url.strip() or item.proxy_url.strip()
                if not url:
                    continue
                values.append(
                    DiscordAttachment(
                        attachment_id=item.attachment_id,
                        url=url,
                        filename=item.filename or "attachment",
                        content_type=item.content_type,
                        size_bytes=item.size_bytes,
                    )
                )
            if values:
                return values
        return await super()._discord_attachments(payload)

    async def _resolve_public_media(self, source: ResolvedContentSource) -> _ResolvedAsset:
        """Resolve platform page URLs to direct media before giving them to a vision model."""

        if self.platform_resolver.supports(source.canonical_url):
            resolved = await self.platform_resolver.resolve(
                source.canonical_url,
                source_key=source.source_key,
            )
            if resolved is not None:
                self._platform_context[source.source_key] = resolved
                if resolved.media_url:
                    filename = resolved.media_id or resolved.title or source.platform
                    if resolved.media_ext:
                        filename = f"{filename}.{resolved.media_ext}"
                    return _ResolvedAsset(
                        asset=MediaAsset(
                            media_key=source.source_key,
                            media_type="video",
                            filename=filename[:255],
                            source_uri=resolved.media_url,
                        ),
                        source_key=source.source_key,
                    )
                if resolved.has_context:
                    raise ValueError(
                        "Platform media has transcript/metadata but no direct media URL."
                    )
        return await super()._resolve_public_media(source)

    async def _analyze(
        self,
        asset: MediaAsset,
        credential: ResolvedProviderCredential,
    ) -> tuple[MediaAnalysis, bool]:
        """Merge reusable yt-dlp transcript/metadata into objective visual analysis."""

        analysis, cache_hit = await super()._analyze(asset, credential)
        platform = self._platform_context.get(asset.media_key)
        if platform is None or asset.media_type != "video":
            return analysis, cache_hit

        summary_parts = [value for value in (platform.title, analysis.summary) if value]
        summary = " — ".join(dict.fromkeys(summary_parts))[:12_000]
        visible_parts = [analysis.visible_text]
        if platform.transcript:
            language = f" ({platform.transcript_language})" if platform.transcript_language else ""
            visible_parts.append(f"Transcript{language}:\n{platform.transcript}")
        visible_text = "\n\n".join(value for value in visible_parts if value)[:16_000]
        details = list(analysis.notable_details)
        if platform.uploader:
            details.append(f"Uploader: {platform.uploader}")
        if platform.duration_seconds is not None:
            details.append(f"Duration: {platform.duration_seconds}s")
        if platform.transcript_source:
            details.append(f"Transcript source: {platform.transcript_source}")
        topics = tuple(dict.fromkeys([*analysis.topics, platform.platform]))
        enhanced = MediaAnalysis(
            summary=summary or analysis.summary,
            visible_text=visible_text,
            people=analysis.people,
            objects=analysis.objects,
            notable_details=tuple(dict.fromkeys(details)),
            topics=topics,
            tone=analysis.tone,
        )
        return enhanced, cache_hit

    async def _article_context(
        self,
        source: ResolvedContentSource,
    ) -> LiveMediaContext | None:
        """Use platform transcript, then Jina Reader, then local HTTP/Chromium fallbacks."""

        platform = self._platform_context.get(source.source_key)
        if platform is None and self.platform_resolver.supports(source.canonical_url):
            platform = await self.platform_resolver.resolve(
                source.canonical_url,
                source_key=source.source_key,
            )
            if platform is not None:
                self._platform_context[source.source_key] = platform
        if platform is not None and platform.has_context:
            return self._platform_fallback_context(source, platform)

        cached = self.media_repository.get(
            media_key=source.source_key,
            analysis_version=_ARTICLE_ANALYSIS_VERSION,
            provider=_ARTICLE_PROVIDER,
            model=_ARTICLE_MODEL,
            ttl=_ARTICLE_TTL,
        )
        if cached is not None:
            try:
                analysis = MediaAnalysis.model_validate_json(cached.result_json)
                return self._analysis_context(
                    source.source_key,
                    "article",
                    source.platform,
                    analysis,
                )
            except ValueError:
                pass

        try:
            article = await self.jina_reader.read(source.canonical_url)
        except JinaReaderUnavailable:
            article = None
        if article is not None:
            details = tuple(
                value
                for value in (
                    f"Published: {article.published_time}" if article.published_time else "",
                    (
                        "Extracted with Jina ReaderLM-v2"
                        if article.structured
                        else "Extracted with Jina Reader"
                    ),
                )
                if value
            )
            analysis = MediaAnalysis(
                summary=article.summary,
                visible_text=article.content[:_ARTICLE_MAX_CHARS],
                notable_details=details,
                topics=(source.platform, "article"),
            )
            self.media_repository.put(
                media_key=source.source_key,
                media_type="article",
                analysis_version=_ARTICLE_ANALYSIS_VERSION,
                provider=_ARTICLE_PROVIDER,
                model=_ARTICLE_MODEL,
                result_json=analysis.model_dump_json(),
                now=datetime.now(UTC),
                ttl=_ARTICLE_TTL,
            )
            return self._analysis_context(
                source.source_key,
                "article",
                article.title or source.platform,
                analysis,
            )

        return await self._local_article_fallback(source)

    async def _local_article_fallback(
        self,
        source: ResolvedContentSource,
    ) -> LiveMediaContext | None:
        cached = self.media_repository.get(
            media_key=source.source_key,
            analysis_version=_HTTP_FALLBACK_VERSION,
            provider=_HTTP_FALLBACK_PROVIDER,
            model=_HTTP_FALLBACK_MODEL,
            ttl=_ARTICLE_TTL,
        )
        if cached is not None:
            try:
                analysis = MediaAnalysis.model_validate_json(cached.result_json)
                return self._analysis_context(
                    source.source_key,
                    "article",
                    source.platform,
                    analysis,
                )
            except ValueError:
                pass

        title = ""
        text = ""
        needs_browser = False
        try:
            fetched = await self.external.fetch_page_http(
                {"url": source.canonical_url, "max_chars": _ARTICLE_MAX_CHARS}
            )
            raw_text = fetched.get("text")
            raw_title = fetched.get("title")
            text = raw_text.strip() if isinstance(raw_text, str) else ""
            title = raw_title.strip() if isinstance(raw_title, str) else ""
            needs_browser = bool(fetched.get("needs_browser_render")) or (
                0 < len(text) < _MIN_USEFUL_HTTP_CHARS
            )
        except (ExternalToolFailed, ValueError):
            needs_browser = True

        browser = self.browser_runtime
        if browser is not None and browser.available and (needs_browser or not text):
            try:
                rendered = await browser.fetch_rendered_page(
                    source.canonical_url,
                    _ARTICLE_MAX_CHARS,
                )
                rendered_text = rendered.get("text")
                rendered_title = rendered.get("title")
                if isinstance(rendered_text, str) and rendered_text.strip():
                    text = rendered_text.strip()
                if isinstance(rendered_title, str) and rendered_title.strip():
                    title = rendered_title.strip()
            except (BrowserToolUnavailable, ValueError):
                pass

        if not text:
            return None

        analysis = MediaAnalysis(
            summary=title or f"Public page from {source.platform}",
            visible_text=text[:_ARTICLE_MAX_CHARS],
            topics=(source.platform, "article"),
        )
        self.media_repository.put(
            media_key=source.source_key,
            media_type="article",
            analysis_version=_HTTP_FALLBACK_VERSION,
            provider=_HTTP_FALLBACK_PROVIDER,
            model=_HTTP_FALLBACK_MODEL,
            result_json=analysis.model_dump_json(),
            now=datetime.now(UTC),
            ttl=_ARTICLE_TTL,
        )
        return self._analysis_context(
            source.source_key,
            "article",
            title or source.platform,
            analysis,
        )

    @staticmethod
    def _platform_fallback_context(
        source: ResolvedContentSource,
        platform: PlatformMediaResolution,
    ) -> LiveMediaContext:
        summary_parts = [value for value in (platform.title, platform.description) if value]
        summary = (
            " — ".join(summary_parts)[:12_000]
            or f"Public video from {source.platform}"
        )
        details = []
        if platform.uploader:
            details.append(f"Uploader: {platform.uploader}")
        if platform.duration_seconds is not None:
            details.append(f"Duration: {platform.duration_seconds}s")
        if platform.transcript_source:
            details.append(f"Transcript source: {platform.transcript_source}")
        return LiveMediaContext(
            source_key=source.source_key,
            kind="video",
            label=platform.title or source.platform,
            summary=summary,
            visible_text=platform.transcript or platform.description,
            notable_details=tuple(details),
        )
