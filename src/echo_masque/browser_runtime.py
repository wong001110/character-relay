"""Lazy, reusable Playwright + Chromium capability for browser-backed Tools."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from contextvars import ContextVar
from dataclasses import dataclass, field
from html.parser import HTMLParser
from time import monotonic
from urllib.parse import parse_qs, quote_plus, unquote, urlparse, urlsplit

import httpx
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    Response,
    Route,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from echo_masque.network_safety import PublicUrlGuard, PublicUrlRejected

_BROWSER_SESSION_KEY: ContextVar[str] = ContextVar(
    "character_relay_browser_session_key",
    default="runtime",
)
_STATIC_SEARCH_ENGINE = "duckduckgo-html"
_WEB_SEARCH_ENGINES = ("google", "bing")
_DDG_SEARCH_HOST = "html.duckduckgo.com"
_DDG_HTTP_TIMEOUT_SECONDS = 8.0
_MAX_RENDERED_COLLECTION_JSON_RESPONSES = 8
_MAX_RENDERED_COLLECTION_JSON_RESPONSE_BYTES = 128 * 1_024
_MAX_RENDERED_COLLECTION_JSON_TOTAL_BYTES = 512 * 1_024
_RENDERED_COLLECTION_JSON_DRAIN_SECONDS = 2.0


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


@dataclass(frozen=True, slots=True)
class RenderedCollectionPage:
    """One bounded public DOM capture for an explicitly approved Fabric Source.

    ``html`` and ``public_json`` are consumed only by the private Knowledge ingestion path and
    are never returned from the Portal API. ``public_json`` contains only bounded successful JSON
    responses loaded by the rendered page from an explicitly approved host; it never contains
    request URLs, headers, or credentials.
    """

    html: str
    hrefs: tuple[str, ...]
    public_json: tuple[str, ...] = ()


@dataclass
class _BrowserSession:
    context: BrowserContext
    created_at: float
    last_used_at: float
    pages: dict[str, Page] = field(default_factory=dict)
    page_last_used: dict[str, float] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class _DuckDuckGoHTMLParser(HTMLParser):
    """Extract the stable no-JavaScript result link/snippet classes from DuckDuckGo HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.snippets: list[str] = []
        self._capture_kind = ""
        self._capture_href = ""
        self._capture_text: list[str] = []
        self._capture_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._capture_kind:
            self._capture_depth += 1
            return
        attributes = {key: value or "" for key, value in attrs}
        classes = set(attributes.get("class", "").split())
        if tag == "a" and "result__a" in classes:
            self._capture_kind = "link"
            self._capture_href = attributes.get("href", "")
            self._capture_text = []
            self._capture_depth = 1
        elif "result__snippet" in classes:
            self._capture_kind = "snippet"
            self._capture_href = ""
            self._capture_text = []
            self._capture_depth = 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._capture_kind:
            return
        self.handle_starttag(tag, attrs)
        if self._capture_kind:
            self._finish_capture()

    def handle_endtag(self, tag: str) -> None:
        del tag
        if not self._capture_kind:
            return
        self._capture_depth -= 1
        if self._capture_depth <= 0:
            self._finish_capture()

    def handle_data(self, data: str) -> None:
        if self._capture_kind:
            self._capture_text.append(data)

    def _finish_capture(self) -> None:
        text = _normalized_text(" ".join(self._capture_text), 1600)
        if self._capture_kind == "link" and self._capture_href and text:
            self.links.append((self._capture_href, text[:500]))
        elif self._capture_kind == "snippet" and text:
            self.snippets.append(text)
        self._capture_kind = ""
        self._capture_href = ""
        self._capture_text = []
        self._capture_depth = 0


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
        engine, results, attempted = await self._search_web_resilient(
            normalized,
            count,
            page_kind="web-search",
        )
        return {
            "ok": True,
            "provider": "browser",
            "engine": engine,
            "attempted_engines": attempted,
            "fallback_used": engine != _STATIC_SEARCH_ENGINE,
            "query": normalized,
            "result_count": len(results),
            "results": results,
            "untrusted_external_content": True,
        }

    async def search_images(self, query: str, count: int) -> dict[str, object]:
        normalized = _query(query)
        count = min(max(count, 1), 10)
        async with self._page_for("image-search") as page:
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
        engine, web_results, attempted = await self._search_web_resilient(
            combined,
            count,
            page_kind="places-search",
        )
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
            "engine": f"{engine}-local-discovery",
            "attempted_engines": attempted,
            "fallback_used": engine != _STATIC_SEARCH_ENGINE,
            "query": normalized_query,
            "location": normalized_location,
            "result_count": len(results),
            "results": results,
            "untrusted_external_content": True,
        }

    async def fetch_rendered_page(self, url: str, max_chars: int) -> dict[str, object]:
        validated = await self.url_guard.validate(url.strip())
        max_chars = min(max(max_chars, 500), 12_000)
        async with self._page_for("rendered-fetch") as page:
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

    async def fetch_rendered_collection_page(
        self,
        *,
        url: str,
        allowed_hosts: frozenset[str],
        max_links: int,
    ) -> RenderedCollectionPage:
        """Render one public page within a Source-approved hostname set.

        This is deliberately separate from interactive Browser Tools: it creates an ephemeral
        cookie-free context, blocks service workers, and refuses every request outside the exact
        Source profile host set.  The caller owns page/graph budgets and canonical URL admission.
        """

        validated = await self.url_guard.validate(url.strip())
        hostname = (urlsplit(validated).hostname or "").casefold().rstrip(".")
        normalized_hosts = frozenset(
            item.strip().casefold().rstrip(".") for item in allowed_hosts if item.strip()
        )
        if not hostname or hostname not in normalized_hosts:
            raise BrowserToolUnavailable("Rendered collection destination is not approved.")
        capped_links = min(max(max_links, 1), 1_000)
        async with self._public_collection_page(normalized_hosts) as page:
            captured_json: list[str] = []
            captured_json_bytes = 0
            response_tasks: list[asyncio.Task[None]] = []

            async def capture_public_json(response: Response) -> None:
                nonlocal captured_json_bytes
                if not _is_admissible_rendered_collection_json_response(
                    url=response.url,
                    request_method=response.request.method,
                    resource_type=response.request.resource_type,
                    status_code=response.status,
                    content_type=response.headers.get("content-type", ""),
                    allowed_hosts=normalized_hosts,
                ):
                    return
                try:
                    body = await response.body()
                except Exception:
                    return
                if len(body) > _MAX_RENDERED_COLLECTION_JSON_RESPONSE_BYTES:
                    return
                try:
                    value = json.loads(body)
                    normalized = json.dumps(
                        value,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                except (TypeError, UnicodeDecodeError, json.JSONDecodeError):
                    return
                encoded = normalized.encode("utf-8")
                if (
                    len(encoded) > _MAX_RENDERED_COLLECTION_JSON_RESPONSE_BYTES
                    or captured_json_bytes + len(encoded) > _MAX_RENDERED_COLLECTION_JSON_TOTAL_BYTES
                ):
                    return
                captured_json.append(normalized)
                captured_json_bytes += len(encoded)

            response_slots = 0

            def schedule_public_json_capture(response: Response) -> None:
                nonlocal response_slots
                if response_slots >= _MAX_RENDERED_COLLECTION_JSON_RESPONSES:
                    return
                if not _is_admissible_rendered_collection_json_response(
                    url=response.url,
                    request_method=response.request.method,
                    resource_type=response.request.resource_type,
                    status_code=response.status,
                    content_type=response.headers.get("content-type", ""),
                    allowed_hosts=normalized_hosts,
                ):
                    return
                response_slots += 1
                response_tasks.append(asyncio.create_task(capture_public_json(response)))

            page.on("response", schedule_public_json_capture)
            await self._navigate(page, validated)
            try:
                await page.wait_for_load_state("networkidle", timeout=4_000)
            except PlaywrightTimeoutError:
                pass
            await page.wait_for_timeout(250)
            page.remove_listener("response", schedule_public_json_capture)
            if response_tasks:
                _done, pending = await asyncio.wait(
                    response_tasks,
                    timeout=_RENDERED_COLLECTION_JSON_DRAIN_SECONDS,
                )
                for task in pending:
                    task.cancel()
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
            try:
                html = await page.content()
                links = page.locator("a")
                link_count = min(await links.count(), capped_links)
                hrefs: list[str] = []
                for index in range(link_count):
                    href = await links.nth(index).get_attribute("href")
                    if href and len(href) <= 2_048:
                        hrefs.append(href)
            except PlaywrightTimeoutError as exc:
                raise BrowserToolUnavailable(
                    "Rendered collection page did not expose a readable DOM."
                ) from exc
        if len(html.encode("utf-8")) > 1_048_576:
            raise BrowserToolUnavailable("Rendered collection DOM exceeded the page limit.")
        return RenderedCollectionPage(
            html=html,
            hrefs=tuple(hrefs),
            public_json=tuple(captured_json),
        )

    @asynccontextmanager
    async def _page_for(self, page_kind: str) -> AsyncIterator[Page]:
        if not self.settings.enabled:
            raise BrowserToolUnavailable("Browser Tools are disabled by Runtime configuration.")
        async with self._semaphore:
            session = await self._ensure_session(_BROWSER_SESSION_KEY.get())
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
    async def _public_collection_page(self, allowed_hosts: frozenset[str]) -> AsyncIterator[Page]:
        """Create a one-use BrowserContext whose route guard is narrower than Browser Tools."""

        if not self.settings.enabled:
            raise BrowserToolUnavailable("Browser Tools are disabled by Runtime configuration.")
        async with self._semaphore:
            async with self._state_lock:
                await self._ensure_browser_locked()
                browser = self._browser
                if browser is None:
                    raise BrowserToolUnavailable("Chromium is unavailable.")
                self._active_operations += 1
            context: BrowserContext | None = None
            try:
                context = await browser.new_context(
                    accept_downloads=False,
                    service_workers="block",
                    locale="en-MY",
                    user_agent=_chromium_user_agent(browser.version),
                    viewport={"width": 1365, "height": 768},
                    extra_http_headers={"Accept-Language": "en-MY,en;q=0.9"},
                )

                async def guard(route: Route) -> None:
                    await self._collection_route_guard(route, allowed_hosts)

                await context.route("**/*", guard)
                page = await context.new_page()
                page.set_default_navigation_timeout(self.settings.navigation_timeout_ms)
                page.set_default_timeout(self.settings.navigation_timeout_ms)
                yield page
            finally:
                if context is not None:
                    with suppress(Exception):
                        await context.close()
                async with self._state_lock:
                    self._active_operations = max(0, self._active_operations - 1)
                    self._browser_operations += 1
                    self._browser_last_used_at = monotonic()

    @asynccontextmanager
    async def use_session_key(self, key: str) -> AsyncIterator[None]:
        """Bind BrowserContext reuse to one owner/deployment for this logical turn."""

        token = _BROWSER_SESSION_KEY.set(key or "runtime")
        try:
            yield
        finally:
            _BROWSER_SESSION_KEY.reset(token)

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
                locale="en-MY",
                user_agent=_chromium_user_agent(self._browser.version),
                viewport={"width": 1365, "height": 768},
                extra_http_headers={"Accept-Language": "en-MY,en;q=0.9"},
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

    async def _search_web_resilient(
        self,
        query: str,
        count: int,
        *,
        page_kind: str,
    ) -> tuple[str, list[dict[str, str]], list[str]]:
        attempted = [_STATIC_SEARCH_ENGINE]
        static_failure = ""
        try:
            static_results = await self._search_duckduckgo_html(query, count)
        except BrowserToolUnavailable as exc:
            static_failure = str(exc)
        else:
            return _STATIC_SEARCH_ENGINE, static_results, attempted

        try:
            async with self._page_for(page_kind) as page:
                engine, results, browser_attempted = await self._search_web_with_fallback(
                    page,
                    query,
                    count,
                )
        except BrowserToolUnavailable as exc:
            detail = "; ".join(
                item
                for item in (
                    f"{_STATIC_SEARCH_ENGINE}: {static_failure}" if static_failure else "",
                    str(exc),
                )
                if item
            )
            raise BrowserToolUnavailable(
                "Web search engines returned no usable results"
                + (f" ({detail})." if detail else ".")
            ) from exc
        attempted.extend(browser_attempted)
        return engine, results, attempted

    async def _search_duckduckgo_html(
        self,
        query: str,
        count: int,
    ) -> list[dict[str, str]]:
        url = (
            f"https://{_DDG_SEARCH_HOST}/html/?"
            f"q={quote_plus(query)}&kp=1&kl=wt-wt"
        )
        validated = await self.url_guard.validate(url)
        headers = {
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-MY,en;q=0.9",
            "User-Agent": _desktop_chromium_user_agent("140.0.0.0"),
        }
        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=_DDG_HTTP_TIMEOUT_SECONDS,
                headers=headers,
            ) as client:
                response = await client.get(validated)
        except httpx.HTTPError as exc:
            raise BrowserToolUnavailable("static HTML request failed") from exc
        if response.status_code >= 400:
            raise BrowserToolUnavailable(
                f"static HTML endpoint returned HTTP {response.status_code}"
            )
        results = _extract_duckduckgo_html_results(response.text, count)
        if results:
            return results
        if _duckduckgo_reports_no_results(response.text):
            return []
        if _duckduckgo_reports_challenge(response.text):
            raise BrowserToolUnavailable("static HTML endpoint returned a challenge page")
        raise BrowserToolUnavailable("static HTML endpoint returned no parsable search results")

    async def _search_web_with_fallback(
        self,
        page: Page,
        query: str,
        count: int,
    ) -> tuple[str, list[dict[str, str]], list[str]]:
        attempted: list[str] = []
        failures: list[str] = []
        for engine in _WEB_SEARCH_ENGINES:
            attempted.append(engine)
            try:
                results = await self._search_web_engine(page, engine, query, count)
            except BrowserToolUnavailable as exc:
                failures.append(f"{engine}: {exc}")
                continue
            if results:
                return engine, results, attempted
            if await self._page_reports_no_results(page):
                return engine, [], attempted
            failures.append(f"{engine}: no parsable search results")
        details = "; ".join(failures)
        raise BrowserToolUnavailable(
            "browser engines returned no usable results"
            + (f" ({details})" if details else "")
        )

    async def _search_web_engine(
        self,
        page: Page,
        engine: str,
        query: str,
        count: int,
    ) -> list[dict[str, str]]:
        if engine == "google":
            url = (
                "https://www.google.com/search?"
                f"q={quote_plus(query)}&num={count}&safe=active&hl=en"
            )
            await self._navigate(page, url)
            with suppress(PlaywrightTimeoutError):
                await page.locator("a:has(h3)").first.wait_for(timeout=3_000)
            return await self._extract_google_results(page, count)
        if engine == "bing":
            url = (
                "https://www.bing.com/search?"
                f"q={quote_plus(query)}&count={count}&safeSearch=Strict"
            )
            await self._navigate(page, url)
            with suppress(PlaywrightTimeoutError):
                await page.locator("li.b_algo h2 a").first.wait_for(timeout=3_000)
            return await self._extract_bing_results(page, count)
        raise BrowserToolUnavailable(f"Unsupported search engine: {engine}.")

    async def _extract_google_results(
        self,
        page: Page,
        count: int,
    ) -> list[dict[str, str]]:
        links = page.locator("a:has(h3)")
        link_count = min(await links.count(), count * 4)
        results: list[dict[str, str]] = []
        seen: set[str] = set()
        for index in range(link_count):
            link = links.nth(index)
            href = _google_target_url((await link.get_attribute("href") or "")[:4096])
            if not _is_external_result_url(href) or href in seen:
                continue
            title_locator = link.locator("h3").first
            title = _normalized_text(await title_locator.inner_text(), 500)
            if not title:
                continue
            snippet = ""
            container = link.locator("xpath=../..").first
            if await container.count():
                with suppress(PlaywrightTimeoutError):
                    container_text = _normalized_text(await container.inner_text(), 1800)
                    if container_text.startswith(title):
                        container_text = container_text[len(title) :].strip()
                    snippet = container_text[:1600]
            results.append({"title": title, "url": href[:2048], "snippet": snippet})
            seen.add(href)
            if len(results) >= count:
                break
        return results

    async def _extract_bing_results(self, page: Page, count: int) -> list[dict[str, str]]:
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
            if _is_external_result_url(href) and title:
                results.append({"title": title, "url": href, "snippet": snippet})
        return results

    async def _page_reports_no_results(self, page: Page) -> bool:
        try:
            text = _normalized_text(await page.locator("body").inner_text(timeout=2_000), 10_000)
        except PlaywrightTimeoutError:
            return False
        lowered = text.casefold()
        return any(
            marker in lowered
            for marker in (
                "did not match any documents",
                "there are no results for",
                "no results found for",
            )
        )

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

    async def _collection_route_guard(self, route: Route, allowed_hosts: frozenset[str]) -> None:
        """Allow only public HTTPS requests to the exact hosts approved in a Source profile."""

        url = route.request.url
        if url.startswith(("data:", "blob:", "about:")):
            await route.continue_()
            return
        if not url.startswith("https://"):
            await route.abort()
            return
        hostname = (urlsplit(url).hostname or "").casefold().rstrip(".")
        if not hostname or hostname not in allowed_hosts:
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


