"""Persistence operations for private provider request and response traces."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from echo_masque.persistence.database import Database
from echo_masque.persistence.provider_trace_models import ProviderTraceRecord


class ProviderTraceRepository:
    """Store bounded provider trace events for Super Admin inspection."""

    def __init__(
        self,
        database: Database,
        *,
        retention_days: int = 7,
        maximum_records: int = 2000,
    ) -> None:
        self.database = database
        self.retention_days = max(1, min(retention_days, 90))
        self.maximum_records = max(100, min(maximum_records, 10000))

    def record_event(self, payload: dict[str, object]) -> None:
        trace_id = str(payload.get("trace_id", "")).strip()
        event = str(payload.get("event", "")).strip()
        if not trace_id or event not in {
            "provider.request",
            "provider.retry",
            "provider.response",
            "provider.error",
        }:
            return

        now = datetime.now(UTC)
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self.database.session() as session:
            record = session.get(ProviderTraceRecord, trace_id)
            if record is None:
                record = ProviderTraceRecord(trace_id=trace_id, created_at=now, updated_at=now)
                session.add(record)

            record.updated_at = now
            record.endpoint = str(payload.get("endpoint", record.endpoint or ""))
            record.trace_mode = str(payload.get("trace_mode", record.trace_mode or "summary"))

            if event == "provider.request":
                record.status = "pending"
                record.request_model = str(payload.get("model", ""))
                record.request_json = encoded
                self._prune(session, now=now)
            elif event == "provider.retry":
                retries = self._json_list(record.retries_json)
                retries.append(payload)
                record.retries_json = json.dumps(
                    retries[-20:], ensure_ascii=False, separators=(",", ":")
                )
            elif event == "provider.response":
                record.status = "succeeded"
                record.response_model = str(payload.get("response_model", ""))
                record.response_json = encoded
                record.status_code = self._optional_int(payload.get("status_code"))
                record.latency_ms = self._optional_int(payload.get("latency_ms"))
                record.input_tokens = self._optional_int(payload.get("input_tokens"))
                record.output_tokens = self._optional_int(payload.get("output_tokens"))
            else:
                record.status = "error"
                record.error_json = encoded
                record.status_code = self._optional_int(payload.get("status_code"))
                record.latency_ms = self._optional_int(payload.get("latency_ms"))

            session.commit()

    def list_traces(
        self,
        *,
        limit: int = 100,
        status: str | None = None,
        model: str | None = None,
        trace_id: str | None = None,
    ) -> list[ProviderTraceRecord]:
        bounded_limit = max(1, min(limit, 200))
        with self.database.session() as session:
            query = select(ProviderTraceRecord)
            if status:
                query = query.where(ProviderTraceRecord.status == status)
            if model:
                query = query.where(
                    func.lower(ProviderTraceRecord.request_model).contains(model.casefold())
                )
            if trace_id:
                query = query.where(ProviderTraceRecord.trace_id == trace_id)
            query = query.order_by(ProviderTraceRecord.created_at.desc()).limit(bounded_limit)
            return list(session.scalars(query))

    def clear(self) -> int:
        with self.database.session() as session:
            result = session.execute(delete(ProviderTraceRecord))
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)

    def _prune(self, session: Session, *, now: datetime) -> None:
        cutoff = now - timedelta(days=self.retention_days)
        session.execute(
            delete(ProviderTraceRecord).where(ProviderTraceRecord.created_at < cutoff)
        )
        excess_ids = list(
            session.scalars(
                select(ProviderTraceRecord.trace_id)
                .order_by(ProviderTraceRecord.created_at.desc())
                .offset(self.maximum_records)
            )
        )
        if excess_ids:
            session.execute(
                delete(ProviderTraceRecord).where(
                    ProviderTraceRecord.trace_id.in_(excess_ids)
                )
            )

    @staticmethod
    def _json_list(value: str) -> list[dict[str, object]]:
        try:
            decoded = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return []
        if not isinstance(decoded, list):
            return []
        return [item for item in decoded if isinstance(item, dict)]

    @staticmethod
    def _optional_int(value: object) -> int | None:
        return value if isinstance(value, int) and not isinstance(value, bool) else None
