"""Privacy policy shared by Discord operational event writes, reads, and migrations."""

from __future__ import annotations

import json
import re
from typing import cast

from echo_masque.security import redact

DISCORD_OPERATIONAL_EVENT_MESSAGE = "Discord connector operational event."

_CONTENT_TOKENS = {
    "answer",
    "body",
    "completion",
    "content",
    "description",
    "detail",
    "error",
    "input",
    "message",
    "messages",
    "output",
    "payload",
    "preview",
    "prompt",
    "query",
    "raw",
    "request",
    "response",
    "text",
    "transcript",
}
_SAFE_STRING_SUFFIXES = (
    "_code",
    "_id",
    "_kind",
    "_mode",
    "_reason",
    "_source",
    "_status",
    "_type",
)


def sanitize_discord_event_details(value: object) -> object:
    """Recursively remove raw/content-bearing values from ordinary event details."""

    if isinstance(value, dict):
        sanitized: dict[str, object] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            normalized = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", key)
            normalized = normalized.casefold().replace("-", "_").replace(" ", "_")
            tokens = set(normalized.split("_"))
            content_bearing = bool(tokens & _CONTENT_TOKENS)
            structured_string = normalized.endswith(_SAFE_STRING_SUFFIXES)
            if (
                content_bearing
                and isinstance(item, (str, dict, list, tuple))
                and not structured_string
            ):
                continue
            sanitized[key] = sanitize_discord_event_details(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_discord_event_details(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_discord_event_details(item) for item in value]
    return value


def safe_discord_event_details(value: object) -> dict[str, object]:
    """Decode and sanitize one stored or inbound details object."""

    decoded: object = value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            decoded = {}
    source = decoded if isinstance(decoded, dict) else {}
    safe = redact(sanitize_discord_event_details(source))
    return cast(dict[str, object], safe) if isinstance(safe, dict) else {}


def safe_runtime_error_classification(error: Exception) -> str:
    """Return a bounded diagnostic classification without exception text."""

    reason_code = getattr(error, "reason_code", "")
    if isinstance(reason_code, str) and reason_code.strip():
        return reason_code.strip()[:120]
    return type(error).__name__[:120]


__all__ = [
    "DISCORD_OPERATIONAL_EVENT_MESSAGE",
    "safe_discord_event_details",
    "safe_runtime_error_classification",
    "sanitize_discord_event_details",
]
