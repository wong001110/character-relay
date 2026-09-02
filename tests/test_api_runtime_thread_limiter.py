import asyncio

from anyio import to_thread

from echo_masque.api.runtime_thread_limiter import limit_request_threads


def test_limit_request_threads_never_increases_or_leaks_the_host_limit() -> None:
    async def scenario() -> None:
        limiter = to_thread.current_default_thread_limiter()
        previous = limiter.total_tokens
        limiter.total_tokens = 3
        try:
            async with limit_request_threads(16):
                assert limiter.total_tokens == 3
            assert limiter.total_tokens == 3
        finally:
            limiter.total_tokens = previous

    asyncio.run(scenario())
