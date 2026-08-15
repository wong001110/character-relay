import asyncio

from echo_masque.api.connector_schemas import DiscordEmbedContent, DiscordInboundMessage
from echo_masque.media_dependency import MediaDependencyResolver, deterministic_media_dependency
from echo_masque.media_planning import MediaPlanningDescriptorService, MediaPlanningRequest


def _payload(text: str, *, with_link_preview: bool = True) -> DiscordInboundMessage:
    embeds = (
        [
            DiscordEmbedContent(
                embed_type="video",
                url="https://example.test/video",
                title="绝区零剧情反派分析",
                description="讨论章节中的反派身份和剧情伏笔。",
                provider_name="bilibili",
            )
        ]
        if with_link_preview
        else []
    )
    return DiscordInboundMessage(
        connection_id="conn",
        deployment_id="ann",
        message_id="m1",
        guild_id="g1",
        channel_id="c1",
        author_id="u1",
        author_display_name="User",
        text=text,
        embeds=embeds,
    )


def test_explicit_media_content_question_is_runtime_locked_required() -> None:
    decision = deterministic_media_dependency(
        _payload("这个视频里面谁是反派？ https://example.test/video")
    )

    assert decision is not None
    assert decision.dependency == "required"
    assert decision.source == "runtime"
    assert decision.locked is True


def test_link_only_share_is_optional_not_guessed_as_perceived() -> None:
    decision = deterministic_media_dependency(_payload("https://example.test/video"))

    assert decision is not None
    assert decision.dependency == "optional"
    assert decision.reason == "media_only_share_without_explicit_question"
    assert decision.locked is False


def test_no_media_is_runtime_locked_none() -> None:
    decision = deterministic_media_dependency(_payload("普通聊天", with_link_preview=False))

    assert decision is not None
    assert decision.dependency == "none"
    assert decision.locked is True


def test_ambiguous_deictic_media_request_uses_safe_optional_fallback_without_gateway() -> None:
    decision = asyncio.run(MediaDependencyResolver().resolve(_payload("这个怎么样？")))

    assert decision.dependency == "optional"
    assert decision.source == "fallback"
    assert decision.confidence == 0.5


def test_planning_descriptor_uses_preview_without_granting_character_perception() -> None:
    service = MediaPlanningDescriptorService()
    descriptor = asyncio.run(
        service.describe(
            MediaPlanningRequest(
                connection_id="conn",
                guild_id="g1",
                channel_id="c1",
                message_id="m1",
                text="https://example.test/video",
                embeds=[
                    DiscordEmbedContent(
                        embed_type="video",
                        url="https://example.test/video",
                        title="绝区零剧情反派分析",
                        description="讨论章节中的反派身份和剧情伏笔。",
                        provider_name="bilibili",
                    )
                ],
            )
        )
    )

    assert descriptor.available is True
    assert descriptor.kind == "video"
    assert descriptor.source == "discord_preview"
    assert "Planner-only objective media descriptor" in descriptor.planning_text
    assert "绝区零剧情反派分析" in descriptor.planning_text
    assert "actual_media_perception" not in descriptor.planning_text
    assert "Character" not in descriptor.planning_text
