import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from echo_masque.condition_watch_service import (
    ConditionWatchEvaluation,
    ConditionWatchService,
)
from echo_masque.persistence import ConditionWatchRepository, Database
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.models import CharacterCardRecord, TargetRecord


def seeded_repository(path: Path) -> ConditionWatchRepository:
    database = Database(f"sqlite:///{path}")
    database.initialize()
    with database.session() as session:
        session.add(TargetRecord(id="target", name="Target", target_kind="prompt_model"))
        session.add(
            CharacterCardRecord(
                id="character",
                owner_id="owner",
                target_id="target",
                display_name="Character",
            )
        )
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


def create_due(repository: ConditionWatchRepository, *, max_attempts: int = 3) -> str:
    now = datetime.now(UTC)
    record = repository.create(
        owner_id="owner",
        deployment_id="deployment",
        condition_text="The result is available",
        notification_text="The result is available now.",
        check_interval_seconds=300,
        expires_at=now + timedelta(hours=1),
        max_attempts=max_attempts,
        next_check_at=now - timedelta(seconds=1),
    )
    return record.id


def test_service_marks_watch_triggered_only_after_notifier_succeeds(tmp_path: Path) -> None:
    repository = seeded_repository(tmp_path / "trigger.db")
    watch_id = create_due(repository)
    notified: list[str] = []

    async def evaluator(_record):
        return ConditionWatchEvaluation(triggered=True, summary="matched")

    async def notifier(record, _evaluation):
        notified.append(record.id)

    service = ConditionWatchService(
        repository,
        evaluator=evaluator,
        notifier=notifier,
    )
    assert asyncio.run(service.run_once()) == 1
    stored = repository.get(owner_id="owner", watch_id=watch_id)
    assert stored is not None
    assert stored.status == "triggered"
    assert notified == [watch_id]


def test_service_keeps_unmet_watch_active_until_attempt_budget_is_exhausted(
    tmp_path: Path,
) -> None:
    repository = seeded_repository(tmp_path / "unmet.db")
    watch_id = create_due(repository, max_attempts=1)

    async def evaluator(_record):
        return ConditionWatchEvaluation(triggered=False, summary="not yet")

    async def notifier(_record, _evaluation):
        raise AssertionError("notifier must not run for an unmet condition")

    service = ConditionWatchService(
        repository,
        evaluator=evaluator,
        notifier=notifier,
    )
    asyncio.run(service.run_once())
    stored = repository.get(owner_id="owner", watch_id=watch_id)
    assert stored is not None
    assert stored.status == "expired"


def test_service_persists_delivery_failure(tmp_path: Path) -> None:
    repository = seeded_repository(tmp_path / "failure.db")
    watch_id = create_due(repository, max_attempts=1)

    async def evaluator(_record):
        return ConditionWatchEvaluation(triggered=True, summary="matched")

    async def notifier(_record, _evaluation):
        raise RuntimeError("delivery unavailable")

    service = ConditionWatchService(
        repository,
        evaluator=evaluator,
        notifier=notifier,
    )
    asyncio.run(service.run_once())
    stored = repository.get(owner_id="owner", watch_id=watch_id)
    assert stored is not None
    assert stored.status == "failed"
    assert "delivery unavailable" in stored.last_error
