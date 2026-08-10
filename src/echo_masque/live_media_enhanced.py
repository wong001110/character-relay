"""Resilient live-media extensions for Discord connector turns."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.browser_runtime import BrowserCapabilityManager, BrowserToolUnavailable
from echo_masque.content_resolver import ResolvedContentSource
from echo_masque.live_media import (
    DiscordAttachment,
    LiveMediaContext,
    LiveMediaContextService,
)
from echo_masque.media_runtime import MediaAnalysis
from echo_masque.tool_external import ExternalToolFailed

_ARTICLE_MAX_CHARS = 7000
_ARTICLE_ANALYSIS_VERSION = "article-v2"
_ARTICLE_PROVIDER = "content-extractor"
_ARTICLE_MODEL = "http-browser-v1"
_MIN_USEFUL_HTTP_CHARS = 300


class EnhancedLiveMediaContextService(LiveMediaContextService):
    """Prefer connector metadata and fall back to rendered pages when HTTP is insufficient."""

    def __init__(
        self,
        *args: Any,
        browser_runtime: BrowserCapabilityManager | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.browser_runtime = browser_runtime

    @classmethod
    def from_service(
        cls,
        service: LiveMediaContextService,
        *,
        browser_runtime: BrowserCapabilityManager | None,
    ) -> EnhancedLiveMediaContextService:
        """Rebuild a just-created base service while preserving its configured dependencies."""

        return cls(
            media_repository=service.media_repository,
            credential_resolver=service.credential_resolver,
            discord_bot_token=service.discord_bot_token,
            provider_factory=service.provider_factory,
            http_transport=service.http_transport,
            url_guard=service.url_guard,
            browser_runtime=browser_runtime,
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

    async def _article_context(
        self,
        source: ResolvedContentSource,
    ) -> LiveMediaContext | None:
        """Use HTTP first, then Chromium for JavaScript-heavy or anti-bot pages."""

        cached = self.media_repository.get(
            media_key=source.source_key,
            analysis_version=_ARTICLE_ANALYSIS_VERSION,
            provider=_ARTICLE_PROVIDER,
            model=_ARTICLE_MODEL,
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
            topics=(source.platform,),
        )
        self.media_repository.put(
            media_key=source.source_key,
            media_type="article",
            analysis_version=_ARTICLE_ANALYSIS_VERSION,
            provider=_ARTICLE_PROVIDER,
            model=_ARTICLE_MODEL,
            result_json=analysis.model_dump_json(),
            now=datetime.now(UTC),
        )
        return self._analysis_context(
            source.source_key,
            "article",
            source.platform,
            analysis,
        )
