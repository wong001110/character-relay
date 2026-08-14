from __future__ import annotations

from datetime import UTC, datetime, timedelta

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.config import Settings
from echo_masque.conversation_topic import (
    ConversationActScores,
    ConversationPendingAction,
    ConversationTopicSnapshot,
    TopicContinuityDecision,
)
from echo_masque.tool_continuation import (
    PendingActionContinuationEvidence,
    ToolContinuationService,
)
from echo_masque.utility_gateway_contracts import ToolContinuationUtilityDecision


class FakeGateway:
    def __init__(self, decision: ToolContinuationUtilityDecision) -> None:
        self.decision = decision
        self.calls = 0
        self.user_prompt = ""

    def invoke(self, capability: str, schema: object, **kwargs: object) -> tuple[object, object]:
        assert capability == "tool_continuation"
        assert schema is ToolContinuationUtilityDecision
        self.calls += 1
        self.user_prompt = str(kwargs["user_prompt"])
        return self.decision, object()


def payload(text: str = "maybe try that again") -> DiscordInboundMessage:
    return DiscordInboundMessage(
        connection_id="connection-1",
        deployment_id="deployment-ann",
        message_id="message-2",
        guild_id="guild-1",
        channel_id="channel-1",
        author_id="user-1",
        author_display_name="Alice",
        text=text,
    )


def pending(tool_id: str = "image.generate") -> ConversationPendingAction:
    now = datetime.now(UTC)
    return ConversationPendingAction(
        tool_id=tool_id,
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


def topic(*actions: ConversationPendingAction) -> ConversationTopicSnapshot:
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
        pending_actions=list(actions),
        status="active",
        message_count=2,
        capsule_version=2,
        last_message_id="message-1",
        started_at=now - timedelta(minutes=2),
        last_active_at=now,
    )


def continuity(
    *,
    retry: float = 0.35,
    cancel: float = 0.0,
    same_topic: bool = True,
) -> TopicContinuityDecision:
    return TopicContinuityDecision(
        same_topic=same_topic,
        topic_similarity=0.7,
        sparse_similarity=0.2,
        acts=ConversationActScores(
            retry_previous_action=retry,
            cancel_previous_action=cancel,
        ),
        reason="semantic_continuation",
    )


def service(gateway: FakeGateway) -> ToolContinuationService:
    return ToolContinuationService(
        object(),  # type: ignore[arg-type]
        settings=Settings(environment="test"),
        utility_gateway=gateway,  # type: ignore[arg-type]
    )


def test_gray_zone_builds_one_authorized_evidence_record_without_utility() -> None:
    action = pending()
    evidence = ToolContinuationService.pending_action_evidence(
        payload=payload(),
        active=topic(action),
        decision=continuity(retry=0.35),
        pending_before=(action,),
        assigned={"image.generate"},
    )

    assert evidence == PendingActionContinuationEvidence(
        tool_id="image.generate",
        current_message="maybe try that again",
        active_topic_label="image generation",
        active_topic_summary="The user was trying to generate one image.",
        pending_intent_summary="generate the image",
        pending_source_message_id="message-1",
        continuation_strength=0.35,
    )


def test_gray_evidence_never_grants_unassigned_or_ambiguous_action() -> None:
    image = pending("image.generate")
    reminder = pending("scheduler.remind")

    assert (
        ToolContinuationService.pending_action_evidence(
            payload=payload(),
            active=topic(image),
            decision=continuity(),
            pending_before=(image,),
            assigned=set(),
        )
        is None
    )
    assert (
        ToolContinuationService.pending_action_evidence(
            payload=payload(),
            active=topic(image, reminder),
            decision=continuity(),
            pending_before=(image, reminder),
            assigned={"image.generate", "scheduler.remind"},
        )
        is None
    )


def test_clear_retry_cancel_and_topic_switch_do_not_enter_gray_utility_path() -> None:
    action = pending()
    common = dict(
        payload=payload(),
        active=topic(action),
        pending_before=(action,),
        assigned={"image.generate"},
    )

    assert ToolContinuationService.pending_action_evidence(
        **common,
        decision=continuity(retry=0.50),
    ) is None
    assert ToolContinuationService.pending_action_evidence(
        **common,
        decision=continuity(retry=0.35, cancel=0.50),
    ) is None
    assert ToolContinuationService.pending_action_evidence(
        **common,
        decision=continuity(retry=0.35, same_topic=False),
    ) is None


def test_legacy_resolver_keeps_exact_tool_and_confidence_guard() -> None:
    evidence = PendingActionContinuationEvidence(
        tool_id="image.generate",
        current_message="maybe try that again",
        active_topic_label="image generation",
        active_topic_summary="The user was trying to generate one image.",
        pending_intent_summary="generate the image",
        pending_source_message_id="message-1",
        continuation_strength=0.35,
    )

    accepted_gateway = FakeGateway(
        ToolContinuationUtilityDecision(
            continue_action=True,
            tool_id="image.generate",
            confidence=0.91,
            reason_code="same_pending_action",
        )
    )
    accepted = service(accepted_gateway)
    assert accepted.resolve_pending_action_evidence(evidence) == "image.generate"
    assert accepted_gateway.calls == 1
    assert "Pending tool id: image.generate" in accepted_gateway.user_prompt

    wrong_tool = service(
        FakeGateway(
            ToolContinuationUtilityDecision(
                continue_action=True,
                tool_id="scheduler.remind",
                confidence=0.99,
                reason_code="invented_tool",
            )
        )
    )
    assert wrong_tool.resolve_pending_action_evidence(evidence) == ""

    low_confidence = service(
        FakeGateway(
            ToolContinuationUtilityDecision(
                continue_action=True,
                tool_id="image.generate",
                confidence=0.60,
                reason_code="uncertain",
            )
        )
    )
    assert low_confidence.resolve_pending_action_evidence(evidence) == ""
