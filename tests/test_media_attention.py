import asyncio

from echo_masque.api.connector_schemas import (
    DiscordEmbedContent,
    DiscordInboundMessage,
)
from echo_masque.media_attention import (
    CharacterMediaAttentionDecider,
    has_complete_visible_embed_preview,
    has_visible_embed_preview,
    media_preview_lines,
    visible_embed_preview_for_url,
)
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
    assert has_visible_embed_preview(payload()) is True
    assert has_complete_visible_embed_preview(payload()) is True


def test_preview_coverage_requires_each_shared_url() -> None:
    value = payload().model_copy(
        update={"text": f"{payload().text} https://example.test/unpreviewed"}
    )

    assert has_complete_visible_embed_preview(value) is False


def test_embed_preview_matching_does_not_reuse_one_card_for_another_url() -> None:
    value = payload().model_copy(
        update={"text": f"{payload().text} https://example.test/unpreviewed"}
    )

    assert visible_embed_preview_for_url(value, payload().text.split()[-1]) is not None
    assert visible_embed_preview_for_url(value, "https://example.test/unpreviewed") is None


def test_x_preview_accepts_fxtwitter_embed_for_the_same_status() -> None:
    value = payload().model_copy(
        update={
            "text": "https://x.com/gwenbina/status/2091052290190827983",
            "embeds": [
                payload().embeds[0].model_copy(
                    update={
                        "url": "https://fxtwitter.com/gwenbina/status/2091052290190827983",
                        "provider_name": "FxTwitter",
                    }
                )
            ],
        }
    )

    assert has_complete_visible_embed_preview(value) is True


def test_attention_decision_uses_persona_without_mutating_character_history() -> None:
    provider = FakeProvider(
        '{"action":"watch","reason":"This topic matches my interests.",'
        '"response_stance":"truthful","stance_reason":"I genuinely want to discuss it."}'
    )
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
    assert decision.response_stance == "truthful"
    assert decision.stance_reason == "I genuinely want to discuss it."
    assert target.history == ()
    assert len(provider.calls) == 1
    messages, model, temperature = provider.calls[0]
    assert model == "character-model"
    assert temperature == 0.3
    assert messages[0].role == "system"
    assert "selective and curious" in messages[0].content
    assert messages[1].content.startswith("[MEDIA_ATTENTION]")
    assert "response_stance" in messages[1].content
    assert "Cherry Studio V2" in messages[1].content


def test_skip_can_declare_bluff_without_granting_unseen_knowledge() -> None:
    decision = CharacterMediaAttentionDecider._parse(
        '{"action":"skip","reason":"I do not actually want to inspect it.",'
        '"response_stance":"bluff","stance_reason":"I would rather save face."}'
    )

    assert decision.action == "skip"
    assert decision.response_stance == "bluff"
    assert decision.stance_reason == "I would rather save face."


def test_legacy_attention_shape_remains_compatible_with_neutral_stance() -> None:
    decision = CharacterMediaAttentionDecider._parse(
        '{"action":"watch","reason":"I am curious."}'
    )

    assert decision.action == "watch"
    assert decision.response_stance == "neutral"
    assert decision.stance_reason == "persona_social_stance"


def test_invalid_attention_output_fails_closed_to_skip() -> None:
    decision = CharacterMediaAttentionDecider._parse("I would probably watch it.")
    assert decision.action == "skip"
    assert decision.reason == "invalid_attention_output"
    assert decision.response_stance == "neutral"


def test_provider_trace_classifies_media_attention_separately() -> None:
    request = (
        '{"latest_message":{"role":"user","content":"[MEDIA_ATTENTION]\\nprivate gate"},'
        '"message_roles":["system","user"]}'
    )
    assert provider_trace_category(request, "{}") == "media_attention"
