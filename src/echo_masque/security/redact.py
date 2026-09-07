"""Redaction helpers for user-supplied configuration and trace data."""

import json
import re
from collections.abc import Mapping, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

type JsonValue = (
    str | int | float | bool | list["JsonValue"] | dict[str, "JsonValue"] | None
)

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
    "credential",
    "cookie",
    "set-cookie",
}
_TOKEN_USAGE_KEYS = {
    "cached_token_count",
    "input_tokens",
    "input_token_count",
    "output_tokens",
    "output_token_count",
    "total_tokens",
    "total_token_count",
    "cached_tokens",
    "reasoning_tokens",
    "reasoning_token_count",
    "token_count",
}
_STRUCTURED_TRACE_STRING_KEYS = {"response_body"}
_URL_PATTERN = re.compile(r"https?://[^\s<>'\"]+", re.IGNORECASE)
_URL_TRAILING_PUNCTUATION = ".,;:!?)}]"


def is_sensitive_key(key: str) -> bool:
    """Return whether a mapping key commonly contains a credential."""

    normalized = key.strip().lower().replace("-", "_")
    if normalized in _TOKEN_USAGE_KEYS:
        return False
    normalized_keys = {item.replace("-", "_") for item in _SENSITIVE_KEYS}
    compact = normalized.replace("_", "")
    compact_keys = {item.replace("_", "") for item in normalized_keys}
    return (
        normalized in normalized_keys
        or compact in compact_keys
        or normalized.endswith(("_api_key", "_secret", "_password", "_credential", "_token"))
    )


def redact(value: object) -> JsonValue:
    """Return a JSON-safe copy with sensitive values removed."""

    return _redact_value(value, key=None)


def _redact_value(value: object, *, key: str | None) -> JsonValue:
    if isinstance(value, Mapping):
        return {
            str(item_key): (
                "[REDACTED]"
                if is_sensitive_key(str(item_key))
                else _redact_value(item, key=str(item_key))
            )
            for item_key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_redact_value(item, key=None) for item in value]
    if isinstance(value, str):
        if key is not None and (
            key.strip().casefold().endswith("_json")
            or key.strip().casefold() in _STRUCTURED_TRACE_STRING_KEYS
        ):
            return _redact_json_string(value)
        return _redact_urls(value)
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return _redact_urls(str(value))


def _redact_json_string(value: str) -> str:
    """Redact an explicitly structured JSON string without inspecting arbitrary prose."""

    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return _redact_urls(value)
    return json.dumps(redact(decoded), ensure_ascii=False, separators=(",", ":"))


def _redact_urls(value: str) -> str:
    return _URL_PATTERN.sub(_redact_url_match, value)


def _redact_url_match(match: re.Match[str]) -> str:
    candidate = match.group(0)
    suffix = ""
    while candidate and candidate[-1] in _URL_TRAILING_PUNCTUATION:
        suffix = candidate[-1] + suffix
        candidate = candidate[:-1]
    try:
        parsed = urlsplit(candidate)
        hostname = parsed.hostname
        if not hostname:
            return match.group(0)
        try:
            port = parsed.port
        except ValueError:
            return "[REDACTED_URL]" + suffix
        host = f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname
        netloc = host if port is None else f"{host}:{port}"
        query = urlencode(
            [
                (key, "[REDACTED]" if is_sensitive_key(key) else item)
                for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            ],
            doseq=True,
        )
        return urlunsplit((parsed.scheme, netloc, parsed.path, query, "")) + suffix
    except (TypeError, ValueError):
        return "[REDACTED_URL]" + suffix
