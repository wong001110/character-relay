import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from echo_masque.persistence import (
    Database,
    DurableRuntimeRepository,
    RuntimeOperationRecord,
    RuntimeStepRecord,
)
from echo_masque.runtime_trace import RuntimeTraceEvent


def repository(path: Path) -> tuple[Database, DurableRuntimeRepository]:
    database = Database(f"sqlite:///{path}")
    database.initialize()
    return database, DurableRuntimeRepository(database)


def claim_operation(
    runtime: DurableRuntimeRepository, *, operation_id: str = "op" * 32
) -> RuntimeOperationRecord:
    return runtime.claim_social_operation(
        operation_id=operation_id,
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="",
        source_message_id="message-1",
        initial_deployment_ids=["ann", "zhi"],
        available_deployment_ids=["ann", "zhi", "ning"],
        continuation_budget=4,
        max_depth=2,
    )


def cursor_after_ann() -> str:
    return json.dumps(
        {
            "pending_turns": [
                {
                    "deployment_id": "zhi",
                    "origin": "selected",
                    "depth": 0,
                    "source_deployment_id": "",
                }
            ],
            "completed_deployment_ids": ["ann"],
            "continuation_budget_remaining": 4,
            "max_depth": 2,
            "step_index": 1,
        }
    )


def completed_cursor() -> str:
    return json.dumps(
        {
            "pending_turns": [],
            "completed_deployment_ids": ["ann"],
            "continuation_budget_remaining": 4,
            "max_depth": 2,
            "step_index": 1,
        }
    )


def test_social_operation_and_generation_are_idempotent(tmp_path: Path) -> None:
    _database, runtime = repository(tmp_path / "durable-operation.db")
    first = claim_operation(runtime)
    second = claim_operation(runtime)

    assert first.operation_id == second.operation_id
    assert second.resume_count == 1

    status, step = runtime.prepare_social_step(
        operation_id=first.operation_id,
        step_index=0,
        deployment_id="ann",
        request_hash="request-hash",
    )
    assert status == "execute"

    runtime.complete_social_step_generation(
        step_id=step.step_id,
        response_json='{"cached":true}',
        cursor_json=cursor_after_ann(),
        delivery_required=True,
    )
    replay_status, replay = runtime.prepare_social_step(
        operation_id=first.operation_id,
        step_index=0,
        deployment_id="ann",
        request_hash="request-hash",
    )

    assert replay_status == "replay"
    assert replay.step_id == step.step_id
    assert replay.response_json == '{"cached":true}'
    assert runtime.get_operation(first.operation_id).status == "awaiting_delivery"  # type: ignore[union-attr]


def test_normal_character_turn_identity_replays_without_request_text_hash(tmp_path: Path) -> None:
    _database, runtime = repository(tmp_path / "durable-character-turn.db")
    first = runtime.claim_character_operation(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="thread-1",
        source_message_id="message-1",
        deployment_id="ann",
    )
    repeated = runtime.claim_character_operation(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="thread-1",
        source_message_id="message-1",
        deployment_id="ann",
    )
    assert first.operation_kind == "character_turn"
    assert first.operation_id == repeated.operation_id

    status, step = runtime.prepare_character_step(
        operation_id=first.operation_id,
        deployment_id="ann",
    )
    assert status == "execute"
    runtime.complete_social_step_generation(
        step_id=step.step_id,
        response_json='{"action":"reply","text":"cached"}',
        cursor_json='{"pending_turns":[]}',
        delivery_required=True,
    )
    replay_status, replay = runtime.prepare_character_step(
        operation_id=first.operation_id,
        deployment_id="ann",
    )
    assert replay_status == "replay"
    assert replay.step_id == step.step_id
    assert replay.response_json == '{"action":"reply","text":"cached"}'

    claim, _ = runtime.claim_delivery(
        operation_id=first.operation_id,
        step_id=step.step_id,
        claim_nonce="character-claim-0001",
    )
    assert claim == "granted"
    restarted = DurableRuntimeRepository(runtime.database)
    assert restarted.get_operation(first.operation_id).status == "uncertain"  # type: ignore[union-attr]


