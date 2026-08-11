"""Stable, privacy-safe classification for Provider Trace Portal filtering."""

from __future__ import annotations

import json
from typing import Literal, cast

ProviderTraceCategory = Literal[
    "tool_calling",
    "character_turn",
    "media_attention",
    "media_understanding",
    "model_call",
]
_MEDIA_TRACE_MARKER = "[MEDIA_UNDERSTANDING]"
_MEDIA_ATTENTION_MARKER = "[MEDIA_ATTENTION]"
_MEDIA_ATTENTION_STANCES = {
    "neutral",
    "truthful",
    "bluff",
    "lie",
    "tease",
    "evasive",
    "guess",
    "uncertain",
}


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


def _embedded_json_object(value: str) -> dict[str, object]:
    """Parse one model-authored JSON object even when harmless prose surrounds it."""

    normalized = value.strip()
    if not normalized:
        return {}
    try:
        decoded = json.loads(normalized)
    except json.JSONDecodeError:
        start = normalized.find("{")
        if start < 0:
            return {}
        try:
            decoded, _ = json.JSONDecoder().raw_decode(normalized[start:])
        except json.JSONDecodeError:
            return {}
    return cast(dict[str, object], decoded) if isinstance(decoded, dict) else {}


def _bounded_string(value: object, maximum: int = 300) -> str:
    if not isinstance(value, str):
        return ""
    return value.replace("\x00", "").strip()[:maximum]


def provider_trace_media_input(request_json: str) -> dict[str, object]:
    """Return bounded media metadata embedded by the multimodal provider trace."""

    text = _request_text(_object(request_json)).strip()
    if not text.startswith(_MEDIA_TRACE_MARKER):
        return {}
    _, separator, payload = text.partition("\n")
    if not separator or not payload.strip():
        return {}
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    if not isinstance(decoded, dict):
        return {}
    allowed = {
        "operation",
        "media_type",
        "media_key",
        "filename",
        "mime_type",
        "size_bytes",
        "input_part_type",
        "source_host",
        "source_uri",
    }
    return {
        str(key): value
        for key, value in decoded.items()
        if str(key) in allowed
        and isinstance(value, (str, int, float, bool, type(None)))
    }


def provider_trace_media_attention(
    request_json: str,
    response_json: str,
) -> dict[str, object]:
    """Return the private watch/skip and declared stance from one attention provider call."""

    request = _object(request_json)
    if not _request_text(request).strip().startswith(_MEDIA_ATTENTION_MARKER):
        return {}
    response = _object(response_json)
    response_text = response.get("response_text")
    if not isinstance(response_text, str):
        # Metadata-only trace mode intentionally does not persist model-authored content.
        return {}
    decoded = _embedded_json_object(response_text)
    action = _bounded_string(decoded.get("action"), 20).casefold()
    if action not in {"watch", "skip"}:
        return {}
    result: dict[str, object] = {"action": action}
    reason = _bounded_string(decoded.get("reason"))
    if reason:
        result["reason"] = reason
    stance = _bounded_string(decoded.get("response_stance"), 30).casefold()
    if stance in _MEDIA_ATTENTION_STANCES:
        result["response_stance"] = stance
    stance_reason = _bounded_string(decoded.get("stance_reason"))
    if stance_reason:
        result["stance_reason"] = stance_reason
    return result


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
    text = _request_text(request).strip()
    if text.startswith(_MEDIA_ATTENTION_MARKER):
        return "media_attention"
    if provider_trace_media_input(request_json):
        return "media_understanding"

    roles = _string_list(request.get("message_roles"))
    tool_names = provider_trace_tool_names(request_json, response_json)
    if (
        tool_names
        or "tool" in roles
        or _positive_int(request.get("tool_result_count"))
    ):
        return "tool_calling"

    if (
        "real Discord group conversation through Character Relay" in text
        or "Return Smart Output now." in text
    ):
        return "character_turn"
    return "model_call"


__all__ = [
    "ProviderTraceCategory",
    "provider_trace_category",
    "provider_trace_media_attention",
    "provider_trace_media_input",
    "provider_trace_tool_names",
]
