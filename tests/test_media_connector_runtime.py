import asyncio
import json
from types import SimpleNamespace
from typing import Any, cast

from echo_masque.api.connector_schemas import (
    DiscordAttachmentContent,
    DiscordEmbedContent,
    DiscordInboundMessage,
)
from echo_masque.live_media import LiveMediaContext, LiveMediaResult
from echo_masque.media_connector_runtime import MediaAwareDiscordConnectorRuntime
from echo_masque.media_tools import MediaToolRegistry
from echo_masque.providers import (
    ChatMessage,
    ChatToolCall,
    ChatToolDefinition,
    ChatToolFunctionCall,
    ProviderCompletion,
)
from echo_masque.providers.errors import ProviderTimeoutError
from echo_masque.targets import PromptModelConfig, PromptModelTarget
from echo_masque.tool_runtime import ToolExecutionContext


class FakeLiveMediaService:
    def __init__(self, result: LiveMediaResult | None = None) -> None:
        self.calls = 0
        self.payload_message_ids: list[str] = []
        self.result = result or LiveMediaResult(
            status="completed",
            reason="ok",
            contexts=(
                LiveMediaContext(
                    source_key="bilibili:test",
                    kind="video",
                    label="Shared video",
                    summary="A short comedy clip about a game character.",
                    visible_text="旅行者: 我是爷们",
                    notable_details=("The clip is presented as a meme.",),
                ),
            ),
        )

    async def contexts_for_turn(self, **values: object) -> LiveMediaResult:
        self.calls += 1
        payload = values.get("payload")
        if isinstance(payload, DiscordInboundMessage):
            self.payload_message_ids.append(payload.message_id)
        return self.result


class FakeConversationMediaService:
    def __init__(self) -> None:
        self.remembered_message_ids: list[str] = []

    def resolve_for_turn(self, **_: object) -> tuple[object, ...]:
        return ()

    def guidance(self, _: object) -> tuple[str, ...]:
        return ()

    def remember_perceived(self, **values: object) -> None:
        payload = values.get("payload")
        if isinstance(payload, DiscordInboundMessage):
            self.remembered_message_ids.append(payload.message_id)


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
        self.updates.append({"deployment_id": deployment_id, "owner_id": owner_id, **values})
        return object()


class SkipMediaProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.seen_tools: list[str] = []

    async def complete(self, **_: object) -> ProviderCompletion:
        raise AssertionError("Tool-capable media turn should use complete_with_tools.")

    async def complete_with_tools(
        self,
        *,
        messages: tuple[ChatMessage, ...],
        model: str,
        temperature: float,
        tools: tuple[ChatToolDefinition, ...],
    ) -> ProviderCompletion:
        del messages, temperature
        self.calls += 1
        self.seen_tools = [item.function.name for item in tools]
        return ProviderCompletion(
            text='[[CR_OUTPUT {"action":"ignore"}]]',
            model=model,
            latency_ms=5,
            finish_reason="stop",
        )


class InspectMediaProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.seen_tool_result = ""

    async def complete(self, **_: object) -> ProviderCompletion:
        raise AssertionError("Media inspection should remain inside the bounded Tool loop.")

    async def complete_with_tools(
        self,
        *,
        messages: tuple[ChatMessage, ...],
        model: str,
        temperature: float,
        tools: tuple[ChatToolDefinition, ...],
    ) -> ProviderCompletion:
        del temperature
        self.calls += 1
        assert "media_inspect" in [item.function.name for item in tools]
        if self.calls == 1:
            return ProviderCompletion(
                text="",
                model=model,
                latency_ms=4,
                finish_reason="tool_calls",
                tool_calls=(
                    ChatToolCall(
                        id="call-media",
                        function=ChatToolFunctionCall(
                            name="media_inspect",
                            arguments="{}",
                        ),
                    ),
                ),
            )

        tool_message = next(item for item in reversed(messages) if item.role == "tool")
        self.seen_tool_result = tool_message.content
        payload = json.loads(tool_message.content)
        assert payload["perception"] == "perceived"
        assert payload["observations"][0]["kind"] == "video"
        return ProviderCompletion(
            text='[[CR_OUTPUT {"action":"message","content":[{"text":"这什么鬼啦"}]}]]',
            model=model,
            latency_ms=6,
            finish_reason="stop",
        )