def test_normal_character_delivery_ack_is_idempotent_and_completes(tmp_path: Path) -> None:
    _database, runtime = repository(tmp_path / "durable-character-delivery.db")
    operation = runtime.claim_character_operation(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="",
        source_message_id="message-2",
        deployment_id="ann",
    )
    _, step = runtime.prepare_character_step(
        operation_id=operation.operation_id,
        deployment_id="ann",
    )
    runtime.complete_social_step_generation(
        step_id=step.step_id,
        response_json='{"action":"reply"}',
        cursor_json='{"pending_turns":[]}',
        delivery_required=True,
    )
    runtime.claim_delivery(
        operation_id=operation.operation_id,
        step_id=step.step_id,
        claim_nonce="character-claim-0002",
    )
    completed = runtime.acknowledge_character_delivery(
        operation_id=operation.operation_id,
        step_id=step.step_id,
        claim_nonce="character-claim-0002",
        sent_message_ids=["discord-message-2"],
    )
    assert completed.status == "completed"
    replay = runtime.acknowledge_character_delivery(
        operation_id=operation.operation_id,
        step_id=step.step_id,
        claim_nonce="character-claim-0002",
        sent_message_ids=["discord-message-2"],
    )
    assert replay.status == "completed"
    claim_status, _ = runtime.claim_delivery(
        operation_id=operation.operation_id,
        step_id=step.step_id,
        claim_nonce="another-character-claim",
    )
    assert claim_status == "already_delivered"


def test_normal_character_generation_restart_becomes_uncertain(tmp_path: Path) -> None:
    database, runtime = repository(tmp_path / "durable-character-generation-restart.db")
    operation = runtime.claim_character_operation(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="",
        source_message_id="message-restart",
        deployment_id="ann",
    )
    _, step = runtime.prepare_character_step(
        operation_id=operation.operation_id,
        deployment_id="ann",
    )

    restarted = DurableRuntimeRepository(database)
    assert restarted.get_operation(operation.operation_id).status == "uncertain"  # type: ignore[union-attr]
    with pytest.raises(RuntimeError, match="reconciliation"):
        restarted.prepare_character_step(
            operation_id=operation.operation_id,
            deployment_id="ann",
        )
    assert step.step_id


def test_concurrent_character_operation_claim_reuses_identity(tmp_path: Path) -> None:
    _database, runtime = repository(tmp_path / "durable-character-concurrent.db")

    def claim() -> str:
        return runtime.claim_character_operation(
            owner_id="owner-1",
            connection_id="connection-1",
            guild_id="guild-1",
            channel_id="channel-1",
            thread_id="",
            source_message_id="message-concurrent",
            deployment_id="ann",
        ).operation_id

    with ThreadPoolExecutor(max_workers=2) as executor:
        operation_ids = list(executor.map(lambda _: claim(), range(2)))

    assert operation_ids[0] == operation_ids[1]


def test_delivery_claim_ack_advances_and_scrubs_payloads(tmp_path: Path) -> None:
    database, runtime = repository(tmp_path / "durable-delivery.db")
    operation = runtime.claim_social_operation(
        operation_id="delivery".ljust(64, "0"),
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="",
        source_message_id="message-2",
        initial_deployment_ids=["ann"],
        available_deployment_ids=["ann"],
        continuation_budget=2,
        max_depth=1,
    )
    _, step = runtime.prepare_social_step(
        operation_id=operation.operation_id,
        step_index=0,
        deployment_id="ann",
        request_hash="delivery-hash",
    )
    runtime.complete_social_step_generation(
        step_id=step.step_id,
        response_json='{"reply":"temporary"}',
        cursor_json=completed_cursor(),
        delivery_required=True,
    )

    claim_status, _ = runtime.claim_delivery(
        operation_id=operation.operation_id,
        step_id=step.step_id,
        claim_nonce="claim-nonce-0001",
    )
    assert claim_status == "granted"

    completed = runtime.acknowledge_delivery(
        operation_id=operation.operation_id,
        step_id=step.step_id,
        claim_nonce="claim-nonce-0001",
        cursor_json=completed_cursor(),
        sent_message_ids=["discord-message-1"],
        outgoing_text="temporary visible text",
        applied=False,
        deployment_id="ann",
    )
    assert completed.status == "completed"
    assert completed.sources_json == "[]"

    runtime.mark_delivery_uncertain(
        operation_id=operation.operation_id,
        step_id=step.step_id,
        claim_nonce="claim-nonce-0001",
        error="lost ack response",
    )
    assert runtime.get_operation(operation.operation_id).status == "completed"  # type: ignore[union-attr]

    with database.session() as session:
        persisted = session.get(RuntimeStepRecord, step.step_id)
        assert persisted is not None
        assert persisted.status == "delivered"
        assert persisted.response_json == "{}"
        assert persisted.outgoing_text == ""
        assert json.loads(persisted.sent_message_ids_json) == ["discord-message-1"]


