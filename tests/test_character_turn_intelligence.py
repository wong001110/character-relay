from __future__ import annotations

from echo_masque.character_turn_intelligence import CharacterTurnIntelligenceCoordinator
from echo_masque.knowledge_route_gate import KnowledgeRouteAssessment
from echo_masque.tool_continuation import PendingActionContinuationEvidence
from echo_masque.turn_intelligence import (
    TurnIntelligenceFieldStatus,
    TurnIntelligenceResult,
    TurnKnowledgeDecision,
    TurnPendingActionDecision,
)


def knowledge(
    route: str,
    *,
    fallback: bool = False,
    contextual: bool = False,
) -> KnowledgeRouteAssessment:
    return KnowledgeRouteAssessment(
        status="matched" if fallback else "not_relevant",
        route=route,  # type: ignore[arg-type]
        fallback_should_retrieve=fallback,
        eligible_base_count=1,
        best_sparse_score=0.01,
        best_dense_score=0.50,
        route_labels=("Docs: runtime reference",),
        current_message="what about that?",
        normalized_query="what about that?",
        is_contextual=contextual,
    )


def pending() -> PendingActionContinuationEvidence:
    return PendingActionContinuationEvidence(
        tool_id="image.generate",
        current_message="maybe try that again",
        active_topic_label="image generation",
        active_topic_summary="The user was trying to generate one image.",
        pending_intent_summary="generate the image",
        pending_source_message_id="message-1",
        continuation_strength=0.35,
    )


def statuses(
    *,
    knowledge_accepted: bool,
    pending_accepted: bool,
) -> dict[str, TurnIntelligenceFieldStatus]:
    return {
        "topic": TurnIntelligenceFieldStatus(False, False, "not_requested"),
        "speaker": TurnIntelligenceFieldStatus(False, False, "not_requested"),
        "knowledge": TurnIntelligenceFieldStatus(
            True,
            knowledge_accepted,
            "accepted" if knowledge_accepted else "low_confidence",
        ),
        "pending_action": TurnIntelligenceFieldStatus(
            True,
            pending_accepted,
            "accepted" if pending_accepted else "wrong_tool_id",
        ),
    }  # type: ignore[return-value]


class FakeTurnIntelligence:
    def __init__(self, result: TurnIntelligenceResult) -> None:
        self.result = result
        self.calls = 0
        self.kwargs: dict[str, object] = {}

    def decide(self, **kwargs: object) -> TurnIntelligenceResult:
        self.calls += 1
        self.kwargs = kwargs
        return self.result


def result(
    *,
    knowledge_route: str | None,
    pending_continue: bool | None,
    pending_tool_id: str = "image.generate",
    knowledge_accepted: bool = True,
    pending_accepted: bool = True,
) -> TurnIntelligenceResult:
    return TurnIntelligenceResult(
        topic=None,
        speaker=None,
        knowledge=(
            TurnKnowledgeDecision(
                route=knowledge_route,  # type: ignore[arg-type]
                confidence=0.9,
                reason_code="knowledge_gray_zone",
            )
            if knowledge_route is not None
            else None
        ),
        pending_action=(
            TurnPendingActionDecision(
                continue_action=pending_continue,
                tool_id=pending_tool_id if pending_continue else "",
                confidence=0.9,
                reason_code="pending_gray_zone",
            )
            if pending_continue is not None
            else None
        ),
        status=statuses(
            knowledge_accepted=knowledge_accepted,
            pending_accepted=pending_accepted,
        ),
    )


def coordinator(fake: FakeTurnIntelligence) -> CharacterTurnIntelligenceCoordinator:
    return CharacterTurnIntelligenceCoordinator(fake)  # type: ignore[arg-type]


def test_unambiguous_knowledge_never_calls_turn_intelligence() -> None:
    fake = FakeTurnIntelligence(
        result(knowledge_route="off", pending_continue=None)
    )
    outcome = coordinator(fake).decide(
        current_burst="clear question",
        current_knowledge=knowledge("on", fallback=True),
        contextual_knowledge=knowledge("gray", contextual=True),
        pending_action=None,
    )

    assert fake.calls == 0
    assert outcome.requested_tasks == ()
    assert outcome.knowledge_route == "current"
    assert outcome.knowledge_source == "deterministic"
    assert outcome.pending_action_source == "not_requested"


def test_two_gray_zones_share_exactly_one_turn_intelligence_call() -> None:
    fake = FakeTurnIntelligence(
        result(knowledge_route="contextual", pending_continue=True)
    )
    outcome = coordinator(fake).decide(
        current_burst="maybe try that again",
        current_knowledge=knowledge("gray", fallback=False),
        contextual_knowledge=knowledge("gray", fallback=True, contextual=True),
        pending_action=pending(),
    )

    assert fake.calls == 1
    assert outcome.requested_tasks == ("knowledge", "pending_action")
    assert fake.kwargs["requested_tasks"] == ("knowledge", "pending_action")
    assert fake.kwargs["pending_tool_id"] == "image.generate"
    assert outcome.knowledge_route == "contextual"
    assert outcome.knowledge_source == "turn_intelligence"
    assert outcome.pending_action_continue is True
    assert outcome.pending_action_tool_id == "image.generate"
    assert outcome.pending_action_source == "turn_intelligence"


def test_invalid_pending_field_does_not_discard_valid_knowledge() -> None:
    fake = FakeTurnIntelligence(
        result(
            knowledge_route="current",
            pending_continue=None,
            knowledge_accepted=True,
            pending_accepted=False,
        )
    )
    outcome = coordinator(fake).decide(
        current_burst="maybe continue",
        current_knowledge=knowledge("gray", fallback=False),
        contextual_knowledge=knowledge("off", contextual=True),
        pending_action=pending(),
    )

    assert fake.calls == 1
    assert outcome.knowledge_route == "current"
    assert outcome.knowledge_source == "turn_intelligence"
    assert outcome.pending_action_continue is None
    assert outcome.pending_action_source == "legacy_fallback_required"


def test_disallowed_knowledge_route_falls_back_without_poisoning_pending_action() -> None:
    # Current is deterministically OFF, so a gray contextual decision may only choose OFF or
    # CONTEXTUAL. A model-returned CURRENT route is rejected locally.
    fake = FakeTurnIntelligence(
        result(knowledge_route="current", pending_continue=False)
    )
    outcome = coordinator(fake).decide(
        current_burst="maybe continue",
        current_knowledge=knowledge("off", fallback=False),
        contextual_knowledge=knowledge("gray", fallback=True, contextual=True),
        pending_action=pending(),
    )

    assert fake.calls == 1
    assert outcome.knowledge_route is None
    assert outcome.knowledge_fallback_required is True
    assert outcome.pending_action_continue is False
    assert outcome.pending_action_source == "turn_intelligence"
    assert outcome.pending_action_fallback_required is False
