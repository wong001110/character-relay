import asyncio
from types import SimpleNamespace
from typing import Any, cast

from echo_masque.live_media import LiveMediaContext, LiveMediaResult
from echo_masque.media_attention import MediaAttentionDecision
from echo_masque.media_connector_runtime import MediaAwareDiscordConnectorRuntime
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
    def __init__(self, action: str) -> None:
        self.action = action
        self.calls = 0

    async def decide(self, **_: object) -> MediaAttentionDecision:
        self.calls += 1
        return MediaAttentionDecision(
            action=cast(Any, self.action),
            reason=f"persona_{self.action}",
        )


def prompt_target() -> PromptModelTarget:
    config = PromptModelConfig(
        name="Character",
        provider="test",
        model="test-model",
        system_prompt="Stay in character.",
        base_url="https://provider.test/v1",
    )
    return PromptModelTarget(
        config=config,
        provider=cast(Any, object()),
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
    )


def runtime_for(
    service: FakeLiveMediaService,
    attention: FakeAttentionDecider | None = None,
) -> MediaAwareDiscordConnectorRuntime:
    return MediaAwareDiscordConnectorRuntime(
        cast(Any, object()),
        cast(Any, object()),
        cast(Any, object()),
        live_media_service=cast(Any, service),
        media_attention_decider=cast(Any, attention) if attention is not None else None,
    )


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


def test_character_can_skip_media_without_running_understanding() -> None:
    service = FakeLiveMediaService()
    attention = FakeAttentionDecider("skip")
    runtime = runtime_for(service, attention)
    prepared = prepared_turn(prompt_target())

    asyncio.run(runtime._ensure_media_context(cast(Any, prepared)))

    assert attention.calls == 1
    assert service.calls == 0
    assert "You chose not to open/watch/read" in prepared.prompt
    assert "technical limitations" in prepared.prompt
    assert "Character media perception for this turn:" not in prepared.prompt


def test_character_watch_runs_media_understanding_then_reacts_in_persona() -> None:
    service = FakeLiveMediaService()
    attention = FakeAttentionDecider("watch")
    runtime = runtime_for(service, attention)
    prepared = prepared_turn(prompt_target())

    async def run() -> None:
        await runtime._ensure_media_context(cast(Any, prepared))
        await runtime._ensure_media_context(cast(Any, prepared))

    asyncio.run(run())

    assert attention.calls == 1
    assert service.calls == 1
    assert "You chose to inspect/watch/read" in prepared.prompt
    assert "React from your own persona" in prepared.prompt
    assert "Do not default to a summary" in prepared.prompt


def test_failed_watch_does_not_turn_runtime_error_into_character_dialogue() -> None:
    service = FakeLiveMediaService(
        LiveMediaResult(status="failed", reason="media_resolution_failed")
    )
    attention = FakeAttentionDecider("watch")
    runtime = runtime_for(service, attention)
    prepared = prepared_turn(prompt_target())

    asyncio.run(runtime._ensure_media_context(cast(Any, prepared)))

    assert service.calls == 1
    assert "no reliable content observations are available" in prepared.prompt
    assert "Do not pretend you watched/read it" in prepared.prompt
    assert "Do not turn this into a support-style message" in prepared.prompt
    assert "media_resolution_failed" not in prepared.prompt
