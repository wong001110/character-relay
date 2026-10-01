"""Host-injected per-HTTP-attempt admission, separate from diagnostics and retries."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from echo_masque.providers.errors import ProviderError


class ModelAttemptBudgetExceeded(ProviderError):
    reason_code = "room_model_attempt_budget_exhausted"


_RESERVE: ContextVar[Callable[[], None] | None] = ContextVar("model_attempt_reserve", default=None)


@contextmanager
def bind_attempt_reservation(reserve: Callable[[], None]) -> Iterator[None]:
    token = _RESERVE.set(reserve)
    try:
        yield
    finally:
        _RESERVE.reset(token)


def reserve_model_attempt() -> None:
    reserve = _RESERVE.get()
    if reserve is not None:
        reserve()
