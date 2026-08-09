import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

import pytest

from echo_masque.browser_runtime import (
    BrowserCapabilityManager,
    BrowserRuntimeSettings,
    BrowserToolUnavailable,
    _chromium_user_agent,
    _duckduckgo_target_url,
    _extract_duckduckgo_html_results,
    _google_target_url,
    _is_external_result_url,
)
from echo_masque.network_safety import PublicUrlGuard, PublicUrlRejected


def test_browser_manager_start_keeps_chromium_cold() -> None:
    async def scenario() -> None:
        manager = BrowserCapabilityManager(
            BrowserRuntimeSettings(
                enabled=True,
                page_idle_seconds=1,
                context_idle_seconds=2,
                browser_idle_seconds=3,
            )
        )
        assert manager.browser_running is False
        await manager.start()
        assert manager.browser_running is False
        await manager.stop()
        assert manager.browser_running is False

    asyncio.run(scenario())


def test_public_url_guard_caches_public_dns_and_blocks_private_targets() -> None:
    calls = 0

    async def resolver(hostname: str) -> tuple[str, ...]:
        nonlocal calls
        calls += 1
        assert hostname == "example.com"
        return ("93.184.216.34",)

    async def scenario() -> None:
        guard = PublicUrlGuard(resolver, cache_seconds=300)
        assert await guard.validate("https://example.com/a") == "https://example.com/a"
        assert await guard.validate("https://example.com/b") == "https://example.com/b"
        with pytest.raises(PublicUrlRejected):
            await guard.validate("http://127.0.0.1/private")

    asyncio.run(scenario())
    assert calls == 1


def test_google_result_redirect_is_unwrapped_and_engine_links_are_rejected() -> None:
    target = _google_target_url(
        "/url?q=https%3A%2F%2Fexample.com%2Fnews%3Fa%3D1&sa=U"
    )
    assert target == "https://example.com/news?a=1"
    assert _is_external_result_url(target) is True
    assert _is_external_result_url("https://www.google.com/search?q=test") is False
    assert _is_external_result_url("https://www.bing.com/search?q=test") is False
    assert _is_external_result_url("https://html.duckduckgo.com/html/?q=test") is False


def test_duckduckgo_html_parser_extracts_redirected_results() -> None:
    document = """
    <html><body>
      <div class="result">
        <a class="result__a"
           href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fnews%3Fa%3D1">
          <b>DeepSeek</b> latest news
        </a>
        <a class="result__snippet">A current DeepSeek release summary.</a>
      </div>
      <div class="result">
        <a class="result__a" href="https://example.org/article">Second result</a>
        <div class="result__snippet">Another source.</div>
      </div>
    </body></html>
    """

    results = _extract_duckduckgo_html_results(document, 5)

    assert results == [
        {
            "title": "DeepSeek latest news",
            "url": "https://example.com/news?a=1",
            "snippet": "A current DeepSeek release summary.",
        },
        {
            "title": "Second result",
            "url": "https://example.org/article",
            "snippet": "Another source.",
        },
    ]
    assert (
        _duckduckgo_target_url(
            "//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fnews%3Fa%3D1"
        )
        == "https://example.com/news?a=1"
    )


def test_browser_user_agent_does_not_advertise_headless_chromium() -> None:
    user_agent = _chromium_user_agent("140.0.0.0")
    assert "Chrome/140.0.0.0" in user_agent
    assert "Headless" not in user_agent


def test_resilient_web_search_prefers_static_html_without_starting_browser() -> None:
    class Manager(BrowserCapabilityManager):
        async def _search_duckduckgo_html(
            self,
            query: str,
            count: int,
        ) -> list[dict[str, str]]:
            assert query == "DeepSeek latest news"
            assert count == 5
            return [
                {
                    "title": "DeepSeek news",
                    "url": "https://example.com/deepseek",
                    "snippet": "Latest news",
                }
            ]

    async def scenario() -> None:
        manager = Manager()
        engine, results, attempted = await manager._search_web_resilient(
            "DeepSeek latest news",
            5,
            page_kind="web-search",
        )
        assert engine == "duckduckgo-html"
        assert attempted == ["duckduckgo-html"]
        assert results[0]["title"] == "DeepSeek news"
        assert manager.browser_running is False

    asyncio.run(scenario())


def test_resilient_web_search_falls_back_to_browser_engines_when_html_is_blocked() -> None:
    class Manager(BrowserCapabilityManager):
        async def _search_duckduckgo_html(
            self,
            query: str,
            count: int,
        ) -> list[dict[str, str]]:
            del query, count
            raise BrowserToolUnavailable("challenge page")

        @asynccontextmanager
        async def _page_for(self, page_kind: str) -> AsyncIterator[Any]:
            assert page_kind == "web-search"
            yield object()

        async def _search_web_with_fallback(
            self,
            page: Any,
            query: str,
            count: int,
        ) -> tuple[str, list[dict[str, str]], list[str]]:
            del page, query, count
            return (
                "bing",
                [
                    {
                        "title": "DeepSeek news",
                        "url": "https://example.com/deepseek",
                        "snippet": "Latest news",
                    }
                ],
                ["google", "bing"],
            )

    async def scenario() -> None:
        manager = Manager()
        engine, results, attempted = await manager._search_web_resilient(
            "DeepSeek latest news",
            5,
            page_kind="web-search",
        )
        assert engine == "bing"
        assert attempted == ["duckduckgo-html", "google", "bing"]
        assert results[0]["title"] == "DeepSeek news"

    asyncio.run(scenario())


def test_web_search_falls_back_from_google_to_bing_when_google_has_no_parsable_results() -> None:
    class Manager(BrowserCapabilityManager):
        async def _search_web_engine(
            self,
            page: Any,
            engine: str,
            query: str,
            count: int,
        ) -> list[dict[str, str]]:
            del page, query, count
            if engine == "google":
                return []
            return [
                {
                    "title": "DeepSeek news",
                    "url": "https://example.com/deepseek",
                    "snippet": "Latest news",
                }
            ]

        async def _page_reports_no_results(self, page: Any) -> bool:
            del page
            return False

    async def scenario() -> None:
        manager = Manager()
        engine, results, attempted = await manager._search_web_with_fallback(
            cast(Any, object()),
            "DeepSeek latest news",
            5,
        )
        assert engine == "bing"
        assert attempted == ["google", "bing"]
        assert results[0]["title"] == "DeepSeek news"

    asyncio.run(scenario())


def test_web_search_does_not_report_ok_when_every_engine_is_unparsable() -> None:
    class Manager(BrowserCapabilityManager):
        async def _search_web_engine(
            self,
            page: Any,
            engine: str,
            query: str,
            count: int,
        ) -> list[dict[str, str]]:
            del page, engine, query, count
            return []

        async def _page_reports_no_results(self, page: Any) -> bool:
            del page
            return False

    async def scenario() -> None:
        manager = Manager()
        with pytest.raises(BrowserToolUnavailable, match="no usable results"):
            await manager._search_web_with_fallback(
                cast(Any, object()),
                "DeepSeek latest news",
                5,
            )

    asyncio.run(scenario())
