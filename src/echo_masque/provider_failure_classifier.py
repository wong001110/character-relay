"""Semantic classification for heterogeneous provider error responses."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, Mapping

from echo_masque.provider_capabilities import ModelCapability

ProviderFailureKind = Literal[
    "rate_limited",
    "quota_exhausted",
    "free_tier_exhausted",
    "billing_required",
    "insufficient_balance",
    "authentication_invalid",
    "model_unavailable",
    "model_not_found",
    "capability_unsupported",
    "temporary_unavailable",
    "protocol_error",
]


@dataclass(frozen=True, slots=True)
class NormalizedProviderFailure:
    kind: ProviderFailureKind
    detail: str
    provider_code: str = ""
    capability: ModelCapability | None = None
    retryable: bool = False


def _json(value: str) -> object | None:
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def _strings(value: object) -> list[str]:
    results: list[str] = []
    if isinstance(value, str):
        compact = " ".join(value.split())
        if compact:
            results.append(compact)
    elif isinstance(value, dict):
        for key, item in value.items():
            if str(key).casefold() in {"message", "detail", "error", "errors", "code", "type", "status", "reason"}:
                results.extend(_strings(item))
            elif isinstance(item, (dict, list, tuple)):
                results.extend(_strings(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            results.extend(_strings(item))
    return results


def _error_envelope(parsed: object | None) -> bool:
    if not isinstance(parsed, dict):
        return False
    if "error" in parsed or "errors" in parsed:
        return True
    # Several OpenAI-compatible gateways return a 2xx object with only code/message/detail.
    return "choices" not in parsed and any(key in parsed for key in ("code", "message", "detail"))


def _provider_code(parsed: object | None) -> str:
    if not isinstance(parsed, dict):
        return ""
    candidates: list[object] = [parsed.get("code"), parsed.get("type")]
    error = parsed.get("error")
    if isinstance(error, dict):
        candidates.extend((error.get("code"), error.get("type"), error.get("status")))
    for value in candidates:
        if isinstance(value, (str, int)) and str(value).strip():
            return str(value).strip()[:120]
    return ""


def _requested_capability(text: str, requested: tuple[ModelCapability, ...]) -> ModelCapability | None:
    lowered = text.casefold()
    if any(token in lowered for token in ("tool", "function call", "function_call")) and "native_tool_calling" in requested:
        return "native_tool_calling"
    if any(token in lowered for token in ("json schema", "json_schema", "structured output")) and "json_schema" in requested:
        return "json_schema"
    if any(token in lowered for token in ("response_format", "json object", "json_object")):
        if "json_object" in requested:
            return "json_object"
        if "json_schema" in requested:
            return "json_schema"
    if any(token in lowered for token in ("video", "video_url")) and "video_url" in requested:
        return "video_url"
    if any(token in lowered for token in ("image", "vision", "multimodal")) and "image_input" in requested:
        return "image_input"
    if "data uri" in lowered and "data_uri_image" in requested:
        return "data_uri_image"
    return requested[0] if len(requested) == 1 else None


def classify_provider_response(
    *,
    status_code: int,
    body: str,
    headers: Mapping[str, str] | None = None,
    requested_capabilities: tuple[ModelCapability, ...] = (),
) -> NormalizedProviderFailure | None:
    """Classify both HTTP errors and 2xx error envelopes into stable semantics."""

    parsed = _json(body)
    if 200 <= status_code < 300 and not _error_envelope(parsed):
        return None

    fragments = _strings(parsed)
    if not fragments and body.strip():
        fragments.append(" ".join(body.split())[:1500])
    text = " | ".join(fragments).casefold()
    detail = (" | ".join(fragments) or f"HTTP {status_code}")[:500]
    code = _provider_code(parsed)
    code_text = code.casefold()
    header_text = " ".join(f"{key}:{value}" for key, value in (headers or {}).items()).casefold()
    combined = f"{text} {code_text} {header_text}"

    billing_markers = (
        "payment method",
        "payment required",
        "billing required",
        "enable billing",
        "billing account",
        "add payment",
        "upgrade your plan",
        "upgrade plan",
        "paid plan",
        "payment_method",
    )
    if status_code == 402 or any(marker in combined for marker in billing_markers):
        return NormalizedProviderFailure("billing_required", detail, code, retryable=False)

    balance_markers = (
        "insufficient balance",
        "insufficient credits",
        "insufficient credit",
        "insufficient funds",
        "credit balance",
        "not enough credits",
        "out of credits",
    )
    if any(marker in combined for marker in balance_markers):
        return NormalizedProviderFailure("insufficient_balance", detail, code, retryable=False)

    free_quota_markers = (
        "free quota",
        "free tier",
        "free-tier",
        "free credits",
        "free credit",
        "free allowance",
    )
    quota_markers = (
        "quota exceeded",
        "quota exhausted",
        "quota has been exceeded",
        "exceeded your quota",
        "usage limit reached",
        "daily limit reached",
        "monthly limit reached",
        "token quota",
        "request quota",
    )
    if any(marker in combined for marker in free_quota_markers) and any(
        marker in combined for marker in ("exceed", "exhaust", "limit", "used", "remaining")
    ):
        return NormalizedProviderFailure("free_tier_exhausted", detail, code, retryable=True)
    if any(marker in combined for marker in quota_markers):
        return NormalizedProviderFailure("quota_exhausted", detail, code, retryable=True)

    unsupported_markers = (
        "not supported",
        "does not support",
        "doesn't support",
        "unsupported",
        "not available for this model",
        "is unavailable for this model",
    )
    if any(marker in combined for marker in unsupported_markers):
        capability = _requested_capability(combined, requested_capabilities)
        if capability is not None:
            return NormalizedProviderFailure(
                "capability_unsupported",
                detail,
                code,
                capability=capability,
                retryable=False,
            )

    model_missing_markers = (
        "model not found",
        "unknown model",
        "no such model",
        "model does not exist",
        "invalid model",
    )
    if any(marker in combined for marker in model_missing_markers):
        return NormalizedProviderFailure("model_not_found", detail, code, retryable=False)

    model_unavailable_markers = (
        "model unavailable",
        "model is unavailable",
        "model is currently unavailable",
        "model overloaded",
        "model capacity",
    )
    if any(marker in combined for marker in model_unavailable_markers):
        return NormalizedProviderFailure("model_unavailable", detail, code, retryable=True)

    rate_markers = ("rate limit", "rate_limit", "too many requests", "request rate")
    if status_code == 429 or any(marker in combined for marker in rate_markers):
        return NormalizedProviderFailure("rate_limited", detail, code, retryable=True)

    auth_markers = (
        "invalid api key",
        "invalid token",
        "unauthorized",
        "authentication failed",
        "authentication required",
        "bad credentials",
    )
    if status_code == 401 or any(marker in combined for marker in auth_markers):
        return NormalizedProviderFailure("authentication_invalid", detail, code, retryable=False)
    if status_code == 403:
        return NormalizedProviderFailure("authentication_invalid", detail, code, retryable=False)

    if status_code >= 500:
        return NormalizedProviderFailure("temporary_unavailable", detail, code, retryable=True)

    if status_code >= 400 or _error_envelope(parsed):
        return NormalizedProviderFailure("protocol_error", detail, code, retryable=False)
    return None


__all__ = ["NormalizedProviderFailure", "ProviderFailureKind", "classify_provider_response"]