class TimeoutProvider:
    async def complete(self, **_: object) -> object:
        raise ProviderTimeoutError("DeepSeek did not respond before timeout.")


def prompt_target(provider: object) -> PromptModelTarget:
    config = PromptModelConfig(
        name="Character",
        provider="test",
        model="test-model",
        system_prompt="Stay in character.",
        base_url="https://provider.test/v1",
    )
    return PromptModelTarget(
        config=config,
        provider=cast(Any, provider),
        runtime_system_prompt="You are a selective, opinionated Character.",
    )


def link_payload() -> DiscordInboundMessage:
    return DiscordInboundMessage(
        connection_id="connection-1",
        deployment_id="deployment-1",
        message_id="message-1",
        guild_id="guild-1",
        channel_id="channel-1",
        author_id="user-1",
        author_display_name="Juen",
        text="【旅行者: 我是爷们-哔哩哔哩】 https://b23.tv/example",
    )


def twitter_gif_payload() -> DiscordInboundMessage:
    return DiscordInboundMessage(
        connection_id="connection-1",
        deployment_id="deployment-1",
        message_id="gif-message-1",
        guild_id="guild-1",
        channel_id="channel-1",
        author_id="user-1",
        author_display_name="Juen",
        text="https://x.com/gwenbina/status/2091052290190827983",
        embeds=[
            DiscordEmbedContent(
                embed_type="rich",
                url="https://x.com/gwenbina/status/2091052290190827983",
                title="ket (@gwenbina)",
                description="A GIF shared from X.",
                provider_name="FxTwitter",
                author_name="ket (@gwenbina)",
            )
        ],
    )


def prepared_turn(target: object) -> SimpleNamespace:
    payload = link_payload()
    return SimpleNamespace(
        resolved=SimpleNamespace(
            deployment=SimpleNamespace(id="deployment-1", owner_id="owner-1"),
            card=SimpleNamespace(id="card-1"),
            target=target,
            payload=payload,
        ),
        prompt="Recent conversation:\nhello\nReturn Smart Output now.",
        prompt_manifest={},
        enabled_tools=(),
        tool_context=ToolExecutionContext(
            owner_id="owner-1",
            deployment_id="deployment-1",
            character_card_id="card-1",
            platform="discord",
            connection_id="connection-1",
            guild_id="guild-1",
            channel_id="channel-1",
            message_id="message-1",
            trigger_text=payload.text,
        ),
    )


def prepared_twitter_gif_turn(target: object) -> SimpleNamespace:
    prepared = prepared_turn(target)
    prepared.resolved.payload = twitter_gif_payload()
    return prepared


def runtime_for(
    service: FakeLiveMediaService,
    deployment_repository: object | None = None,
    conversation_media_service: object | None = None,
) -> MediaAwareDiscordConnectorRuntime:
    registry = MediaToolRegistry()
    runtime = MediaAwareDiscordConnectorRuntime(
        cast(Any, object()),
        cast(Any, deployment_repository or FakeDeploymentRepository()),
        cast(Any, object()),
        tool_registry=registry,
        live_media_service=cast(Any, service),
        conversation_media_service=cast(Any, conversation_media_service),
    )
    return runtime


def register_payload(
    runtime: MediaAwareDiscordConnectorRuntime,
    prepared: SimpleNamespace,
) -> None:
    setter = cast(Any, runtime.tool_registry).set_turn_media_payload
    setter(
        deployment_id="deployment-1",
        message_id=prepared.resolved.payload.message_id,
        payload=prepared.resolved.payload,
    )


def trace_metadata(
    runtime: MediaAwareDiscordConnectorRuntime,
    prepared: SimpleNamespace,
) -> dict[str, str]:
    return dict(runtime.epistemic_trace_metadata(cast(Any, prepared)))


def test_link_preview_does_not_run_media_understanding_before_character_decision() -> None:
    service = FakeLiveMediaService()
    runtime = runtime_for(service)
    prepared = prepared_turn(prompt_target(SkipMediaProvider()))
    register_payload(runtime, prepared)

    asyncio.run(runtime._ensure_media_context(cast(Any, prepared)))

    assert service.calls == 0
    assert "Character media inspection choice:" in prepared.prompt
    assert "call media_inspect" in prepared.prompt


