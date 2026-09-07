import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from echo_masque.persistence.database import Database
from echo_masque.persistence.runtime_durability_models import (
    RuntimeOperationRecord,
    RuntimeSideEffectRecord,
    RuntimeStepRecord,
    RuntimeTraceEventRecord,
    RuntimeTraceRunRecord,
)
from echo_masque.persistence.runtime_durability_repository import DurableRuntimeRepository
from echo_masque.runtime_trace import RuntimeTraceEvent
from echo_masque.runtime_trace_buffer import BufferedRuntimeTraceSink


def test_diagnostics_batch_preserves_event_time_and_node_duration(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'trace.db'}")
    database.initialize()
    repository = DurableRuntimeRepository(database)
    sink = BufferedRuntimeTraceSink(repository)
    start = datetime.now(UTC)

    async def exercise() -> None:
        await sink.start()
        for status, when in [
            ("started", start),
            ("completed", start + timedelta(milliseconds=125)),
        ]:
            sink.emit(
                RuntimeTraceEvent(
                    trace_id="trace",
                    graph_run_id="graph",
                    graph_name="test",
                    node_name="tool",
                    node_kind="capability",
                    status=status,
                    occurred_at=when,
                )
            )
        await sink.stop()

    asyncio.run(exercise())
    with database.session() as session:
        events = list(
            session.scalars(select(RuntimeTraceEventRecord).order_by(RuntimeTraceEventRecord.id))
        )
        assert len(events) == 2
        assert ["duration_ms", "125"] in json.loads(events[-1].metadata_json)
        assert events[-1].created_at - events[0].created_at == timedelta(milliseconds=125)


def test_prune_preserves_unresolved_authority_and_cleans_settled_diagnostics(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{tmp_path / 'retention.db'}")
    database.initialize()
    old = datetime.now(UTC) - timedelta(days=10)
    with database.session() as session:
        for identifier, status in [
            ("active", "active"),
            ("uncertain", "uncertain"),
            ("settled", "completed"),
            ("failed-effect", "failed"),
        ]:
            session.add(
                RuntimeOperationRecord(operation_id=identifier, status=status, updated_at=old)
            )
            session.add(
                RuntimeTraceRunRecord(
                    graph_run_id=identifier,
                    operation_id=identifier,
                    graph_name="test",
                    status="completed",
                    created_at=old,
                    updated_at=old,
                )
            )
        session.add(
            RuntimeStepRecord(
                step_id="effect-step", operation_id="failed-effect", step_index=0, status="failed"
            )
        )
        session.add(
            RuntimeSideEffectRecord(
                idempotency_key="effect", step_id="effect-step", status="uncertain"
            )
        )
        session.commit()
    DurableRuntimeRepository(database).prune()
    with database.session() as session:
        assert session.get(RuntimeOperationRecord, "settled") is None
        assert session.get(RuntimeTraceRunRecord, "settled") is None
        for identifier in ("active", "uncertain", "failed-effect"):
            assert session.get(RuntimeOperationRecord, identifier) is not None
        assert session.get(RuntimeSideEffectRecord, "effect") is not None
        assert session.get(RuntimeTraceRunRecord, "active") is not None
        assert session.get(RuntimeTraceRunRecord, "uncertain") is not None
