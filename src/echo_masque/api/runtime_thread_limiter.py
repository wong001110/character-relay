"""Explicit bounds for synchronous FastAPI dependencies in the HTTP process."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from anyio import to_thread


@asynccontextmanager
async def limit_request_threads(maximum: int) -> AsyncIterator[None]:
    """Cap AnyIO's request-thread pool for one API lifespan.

    Starlette executes synchronous dependencies in this pool.  Leaving its default unbounded
    relative to the container PID budget turns a temporary traffic spike into an OS-level
    ``can't start new thread`` failure.  Never raise an already tighter host-level cap.
    """

    limiter = to_thread.current_default_thread_limiter()
    previous = limiter.total_tokens
    limiter.total_tokens = min(previous, maximum)
    try:
        yield
    finally:
        limiter.total_tokens = previous


__all__ = ["limit_request_threads"]
