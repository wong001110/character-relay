from __future__ import annotations

from datetime import UTC, datetime, timedelta

from echo_masque.conversation_topic import (
    ConversationActScores,
    ConversationPendingAction,
    ConversationTopicSnapshot,
    TopicContinuityDecision,
)

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.config import Settings
from echo_masque.tool_continuation import ToolContinuationService
from echo_masque.utility_gateway_contracts import ToolContinuationUtilityDecision


class FakeGateway:
    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, capability: str, schema: object, **_kwargs: object) -> tuple[object, object]:
        assert capability == "tool_continuation"
        assert schema is ToolContinuationUtilityDecision
        self.calls += 1
        return (
            ToolContinuationUtilityDecision(
                continue_action=True,
                tool_id="image.generate",
                confidence=0.91,
                reason_code="same_pending_action",
            ),
            object(),
        )


class FakeTopicRepository:
    def __init__(self) -> None:
        self.database = object()

    @staticmethod
    def active_for_scope(**_kwargs: object) -> object:
        return object()


class FakeTopicMemory:
    def __init__(
        self,
        snapshot: ConversationTopicSnapshot,
        decision: TopicContinuityDecision,
        pending_actions: tuple[ConversationPendingAction, ...],
    ) -> None:
        self.repository = FakeTopicRepository()
        self._snapshot = snapshot
        self._decision = decision
        self._pending_actions = pending_actions

    def snapshot(self, _record: object) -> ConversationTopicSnapshot:
        return self._snapshot

    def classify_continuity(
        self,
        *,
        text: str,
        active: object,
    ) -> TopicContinuityDecision:
        assert text
        assert active is not None
        return self._decision

    def pending_for_actor(self, **_kwargs: object) -> tuple[ConversationPendingAction, ...]:
        return self._pending_actions

    def observe_turn(self, **_kwargs: object) -> ConversationTopicSnapshot:
        return self._snapshot

    def record_pending_action(self, **_kwargs: object) -> None:
        raise AssertionError("this fixture has no new blocked side-effect intent")


def action() -> ConversationPendingAction:
    now = datetime.now(UTC)
    return ConversationPendingAction(
        tool_id="image.generate",
        state="pending",
        requested_by_user_id="user-1",
        target_character_card_id="card-ann",
        deployment_id="deployment-ann",
        source_message_id="message-1",
        intent_summary="generate the image",
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=1),
    )


def topic(value: ConversationPendingAction) -> ConversationTopicSnapshot:
    now = datetime.now(UTC)
    return ConversationTopicSnapshot(
        id="topic-1",
        owner_id="owner-1",
        platform="discord",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="",
        topic_label="image generation",
        summary="The user was trying to generate one image.",
        pending_actions=[value],
        status="active",
        message_count=2,
        capsule_version=2,
        last_message_id="message-1",
        started_at=now - timedelta(minutes=2),
        last_active_at=now,
    )


def decision() -> TopicContinuityDecision:
    return TopicContinuityDecision(
        same_topic=True,
        topic_similarity=0.7,
        sparse_similarity=0.2,
        acts=ConversationActScores(retry_previous_action=0.35),
        reason="semantic_continuation",
    )


def payload() -> DiscordInboundMessage:
    return DiscordInboundMessage(
        connection_id="connection-1",
        deployment_id="deployment-ann",
        message_id="message-2",
        guild_id="guild-1",
        channel_id="channel-1",
        author_id="user-1",
        author_display_name="Alice",
        text="maybe try that again",
    )


def make_service(gateway: FakeGateway) -> ToolContinuationService:
    pending = action()
    return ToolContinuationService(
        FakeTopicMemory(topic(pending), decision(), (pending,)),  # type: ignore[arg-type]
        settings=Settings(
            environment="test",
            semantic_embedding_runtime_enabled=False,
        ),
        utility_gateway=gateway,  # type: ignore[arg-type]
    )


def test_default_plan_keeps_legacy_immediate_utility_behavior() -> None:
    gateway = FakeGateway()
    result = make_service(gateway).plan_turn(
        owner_id="owner-1",
        payload=payload(),
        character_card_id="card-ann",
        deployment_id="deployment-ann",
        assigned_tool_ids=("image.generate",),
    )

    assert gateway.calls == 1
    assert result.continuation_tool_ids == ("image.generate",)
    assert result.pending_action_evidence is None
    assert result.continuity_reason == "utility_tool_continuation"


def test_deferred_plan_emits_same_authorized_gray_evidence_without_utility() -> None:
    gateway = FakeGateway()
    result = make_service(gateway).plan_turn(
        owner_id="owner-1",
        payload=payload(),
        character_card_id="card-ann",
        deployment_id="deployment-ann",
        assigned_tool_ids=("image.generate",),
        defer_utility=True,
    )

    assert gateway.calls == 0
    assert result.continuation_tool_ids == ()
    assert result.pending_action_evidence is not None
    assert result.pending_action_evidence.tool_id == "image.generate"
    assert result.pending_action_evidence.continuation_strength == 0.35
    assert result.continuity_reason == "pending_action_gray_zone"
