import asyncio
from types import SimpleNamespace
from typing import Any, cast

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.live_media import LiveMediaContext, LiveMediaResult
from echo_masque.media_connector_runtime import MediaAwareDiscordConnectorRuntime
from echo_masque.media_tools import MediaToolRegistry
from echo_masque.tool_runtime import ToolExecutionContext


class RequiredMediaService:
    def __init__(self) -> None:
        self.calls = 0

    async def contexts_for_turn(self, **_: object) -> LiveMediaResult:
        self.calls += 1
        return LiveMediaResult(
            status="completed",
            reason="required-video-summary",
            contexts=(
                LiveMediaContext(
                    source_key="video:test",
                    kind="video",
                    label="剧情分析",
                    summary="视频讨论反派身份，并指出角色 A 的行为是刻意误导。",
                    notable_details=("角色 B 被认为更可疑。",),
                ),
            ),
        )


class NoopDeploymentRepository:
    def record_deployment_error(self, *_: object) -> None:
        return None


def _prepared() -> SimpleNamespace:
    payload = DiscordInboundMessage(
        connection_id="connection-1",
        deployment_id="deployment-1",
        message_id="message-1",
        guild_id="guild-1",
        channel_id="channel-1",
        author_id="user-1",
        author_display_name="Juen",
        text="这个视频里面谁是反派？ https://example.test/video",
        embeds=[],
    )
    return SimpleNamespace(
        resolved=SimpleNamespace(
            deployment=SimpleNamespace(id="deployment-1", owner_id="owner-1"),
            card=SimpleNamespace(id="card-1"),
            payload=payload,
        ),
        prompt="Recent conversation:\n这个视频里面谁是反派？\nReturn Smart Output now.",
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


def test_required_media_is_resolved_before_roleplay_and_disables_optional_inspect() -> None:
    service = RequiredMediaService()
    runtime = MediaAwareDiscordConnectorRuntime(
        cast(Any, object()),
        cast(Any, NoopDeploymentRepository()),
        cast(Any, object()),
        tool_registry=MediaToolRegistry(),
        live_media_service=cast(Any, service),
    )
    prepared = _prepared()

    asyncio.run(runtime._ensure_media_context(cast(Any, prepared)))

    assert service.calls == 1
    assert "Character required media perception:" in prepared.prompt
    assert "视频讨论反派身份" in prepared.prompt
    assert "Character media inspection choice:" not in prepared.prompt
    assert runtime._media_inspection_enabled(cast(Any, prepared)) is False

    metadata = dict(runtime.epistemic_trace_metadata(cast(Any, prepared)))
    assert metadata["actual_perception"] == "perceived"
    assert metadata["attention_action"] == "required"
    assert metadata["media_context_count"] == "1"
    assert metadata["media_result_reason"] == "required-video-summary"