def _desktop_chromium_user_agent(version: str) -> str:
    normalized = version.strip() or "140.0.0.0"
    return (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{normalized} Safari/537.36"
    )


def _chromium_user_agent(version: str) -> str:
    return _desktop_chromium_user_agent(version.replace("HeadlessChrome/", ""))


def _extract_duckduckgo_html_results(value: str, count: int) -> list[dict[str, str]]:
    parser = _DuckDuckGoHTMLParser()
    parser.feed(value)
    parser.close()
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, (href, title) in enumerate(parser.links):
        target = _duckduckgo_target_url(href)
        if not _is_external_result_url(target) or target in seen:
            continue
        snippet = parser.snippets[index] if index < len(parser.snippets) else ""
        results.append(
            {
                "title": title[:500],
                "url": target[:2048],
                "snippet": snippet[:1600],
            }
        )
        seen.add(target)
        if len(results) >= count:
            break
    return results


def _duckduckgo_target_url(value: str) -> str:
    candidate = value.strip()
    if candidate.startswith("//"):
        candidate = "https:" + candidate
    elif candidate.startswith("/"):
        candidate = "https://duckduckgo.com" + candidate
    parsed = urlparse(candidate)
    hostname = (parsed.hostname or "").casefold()
    if hostname.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        return target[:2048]
    return candidate[:2048]


