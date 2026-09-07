"""A narrow progress channel available only while a turn job is executing."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

ProgressCallback = Callable[[str], Awaitable[bool]]
TurnActiveCheck = Callable[[], bool]
_callback: ContextVar[ProgressCallback | None] = ContextVar("turn_progress_callback", default=None)
_active_check: ContextVar[TurnActiveCheck | None] = ContextVar(
    "turn_job_active_check", default=None
)


class TurnNoLongerActive(RuntimeError):
    """The durable turn was cancelled, timed out, or otherwise terminalized.

    Runtime/tool callers use this narrow signal before publishing a side effect.  It is
    intentionally distinct from transport failures: a caller that has already started
    an external operation must record an unknown outcome rather than retry it.
    """


async def publish_turn_progress(text: str) -> bool:
    callback = _callback.get()
    return await callback(text) if callback is not None else False


def turn_progress_available() -> bool:
    """Whether the current Runtime call is executing inside an accepted turn job."""
    return _callback.get() is not None


def require_active_turn() -> None:
    """Reject new work when the current durable job is no longer running."""
    checker = _active_check.get()
    if checker is not None and not checker():
        raise TurnNoLongerActive("turn_job_no_longer_active")


@contextmanager
def bind_turn_progress(
    callback: ProgressCallback, *, is_active: TurnActiveCheck | None = None
) -> Iterator[None]:
    token = _callback.set(callback)
    active_token = _active_check.set(is_active)
    try:
        yield
    finally:
        _callback.reset(token)
        _active_check.reset(active_token)