def test_restart_after_delivery_claim_becomes_uncertain_instead_of_resending(
    tmp_path: Path,
) -> None:
    database, runtime = repository(tmp_path / "durable-restart.db")
    operation = runtime.claim_social_operation(
        operation_id="restart".ljust(64, "0"),
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="",
        source_message_id="message-3",
        initial_deployment_ids=["ann"],
        available_deployment_ids=["ann"],
        continuation_budget=2,
        max_depth=1,
    )
    _, step = runtime.prepare_social_step(
        operation_id=operation.operation_id,
        step_index=0,
        deployment_id="ann",
        request_hash="restart-hash",
    )
    runtime.complete_social_step_generation(
        step_id=step.step_id,
        response_json='{"reply":"cached"}',
        cursor_json=completed_cursor(),
        delivery_required=True,
    )
    runtime.claim_delivery(
        operation_id=operation.operation_id,
        step_id=step.step_id,
        claim_nonce="claim-nonce-0002",
    )

    restarted = DurableRuntimeRepository(database)
    recovered = restarted.get_operation(operation.operation_id)
    assert recovered is not None
    assert recovered.status == "uncertain"
    assert "delivery_claim" in recovered.last_error
    assert restarted.pending_social_operations(connection_id="connection-1") == []

    with database.session() as session:
        persisted = session.get(RuntimeStepRecord, step.step_id)
        assert persisted is not None
        assert persisted.status == "uncertain"


def test_side_effect_ledger_replays_completed_and_blocks_uncertain(tmp_path: Path) -> None:
    database, runtime = repository(tmp_path / "durable-side-effects.db")
    operation = claim_operation(runtime, operation_id="effects".ljust(64, "0"))
    step_id = runtime.social_step_id(operation.operation_id, 0, "ann")

    claim, key, _, _ = runtime.claim_side_effect(
        operation_id=operation.operation_id,
        step_id=step_id,
        deployment_id="ann",
        tool_id="scheduler.remind",
        arguments_hash="args-1",
    )
    assert claim == "granted"
    runtime.complete_side_effect(
        idempotency_key=key,
        content='{"ok":true,"id":"reminder-1"}',
        trace={"tool_id": "scheduler.remind", "status": "completed"},
    )
    replay, replay_key, content, trace = runtime.claim_side_effect(
        operation_id=operation.operation_id,
        step_id=step_id,
        deployment_id="ann",
        tool_id="scheduler.remind",
        arguments_hash="args-1",
    )
    assert replay == "replay"
    assert replay_key == key
    assert "reminder-1" in content
    assert trace["status"] == "completed"

    changed_arguments, changed_key, _, _ = runtime.claim_side_effect(
        operation_id=operation.operation_id,
        step_id=step_id,
        deployment_id="ann",
        tool_id="scheduler.remind",
        arguments_hash="args-changed-after-crash",
    )
    assert changed_arguments == "uncertain"
    assert changed_key == key

    changed_tool, changed_tool_key, _, _ = runtime.claim_side_effect(
        operation_id=operation.operation_id,
        step_id=step_id,
        deployment_id="ann",
        tool_id="watch.condition",
        arguments_hash="args-2",
    )
    assert changed_tool == "uncertain"
    assert changed_tool_key == key

    other_step_id = runtime.social_step_id(operation.operation_id, 1, "ann")
    pending, uncertain_key, _, _ = runtime.claim_side_effect(
        operation_id=operation.operation_id,
        step_id=other_step_id,
        deployment_id="ann",
        tool_id="watch.condition",
        arguments_hash="args-2",
    )
    assert pending == "granted"

    restarted = DurableRuntimeRepository(database)
    uncertain, same_key, _, _ = restarted.claim_side_effect(
        operation_id=operation.operation_id,
        step_id=other_step_id,
        deployment_id="ann",
        tool_id="watch.condition",
        arguments_hash="args-2",
    )
    assert uncertain == "uncertain"
    assert same_key == uncertain_key


