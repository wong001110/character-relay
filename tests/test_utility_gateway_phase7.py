from __future__ import annotations

from datetime import UTC, datetime, timedelta

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.config import Settings
from echo_masque.conversation_topic import (
    ConversationActScores,
    ConversationPendingAction,
    ConversationTopicMemoryService,
    ConversationTopicSnapshot,
    TopicContinuityDecision,
)
from echo_masque.participation_tiebreak import (
    ParticipationTieBreakService,
    ParticipationTieCandidate,
)
from echo_masque.persistence import Database
from echo_masque.persistence.conversation_topic_repository import ConversationTopicRepository
from echo_masque.persistence.repository import Repository
from echo_masque.tool_continuation import ToolContinuationService
from echo_masque.utility_gateway_contracts import (
    ParticipationUtilityDecision,
    ToolContinuationUtilityDecision,
    UtilityGatewayUnavailable,
)


def settings() -> Settings:
    return Settings(
        environment="test",
        database_url="sqlite://",
        semantic_embedding_runtime_enabled=False,
    )


class ParticipationGateway:
    def __init__(self, deployment_id: str = "deployment-a", confidence: float = 0.91) -> None:
        self.deployment_id = deployment_id
        self.confidence = confidence
        self.calls = 0

    def invoke(self, capability: str, schema: object, **_: object) -> tuple[object, object]:
        del schema
        assert capability == "participation_tiebreak"
        self.calls += 1
        return (
            ParticipationUtilityDecision(
                deployment_id=self.deployment_id,
                confidence=self.confidence,
                reason_code="best_fit",
            ),
            object(),
        )


class ContinuationGateway:
    def __init__(
        self,
        *,
        tool_id: str = "scheduler.remind",
        continue_action: bool = True,
        confidence: float = 0.91,
        unavailable: bool = False,
    ) -> None:
        self.tool_id = tool_id
        self.continue_action = continue_action
        self.confidence = confidence
        self.unavailable = unavailable
        self.calls = 0

    def invoke(self, capability: str, schema: object, **_: object) -> tuple[object, object]:
        del schema
        assert capability == "tool_continuation"
        self.calls += 1
        if self.unavailable:
            raise UtilityGatewayUnavailable("no_eligible_provider")
        return (
            ToolContinuationUtilityDecision(
                continue_action=self.continue_action,
                tool_id=self.tool_id,
                confidence=self.confidence,
                reason_code="same_pending_action",
            ),
            object(),
        )


def participation_service(gateway: ParticipationGateway) -> ParticipationTieBreakService:
    database = Database("sqlite://")
    database.initialize()
    return ParticipationTieBreakService(
        Repository(database),
        settings(),
        utility_gateway=gateway,  # type: ignore[arg-type]
    )


def candidates() -> list[ParticipationTieCandidate]:
    return [
        ParticipationTieCandidate(
            deployment_id="deployment-a",
            character_card_id="card-a",
            display_name="Ann",
            semantic_summary="Calm technical character interested in launch planning.",
            relevance=0.82,
        ),
        ParticipationTieCandidate(
            deployment_id="deployment-b",
            character_card_id="card-b",
            display_name="Ning",
            semantic_summary="Social character interested in launch planning and group chat.",
            relevance=0.80,
        ),
    ]


def test_participation_tiebreak_only_demotes_non_selected_candidate() -> None:
    gateway = ParticipationGateway("deployment-a")
    service = participation_service(gateway)
    original = {item.deployment_id: item.relevance for item in candidates()}

    result = service.apply(message="What do you think about the launch plan?", candidates=candidates())

    assert result.used is True
    assert result.selected_deployment_id == "deployment-a"
    assert result.adjusted_relevance["deployment-a"] == original["deployment-a"]
    assert result.adjusted_relevance["deployment-b"] < original["deployment-b"]
    assert all(
        result.adjusted_relevance[key] <= relevance
        for key, relevance in original.items()
    )
    assert gateway.calls == 1


def test_participation_tiebreak_skips_clear_e5_winner() -> None:
    gateway = ParticipationGateway("deployment-a")
    service = participation_service(gateway)
    values = candidates()
    values[0] = ParticipationTieCandidate(
        deployment_id="deployment-a",
        character_card_id="card-a",
        display_name="Ann",
        semantic_summary="Launch specialist.",
        relevance=0.88,
    )
    values[1] = ParticipationTieCandidate(
        deployment_id="deployment-b",
        character_card_id="card-b",
        display_name="Ning",
        semantic_summary="General social character.",
        relevance=0.78,
    )

    result = service.apply(message="launch", candidates=values)

    assert result.used is False
    assert result.reason == "clear_e5_winner"
    assert gateway.calls == 0


