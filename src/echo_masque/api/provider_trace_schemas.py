"""HTTP views for Super Admin provider trace inspection."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel

from echo_masque.persistence.provider_trace_models import ProviderTraceRecord

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


class ProviderTraceView(BaseModel):
    trace_id: str
    status: TraceStatus
    trace_mode: str
    endpoint: str
    request_model: str
    response_model: str
    request: dict[str, object]
    retries: list[dict[str, object]]
    response: dict[str, object]
    error: dict[str, object]
    status_code: int | None
    latency_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record: ProviderTraceRecord) -> ProviderTraceView:
        return cls(
            trace_id=record.trace_id,
            status=cast(TraceStatus, record.status),
            trace_mode=record.trace_mode,
            endpoint=record.endpoint,
            request_model=record.request_model,
            response_model=record.response_model,
            request=_json_object(record.request_json),
            retries=_json_list(record.retries_json),
            response=_json_object(record.response_json),
            error=_json_object(record.error_json),
            status_code=record.status_code,
            latency_ms=record.latency_ms,
            input_tokens=record.input_tokens,
            output_tokens=record.output_tokens,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


class ProviderTraceClearResult(BaseModel):
    deleted_count: int
