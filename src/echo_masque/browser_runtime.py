"""Lazy, reusable Playwright + Chromium capability for browser-backed Tools."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from time import monotonic
from urllib.parse import quote_plus

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    Route,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from echo_masque.network_safety import PublicUrlGuard, PublicUrlRejected


class BrowserToolUnavailable(RuntimeError):
    """Raised when the Browser Capability cannot complete a requested operation."""


@dataclass(frozen=True)
class BrowserRuntimeSettings:
    enabled: bool = True
    page_idle_seconds: int = 180
    context_idle_seconds: int = 300
    browser_idle_seconds: int = 600
    browser_max_lifetime_seconds: int = 3600
    browser_max_operations: int = 100
    max_concurrent_contexts: int = 3
    navigation_timeout_ms: int = 15_000


@dataclass
class _BrowserSession:
    context: BrowserContext
    created_at: float
    last_used_at: float
    pages: dict[str, Page] = field(default_factory=dict)
    page_last_used: dict[str, float] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class BrowserCapabilityManager:
    """Keep Chromium warm briefly, then recycle it when idle or old.

    Chromium launches only on the first browser-backed Tool call. The Browser process is
    shared, while BrowserContexts are isolated by owner + deployment and are recycled on a
    short TTL. Pages are even shorter-lived. This avoids paying Chromium startup cost on
    every search without leaving a browser resident indefinitely.
    """

    def __init__(
        self,
        settings: BrowserRuntimeSettings | None = None,
        *,
        url_guard: PublicUrlGuard | None = None,
    ) -> None:
        self.settings = settings or BrowserRuntimeSettings()
        self.url_guard = url_guard or PublicUrlGuard()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._browser_created_at = 0.0
        self._browser_last_used_at = 0.0
        self._browser_operations = 0
        self._active_operations = 0
        self._sessions: dict[str, _BrowserSession] = {}
        self._state_lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(max(1, self.settings.max_concurrent_contexts))
        self._cleanup_task: asyncio.Task[None] | None = None

    @property
    def available(self) -> bool:
        return self.settings.enabled

    @property
    def browser_running(self) -> bool:
        return self._browser is not None and self._browser.is_connected()

    async def start(self) -> None:
        """Start only the cleanup loop; Chromium remains cold until first use."""

        if not self.settings.enabled or self._cleanup_task is not None:
            return
        self._cleanup_task = asyncio.create_task(
            self._cleanup_loop(),
            name="character-relay-browser-cleanup",
        )

    async def stop(self) -> None:
        task = self._cleanup_task
        self._cleanup_task = None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        async with self._state_lock:
            await self._close_browser_locked()

    async def search_web(self, query: str, count: int) -> dict[str, object]:
        normalized = _query(query)
        count = min(max(count, 1), 10)
        async with self._page_for("web-search", normalized) as page:
            url = (
                "https://www.bing.com/search?"
                f"q={quote_plus(normalized)}&count={count}&safeSearch=Strict"
            )
            await self._navigate(page, url)
            results = await self._extract_web_results(page, count)
        return {
            "ok": True,
            "provider": "browser",
            "engine": "bing",
            "query": normalized,
            "result_count": len(results),
            "results": results,
            "untrusted_external_content": True,
        }

    async def search_images(self, query: str, count: int) -> dict[str, object]:
        normalized = _query(query)
        count = min(max(count, 1), 10)
        async with self._page_for("image-search", normalized) as page:
            url = (
                "https://www.bing.com/images/search?"
                f"q={quote_plus(normalized)}&safeSearch=Strict"
            )
            await self._navigate(page, url)
            cards = page.locator("a.iusc")
            card_count = min(await cards.count(), count)
            results: list[dict[str, object]] = []
            for index in range(card_count):
                card = cards.nth(index)
                raw = await card.get_attribute("m")
                metadata: dict[str, object] = {}
                if raw:
                    try:
                        parsed = json.loads(raw)
                        if isinstance(parsed, dict):
                            metadata = {str(key): value for key, value in parsed.items()}
                    except json.JSONDecodeError:
                        metadata = {}
                image_url = _safe_string(metadata.get("murl"), 2048)
                thumbnail_url = _safe_string(metadata.get("turl"), 2048)
                source_url = _safe_string(metadata.get("purl"), 2048)
                title = _safe_string(metadata.get("t"), 500)
                if not image_url and not thumbnail_url:
                    image = card.locator("img").first
                    thumbnail_url = (await image.get_attribute("src") or "")[:2048]
                if not image_url and not thumbnail_url:
                    continue
                results.append(
                    {
                        "title": title,
                        "image_url": image_url,
                        "thumbnail_url": thumbnail_url,
                        "source_url": source_url,
                    }
                )
        return {
            "ok": True,
            "provider": "browser",
            "engine": "bing-images",
            "query": normalized,
            "safe_search": "strict",
            "result_count": len(results),
            "results": results,
            "untrusted_external_content": True,
        }

    async def search_places(
        self,
        query: str,
        location: str,
        count: int,
    ) -> dict[str, object]:
        normalized_query = _query(query)
        normalized_location = location.strip()[:240]
        if not normalized_location:
            raise ValueError("A place search location is required; do not guess the user's location.")
        count = min(max(count, 1), 10)
        combined = f"{normalized_query} near {normalized_location} address"
        async with self._page_for("places-search", combined) as page:
            url = (
                "https://www.bing.com/search?"
                f"q={quote_plus(combined)}&count={count}&safeSearch=Strict"
            )
            await self._navigate(page, url)
            web_results = await self._extract_web_results(page, count)
        results = [
            {
                "name": item.get("title", ""),
                "description": item.get("snippet", ""),
                "source_url": item.get("url", ""),
            }
            for item in web_results
        ]
        return {
            "ok": True,
            "provider": "browser",
            "engine": "bing-local-discovery",
            "query": normalized_query,
            "location": normalized_location,
            "result_count": len(results),
            "results": results,
            "untrusted_external_content": True,
        }

    async def fetch_rendered_page(self, url: str, max_chars: int) -> dict[str, object]:
        validated = await self.url_guard.validate(url.strip())
        max_chars = min(max(max_chars, 500), 12_000)
        async with self._page_for("rendered-fetch", validated) as page:
            await self._navigate(page, validated)
            try:
                await page.wait_for_load_state("networkidle", timeout=4_000)
            except PlaywrightTimeoutError:
                pass
            title = (await page.title())[:500]
            try:
                text = await page.locator("body").inner_text(timeout=5_000)
            except PlaywrightTimeoutError as exc:
                raise BrowserToolUnavailable("Rendered page did not expose readable text.") from exc
        normalized = _normalized_text(text, max_chars)
        if not normalized:
            raise BrowserToolUnavailable("Rendered page did not contain readable text.")
        return {
            "ok": True,
            "final_url": validated,
            "title": title,
            "text": normalized,
            "truncated": len(_normalized_text(text, max_chars + 1)) > max_chars,
            "rendered_with": "playwright-chromium",
            "untrusted_external_content": True,
        }

    @asynccontextmanager
    async def _page_for(self, page_kind: str, activity_key: str) -> AsyncIterator[Page]:
        del activity_key  # Kept in the API for future per-query observability without logging text.
        if not self.settings.enabled:
            raise BrowserToolUnavailable("Browser Tools are disabled by Runtime configuration.")
        async with self._semaphore:
            session_key = asyncio.current_task()
            if session_key is None:
                key = "runtime"
            else:
                key = getattr(session_key, "_character_relay_browser_key", "runtime")
            # ToolRegistry sets a task-local key through use_session_key(); otherwise a shared
            # ephemeral runtime context is still isolated from persistent browser profiles.
            session_id = str(key)
            session = await self._ensure_session(session_id)
            async with self._state_lock:
                self._active_operations += 1
            try:
                async with session.lock:
                    page = await self._ensure_page(session, page_kind)
                    yield page
                    now = monotonic()
                    session.last_used_at = now
                    session.page_last_used[page_kind] = now
            finally:
                async with self._state_lock:
                    self._active_operations = max(0, self._active_operations - 1)
                    self._browser_operations += 1
                    self._browser_last_used_at = monotonic()

    @asynccontextmanager
    async def use_session_key(self, key: str) -> AsyncIterator[None]:
        """Bind browser Context reuse to one owner/deployment for this async task."""

        task = asyncio.current_task()
        if task is None:
            yield
            return
        sentinel = object()
        previous = getattr(task, "_character_relay_browser_key", sentinel)
        setattr(task, "_character_relay_browser_key", key)
        try:
            yield
        finally:
            if previous is sentinel:
                with suppress(AttributeError):
                    delattr(task, "_character_relay_browser_key")
            else:
                setattr(task, "_character_relay_browser_key", previous)

    async def _ensure_session(self, session_id: str) -> _BrowserSession:
        async with self._state_lock:
            await self._ensure_browser_locked()
            existing = self._sessions.get(session_id)
            if existing is not None:
                return existing
            if self._browser is None:
                raise BrowserToolUnavailable("Chromium is unavailable.")
            context = await self._browser.new_context(
                accept_downloads=False,
                service_workers="block",
                locale="en-US",
            )
            await context.route("**/*", self._route_guard)
            now = monotonic()
            session = _BrowserSession(
                context=context,
                created_at=now,
                last_used_at=now,
            )
            self._sessions[session_id] = session
            return session

    async def _ensure_browser_locked(self) -> None:
        now = monotonic()
        if self._browser is not None and self._browser.is_connected():
            hard_expired = (
                now - self._browser_created_at >= self.settings.browser_max_lifetime_seconds
                or self._browser_operations >= self.settings.browser_max_operations
            )
            if hard_expired and self._active_operations == 0:
                await self._close_browser_locked()
            else:
                return
        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=["--disable-dev-shm-usage", "--no-sandbox"],
            )
        except Exception as exc:  # Playwright raises platform-specific launch errors.
            await self._close_browser_locked()
            raise BrowserToolUnavailable(
                "Chromium could not be launched. Ensure the Playwright Chromium runtime is installed."
            ) from exc
        self._browser_created_at = now
        self._browser_last_used_at = now
        self._browser_operations = 0

    async def _ensure_page(self, session: _BrowserSession, page_kind: str) -> Page:
        page = session.pages.get(page_kind)
        if page is not None and not page.is_closed():
            return page
        page = await session.context.new_page()
        page.set_default_navigation_timeout(self.settings.navigation_timeout_ms)
        page.set_default_timeout(self.settings.navigation_timeout_ms)
        session.pages[page_kind] = page
        session.page_last_used[page_kind] = monotonic()
        return page

    async def _navigate(self, page: Page, url: str) -> None:
        try:
            response = await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=self.settings.navigation_timeout_ms,
            )
        except PlaywrightTimeoutError as exc:
            raise BrowserToolUnavailable("Browser navigation timed out.") from exc
        except Exception as exc:
            raise BrowserToolUnavailable("Browser navigation failed.") from exc
        if response is not None and response.status >= 400:
            raise BrowserToolUnavailable(f"Browser destination returned HTTP {response.status}.")

    async def _extract_web_results(self, page: Page, count: int) -> list[dict[str, str]]:
        cards = page.locator("li.b_algo")
        card_count = min(await cards.count(), count)
        results: list[dict[str, str]] = []
        for index in range(card_count):
            card = cards.nth(index)
            link = card.locator("h2 a").first
            href = (await link.get_attribute("href") or "")[:2048]
            title = _normalized_text(await link.inner_text(), 500)
            snippet_locator = card.locator("p").first
            snippet = ""
            if await snippet_locator.count():
                with suppress(PlaywrightTimeoutError):
                    snippet = _normalized_text(await snippet_locator.inner_text(), 1600)
            if href and title:
                results.append({"title": title, "url": href, "snippet": snippet})
        return results

    async def _route_guard(self, route: Route) -> None:
        url = route.request.url
        if url.startswith(("data:", "blob:", "about:")):
            await route.continue_()
            return
        if not url.startswith(("http://", "https://")):
            await route.abort()
            return
        try:
            await self.url_guard.validate(url)
        except PublicUrlRejected:
            await route.abort()
            return
        await route.continue_()

    async def _cleanup_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(30)
                await self.cleanup_idle()
        except asyncio.CancelledError:
            raise

    async def cleanup_idle(self) -> None:
        now = monotonic()
        async with self._state_lock:
            for session_id, session in list(self._sessions.items()):
                if session.lock.locked():
                    continue
                for page_kind, page in list(session.pages.items()):
                    last_used = session.page_last_used.get(page_kind, session.last_used_at)
                    if now - last_used < self.settings.page_idle_seconds:
                        continue
                    with suppress(Exception):
                        await page.close()
                    session.pages.pop(page_kind, None)
                    session.page_last_used.pop(page_kind, None)
                if now - session.last_used_at >= self.settings.context_idle_seconds:
                    with suppress(Exception):
                        await session.context.close()
                    self._sessions.pop(session_id, None)

            if self._browser is None or self._active_operations:
                return
            hard_expired = (
                now - self._browser_created_at >= self.settings.browser_max_lifetime_seconds
                or self._browser_operations >= self.settings.browser_max_operations
            )
            idle_expired = (
                not self._sessions
                and now - self._browser_last_used_at >= self.settings.browser_idle_seconds
            )
            if hard_expired or idle_expired:
                await self._close_browser_locked()

    async def _close_browser_locked(self) -> None:
        for session in list(self._sessions.values()):
            with suppress(Exception):
                await session.context.close()
        self._sessions.clear()
        browser = self._browser
        self._browser = None
        if browser is not None:
            with suppress(Exception):
                await browser.close()
        playwright = self._playwright
        self._playwright = None
        if playwright is not None:
            with suppress(Exception):
                await playwright.stop()
        self._browser_created_at = 0.0
        self._browser_last_used_at = 0.0
        self._browser_operations = 0


def _query(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value).strip()[:400]
    if not normalized:
        raise ValueError("Search query cannot be blank.")
    return normalized


def _normalized_text(value: str, maximum: int) -> str:
    return re.sub(r"\s+", " ", value).strip()[:maximum]


def _safe_string(value: object, maximum: int) -> str:
    if not isinstance(value, (str, int, float)):
        return ""
    return str(value).strip()[:maximum]
