from __future__ import annotations

from echo_masque.api.connector_schemas import DiscordContextMessage, DiscordInboundMessage
from echo_masque.context_layer import (
    CharacterContextTraceView,
    CharacterTurnContext,
    ContextOrchestrator,
)
from echo_masque.persistence import Database, KnowledgeRepository
from echo_masque.prompt_budget import BudgetSmartOutputContext
from echo_masque.semantic_turn_runtime import SemanticTurnSignals, SemanticTurnSignalStore


def _repository() -> KnowledgeRepository:
    database = Database("sqlite://")
    database.initialize()
    return KnowledgeRepository(database, semantic_enabled=False)


def _payload(
    text: str = "current trigger",
    *,
    recent_messages: list[DiscordContextMessage] | None = None,
) -> DiscordInboundMessage:
    return DiscordInboundMessage(
        connection_id="connection-1",
        deployment_id="deployment-ann",
        message_id="trigger",
        guild_id="guild-a",
        guild_name="Guild",
        channel_id="general",
        channel_name="general",
        category_id="",
        thread_id="",
        thread_name="",
        author_id="user-1",
        author_display_name="Juen",
        text=text,
        mentioned_bot=True,
        smart_candidate=True,
        recent_messages=recent_messages or [],
    )


def setup_function() -> None:
    SemanticTurnSignalStore.reset_for_test()


def teardown_function() -> None:
    SemanticTurnSignalStore.reset_for_test()


def test_prompt_budget_v2_defaults_reduce_raw_history_and_knowledge() -> None:
    orchestrator = ContextOrchestrator(_repository())

    assert orchestrator.conversation_token_budget == 700
    assert orchestrator.knowledge_token_budget == 800


def test_raw_recent_history_is_bounded_to_default_budget() -> None:
    recent = [
        DiscordContextMessage(
            message_id=f"m{index}",
            author_id="user-1",
            author_display_name="Juen",
            text=f"history-{index} " + ("x" * 480),
            is_bot=False,
        )
        for index in range(12)
    ]
    recent.append(
        DiscordContextMessage(
            message_id="trigger",
            author_id="user-1",
            author_display_name="Juen",
            text="current trigger",
            is_bot=False,
        )
    )
    payload = _payload(recent_messages=recent)
    orchestrator = ContextOrchestrator(_repository())

    selected_count, selected_chars = orchestrator._apply_conversation_budget(payload)

    assert selected_chars <= 700 * 4
    assert selected_count < 12
    ids = [item.message_id for item in payload.recent_messages]
    assert "m11" in ids
    assert ids[-1] == "trigger"
    trigger_copy = payload.recent_messages[-1]
    assert trigger_copy.text == ""
    assert payload.text == "current trigger"


def test_prior_topic_summary_excludes_current_trigger_line() -> None:
    summary = "Juen: generate a cat image\nAnn: I cannot yet\nJuen: 你再试试"

    prior = ContextOrchestrator._prior_topic_summary(summary, message_count=3)

    assert "generate a cat image" in prior
    assert "I cannot yet" in prior
    assert "你再试试" not in prior


def test_active_topic_capsule_is_prompt_safe_and_bounded() -> None:
    SemanticTurnSignalStore.put(
        SemanticTurnSignals(
            deployment_id="deployment-ann",
            message_id="trigger",
            topic_id="topic-1",
            topic_label="cat image request",
            topic_summary="Juen: generate a cat image\nAnn: image generation was unavailable",
            topic_message_count=3,
            continuation_tool_ids=("image.generate",),
            blocked_side_effect_intents=("image.generate",),
            continuity_reason="semantic_continuation",
            retry_score=0.91,
        )
    )
    payload = _payload("你再试试")
    context = CharacterTurnContext(
        smart_output=BudgetSmartOutputContext.from_payload(payload, character_name="Ann"),
        knowledge=(),
        trace=CharacterContextTraceView(
            topic_id="topic-1",
            topic_status="active",
            topic_message_count=3,
            conversation_token_budget=700,
            knowledge_token_budget=800,
        ),
    )

    guidance = "\n".join(context.knowledge_prompt_guidance())

    assert "Active conversation topic capsule:" in guidance
    assert "Topic: cat image request" in guidance
    assert "generate a cat image" in guidance
    assert "image generation was unavailable" in guidance
    assert "continuation_tool_ids" not in guidance
    assert "blocked_side_effect_intents" not in guidance
    assert "blocked_unavailable" not in guidance
    assert "pending_actions" not in guidance


def test_topic_capsule_store_clamps_prompt_visible_text() -> None:
    SemanticTurnSignalStore.put(
        SemanticTurnSignals(
            deployment_id="deployment-ann",
            message_id="m1",
            topic_id="topic-1",
            topic_label="L" * 500,
            topic_summary="S" * 1500,
            topic_message_count=9,
        )
    )

    capsule = SemanticTurnSignalStore.topic_capsule("topic-1")

    assert capsule is not None
    label, summary, message_count = capsule
    assert len(label) == 240
    assert len(summary) == 800
    assert message_count == 9
