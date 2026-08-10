"""Durable operation, side-effect idempotency, and Runtime Trace persistence."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import and_, delete, or_, select

from echo_masque.pagination import decode_time_cursor, encode_time_cursor
from echo_masque.persistence.database import Database
from echo_masque.persistence.runtime_durability_models import (
    RuntimeOperationRecord,
    RuntimeSideEffectRecord,
    RuntimeStepRecord,
    RuntimeTraceEventRecord,
    RuntimeTraceRunRecord,
)
from echo_masque.runtime_trace import RuntimeTraceEvent

OperationStatus = Literal["active", "awaiting_delivery", "completed", "uncertain", "failed"]
SideEffectClaimStatus = Literal["granted", "replay", "uncertain"]
DeliveryClaimStatus = Literal["granted", "already_delivered", "uncertain"]
StepPreparationStatus = Literal["execute", "replay", "in_progress", "uncertain"]


class DurableRuntimeRepository:
    """Business checkpoint authority for delivery-delimited LangGraph workflows.

    Raw prompts and provider payloads are never stored here. A generated platform reply is kept
    only while a step is waiting for Discord delivery; delivery acknowledgement scrubs it.
    """

    def __init__(
        self,
        database: Database,
        *,
        retention_days: int = 7,
        maximum_trace_runs: int = 5000,
    ) -> None:
        self.database = database
        self.retention_days = max(1, min(retention_days, 30))
        self.maximum_trace_runs = max(200, min(maximum_trace_runs, 20000))
        self.recover_interrupted()
        self.prune()

    @staticmethod
    def _json(value: object) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _object(value: str) -> dict[str, object]:
        try:
            decoded = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return {}
        return decoded if isinstance(decoded, dict) else {}

    @staticmethod
    def _list(value: str) -> list[object]:
        try:
            decoded = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return []
        return decoded if isinstance(decoded, list) else []

    @staticmethod
    def stable_hash(*parts: object) -> str:
        payload = "\x1f".join(str(item) for item in parts)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def social_step_id(cls, operation_id: str, step_index: int, deployment_id: str) -> str:
        return cls.stable_hash("social-step-v1", operation_id, step_index, deployment_id)

    @staticmethod
    def initial_cursor(
        initial_deployment_ids: list[str],
        *,
        continuation_budget: int,
        max_depth: int,
    ) -> dict[str, object]:
        unique = list(
            dict.fromkeys(item.strip() for item in initial_deployment_ids if item.strip())
        )
        return {
            "pending_turns": [
                {
                    "deployment_id": item,
                    "origin": "selected",
                    "depth": 0,
                    "source_deployment_id": "",
                }
                for item in unique
            ],
            "completed_deployment_ids": [],
            "continuation_budget_remaining": continuation_budget,
            "max_depth": max_depth,
            "step_index": 0,
        }

    def claim_social_operation(
        self,
        *,
        operation_id: str,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
        source_message_id: str,
        initial_deployment_ids: list[str],
        available_deployment_ids: list[str],
        continuation_budget: int,
        max_depth: int,
    ) -> RuntimeOperationRecord:
        now = datetime.now(UTC)
        with self.database.session() as session:
            record = session.get(RuntimeOperationRecord, operation_id)
            if record is None:
                cursor = self.initial_cursor(
                    initial_deployment_ids,
                    continuation_budget=continuation_budget,
                    max_depth=max_depth,
                )
                record = RuntimeOperationRecord(
                    operation_id=operation_id,
                    operation_kind="social_turn",
                    owner_id=owner_id,
                    connection_id=connection_id,
                    guild_id=guild_id,
                    channel_id=channel_id,
                    thread_id=thread_id,
                    source_message_id=source_message_id,
                    status="active",
                    initial_deployment_ids_json=self._json(initial_deployment_ids),
                    available_deployment_ids_json=self._json(available_deployment_ids),
                    cursor_json=self._json(cursor),
                    sources_json="[]",
                    continuation_budget=continuation_budget,
                    max_depth=max_depth,
                    created_at=now,
                    updated_at=now,
                )
                session.add(record)
                session.commit()
                session.refresh(record)
                return record

            identity = (
                record.connection_id,
                record.guild_id,
                record.channel_id,
                record.thread_id,
                record.source_message_id,
            )
            supplied = (connection_id, guild_id, channel_id, thread_id, source_message_id)
            if identity != supplied:
                raise ValueError(
                    "Runtime operation identity does not match its original Discord event."
                )
            if record.owner_id and owner_id and record.owner_id != owner_id:
                raise ValueError("Runtime operation owner does not match the selected deployment.")
            if record.status in {"active", "awaiting_delivery"}:
                record.resume_count += 1
                record.updated_at = now
                session.commit()
                session.refresh(record)
            return record

    def pending_social_operations(
        self,
        *,
        connection_id: str,
        limit: int = 20,
    ) -> list[RuntimeOperationRecord]:
        with self.database.session() as session:
            query = (
                select(RuntimeOperationRecord)
                .where(
                    RuntimeOperationRecord.connection_id == connection_id,
                    RuntimeOperationRecord.operation_kind == "social_turn",
                    RuntimeOperationRecord.status.in_(["active", "awaiting_delivery"]),
                )
                .order_by(RuntimeOperationRecord.updated_at.asc())
                .limit(max(1, min(limit, 100)))
            )
            return list(session.scalars(query))

    def get_operation(self, operation_id: str) -> RuntimeOperationRecord | None:
        with self.database.session() as session:
            return session.get(RuntimeOperationRecord, operation_id)

    def prepare_social_step(
        self,
        *,
        operation_id: str,
        step_index: int,
        deployment_id: str,
        request_hash: str,
    ) -> tuple[StepPreparationStatus, RuntimeStepRecord]:
        step_id = self.social_step_id(operation_id, step_index, deployment_id)
        now = datetime.now(UTC)
        with self.database.session() as session:
            operation = session.get(RuntimeOperationRecord, operation_id)
            if operation is None:
                raise ValueError("Durable Social Turn operation has not been claimed.")
            if operation.status == "completed":
                raise ValueError("Durable Social Turn operation is already completed.")
            if operation.status == "uncertain":
                raise RuntimeError(
                    "Durable Social Turn operation requires delivery reconciliation."
                )

            step = session.get(RuntimeStepRecord, step_id)
            if step is None:
                step = RuntimeStepRecord(
                    step_id=step_id,
                    operation_id=operation_id,
                    step_index=step_index,
                    deployment_id=deployment_id,
                    status="generating",
                    request_hash=request_hash,
                    created_at=now,
                    updated_at=now,
                )
                session.add(step)
                session.commit()
                session.refresh(step)
                return "execute", step

            if step.request_hash != request_hash:
                raise ValueError(
                    "Durable Social Turn retry does not match the original step request."
                )
            if step.status in {"generated", "delivery_claimed", "silent"} and step.response_json:
                return "replay", step
            if step.status == "generating":
                return "in_progress", step
            if step.status == "uncertain":
                return "uncertain", step
            if step.status == "failed":
                step.status = "generating"
                step.last_error = ""
                step.updated_at = now
                session.commit()
                session.refresh(step)
                return "execute", step
            if step.status == "delivered" and step.response_json:
                return "replay", step
            raise ValueError("Durable Social Turn step cannot be executed from its current state.")

    def fail_social_step(self, step_id: str, error: str) -> None:
        with self.database.session() as session:
            step = session.get(RuntimeStepRecord, step_id)
            if step is None:
                return
            step.status = "failed"
            step.last_error = error[:1000]
            step.updated_at = datetime.now(UTC)
            operation = session.get(RuntimeOperationRecord, step.operation_id)
            if operation is not None and operation.status not in {"completed", "uncertain"}:
                operation.status = "active"
                operation.last_error = error[:1000]
            session.commit()

    def complete_social_step_generation(
        self,
        *,
        step_id: str,
        response_json: str,
        cursor_json: str,
        delivery_required: bool,
    ) -> RuntimeStepRecord:
        now = datetime.now(UTC)
        with self.database.session() as session:
            step = session.get(RuntimeStepRecord, step_id)
            if step is None:
                raise KeyError("Durable Social Turn step not found.")
            operation = session.get(RuntimeOperationRecord, step.operation_id)
            if operation is None:
                raise KeyError("Durable Social Turn operation not found.")
            step.response_json = response_json
            step.cursor_json = cursor_json
            step.status = "generated" if delivery_required else "silent"
            step.updated_at = now
            if delivery_required:
                operation.status = "awaiting_delivery"
            else:
                self._advance_operation(session, operation, cursor_json=cursor_json, now=now)
            operation.last_error = ""
            session.commit()
            session.refresh(step)
            return step

    def claim_delivery(
        self,
        *,
        operation_id: str,
        step_id: str,
        claim_nonce: str,
    ) -> tuple[DeliveryClaimStatus, RuntimeStepRecord]:
        now = datetime.now(UTC)
        with self.database.session() as session:
            step = session.get(RuntimeStepRecord, step_id)
            if step is None or step.operation_id != operation_id:
                raise KeyError("Durable delivery step not found.")
            operation = session.get(RuntimeOperationRecord, operation_id)
            if operation is None:
                raise KeyError("Durable Social Turn operation not found.")
            if step.status == "generated":
                step.status = "delivery_claimed"
                step.delivery_claim_nonce = claim_nonce
                step.updated_at = now
                session.commit()
                session.refresh(step)
                return "granted", step
            if step.status == "delivery_claimed":
                if step.delivery_claim_nonce == claim_nonce:
                    return "granted", step
                step.status = "uncertain"
                step.last_error = "delivery_claim_lost_before_ack"
                operation.status = "uncertain"
                operation.last_error = step.last_error
                operation.updated_at = now
                session.commit()
                session.refresh(step)
                return "uncertain", step
            if step.status in {"delivered", "silent"}:
                return "already_delivered", step
            if step.status == "uncertain" or operation.status == "uncertain":
                return "uncertain", step
            raise ValueError("Durable delivery cannot be claimed from the current step state.")

    def acknowledge_delivery(
        self,
        *,
        operation_id: str,
        step_id: str,
        claim_nonce: str,
        cursor_json: str,
        sent_message_ids: list[str],
        outgoing_text: str,
        applied: bool,
        deployment_id: str,
    ) -> RuntimeOperationRecord:
        now = datetime.now(UTC)
        with self.database.session() as session:
            step = session.get(RuntimeStepRecord, step_id)
            operation = session.get(RuntimeOperationRecord, operation_id)
            if step is None or operation is None or step.operation_id != operation_id:
                raise KeyError("Durable delivery operation was not found.")
            if step.status == "delivered":
                return operation
            if step.status != "delivery_claimed" or step.delivery_claim_nonce != claim_nonce:
                raise ValueError("Durable delivery acknowledgement does not own the active claim.")

            step.status = "delivered"
            step.sent_message_ids_json = self._json(sent_message_ids)
            step.outgoing_text = outgoing_text
            step.applied = applied
            step.delivered_at = now
            step.updated_at = now
            self._record_source(
                operation,
                deployment_id=deployment_id,
                text=outgoing_text,
                sent_message_ids=sent_message_ids,
            )
            self._advance_operation(session, operation, cursor_json=cursor_json, now=now)
            step.response_json = "{}"
            self._scrub_side_effect_payloads(session, step_id)
            if operation.status == "completed":
                operation.sources_json = "[]"
            session.commit()
            session.refresh(operation)
            return operation

    def mark_delivery_uncertain(
        self,
        *,
        operation_id: str,
        step_id: str,
        claim_nonce: str,
        error: str,
    ) -> None:
        with self.database.session() as session:
            step = session.get(RuntimeStepRecord, step_id)
            operation = session.get(RuntimeOperationRecord, operation_id)
            if step is None or operation is None:
                return
            if step.status == "delivered" or operation.status == "completed":
                return
            if step.delivery_claim_nonce and step.delivery_claim_nonce != claim_nonce:
                return
            step.status = "uncertain"
            step.last_error = error[:1000]
            operation.status = "uncertain"
            operation.last_error = error[:1000]
            now = datetime.now(UTC)
            step.updated_at = now
            operation.updated_at = now
            session.commit()

    def _advance_operation(
        self,
        session: object,
        operation: RuntimeOperationRecord,
        *,
        cursor_json: str,
        now: datetime,
    ) -> None:
        operation.cursor_json = cursor_json
        operation.updated_at = now
        cursor = self._object(cursor_json)
        pending = cursor.get("pending_turns")
        if isinstance(pending, list) and not pending:
            operation.status = "completed"
            operation.completed_at = now
            self._scrub_completed_operation(session, operation.operation_id)
        else:
            operation.status = "active"

    def _record_source(
        self,
        operation: RuntimeOperationRecord,
        *,
        deployment_id: str,
        text: str,
        sent_message_ids: list[str],
    ) -> None:
        sources = [item for item in self._list(operation.sources_json) if isinstance(item, dict)]
        sources = [item for item in sources if item.get("deployment_id") != deployment_id]
        sources.append(
            {
                "deployment_id": deployment_id,
                "text": text,
                "sent_message_ids": sent_message_ids,
            }
        )
        operation.sources_json = self._json(sources[-12:])

    def claim_side_effect(
        self,
        *,
        operation_id: str,
        step_id: str,
        deployment_id: str,
        tool_id: str,
        arguments_hash: str,
    ) -> tuple[SideEffectClaimStatus, str, str, dict[str, object]]:
        key = self.stable_hash(
            "tool-side-effect-slot-v2",
            operation_id,
            step_id,
            deployment_id,
        )
        with self.database.session() as session:
            record = session.get(RuntimeSideEffectRecord, key)
            if record is None:
                record = RuntimeSideEffectRecord(
                    idempotency_key=key,
                    operation_id=operation_id,
                    step_id=step_id,
                    deployment_id=deployment_id,
                    tool_id=tool_id,
                    arguments_hash=arguments_hash,
                    status="claimed",
                )
                session.add(record)
                session.commit()
                return "granted", key, "", {}
            if record.tool_id != tool_id or record.arguments_hash != arguments_hash:
                return "uncertain", key, "", {}
            if record.status == "completed":
                return "replay", key, record.content, self._object(record.trace_json)
            return "uncertain", key, "", {}

    def complete_side_effect(
        self,
        *,
        idempotency_key: str,
        content: str,
        trace: dict[str, object],
    ) -> None:
        with self.database.session() as session:
            record = session.get(RuntimeSideEffectRecord, idempotency_key)
            if record is None:
                return
            record.status = "completed"
            record.content = content
            record.trace_json = self._json(trace)
            record.updated_at = datetime.now(UTC)
            session.commit()

    def recover_interrupted(self) -> dict[str, int]:
        """Make process-restart semantics explicit instead of silently redoing side effects."""

        recovered = {"generation": 0, "delivery_uncertain": 0, "side_effect_uncertain": 0}
        now = datetime.now(UTC)
        with self.database.session() as session:
            generating = list(
                session.scalars(
                    select(RuntimeStepRecord).where(RuntimeStepRecord.status == "generating")
                )
            )
            for step in generating:
                step.status = "failed"
                step.last_error = "process_restarted_during_generation"
                step.updated_at = now
                recovered["generation"] += 1

            claimed_deliveries = list(
                session.scalars(
                    select(RuntimeStepRecord).where(RuntimeStepRecord.status == "delivery_claimed")
                )
            )
            for step in claimed_deliveries:
                step.status = "uncertain"
                step.last_error = "process_restarted_after_delivery_claim_before_ack"
                operation = session.get(RuntimeOperationRecord, step.operation_id)
                if operation is not None and operation.status != "completed":
                    operation.status = "uncertain"
                    operation.last_error = step.last_error
                    operation.updated_at = now
                recovered["delivery_uncertain"] += 1

            side_effects = list(
                session.scalars(
                    select(RuntimeSideEffectRecord).where(
                        RuntimeSideEffectRecord.status == "claimed"
                    )
                )
            )
            for item in side_effects:
                item.status = "uncertain"
                item.updated_at = now
                recovered["side_effect_uncertain"] += 1
            session.commit()
        return recovered

    def _scrub_side_effect_payloads(self, session: object, step_id: str) -> None:
        from sqlalchemy.orm import Session

        scoped = session if isinstance(session, Session) else None
        if scoped is None:
            return
        records = list(
            scoped.scalars(
                select(RuntimeSideEffectRecord).where(RuntimeSideEffectRecord.step_id == step_id)
            )
        )
        for item in records:
            item.content = ""
            item.trace_json = "{}"

    def _scrub_completed_operation(self, session: object, operation_id: str) -> None:
        from sqlalchemy.orm import Session

        scoped = session if isinstance(session, Session) else None
        if scoped is None:
            return
        steps = list(
            scoped.scalars(
                select(RuntimeStepRecord).where(RuntimeStepRecord.operation_id == operation_id)
            )
        )
        for step in steps:
            if step.status in {"delivered", "silent"}:
                step.response_json = "{}"
                step.outgoing_text = ""
                self._scrub_side_effect_payloads(scoped, step.step_id)

    def emit(self, event: RuntimeTraceEvent) -> None:
        """Persist only the privacy-safe RuntimeTraceEvent contract."""

        graph_run_id = event.graph_run_id.strip()
        if not graph_run_id:
            return
        now = datetime.now(UTC)
        with self.database.session() as session:
            run = session.get(RuntimeTraceRunRecord, graph_run_id)
            if run is None:
                run = RuntimeTraceRunRecord(
                    graph_run_id=graph_run_id,
                    trace_id=event.trace_id,
                    operation_id=event.operation_id,
                    graph_name=event.graph_name,
                    status="running",
                    owner_id=event.owner_id,
                    deployment_id=event.deployment_id,
                    character_card_id=event.character_card_id,
                    event_count=0,
                    created_at=now,
                    updated_at=now,
                )
                session.add(run)
            run.trace_id = event.trace_id or run.trace_id
            run.operation_id = event.operation_id or run.operation_id
            run.graph_name = event.graph_name or run.graph_name
            run.owner_id = event.owner_id or run.owner_id
            run.deployment_id = event.deployment_id or run.deployment_id
            run.character_card_id = event.character_card_id or run.character_card_id
            run.last_node = event.node_name
            run.event_count = (run.event_count or 0) + 1
            run.updated_at = now
            if event.status == "failed":
                run.status = "failed"
                run.error = event.error[:1000]
            elif self._final_completed_event(event):
                run.status = "completed"

            session.add(
                RuntimeTraceEventRecord(
                    graph_run_id=graph_run_id,
                    trace_id=event.trace_id,
                    operation_id=event.operation_id,
                    graph_name=event.graph_name,
                    node_name=event.node_name,
                    node_kind=event.node_kind,
                    status=event.status,
                    changed_keys_json=self._json(list(event.changed_keys)),
                    metadata_json=self._json([list(item) for item in event.metadata]),
                    error=event.error[:1000],
                    created_at=now,
                )
            )
            session.commit()

    @staticmethod
    def _final_completed_event(event: RuntimeTraceEvent) -> bool:
        if event.status != "completed":
            return False
        if event.node_name == "turn_resolve":
            return any(key == "result" for key, _value in event.metadata)
        return event.node_name in {
            "turn_authority",
            "social_continuation_authority",
            "watch_mark_not_met",
            "watch_mark_triggered",
            "watch_mark_failure",
        }

    def get_trace_run(self, graph_run_id: str) -> RuntimeTraceRunRecord | None:
        with self.database.session() as session:
            return session.get(RuntimeTraceRunRecord, graph_run_id)

    def trace_events(self, graph_run_id: str) -> list[RuntimeTraceEventRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(RuntimeTraceEventRecord)
                    .where(RuntimeTraceEventRecord.graph_run_id == graph_run_id)
                    .order_by(RuntimeTraceEventRecord.id.asc())
                )
            )

    def list_trace_runs_page(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
        graph_name: str | None = None,
        status: str | None = None,
        operation_id: str | None = None,
        owner_id: str | None = None,
    ) -> tuple[list[RuntimeTraceRunRecord], str | None]:
        bounded = max(1, min(limit, 100))
        with self.database.session() as session:
            query = select(RuntimeTraceRunRecord)
            if graph_name:
                query = query.where(RuntimeTraceRunRecord.graph_name == graph_name)
            if status:
                query = query.where(RuntimeTraceRunRecord.status == status)
            if operation_id:
                query = query.where(RuntimeTraceRunRecord.operation_id == operation_id)
            if owner_id:
                query = query.where(RuntimeTraceRunRecord.owner_id == owner_id)
            if cursor:
                created_at, identifier = decode_time_cursor(cursor)
                query = query.where(
                    or_(
                        RuntimeTraceRunRecord.created_at < created_at,
                        and_(
                            RuntimeTraceRunRecord.created_at == created_at,
                            RuntimeTraceRunRecord.graph_run_id < identifier,
                        ),
                    )
                )
            records = list(
                session.scalars(
                    query.order_by(
                        RuntimeTraceRunRecord.created_at.desc(),
                        RuntimeTraceRunRecord.graph_run_id.desc(),
                    ).limit(bounded + 1)
                )
            )
            items = records[:bounded]
            next_cursor = (
                encode_time_cursor(items[-1].created_at, items[-1].graph_run_id)
                if len(records) > bounded and items
                else None
            )
            return items, next_cursor

    def clear_traces(self, *, owner_id: str | None = None) -> int:
        with self.database.session() as session:
            query = select(RuntimeTraceRunRecord.graph_run_id)
            if owner_id:
                query = query.where(RuntimeTraceRunRecord.owner_id == owner_id)
            ids = list(session.scalars(query))
            if not ids:
                return 0
            session.execute(
                delete(RuntimeTraceEventRecord).where(RuntimeTraceEventRecord.graph_run_id.in_(ids))
            )
            result = session.execute(
                delete(RuntimeTraceRunRecord).where(RuntimeTraceRunRecord.graph_run_id.in_(ids))
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)

    def prune(self) -> None:
        cutoff = datetime.now(UTC) - timedelta(days=self.retention_days)
        with self.database.session() as session:
            old_operation_ids = list(
                session.scalars(
                    select(RuntimeOperationRecord.operation_id).where(
                        RuntimeOperationRecord.updated_at < cutoff,
                        RuntimeOperationRecord.status.in_(["completed", "failed", "uncertain"]),
                    )
                )
            )
            if old_operation_ids:
                step_ids = list(
                    session.scalars(
                        select(RuntimeStepRecord.step_id).where(
                            RuntimeStepRecord.operation_id.in_(old_operation_ids)
                        )
                    )
                )
                if step_ids:
                    session.execute(
                        delete(RuntimeSideEffectRecord).where(
                            RuntimeSideEffectRecord.step_id.in_(step_ids)
                        )
                    )
                session.execute(
                    delete(RuntimeStepRecord).where(
                        RuntimeStepRecord.operation_id.in_(old_operation_ids)
                    )
                )
                session.execute(
                    delete(RuntimeOperationRecord).where(
                        RuntimeOperationRecord.operation_id.in_(old_operation_ids)
                    )
                )

            trace_ids = list(
                session.scalars(
                    select(RuntimeTraceRunRecord.graph_run_id).where(
                        RuntimeTraceRunRecord.created_at < cutoff
                    )
                )
            )
            excess = list(
                session.scalars(
                    select(RuntimeTraceRunRecord.graph_run_id)
                    .order_by(RuntimeTraceRunRecord.created_at.desc())
                    .offset(self.maximum_trace_runs)
                )
            )
            remove = list(dict.fromkeys([*trace_ids, *excess]))
            if remove:
                session.execute(
                    delete(RuntimeTraceEventRecord).where(
                        RuntimeTraceEventRecord.graph_run_id.in_(remove)
                    )
                )
                session.execute(
                    delete(RuntimeTraceRunRecord).where(
                        RuntimeTraceRunRecord.graph_run_id.in_(remove)
                    )
                )
            session.commit()
