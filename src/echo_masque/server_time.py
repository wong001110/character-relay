"""Server-scoped timezone context shared by prompts and Tool execution."""

from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_DEFAULT_TIMEZONE = "UTC"
_SERVER_TIMEZONE: ContextVar[str] = ContextVar(
    "character_relay_server_timezone",
    default=_DEFAULT_TIMEZONE,
)


def validate_timezone(value: str) -> str:
    """Validate and normalize one IANA timezone name."""

    normalized = value.strip() or _DEFAULT_TIMEZONE
    try:
        ZoneInfo(normalized)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Unknown IANA timezone.") from exc
    return normalized


def activate_server_timezone(value: str) -> str:
    """Set the current request/task timezone, falling back safely to UTC."""

    try:
        normalized = validate_timezone(value)
    except ValueError:
        normalized = _DEFAULT_TIMEZONE
    _SERVER_TIMEZONE.set(normalized)
    return normalized


def current_server_timezone() -> str:
    return _SERVER_TIMEZONE.get()


def server_local_now(timezone: str | None = None) -> datetime:
    name = validate_timezone(timezone or current_server_timezone())
    return datetime.now(ZoneInfo(name))


__all__ = [
    "activate_server_timezone",
    "current_server_timezone",
    "server_local_now",
    "validate_timezone",
]