def _duckduckgo_reports_no_results(value: str) -> bool:
    lowered = re.sub(r"<[^>]+>", " ", value).casefold()
    return any(
        marker in lowered
        for marker in (
            "no results.",
            "no results found",
            "no more results",
        )
    )


def _duckduckgo_reports_challenge(value: str) -> bool:
    lowered = value.casefold()
    return any(
        marker in lowered
        for marker in (
            "bots use duckduckgo too",
            "please complete the following challenge",
            "anomaly-modal",
            "captcha",
        )
    )


def _google_target_url(value: str) -> str:
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.path == "/url":
        query = parse_qs(parsed.query)
        target = query.get("q", [""])[0] or query.get("url", [""])[0]
        return unquote(target)[:2048]
    return value[:2048]


def _is_external_result_url(value: str) -> bool:
    if not value.startswith(("http://", "https://")):
        return False
    hostname = (urlparse(value).hostname or "").casefold()
    if not hostname:
        return False
    blocked_hosts = (
        "google.com",
        "www.google.com",
        "bing.com",
        "www.bing.com",
        "duckduckgo.com",
        "www.duckduckgo.com",
        "html.duckduckgo.com",
        "lite.duckduckgo.com",
    )
    return hostname not in blocked_hosts and not hostname.endswith(
        (".google.com", ".bing.com", ".duckduckgo.com")
    )


def _is_admissible_rendered_collection_json_response(
    *,
    url: str,
    request_method: str,
    resource_type: str,
    status_code: int,
    content_type: str,
    allowed_hosts: frozenset[str],
) -> bool:
    """Keep optional SPA data capture inside the already-approved public request boundary."""

    hostname = (urlsplit(url).hostname or "").casefold().rstrip(".")
    media_type = content_type.casefold().split(";", maxsplit=1)[0].strip()
    return (
        url.startswith("https://")
        and hostname in allowed_hosts
        and request_method.upper() == "GET"
        and resource_type in {"fetch", "xhr"}
        and 200 <= status_code < 300
        and (media_type == "application/json" or media_type.endswith("+json"))
    )


def _safe_string(value: object, maximum: int) -> str:
    if not isinstance(value, (str, int, float)):
        return ""
    return str(value).strip()[:maximum]
