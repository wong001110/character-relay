"""Stable, privacy-safe classification for Provider Trace Portal filtering."""

from __future__ import annotations

import json
from typing import Literal, cast

ProviderTraceCategory = Literal["tool_calling", "character_turn", "model_call"]


def _object(value: str) -> dict[str, object]:
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return cast(dict[str, object], decoded) if isinstance(decoded, dict) else {}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _request_text(request: dict[str, object]) -> str:
    latest = request.get("latest_message")
    if isinstance(latest, dict):
        content = latest.get("content")
        if isinstance(content, str):
            return content
    messages = request.get("messages")
    if isinstance(messages, list):
        parts: list[str] = []
        for item in messages:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if isinstance(content, str):
                parts.append(content)
        return "\n".join(parts)
    return ""


def provider_trace_tool_names(request_json: str, response_json: str) -> list[str]:
    request = _object(request_json)
    response = _object(response_json)
    names: list[str] = []
    for source in (
        response.get("tool_call_names"),
        request.get("prior_tool_call_names"),
    ):
        for name in _string_list(source):
            if name not in names:
                names.append(name)
    return names


def provider_trace_category(request_json: str, response_json: str) -> ProviderTraceCategory:
    request = _object(request_json)
    response = _object(response_json)
    roles = _string_list(request.get("message_roles"))
    tool_names = provider_trace_tool_names(request_json, response_json)
    if (
        tool_names
        or "tool" in roles
        or _positive_int(request.get("tool_result_count"))
    ):
        return "tool_calling"

    text = _request_text(request)
    if (
        "real Discord group conversation through Character Relay" in text
        or "Return Smart Output now." in text
    ):
        return "character_turn"
    return "model_call"


__all__ = [
    "ProviderTraceCategory",
    "provider_trace_category",
    "provider_trace_tool_names",
]
