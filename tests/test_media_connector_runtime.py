import asyncio
from types import SimpleNamespace
from typing import Any, cast

from echo_masque.live_media import LiveMediaContext, LiveMediaResult
from echo_masque.media_attention import MediaAttentionDecision
from echo_masque.media_connector_runtime import MediaAwareDiscordConnectorRuntime
from echo_masque.providers.errors import ProviderTimeoutError
from echo_masque.targets import PromptModelConfig, PromptModelTarget


class FakeLiveMediaService:
    def __init__(self, result: LiveMediaResult | None = None) -> None:
        self.calls = 0
        self.result = result or LiveMediaResult(
            status="completed",
            reason="ok",
            contexts=(
                LiveMediaContext(
                    source_key="sha256:abc",
                    kind="image",
                    label="cat.png",
                    summary="An orange cat is sitting on a laptop.",
                    visible_text="Build failed",
                    notable_details=("One paw is on the keyboard.",),
                ),
            ),
        )

    async def contexts_for_turn(self, **_: object) -> LiveMediaResult:
        self.calls += 1
        return self.result


class FakeAttentionDecider:
    def __init__(self, action: str, stance: str = "truthful") -> None:
        self.action = action
        self.stance = stance
        self.calls = 0

    async def decide(self, **_: object) -> MediaAttentionDecision:
        self.calls += 1
        return MediaAttentionDecision(
            action=cast(Any, self.action),
            reason=f"persona_{self.action}",
            response_stance=cast(Any, self.stance),
            stance_reason=f"persona_{self.stance}",
        )


class FakeDeploymentRepository:
    def __init__(self) -> None:
        self.errors: list[tuple[str, str]] = []
        self.updates: list[dict[str, object]] = []

    def record_deployment_error(self, deployment_id: str, message: str) -> None:
        self.errors.append((deployment_id, message))

    def update_deployment(
        self,
        deployment_id: str,
        owner_id: str,
        **values: object,
    ) -> object:
        self.updates.append(
            {"deployment_id": deployment_id, "owner_id": owner_id, **values}
        )
        return object()


class TimeoutProvider:
    async def complete(self, **_: object) -> object:
        raise ProviderTimeoutError("DeepSeek did not respond before timeout.")


def prompt_target(provider: object | None = None) -> PromptModelTarget:
    config = PromptModelConfig(
        name="Character",
        provider="test",
        model="test-model",
        system_prompt="Stay in character.",
        base_url="https://provider.test/v1",
    )
    return PromptModelTarget(
        config=config,
        provider=cast(Any, provider or object()),
        runtime_system_prompt="You are a selective, opinionated Character.",
    )


def prepared_turn(target: object | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        resolved=SimpleNamespace(
            deployment=SimpleNamespace(id="deployment-1", owner_id="owner-1"),
            card=SimpleNamespace(id="card-1"),
            target=target or object(),
            payload=SimpleNamespace(
                message_id="message-1",
                text="@Ann 看看这个 https://example.com/cat.png",
                attachments=[],
                embeds=[],
            ),
        ),
        prompt="Recent conversation:\nhello\nReturn Smart Output now.",
        enabled_tools=(),
    )


def runtime_for(
    service: FakeLiveMediaService,
    attention: FakeAttentionDecider | None = None,
    deployment_repository: object | None = None,
) -> MediaAwareDiscordConnectorRuntime:
    return MediaAwareDiscordConnectorRuntime(
        cast(Any, object()),
        cast(Any, deployment_repository or object()),
        cast(Any, object()),
        live_media_service=cast(Any, service),
        media_attention_decider=cast(Any, attention) if attention is not None else None,
    )


def trace_metadata(
    runtime: MediaAwareDiscordConnectorRuntime,
    prepared: SimpleNamespace,
) -> dict[str, str]:
    return dict(runtime.epistemic_trace_metadata(cast(Any, prepared)))