def test_visible_twitter_gif_embed_uses_preview_without_exposing_media_tool() -> None:
    service = FakeLiveMediaService()
    provider = SkipMediaProvider()
    runtime = runtime_for(service)
    prepared = prepared_twitter_gif_turn(prompt_target(provider))
    register_payload(runtime, prepared)

    asyncio.run(runtime._ensure_media_context(cast(Any, prepared)))

    assert service.calls == 0
    assert "Character media preview:" in prepared.prompt
    assert "actual_media_perception=skipped" in prepared.prompt
    assert "Character media inspection choice:" not in prepared.prompt
    assert runtime._enabled_tools_for_turn(cast(Any, prepared)) == ()
    assert runtime._forced_tool_ids(cast(Any, prepared)) == ()

    runtime._finalize_media_epistemic(
        cast(Any, prepared),
        cast(Any, SimpleNamespace(tool_traces=[])),
    )
    metadata = trace_metadata(runtime, prepared)
    assert metadata["actual_perception"] == "skipped"
    assert metadata["attention_action"] == "preview"
    assert metadata["media_result_reason"] == "visible_link_preview_only"


def test_multiple_image_attachments_remain_passive_as_one_media_batch() -> None:
    service = FakeLiveMediaService(
        LiveMediaResult(
            status="completed",
            reason="ok",
            contexts=(
                LiveMediaContext(
                    source_key="sha256:image-1",
                    kind="image",
                    label="image-1.png",
                    summary="The first visible image.",
                ),
            ),
        )
    )
    runtime = runtime_for(service)
    prepared = prepared_twitter_gif_turn(prompt_target(SkipMediaProvider()))
    prepared.resolved.payload = prepared.resolved.payload.model_copy(
        update={
            "text": "看这些",
            "embeds": [],
            "attachments": [
                DiscordAttachmentContent(
                    attachment_id=f"image-{index}",
                    url=f"https://cdn.discord.test/image-{index}.png",
                    filename=f"image-{index}.png",
                    content_type="image/png",
                )
                for index in range(1, 4)
            ],
        }
    )
    register_payload(runtime, prepared)

    passive, active = runtime._split_passive_images(prepared.resolved.payload)

    assert passive is not None
    assert len(passive.attachments) == 3
    assert active.attachments == []
    assert runtime._active_shared_payload(prepared.resolved.payload) is None
    assert runtime._enabled_tools_for_turn(cast(Any, prepared)) == ()

    asyncio.run(runtime._ensure_media_context(cast(Any, prepared)))
    assert "1 of 3 visible image attachments" in prepared.prompt


def test_preview_does_not_hide_inspection_for_another_unpreviewed_media_item() -> None:
    service = FakeLiveMediaService()
    runtime = runtime_for(service)
    prepared = prepared_twitter_gif_turn(prompt_target(SkipMediaProvider()))
    prepared.resolved.payload = prepared.resolved.payload.model_copy(
        update={
            "attachments": [
                DiscordAttachmentContent(
                    attachment_id="video-1",
                    url="https://cdn.discord.test/video.mp4",
                    filename="video.mp4",
                    content_type="video/mp4",
                )
            ]
        }
    )
    register_payload(runtime, prepared)

    assert runtime._enabled_tools_for_turn(cast(Any, prepared)) == ("media.inspect",)


def test_skip_and_ignore_is_one_character_call_and_zero_media_calls() -> None:
    service = FakeLiveMediaService()
    provider = SkipMediaProvider()
    runtime = runtime_for(service)
    prepared = prepared_turn(prompt_target(provider))
    register_payload(runtime, prepared)

    turn = asyncio.run(runtime.start_character_tool_turn(cast(Any, prepared)))
    assert turn is not None
    response = asyncio.run(runtime.advance_character_tool_model(cast(Any, prepared), turn))

    assert response is not None
    assert response.text == '[[CR_OUTPUT {"action":"ignore"}]]'
    assert provider.calls == 1
    assert provider.seen_tools == ["media_inspect"]
    assert service.calls == 0

    runtime._finalize_media_epistemic(
        cast(Any, prepared),
        cast(Any, SimpleNamespace(tool_traces=[])),
    )
    metadata = trace_metadata(runtime, prepared)
    assert metadata["actual_perception"] == "skipped"
    assert metadata["attention_action"] == "skip"
    assert metadata["media_result_reason"] == "active_content_not_inspected"


