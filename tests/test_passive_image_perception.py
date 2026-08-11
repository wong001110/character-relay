import asyncio
from types import SimpleNamespace
from typing import Any, cast

from echo_masque.api.connector_schemas import DiscordAttachmentContent, DiscordInboundMessage
from echo_masque.live_media import LiveMediaContext, LiveMediaResult
from echo_masque.media_attention import MediaAttentionDecision
from echo_masque.media_connector_runtime import MediaAwareDiscordConnectorRuntime


class FakeLiveMediaService:
    def __init__(self) -> None:
        self.calls = 0

    async def contexts_for_turn(self, **_: object) -> LiveMediaResult:
        self.calls += 1
        return LiveMediaResult(
            status="completed",
            reason="ok",
            contexts=(
                LiveMediaContext(
                    source_key="sha256:cat",
                    kind="image",
                    label="cat.png",
                    summary="An orange cat is sitting on a laptop keyboard.",
                ),
            ),
        )


class FakeAttentionDecider:
    def __init__(self) -> None:
        self.calls = 0

    async def decide(self, **_: object) -> MediaAttentionDecision:
        self.calls += 1
        return MediaAttentionDecision(action="skip", reason="persona_skip")


def image_payload() -> DiscordInboundMessage:
    return DiscordInboundMessage(
        connection_id="connection-1",
        deployment_id="deployment-1",
        message_id="message-1",
        guild_id="guild-1",
        channel_id="channel-1",
        author_id="user-1",
        author_display_name="Juen",
        text="看这个",
        attachments=[
            DiscordAttachmentContent(
                attachment_id="attachment-1",
                url="https://cdn.discord.test/cat.png",
                filename="cat.png",
                content_type="image/png",
                size_bytes=1234,
                width=800,
                height=600,
            )
        ],
    )


def test_visible_image_attachment_is_perceived_without_attention_gate() -> None:
    service = FakeLiveMediaService()
    attention = FakeAttentionDecider()
    runtime = MediaAwareDiscordConnectorRuntime(
        cast(Any, object()),
        cast(Any, object()),
        cast(Any, object()),
        live_media_service=cast(Any, service),
        media_attention_decider=cast(Any, attention),
    )
    prepared = SimpleNamespace(
        resolved=SimpleNamespace(
            deployment=SimpleNamespace(id="deployment-1", owner_id="owner-1"),
            card=SimpleNamespace(id="card-1"),
            target=object(),
            payload=image_payload(),
        ),
        prompt="Recent conversation:\nhello\nReturn Smart Output now.",
        enabled_tools=(),
    )

    asyncio.run(runtime._ensure_media_context(cast(Any, prepared)))

    assert service.calls == 1
    assert attention.calls == 0
    assert "Character passive image perception:" in prepared.prompt
    assert "Seeing the image does not obligate you to comment" in prepared.prompt
    metadata = dict(runtime.epistemic_trace_metadata(cast(Any, prepared)))
    assert metadata["actual_perception"] == "perceived"
    assert metadata["attention_action"] == "passive"
    assert metadata["media_context_count"] == "1"
