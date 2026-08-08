import asyncio

import pytest

from echo_masque.browser_runtime import BrowserCapabilityManager, BrowserRuntimeSettings
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
