import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import SecretStr

from echo_masque.condition_watch_runtime import (
    ConditionWatchEvaluatorRuntime,
    ConditionWatchReminderNotifier,
)
from echo_masque.condition_watch_service import ConditionWatchEvaluation
from echo_masque.credentials import CredentialStore
from echo_masque.persistence import (
    ConditionWatchRepository,
    Database,
    DeploymentRepository,
    DeploymentToolRepository,
    Repository,
    ScheduledReminderRepository,
)
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.models import CharacterCardRecord, TargetRecord
from echo_masque.providers import ChatMessage, ProviderCompletion
from echo_masque.targets import PromptModelConfig
from echo_masque.tool_runtime import default_tool_registry


class FakeCredentialStore(CredentialStore):
    def get(self, owner_id: str, character_card_id: str) -> SecretStr | None:
        if owner_id == "owner" and character_card_id == "character":
            return SecretStr("test-key")
        return None


class FakeProvider:
    async def complete(
        self,
        *,
        messages: tuple[ChatMessage, ...],
        model: str,
        temperature: float,
    ) -> ProviderCompletion:
        del messages, temperature
        return ProviderCompletion(
            text='[[CR_WATCH {"triggered":true,"summary":"fresh evidence matched"}]]',
            model=model,
            latency_ms=1,
        )


def seed(path: Path) -> Database:
    database = Database(f"sqlite:///{path}")
    database.initialize()
    config = PromptModelConfig(
        name="Watch Character",
        provider="custom",
        model="watch-model",
        system_prompt="Character system prompt",
        base_url="https://example.invalid",
        temperature=0.2,
    )
    with database.session() as session:
        session.add(
            TargetRecord(
                id="target",
                name="Watch Target",
                target_kind="prompt_model",
                config_json=config.model_dump_json(),
            )
        )
        session.flush()
        session.add(
            CharacterCardRecord(
                id="character",
                owner_id="owner",
                target_id="target",
                display_name="Watch Character",
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
                workspace_id="guild",
                workspace_name="Guild",
                channel_id="@server:guild",
                channel_name="All allowed channels",
                thread_id="",
                thread_name="",
                status="active",
            )
        )
        session.commit()
    return database


def test_evaluator_uses_character_model_configuration_and_parses_control_output(
    tmp_path: Path,
) -> None:
    database = seed(tmp_path / "watch-runtime.db")
    watches = ConditionWatchRepository(database)
    watch = watches.create(
        owner_id="owner",
        deployment_id="deployment",
        channel_id="actual-channel",
        thread_id="actual-thread",
        target_user_id="member-1",
        condition_text="The release is available",
        notification_text="The release is available now.",
        check_interval_seconds=300,
        expires_at=datetime.now(UTC) + timedelta(days=1),
        max_attempts=10,
    )
    evaluator = ConditionWatchEvaluatorRuntime(
        Repository(database),
        DeploymentRepository(database),
        DeploymentToolRepository(database),
        FakeCredentialStore(),
        default_tool_registry(),
        provider_factory=lambda _base_url, _api_key: FakeProvider(),
    )

    result = asyncio.run(evaluator(watch))
    assert result.triggered is True
    assert result.summary == "fresh evidence matched"


def test_evaluator_filters_background_capabilities_to_read_only_tools(tmp_path: Path) -> None:
    database = seed(tmp_path / "watch-readonly.db")
    evaluator = ConditionWatchEvaluatorRuntime(
        Repository(database),
        DeploymentRepository(database),
        DeploymentToolRepository(database),
        FakeCredentialStore(),
        default_tool_registry(),
        provider_factory=lambda _base_url, _api_key: FakeProvider(),
    )

    assert evaluator._read_only_tools(
        ("utility.calculator", "scheduler.remind", "discord.create_poll")
    ) == ("utility.calculator",)


def test_trigger_notifier_queues_delivery_to_original_concrete_destination(
    tmp_path: Path,
) -> None:
    database = seed(tmp_path / "watch-notifier.db")
    watches = ConditionWatchRepository(database)
    reminders = ScheduledReminderRepository(database)
    watch = watches.create(
        owner_id="owner",
        deployment_id="deployment",
        channel_id="actual-channel",
        thread_id="actual-thread",
        target_user_id="member-1",
        condition_text="The release is available",
        notification_text="The release is available now.",
        check_interval_seconds=300,
        expires_at=datetime.now(UTC) + timedelta(days=1),
        max_attempts=10,
    )
    notifier = ConditionWatchReminderNotifier(
        reminders,
        DeploymentRepository(database),
    )

    asyncio.run(
        notifier(
            watch,
            ConditionWatchEvaluation(triggered=True, summary="matched"),
        )
    )
    queued = reminders.list_for_deployment(
        owner_id="owner",
        deployment_id="deployment",
        include_finished=True,
    )
    assert len(queued) == 1
    assert queued[0].channel_id == "actual-channel"
    assert queued[0].thread_id == "actual-thread"
    assert queued[0].target_user_id == "member-1"
    assert queued[0].reminder_text == "The release is available now."