def test_media_context_is_injected_once_before_smart_output_instruction() -> None:
    service = FakeLiveMediaService()
    runtime = runtime_for(service)
    prepared = prepared_turn()

    async def run() -> None:
        await runtime._ensure_media_context(cast(Any, prepared))
        await runtime._ensure_media_context(cast(Any, prepared))

    asyncio.run(run())

    assert service.calls == 1
    assert "Character media perception for this turn:" in prepared.prompt
    assert "An orange cat is sitting on a laptop." in prepared.prompt
    assert "Visible/readable text: Build failed" in prepared.prompt
    assert "Do not default to a summary" in prepared.prompt
    assert prepared.prompt.endswith("Return Smart Output now.")
    assert prepared.prompt.index("Character media perception") < prepared.prompt.index(
        "Return Smart Output now."
    )


def test_character_can_skip_and_bluff_without_running_understanding() -> None:
    service = FakeLiveMediaService()
    attention = FakeAttentionDecider("skip", "bluff")
    runtime = runtime_for(service, attention)
    prepared = prepared_turn(prompt_target())

    asyncio.run(runtime._ensure_media_context(cast(Any, prepared)))

    assert attention.calls == 1
    assert service.calls == 0
    assert "actual_media_perception=skipped" in prepared.prompt
    assert "free to be honest, evasive, bluff, lie, tease" in prepared.prompt
    assert "Private media response stance for this turn: bluff" in prepared.prompt
    metadata = trace_metadata(runtime, prepared)
    assert metadata["actual_perception"] == "skipped"
    assert metadata["response_stance"] == "bluff"
    assert metadata["stance_grounding"] == "intentional_without_perception"
    assert metadata["media_context_count"] == "0"


def test_character_watch_runs_media_understanding_then_reacts_in_persona() -> None:
    service = FakeLiveMediaService()
    attention = FakeAttentionDecider("watch", "truthful")
    runtime = runtime_for(service, attention)
    prepared = prepared_turn(prompt_target())

    async def run() -> None:
        await runtime._ensure_media_context(cast(Any, prepared))
        await runtime._ensure_media_context(cast(Any, prepared))

    asyncio.run(run())

    assert attention.calls == 1
    assert service.calls == 1
    assert "actual_media_perception=perceived" in prepared.prompt
    assert "React from your own persona" in prepared.prompt
    assert "Do not default to a summary" in prepared.prompt
    metadata = trace_metadata(runtime, prepared)
    assert metadata["actual_perception"] == "perceived"
    assert metadata["response_stance"] == "truthful"
    assert metadata["stance_grounding"] == "grounded_in_perception"
    assert metadata["media_context_count"] == "1"


def test_failed_watch_records_unavailable_without_exposing_runtime_error_to_character() -> None:
    service = FakeLiveMediaService(
        LiveMediaResult(status="failed", reason="media_resolution_failed")
    )
    attention = FakeAttentionDecider("watch", "uncertain")
    runtime = runtime_for(service, attention)
    prepared = prepared_turn(prompt_target())

    asyncio.run(runtime._ensure_media_context(cast(Any, prepared)))

    assert service.calls == 1
    assert "actual_media_perception=unavailable" in prepared.prompt
    assert "no reliable content observations became available" in prepared.prompt
    assert "Do not turn this into a support-style message" in prepared.prompt
    assert "media_resolution_failed" not in prepared.prompt
    metadata = trace_metadata(runtime, prepared)
    assert metadata["actual_perception"] == "unavailable"
    assert metadata["response_stance"] == "uncertain"
    assert metadata["stance_grounding"] == "speculative_without_perception"
    assert metadata["media_result_reason"] == "media_resolution_failed"


def test_transient_provider_failure_returns_silent_control_without_disabling_deployment() -> None:
    service = FakeLiveMediaService()
    attention = FakeAttentionDecider("skip", "truthful")
    deployments = FakeDeploymentRepository()
    runtime = runtime_for(service, attention, deployments)
    prepared = prepared_turn(prompt_target(TimeoutProvider()))

    response = asyncio.run(runtime.invoke_character_model(cast(Any, prepared)))

    assert response.text == '[[CR_OUTPUT {"action":"ignore"}]]'
    assert response.trace["provider_failure"] == "provider_timeout"
    # Base Runtime records the exception first; the Media-aware production Runtime then
    # restores a transient provider failure to active turn health.
    assert deployments.errors == [
        ("deployment-1", "DeepSeek did not respond before timeout.")
    ]
    assert deployments.updates[-1]["status"] == "active"
    assert str(deployments.updates[-1]["last_error"]).startswith("provider_timeout:")
