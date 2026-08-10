import asyncio

from echo_masque.api.connector_schemas import (
    DiscordEmbedContent,
    DiscordInboundMessage,
)
from echo_masque.media_attention import CharacterMediaAttentionDecider, media_preview_lines
from echo_masque.provider_trace_classification import provider_trace_category
from echo_masque.providers import ChatMessage, ProviderCompletion
from echo_masque.targets import PromptModelConfig, PromptModelTarget


class FakeProvider:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[tuple[ChatMessage, ...], str, float]] = []

    async def complete(
        self,
        *,
        messages: tuple[ChatMessage, ...],
        model: str,
        temperature: float,
    ) -> ProviderCompletion:
        self.calls.append((messages, model, temperature))
        return ProviderCompletion(
            text=self.response,
            model=model,
            latency_ms=4,
        )


def payload() -> DiscordInboundMessage:
    return DiscordInboundMessage(
        connection_id="connection-1",
        deployment_id="deployment-1",
        message_id="message-1",
        guild_id="guild-1",
        channel_id="channel-1",
        author_id="user-1",
        author_display_name="Member",
        text="安, 那这个 B站链接呢? https://www.bilibili.com/video/BV1abc/",
        embeds=[
            DiscordEmbedContent(
                embed_type="video",
                url="https://www.bilibili.com/video/BV1abc/",
                title="Cherry Studio V2 来了, 超详细攻略 + 真实使用场景分享",
                description="视频播放量与作者简介的 Discord 可见预览。",
                provider_name="哔哩哔哩",
                author_name="技术爬爬虾",
            )
        ],
    )


def test_media_preview_includes_discord_visible_embed_before_watching() -> None:
    preview = media_preview_lines(payload())

    assert any("Cherry Studio V2" in line for line in preview)
    assert any("bilibili" in line.casefold() for line in preview)


def test_attention_decision_uses_persona_without_mutating_character_history() -> None:
    provider = FakeProvider('{"action":"watch","reason":"This topic matches my interests."}')
    target = PromptModelTarget(
        config=PromptModelConfig(
            name="Ann",
            provider="test",
            model="character-model",
            system_prompt="Stay in character.",
            base_url="https://provider.test/v1",
            temperature=0.9,
        ),
        provider=provider,
        runtime_system_prompt="You are Ann. You are selective and curious about AI products.",
    )

    decision = asyncio.run(
        CharacterMediaAttentionDecider().decide(target=target, payload=payload())
    )

    assert decision.action == "watch"
    assert target.history == ()
    assert len(provider.calls) == 1
    messages, model, temperature = provider.calls[0]
    assert model == "character-model"
    assert temperature == 0.3
    assert messages[0].role == "system"
    assert "selective and curious" in messages[0].content
    assert messages[1].content.startswith("[MEDIA_ATTENTION]")
    assert "Cherry Studio V2" in messages[1].content


def test_invalid_attention_output_fails_closed_to_skip() -> None:
    decision = CharacterMediaAttentionDecider._parse("I would probably watch it.")
    assert decision.action == "skip"
    assert decision.reason == "invalid_attention_output"


def test_provider_trace_classifies_media_attention_separately() -> None:
    request = (
        '{"latest_message":{"role":"user","content":"[MEDIA_ATTENTION]\\nprivate gate"},'
        '"message_roles":["system","user"]}'
    )
    assert provider_trace_category(request, "{}") == "media_attention"
