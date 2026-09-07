"""A narrow progress channel available only while a turn job is executing."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

ProgressCallback = Callable[[str], Awaitable[bool]]
_callback: ContextVar[ProgressCallback | None] = ContextVar("turn_progress_callback", default=None)


async def publish_turn_progress(text: str) -> bool:
    callback = _callback.get()
    return await callback(text) if callback is not None else False


def turn_progress_available() -> bool:
    """Whether the current Runtime call is executing inside an accepted turn job."""
    return _callback.get() is not None


@contextmanager
def bind_turn_progress(callback: ProgressCallback) -> Iterator[None]:
    token = _callback.set(callback)
    try:
        yield
    finally:
        _callback.reset(token)
