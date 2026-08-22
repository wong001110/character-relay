from pydantic import SecretStr

from echo_masque.config import Settings, get_settings
from echo_masque.conversation_media import (
    ConversationMediaMemory,
    ConversationMediaReferenceService,
)
from echo_masque.live_media import LiveMediaContext
from echo_masque.prompt_budget import select_tool_ids_for_turn
from echo_masque.semantic_participation import SemanticEmbeddingUnavailable
from echo_masque.targets.prompt_model import PromptModelTarget
from echo_masque.tool_runtime import ToolExecutionContext, ToolRegistry


class WeatherEncoder:
    model_name = "fake-weather"
    dimension = 2

    def embed_query(self, text: str) -> list[float]:
        del text
        return [1.0, 0.0]

    def embed_passage(self, text: str) -> list[float]:
        if "weather" in text.casefold() or "forecast" in text.casefold():
            return [1.0, 0.0]
        return [0.0, 1.0]


class UnavailableEncoder:
    model_name = "fake-unavailable"
    dimension = 2

    def embed_query(self, text: str) -> list[float]:
        del text
        raise SemanticEmbeddingUnavailable("offline")

    def embed_passage(self, text: str) -> list[float]:
        del text
        raise SemanticEmbeddingUnavailable("offline")


def _semantic_settings() -> Settings:
    return get_settings().model_copy(update={"environment": "production"})


def _tool_context(text: str) -> ToolExecutionContext:
    return ToolExecutionContext(
        owner_id="owner-1",
        deployment_id="deployment-1",
        character_card_id="character-1",
        platform="discord",
        guild_id="guild-1",
        channel_id="channel-1",
        message_id="message-1",
        trigger_text=text,
        initiator_user_id="member-1",
    )


def test_dense_tool_selection_exposes_only_relevant_read_tools() -> None:
    registry = ToolRegistry()
    assigned = (
        "utility.calculator",
        "utility.current_time",
        "weather.get",
        "random.roll",
        "random.choose",
    )
    selected = select_tool_ids_for_turn(
        registry,
        assigned,
        _tool_context("明天吉隆坡会不会下雨？"),
        settings=_semantic_settings(),
        encoder=WeatherEncoder(),
    )
    assert selected == ("weather.get",)
    assert set(selected).issubset(set(assigned))


def test_side_effect_tool_requires_explicit_intent_even_when_dense_matches() -> None:
    registry = ToolRegistry(discord_bot_token=SecretStr("test-bot-token"))
    assigned = ("weather.get", "discord.create_poll")

    unrelated = select_tool_ids_for_turn(
        registry,
        assigned,
        _tool_context("大家觉得周五还是周六比较好？"),
        settings=_semantic_settings(),
        encoder=WeatherEncoder(),
    )
    assert "discord.create_poll" not in unrelated

    explicit = select_tool_ids_for_turn(
        registry,
        assigned,
        _tool_context("开个投票看看周五还是周六。"),
        settings=_semantic_settings(),
        encoder=WeatherEncoder(),
    )
    assert "discord.create_poll" in explicit
    assert set(explicit).issubset(set(assigned))


def test_tool_embedding_failure_preserves_assigned_capabilities() -> None:
    registry = ToolRegistry()
    assigned = ("utility.calculator", "weather.get", "random.roll")
    selected = select_tool_ids_for_turn(
        registry,
        assigned,
        _tool_context("weather tomorrow"),
        settings=_semantic_settings(),
        encoder=UnavailableEncoder(),
    )
    assert selected == assigned


def test_media_recall_guidance_never_rehydrates_full_transcript() -> None:
    transcript = "开场介绍。" + ("无关内容 " * 2500) + "关键价格是 199 元。" + ("尾声 " * 500)
    memory = ConversationMediaMemory(
        message_id="video-1",
        context=LiveMediaContext(
            source_key="video:1",
            kind="video",
            label="Demo",
            summary="A long product demonstration video.",
            visible_text=transcript,
            notable_details=("Shows a product", "Contains a price", "Long transcript"),
        ),
        recall_query="那个价格是多少？",
    )
    guidance = "\n".join(ConversationMediaReferenceService.guidance((memory,)))

    assert "199 元" in guidance
    assert len(guidance) <= 3600
    assert len(guidance) < len(transcript) // 3


def test_format_repair_does_not_repeat_the_full_turn_prompt() -> None:
    original = "Recent conversation:\n" + ("x" * 8000) + "\nReturn Smart Output now."
    repair = "\n".join(
        (
            original,
            "",
            "Your previous Smart Output was rejected (invalid_smart_output_control).",
            "Regenerate once. Return exactly one valid [[CR_OUTPUT {...}]] line and nothing else.",
        )
    )
    compact = PromptModelTarget._compact_format_repair(repair)
    assert compact.startswith("Your previous Smart Output was rejected")
    assert "Recent conversation" not in compact
    assert len(compact) < 500
