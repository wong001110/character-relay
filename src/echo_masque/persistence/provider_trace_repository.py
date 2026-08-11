"""Persistence operations for private provider request and response traces."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from echo_masque.pagination import decode_time_cursor, encode_time_cursor
from echo_masque.persistence.database import Database
from echo_masque.persistence.provider_trace_models import (
    ProviderTraceIndexRecord,
    ProviderTraceRecord,
)
from echo_masque.provider_trace_classification import (
    ProviderTraceCategory,
    provider_trace_category,
    provider_trace_tool_names,
)


class ProviderTraceRepository:
    """Store bounded provider trace events for Super Admin inspection."""

    def __init__(
        self,
        database: Database,
        *,
        retention_days: int = 7,
        maximum_records: int = 2000,
        pending_timeout_seconds: int = 300,
    ) -> None:
        self.database = database
        self.retention_days = max(1, min(retention_days, 90))
        self.maximum_records = max(100, min(maximum_records, 10000))
        self.pending_timeout_seconds = max(60, min(pending_timeout_seconds, 3600))
        self._backfill_indexes()

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
                record.status = (
                    "error" if self._payload_has_failed_tool_result(payload) else "pending"
                )
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
                record.status = (
                    "error"
                    if self._request_has_failed_tool_result(record.request_json)
                    else "succeeded"
                )
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

            session.flush()
            self._sync_index(session, record)
            session.commit()

    def get_trace(self, trace_id: str) -> ProviderTraceRecord | None:
        with self.database.session() as session:
            self._reconcile_stale_pending(session, now=datetime.now(UTC))
            record = session.get(ProviderTraceRecord, trace_id)
            session.commit()
            return record

    def list_traces(
        self,
        *,
        limit: int = 100,
        status: str | None = None,
        model: str | None = None,
        trace_id: str | None = None,
        category: ProviderTraceCategory | None = None,
        owner_id: str | None = None,
    ) -> list[ProviderTraceRecord]:
        bounded_limit = max(1, min(limit, 200))
        with self.database.session() as session:
            self._reconcile_stale_pending(session, now=datetime.now(UTC))
            query = select(ProviderTraceRecord)
            query = self._apply_index_filters(
                query,
                owner_id=owner_id,
                category=category,
            )
            if status:
                query = query.where(ProviderTraceRecord.status == status)
            if model:
                query = query.where(
                    func.lower(ProviderTraceRecord.request_model).contains(model.casefold())
                )
            if trace_id:
                query = query.where(ProviderTraceRecord.trace_id == trace_id)
            query = query.order_by(ProviderTraceRecord.created_at.desc())
            records = list(session.scalars(query.limit(bounded_limit)))
            session.commit()
            return records

    def list_traces_page(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
        status: str | None = None,
        model: str | None = None,
        trace_id: str | None = None,
        category: ProviderTraceCategory | None = None,
        owner_id: str | None = None,
    ) -> tuple[list[ProviderTraceRecord], str | None]:
        bounded_limit = max(1, min(limit, 100))
        with self.database.session() as session:
            self._reconcile_stale_pending(session, now=datetime.now(UTC))
            query = select(ProviderTraceRecord)
            query = self._apply_index_filters(
                query,
                owner_id=owner_id,
                category=category,
            )
            if status:
                query = query.where(ProviderTraceRecord.status == status)
            if model:
                query = query.where(
                    func.lower(ProviderTraceRecord.request_model).contains(
                        model.casefold()
                    )
                )
            if trace_id:
                query = query.where(ProviderTraceRecord.trace_id == trace_id)
            if cursor:
                created_at, identifier = decode_time_cursor(cursor)
                query = query.where(
                    or_(
                        ProviderTraceRecord.created_at < created_at,
                        and_(
                            ProviderTraceRecord.created_at == created_at,
                            ProviderTraceRecord.trace_id < identifier,
                        ),
                    )
                )
            records = list(
                session.scalars(
                    query.order_by(
                        ProviderTraceRecord.created_at.desc(),
                        ProviderTraceRecord.trace_id.desc(),
                    ).limit(bounded_limit + 1)
                )
            )
            has_more = len(records) > bounded_limit
            items = records[:bounded_limit]
            next_cursor = (
                encode_time_cursor(items[-1].created_at, items[-1].trace_id)
                if has_more and items
                else None
            )
            session.commit()
            return items, next_cursor

    def clear(self, *, owner_id: str | None = None) -> int:
        with self.database.session() as session:
            if owner_id:
                trace_ids = list(
                    session.scalars(
                        select(ProviderTraceIndexRecord.trace_id).where(
                            ProviderTraceIndexRecord.owner_id == owner_id
                        )
                    )
                )
                if not trace_ids:
                    return 0
                session.execute(
                    delete(ProviderTraceIndexRecord).where(
                        ProviderTraceIndexRecord.trace_id.in_(trace_ids)
                    )
                )
                result = session.execute(
                    delete(ProviderTraceRecord).where(
                        ProviderTraceRecord.trace_id.in_(trace_ids)
                    )
                )
            else:
                session.execute(delete(ProviderTraceIndexRecord))
                result = session.execute(delete(ProviderTraceRecord))
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)

    @staticmethod
    def _apply_index_filters(
        query: Select[tuple[ProviderTraceRecord]],
        *,
        owner_id: str | None,
        category: ProviderTraceCategory | None,
    ) -> Select[tuple[ProviderTraceRecord]]:
        if owner_id is None and category is None:
            return query
        filtered = query.join(
            ProviderTraceIndexRecord,
            ProviderTraceIndexRecord.trace_id == ProviderTraceRecord.trace_id,
        )
        if owner_id is not None:
            filtered = filtered.where(ProviderTraceIndexRecord.owner_id == owner_id)
        if category is not None:
            filtered = filtered.where(ProviderTraceIndexRecord.category == category)
        return filtered

    def _backfill_indexes(self) -> None:
        with self.database.session() as session:
            self._reconcile_stale_pending(session, now=datetime.now(UTC))
            records = list(session.scalars(select(ProviderTraceRecord)))
            for record in records:
                if (
                    record.status != "error"
                    and self._request_has_failed_tool_result(record.request_json)
                ):
                    record.status = "error"
                self._sync_index(session, record)
            session.commit()

    def _reconcile_stale_pending(self, session: Session, *, now: datetime) -> int:
        cutoff = now - timedelta(seconds=self.pending_timeout_seconds)
        stale = list(
            session.scalars(
                select(ProviderTraceRecord).where(
                    ProviderTraceRecord.status == "pending",
                    ProviderTraceRecord.updated_at < cutoff,
                )
            )
        )
        if not stale:
            return 0
        for record in stale:
            started_at = self._as_utc(record.created_at)
            latency_ms = max(0, round((now - started_at).total_seconds() * 1000))
            payload: dict[str, object] = {
                "event": "provider.error",
                "trace_id": record.trace_id,
                "endpoint": record.endpoint,
                "model": record.request_model,
                "status_code": None,
                "reason": "trace_abandoned",
                "detail": (
                    "No terminal provider event was recorded before the trace deadline. "
                    "The request may have been cancelled, interrupted, disconnected, or "
                    "the runtime may have restarted while it was in flight."
                ),
                "latency_ms": latency_ms,
                "trace_mode": record.trace_mode,
                "owner_id": self._scope_value(record, "owner_id"),
                "deployment_id": self._scope_value(record, "deployment_id"),
                "character_card_id": self._scope_value(record, "character_card_id"),
            }
            record.status = "error"
            record.error_json = json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            record.latency_ms = latency_ms
            record.updated_at = now
            self._sync_index(session, record)
        session.flush()
        return len(stale)

    def _sync_index(self, session: Session, record: ProviderTraceRecord) -> None:
        index = session.get(ProviderTraceIndexRecord, record.trace_id)
        if index is None:
            index = ProviderTraceIndexRecord(trace_id=record.trace_id)
            session.add(index)
        index.owner_id = self._scope_value(record, "owner_id")
        index.deployment_id = self._scope_value(record, "deployment_id")
        index.character_card_id = self._scope_value(record, "character_card_id")
        index.category = provider_trace_category(record.request_json, record.response_json)
        index.tool_names_json = json.dumps(
            provider_trace_tool_names(record.request_json, record.response_json),
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @staticmethod
    def _scope_value(record: ProviderTraceRecord, key: str) -> str:
        for value in (record.request_json, record.response_json, record.error_json):
            try:
                decoded = json.loads(value)
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(decoded, dict):
                continue
            candidate = decoded.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return ""

    @classmethod
    def _request_has_failed_tool_result(cls, value: str) -> bool:
        try:
            decoded = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return False
        return isinstance(decoded, dict) and cls._payload_has_failed_tool_result(decoded)

    @classmethod
    def _payload_has_failed_tool_result(cls, payload: dict[str, object]) -> bool:
        latest = payload.get("latest_message")
        if (
            isinstance(latest, dict)
            and latest.get("role") == "tool"
            and cls._tool_content_failed(latest.get("content"))
        ):
            return True
        messages = payload.get("messages")
        if not isinstance(messages, list):
            return False
        return any(
            isinstance(message, dict)
            and message.get("role") == "tool"
            and cls._tool_content_failed(message.get("content"))
            for message in messages
        )

    @staticmethod
    def _tool_content_failed(content: object) -> bool:
        if not isinstance(content, str) or not content.strip():
            return False
        try:
            decoded = json.loads(content)
        except json.JSONDecodeError:
            return False
        if not isinstance(decoded, dict):
            return False
        if decoded.get("ok") is False:
            return True
        status = decoded.get("status")
        return isinstance(status, str) and status.casefold() in {"failed", "rejected", "error"}

    def _prune(self, session: Session, *, now: datetime) -> None:
        cutoff = now - timedelta(days=self.retention_days)
        expired_ids = list(
            session.scalars(
                select(ProviderTraceRecord.trace_id).where(
                    ProviderTraceRecord.created_at < cutoff
                )
            )
        )
        self._delete_ids(session, expired_ids)

        excess_ids = list(
            session.scalars(
                select(ProviderTraceRecord.trace_id)
                .order_by(ProviderTraceRecord.created_at.desc())
                .offset(self.maximum_records)
            )
        )
        self._delete_ids(session, excess_ids)

    @staticmethod
    def _delete_ids(session: Session, trace_ids: list[str]) -> None:
        if not trace_ids:
            return
        session.execute(
            delete(ProviderTraceIndexRecord).where(
                ProviderTraceIndexRecord.trace_id.in_(trace_ids)
            )
        )
        session.execute(
            delete(ProviderTraceRecord).where(ProviderTraceRecord.trace_id.in_(trace_ids))
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

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
