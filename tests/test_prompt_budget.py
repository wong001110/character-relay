from pydantic import SecretStr

from echo_masque.conversation_media import (
    ConversationMediaMemory,
    ConversationMediaReferenceService,
)
from echo_masque.live_media import LiveMediaContext
from echo_masque.prompt_budget import select_tool_ids_for_turn
from echo_masque.targets.prompt_model import PromptModelTarget
from echo_masque.tool_runtime import ToolExecutionContext, ToolRegistry


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


def test_sparse_tool_selection_exposes_only_relevant_read_tools() -> None:
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
    )
    assert selected == ("weather.get",)
    assert set(selected).issubset(set(assigned))


def test_side_effect_tool_requires_explicit_intent_without_semantic_scoring() -> None:
    registry = ToolRegistry(discord_bot_token=SecretStr("test-bot-token"))
    assigned = ("weather.get", "discord.create_poll")

    unrelated = select_tool_ids_for_turn(
        registry,
        assigned,
        _tool_context("大家觉得周五还是周六比较好？"),
    )
    assert "discord.create_poll" not in unrelated

    explicit = select_tool_ids_for_turn(
        registry,
        assigned,
        _tool_context("开个投票看看周五还是周六。"),
    )
    assert "discord.create_poll" in explicit
    assert set(explicit).issubset(set(assigned))


def test_tool_sparse_no_match_preserves_assigned_available_reads() -> None:
    registry = ToolRegistry()
    assigned = ("utility.calculator", "weather.get", "random.roll")
    selected = select_tool_ids_for_turn(
        registry,
        assigned,
        _tool_context("qzxvnhfg"),
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


def test_missing_trigger_keeps_assigned_reads_without_enabling_effects() -> None:
    from echo_masque.tool_runtime import default_tool_registry

    registry = default_tool_registry()
    selected = select_tool_ids_for_turn(
        registry,
        ("utility.calculator", "discord.create_poll"),
        ToolExecutionContext(
            owner_id="owner", deployment_id="role", character_card_id="card", platform="discord"
        ),
    )
    assert "utility.calculator" in selected
    assert "discord.create_poll" not in selected