def test_participation_tiebreak_rejects_unknown_or_low_confidence_choice() -> None:
    unknown = ParticipationGateway("deployment-x")
    result = participation_service(unknown).apply(message="launch", candidates=candidates())
    assert result.used is False
    assert result.adjusted_relevance == {"deployment-a": 0.82, "deployment-b": 0.80}

    low_confidence = ParticipationGateway("deployment-a", confidence=0.40)
    result = participation_service(low_confidence).apply(
        message="launch",
        candidates=candidates(),
    )
    assert result.used is False
    assert result.adjusted_relevance == {"deployment-a": 0.82, "deployment-b": 0.80}


def topic_service(gateway: ContinuationGateway) -> ToolContinuationService:
    database = Database("sqlite://")
    database.initialize()
    memory = ConversationTopicMemoryService(
        ConversationTopicRepository(database),
        settings=settings(),
        semantic_enabled=False,
    )
    return ToolContinuationService(
        memory,
        settings=settings(),
        utility_gateway=gateway,  # type: ignore[arg-type]
    )


def payload(text: str = "can we do that now?") -> DiscordInboundMessage:
    return DiscordInboundMessage(
        connection_id="connection-1",
        deployment_id="deployment-a",
        message_id="message-2",
        guild_id="guild-1",
        channel_id="channel-1",
        author_id="user-1",
        author_display_name="Juen",
        text=text,
    )


def pending(tool_id: str = "scheduler.remind") -> ConversationPendingAction:
    now = datetime.now(UTC)
    return ConversationPendingAction(
        tool_id=tool_id,
        state="blocked_unavailable",
        requested_by_user_id="user-1",
        target_character_card_id="card-a",
        deployment_id="deployment-a",
        source_message_id="message-1",
        intent_summary="Remind me when the launch begins.",
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=1),
    )


def snapshot(actions: list[ConversationPendingAction]) -> ConversationTopicSnapshot:
    now = datetime.now(UTC)
    return ConversationTopicSnapshot(
        id="topic-1",
        owner_id="owner-1",
        platform="discord",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="",
        topic_label="Launch reminder",
        summary="The user asked for a launch reminder but the Tool was unavailable.",
        keywords=["launch", "reminder"],
        open_loops=["Create the launch reminder when available."],
        pending_actions=actions,
        participants=[{"user_id": "user-1", "display_name": "Juen"}],
        status="active",
        message_count=2,
        capsule_version=1,
        last_message_id="message-1",
        started_at=now - timedelta(minutes=5),
        last_active_at=now,
    )


def continuity(
    *,
    continue_score: float = 0.35,
    cancel_score: float = 0.0,
    same_topic: bool = True,
) -> TopicContinuityDecision:
    return TopicContinuityDecision(
        same_topic=same_topic,
        topic_similarity=0.51,
        sparse_similarity=0.12,
        acts=ConversationActScores(
            continue_previous_topic=continue_score,
            cancel_previous_action=cancel_score,
        ),
        reason="semantic_continuation",
    )


def test_tool_continuation_utility_only_resolves_one_assigned_gray_zone_action() -> None:
    gateway = ContinuationGateway()
    service = topic_service(gateway)
    action = pending()

    selected = service._utility_continuation(
        payload=payload(),
        active=snapshot([action]),
        decision=continuity(),
        pending_before=(action,),
        assigned={"scheduler.remind"},
    )

    assert selected == "scheduler.remind"
    assert gateway.calls == 1


def test_tool_continuation_refuses_multi_action_unassigned_cancel_and_wrong_tool() -> None:
    gateway = ContinuationGateway()
    service = topic_service(gateway)
    reminder = pending()
    poll = pending("discord.create_poll")

    assert (
        service._utility_continuation(
            payload=payload(),
            active=snapshot([reminder, poll]),
            decision=continuity(),
            pending_before=(reminder, poll),
            assigned={"scheduler.remind", "discord.create_poll"},
        )
        == ""
    )
    assert (
        service._utility_continuation(
            payload=payload(),
            active=snapshot([reminder]),
            decision=continuity(),
            pending_before=(reminder,),
            assigned=set(),
        )
        == ""
    )
    assert (
        service._utility_continuation(
            payload=payload("cancel that"),
            active=snapshot([reminder]),
            decision=continuity(cancel_score=0.60),
            pending_before=(reminder,),
            assigned={"scheduler.remind"},
        )
        == ""
    )
    assert gateway.calls == 0

    wrong_tool = ContinuationGateway(tool_id="discord.create_poll")
    assert (
        topic_service(wrong_tool)._utility_continuation(
            payload=payload(),
            active=snapshot([reminder]),
            decision=continuity(),
            pending_before=(reminder,),
            assigned={"scheduler.remind"},
        )
        == ""
    )


def test_tool_continuation_utility_unavailable_keeps_existing_runtime_path() -> None:
    gateway = ContinuationGateway(unavailable=True)
    service = topic_service(gateway)
    action = pending()

    selected = service._utility_continuation(
        payload=payload(),
        active=snapshot([action]),
        decision=continuity(),
        pending_before=(action,),
        assigned={"scheduler.remind"},
    )

    assert selected == ""
    assert gateway.calls == 1