def test_runtime_trace_events_persist_privacy_safe_run_summary(tmp_path: Path) -> None:
    _database, runtime = repository(tmp_path / "durable-trace.db")
    common = {
        "trace_id": "trace-1",
        "graph_run_id": "graph-run-1",
        "graph_name": "character_turn",
        "operation_id": "operation-1",
        "owner_id": "owner-1",
        "deployment_id": "ann",
        "character_card_id": "ann-card",
    }
    runtime.emit(
        RuntimeTraceEvent(
            **common,
            node_name="turn_model",
            node_kind="agentic",
            status="completed",
            changed_keys=("model_status",),
            metadata=(("next", "smart_output"),),
        )
    )
    runtime.emit(
        RuntimeTraceEvent(
            **common,
            node_name="turn_authority",
            node_kind="authority",
            status="completed",
            changed_keys=("authority_status",),
            metadata=(("action", "reply"),),
        )
    )

    record = runtime.get_trace_run("graph-run-1")
    assert record is not None
    assert record.status == "completed"
    assert record.event_count == 2
    assert record.operation_id == "operation-1"
    assert record.owner_id == "owner-1"
    assert record.deployment_id == "ann"
    events = runtime.trace_events("graph-run-1")
    assert [event.node_name for event in events] == ["turn_model", "turn_authority"]
    assert "secret" not in repr(events).lower()

    page, cursor = runtime.list_trace_runs_page(limit=10, operation_id="operation-1")
    assert [item.graph_run_id for item in page] == ["graph-run-1"]
    assert cursor is None


def test_operation_identity_cannot_be_rebound_to_another_discord_event(tmp_path: Path) -> None:
    _database, runtime = repository(tmp_path / "durable-identity.db")
    operation = claim_operation(runtime, operation_id="identity".ljust(64, "0"))

    try:
        runtime.claim_social_operation(
            operation_id=operation.operation_id,
            owner_id="owner-1",
            connection_id="connection-1",
            guild_id="guild-1",
            channel_id="other-channel",
            thread_id="",
            source_message_id="message-1",
            initial_deployment_ids=["ann"],
            available_deployment_ids=["ann"],
            continuation_budget=1,
            max_depth=1,
        )
    except ValueError as exc:
        assert "identity" in str(exc).lower()
    else:
        raise AssertionError("Operation identity was unexpectedly rebound.")

    with runtime.database.session() as session:
        persisted = session.get(RuntimeOperationRecord, operation.operation_id)
        assert persisted is not None
        assert persisted.channel_id == "channel-1"


def test_early_silent_character_trace_is_completed(tmp_path: Path) -> None:
    _database, runtime = repository(tmp_path / "durable-early-silent-trace.db")
    runtime.emit(
        RuntimeTraceEvent(
            trace_id="trace-silent",
            graph_run_id="graph-run-silent",
            graph_name="character_turn",
            node_name="turn_resolve",
            node_kind="decision",
            status="completed",
            deployment_id="ann",
            changed_keys=("resolve_status", "status", "outcome", "deployment_id"),
            metadata=(("result", "trigger_not_matched"),),
        )
    )
    record = runtime.get_trace_run("graph-run-silent")
    assert record is not None
    assert record.status == "completed"
