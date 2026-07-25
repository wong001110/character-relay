"""Redaction helpers for user-supplied configuration and trace data."""

from collections.abc import Mapping, Sequence
from typing import TypeAlias

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]

_SENSITIVE_KEYS = {
    "authorization",
    "proxy-authorization",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "token",
    "secret",
    "password",
    "cookie",
    "set-cookie",
}


def is_sensitive_key(key: str) -> bool:
    """Return whether a mapping key commonly contains a credential."""

    normalized = key.strip().lower().replace("-", "_")
    normalized_keys = {item.replace("-", "_") for item in _SENSITIVE_KEYS}
    return normalized in normalized_keys or normalized.endswith(
        ("_api_key", "_secret", "_password", "_credential")
    )


def redact(value: object) -> JsonValue:
    """Return a JSON-safe copy with sensitive values removed."""

    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if is_sensitive_key(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
