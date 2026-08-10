"""HTTP views for Super Admin provider trace inspection."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel

from echo_masque.persistence.provider_trace_models import ProviderTraceRecord
from echo_masque.provider_trace_classification import (
    ProviderTraceCategory,
    provider_trace_category,
    provider_trace_media_input,
    provider_trace_tool_names,
)

TraceStatus = Literal["pending", "succeeded", "error"]


def _json_object(value: str) -> dict[str, object]:
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return cast(dict[str, object], decoded) if isinstance(decoded, dict) else {}


def _json_list(value: str) -> list[dict[str, object]]:
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(decoded, list):
        return []
    return [cast(dict[str, object], item) for item in decoded if isinstance(item, dict)]


def _scope_value(record: ProviderTraceRecord, key: str) -> str:
    for value in (record.request_json, record.response_json, record.error_json):
        candidate = _json_object(value).get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return ""


class ProviderTraceSummary(BaseModel):
    trace_id: str
    status: TraceStatus
    category: ProviderTraceCategory
    tool_names: list[str]
    media_input: dict[str, object]
    owner_id: str
    deployment_id: str
    character_card_id: str
    trace_mode: str
    endpoint: str
    request_model: str
    response_model: str
    status_code: int | None
    latency_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record: ProviderTraceRecord) -> ProviderTraceSummary:
        return cls(
            trace_id=record.trace_id,
            status=cast(TraceStatus, record.status),
            category=provider_trace_category(record.request_json, record.response_json),
            tool_names=provider_trace_tool_names(record.request_json, record.response_json),
            media_input=provider_trace_media_input(record.request_json),
            owner_id=_scope_value(record, "owner_id"),
            deployment_id=_scope_value(record, "deployment_id"),
            character_card_id=_scope_value(record, "character_card_id"),
            trace_mode=record.trace_mode,
            endpoint=record.endpoint,
            request_model=record.request_model,
            response_model=record.response_model,
            status_code=record.status_code,
            latency_ms=record.latency_ms,
            input_tokens=record.input_tokens,
            output_tokens=record.output_tokens,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


class ProviderTraceView(ProviderTraceSummary):
    request: dict[str, object]
    retries: list[dict[str, object]]
    response: dict[str, object]
    error: dict[str, object]

    @classmethod
    def from_record(cls, record: ProviderTraceRecord) -> ProviderTraceView:
        summary = ProviderTraceSummary.from_record(record)
        return cls(
            **summary.model_dump(),
            request=_json_object(record.request_json),
            retries=_json_list(record.retries_json),
            response=_json_object(record.response_json),
            error=_json_object(record.error_json),
        )


class ProviderTraceClearResult(BaseModel):
    deleted_count: int


class ProviderTraceAccessView(BaseModel):
    allowed: bool = True


class ProviderTracePage(BaseModel):
    items: list[ProviderTraceSummary]
    next_cursor: str | None
    has_more: bool
