from pydantic import SecretStr

from echo_masque.api.connector_schemas import DiscordContextMessage, DiscordInboundMessage
from echo_masque.api.expression_schemas import ExpressionCandidate, ExpressionContent
from echo_masque.config import get_settings
from echo_masque.connector_runtime import DiscordConnectorRuntime
from echo_masque.context_layer import ContextOrchestrator
from echo_masque.conversation_media import ConversationMediaMemory, ConversationMediaReferenceService
from echo_masque.live_media import LiveMediaContext
from echo_masque.prompt_budget import BudgetSmartOutputContext, select_tool_ids_for_turn
from echo_masque.providers.errors import ProviderProtocolError
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


def _semantic_settings():
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


def _expression_candidate() -> ExpressionCandidate:
    return ExpressionCandidate(
        resource_key="emoji:party",
        resource_type="emoji",
        resource_id="party",
        name="party",
        animated=False,
        available=True,
        enabled=True,
        allowed_actions=["inline", "reaction"],
        semantic_intent="celebration",
        semantic_emotion="happy",
        semantic_description="celebratory party reaction",
        semantic_source="manual",
        semantic_confidence=1.0,
        asset_url="https://cdn.example.test/party.png",
        format_type="png",
        score=0.9,
    )


def _smart_context() -> BudgetSmartOutputContext:
    return BudgetSmartOutputContext(
        message_alias_to_id={"trigger": "message-1"},
        message_id_to_alias={"message-1": "trigger"},
        participant_alias_to_ref={},
        participant_ref_to_name={},
        participant_alias_descriptions=(),
    )


def test_smart_output_guidance_is_dynamic_and_compact() -> None:
    plain = "\n".join(_smart_context().prompt_guidance([]))
    assert "Allowed actions this turn: ignore, message, short_message." in plain
    assert "action=react" not in plain
    assert "action=sticker" not in plain
    assert "Retrieved Server expressions" not in plain
    assert plain.count("Message shape: [[CR_OUTPUT") == 1
    assert plain.count("Short message shape: [[CR_OUTPUT") == 1
    assert plain.count("Silence shape: [[CR_OUTPUT") == 1

    expressive = "\n".join(_smart_context().prompt_guidance([_expression_candidate()]))
    assert "ignore, message, short_message, react" in expressive
    assert "party" in expressive
    assert "action=react" in expressive


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


def _emoji() -> ExpressionContent:
    return ExpressionContent(
        resource_key="emoji:laugh",
        resource_type="emoji",
        resource_id="laugh",
        name="laugh",
        animated=False,
        available=True,
        enabled=True,
        allowed_actions=["inline", "reaction"],
        semantic_intent="laugh",
        semantic_emotion="happy",
        semantic_description="laughing very hard because something is funny",
        semantic_source="manual",
        semantic_confidence=0.98,
        asset_url="https://cdn.example.test/laugh.png",
        format_type="png",
    )


def test_conversation_budget_removes_trigger_duplication_and_compacts_history() -> None:
    trigger = "你觉得刚才那个怎么样？"
    payload = DiscordInboundMessage(
        connection_id="conn-1",
        deployment_id="deployment-1",
        message_id="current",
        guild_id="guild-1",
        guild_name="Guild",
        channel_id="channel-1",
        channel_name="chat",
        author_id="member-1",
        author_display_name="Member",
        text=trigger,
        recent_messages=[
            DiscordContextMessage(
                message_id="old-1",
                author_id="member-2",
                author_display_name="Other",
                text="A" * 5000,
                is_bot=False,
            ),
            DiscordContextMessage(
                message_id="old-2",
                author_id="member-1",
                author_display_name="Member",
                text="这个真的很好笑",
                emojis=[_emoji()],
                is_bot=False,
            ),
            DiscordContextMessage(
                message_id="current",
                author_id="member-1",
                author_display_name="Member",
                text=trigger,
                is_bot=False,
            ),
        ],
    )
    orchestrator = object.__new__(ContextOrchestrator)
    orchestrator.conversation_token_budget = 400
    count, chars = orchestrator._apply_conversation_budget(payload)

    assert count >= 1
    assert chars <= 1600
    current = next(item for item in payload.recent_messages if item.message_id == "current")
    assert current.text == ""
    compact = next(item for item in payload.recent_messages if item.message_id == "old-2")
    assert "[emoji laugh:" in compact.text
    assert not compact.emojis
    assert "confidence" not in compact.text
    assert "source" not in compact.text

    prompt = DiscordConnectorRuntime._social_prompt(
        character_name="Ann",
        payload=payload,
        smart_context=_smart_context(),
    )
    assert prompt.count(trigger) == 1


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


def test_unused_protocol_error_import_stays_false() -> None:
    assert issubclass(ProviderProtocolError, Exception)