def test_interested_character_calls_media_api_only_after_media_tool_request() -> None:
    service = FakeLiveMediaService()
    provider = InspectMediaProvider()
    runtime = runtime_for(service)
    prepared = prepared_turn(prompt_target(provider))
    register_payload(runtime, prepared)

    turn = asyncio.run(runtime.start_character_tool_turn(cast(Any, prepared)))
    assert turn is not None

    first = asyncio.run(runtime.advance_character_tool_model(cast(Any, prepared), turn))
    assert first is None
    assert provider.calls == 1
    assert service.calls == 0

    assert asyncio.run(runtime.execute_character_tools(cast(Any, prepared), turn)) == 1
    assert service.calls == 1

    second = asyncio.run(runtime.advance_character_tool_model(cast(Any, prepared), turn))
    assert second is not None
    assert provider.calls == 2
    assert provider.seen_tool_result
    assert second.text.startswith("[[CR_OUTPUT")

    metadata = trace_metadata(runtime, prepared)
    assert metadata["actual_perception"] == "perceived"
    assert metadata["attention_action"] == "watch"
    assert metadata["media_context_count"] == "1"
    assert metadata["media_result_reason"] == "ok"


def test_runtime_owned_media_tool_is_hidden_from_manual_tool_catalog() -> None:
    registry = MediaToolRegistry()
    ids = {item.id for item in registry.catalog()}
    assert "media.inspect" not in ids
    assert registry.tool_id_for_provider_name("media_inspect") == "media.inspect"


def test_roleplay_does_not_receive_runtime_owned_internal_context_tools() -> None:
    service = FakeLiveMediaService()

    class InternalOnlyRegistry:
        def internal_tool_ids(self) -> tuple[str, ...]:
            return ("memory.search", "conversation.search", "wiki.lookup")

        def tool_id_for_provider_name(self, _: str) -> None:
            return None

    runtime = MediaAwareDiscordConnectorRuntime(
        cast(Any, object()),
        cast(Any, FakeDeploymentRepository()),
        cast(Any, object()),
        tool_registry=cast(Any, InternalOnlyRegistry()),
        live_media_service=cast(Any, service),
    )
    prepared = prepared_turn(prompt_target(SkipMediaProvider()))
    prepared.enabled_tools = ("image.generate",)

    assert runtime._enabled_tools_for_turn(cast(Any, prepared)) == ("image.generate",)
    assert runtime._forced_tool_ids(cast(Any, prepared)) == ()


def test_transient_provider_failure_returns_silent_control_without_disabling_deployment() -> None:
    service = FakeLiveMediaService()
    deployments = FakeDeploymentRepository()
    runtime = runtime_for(service, deployments)
    prepared = prepared_turn(prompt_target(TimeoutProvider()))
    register_payload(runtime, prepared)

    response = asyncio.run(runtime.invoke_character_model(cast(Any, prepared)))

    assert response.text == '[[CR_OUTPUT {"action":"ignore"}]]'
    assert response.trace["provider_failure"] == "provider_timeout"
    assert deployments.errors == [("deployment-1", "provider_timeout")]
    assert deployments.updates[-1]["status"] == "active"
    assert deployments.updates[-1]["last_error"] == "provider_timeout"


def test_burst_visible_image_uses_original_source_message_for_perception() -> None:
    service = FakeLiveMediaService(
        LiveMediaResult(
            status="completed",
            reason="ok",
            contexts=(
                LiveMediaContext(
                    source_key="sha256:image-source",
                    kind="image",
                    label="photo.png",
                    summary="A visible image from the immediately preceding Discord message.",
                ),
            ),
        )
    )
    memory = FakeConversationMediaService()
    runtime = runtime_for(service, conversation_media_service=memory)
    prepared = prepared_turn(prompt_target(SkipMediaProvider()))
    prepared.resolved.payload = prepared.resolved.payload.model_copy(
        update={
            "message_id": "text-message",
            "text": "这个是不是很像 Ann",
            "burst_media_message_ids": ["image-message"],
        }
    )

    asyncio.run(runtime._ensure_media_context(cast(Any, prepared)))

    assert service.payload_message_ids == ["image-message"]
    assert memory.remembered_message_ids == ["image-message"]
    assert "actual_media_perception=perceived" in prepared.prompt
