import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from echo_masque.condition_watch_service import ConditionWatchEvaluation
from echo_masque.orchestration import ConditionWatchGraphRunner, RuntimeTraceEvent
from echo_masque.persistence import ConditionWatchRepository, Database
from echo_masque.persistence.condition_watch_models import ConditionWatchRecord
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.models import CharacterCardRecord, TargetRecord


@dataclass
class MemoryTraceSink:
    events: list[RuntimeTraceEvent] = field(default_factory=list)

    def emit(self, event: RuntimeTraceEvent) -> None:
        self.events.append(event)


def seeded_repository(path: Path) -> ConditionWatchRepository:
    database = Database(f"sqlite:///{path}")
    database.initialize()
    with database.session() as session:
        session.add(TargetRecord(id="target", name="Target", target_kind="prompt_model"))
        session.flush()
        session.add(
            CharacterCardRecord(
                id="character",
                owner_id="owner",
                target_id="target",
                display_name="Character",
            )
        )
        session.flush()
        session.add(
            CharacterDeploymentRecord(
                id="deployment",
                owner_id="owner",
                character_card_id="character",
                connection_id="connection",
                platform="discord",
                channel_id="channel",
                channel_name="general",
            )
        )
        session.commit()
    return ConditionWatchRepository(database)


def claimed_watch(
    repository: ConditionWatchRepository,
    *,
    max_attempts: int = 3,
) -> ConditionWatchRecord:
    now = datetime.now(UTC)
    repository.create(
        owner_id="owner",
        deployment_id="deployment",
        channel_id="channel",
        condition_text="The result is available",
        notification_text="The result is available now.",
        check_interval_seconds=300,
        expires_at=now + timedelta(hours=1),
        max_attempts=max_attempts,
        next_check_at=now - timedelta(seconds=1),
    )
    records = repository.claim_due(limit=1)
    assert len(records) == 1
    return records[0]


def test_graph_marks_triggered_only_after_notification(tmp_path: Path) -> None:
    repository = seeded_repository(tmp_path / "graph-trigger.db")
    watch = claimed_watch(repository)
    notified: list[str] = []

    async def evaluator(_record: ConditionWatchRecord) -> ConditionWatchEvaluation:
        return ConditionWatchEvaluation(triggered=True, summary="matched")

    async def notifier(
        record: ConditionWatchRecord,
        _evaluation: ConditionWatchEvaluation,
    ) -> None:
        notified.append(record.id)

    runner = ConditionWatchGraphRunner(
        repository,
        evaluator=evaluator,
        notifier=notifier,
    )
    result = asyncio.run(runner.run(watch))

    stored = repository.get(owner_id="owner", watch_id=watch.id)
    assert stored is not None
    assert stored.status == "triggered"
    assert result["outcome"] == "triggered"
    assert result["status"] == "completed"
    assert notified == [watch.id]


def test_graph_marks_unmet_watch_with_existing_attempt_policy(tmp_path: Path) -> None:
    repository = seeded_repository(tmp_path / "graph-unmet.db")
    watch = claimed_watch(repository, max_attempts=1)

    async def evaluator(_record: ConditionWatchRecord) -> ConditionWatchEvaluation:
        return ConditionWatchEvaluation(triggered=False, summary="not yet")

    async def notifier(
        _record: ConditionWatchRecord,
        _evaluation: ConditionWatchEvaluation,
    ) -> None:
        raise AssertionError("notifier must not run for an unmet condition")

    runner = ConditionWatchGraphRunner(
        repository,
        evaluator=evaluator,
        notifier=notifier,
    )
    result = asyncio.run(runner.run(watch))

    stored = repository.get(owner_id="owner", watch_id=watch.id)
    assert stored is not None
    assert stored.status == "expired"
    assert result["outcome"] == "not_met"
    assert result["status"] == "completed"


def test_graph_persists_evaluation_failure(tmp_path: Path) -> None:
    repository = seeded_repository(tmp_path / "graph-evaluation-failure.db")
    watch = claimed_watch(repository, max_attempts=1)

    async def evaluator(_record: ConditionWatchRecord) -> ConditionWatchEvaluation:
        raise RuntimeError("provider unavailable")

    async def notifier(
        _record: ConditionWatchRecord,
        _evaluation: ConditionWatchEvaluation,
    ) -> None:
        raise AssertionError("notifier must not run after evaluator failure")

    runner = ConditionWatchGraphRunner(
        repository,
        evaluator=evaluator,
        notifier=notifier,
    )
    result = asyncio.run(runner.run(watch))

    stored = repository.get(owner_id="owner", watch_id=watch.id)
    assert stored is not None
    assert stored.status == "failed"
    assert "provider unavailable" in stored.last_error
    assert result["outcome"] == "failed"
    assert result["status"] == "failed"


def test_graph_persists_notification_failure(tmp_path: Path) -> None:
    repository = seeded_repository(tmp_path / "graph-notification-failure.db")
    watch = claimed_watch(repository, max_attempts=1)

    async def evaluator(_record: ConditionWatchRecord) -> ConditionWatchEvaluation:
        return ConditionWatchEvaluation(triggered=True, summary="matched")

    async def notifier(
        _record: ConditionWatchRecord,
        _evaluation: ConditionWatchEvaluation,
    ) -> None:
        raise RuntimeError("delivery unavailable")

    runner = ConditionWatchGraphRunner(
        repository,
        evaluator=evaluator,
        notifier=notifier,
    )
    result = asyncio.run(runner.run(watch))

    stored = repository.get(owner_id="owner", watch_id=watch.id)
    assert stored is not None
    assert stored.status == "failed"
    assert "delivery unavailable" in stored.last_error
    assert result["outcome"] == "failed"


def test_graph_trace_omits_evaluation_summary(tmp_path: Path) -> None:
    repository = seeded_repository(tmp_path / "graph-trace.db")
    watch = claimed_watch(repository)
    sink = MemoryTraceSink()
    secret_summary = "private evidence should not enter graph trace"

    async def evaluator(_record: ConditionWatchRecord) -> ConditionWatchEvaluation:
        return ConditionWatchEvaluation(triggered=False, summary=secret_summary)

    async def notifier(
        _record: ConditionWatchRecord,
        _evaluation: ConditionWatchEvaluation,
    ) -> None:
        raise AssertionError("notifier must not run")

    runner = ConditionWatchGraphRunner(
        repository,
        evaluator=evaluator,
        notifier=notifier,
        trace_sink=sink,
    )
    asyncio.run(runner.run(watch))

    assert [event.node_name for event in sink.events] == [
        "watch_evaluate",
        "watch_evaluate",
        "watch_mark_not_met",
        "watch_mark_not_met",
    ]
    assert all(secret_summary not in repr(event) for event in sink.events)
    assert sink.events[-1].metadata == (("business_transition", "not_met"),)
