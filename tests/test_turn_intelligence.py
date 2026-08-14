from __future__ import annotations

from typing import Any

from echo_masque.turn_intelligence import (
    TurnIntelligenceEnvelope,
    TurnIntelligenceService,
)


class FakeGateway:
    def __init__(self, envelope: TurnIntelligenceEnvelope) -> None:
        self.envelope = envelope
        self.calls = 0
        self.capability = ""
        self.system_prompt = ""
        self.user_prompt = ""

    def invoke(self, capability: str, schema: object, **kwargs: object) -> tuple[Any, Any]:
        assert schema is TurnIntelligenceEnvelope
        self.calls += 1
        self.capability = capability
        self.system_prompt = str(kwargs["system_prompt"])
        self.user_prompt = str(kwargs["user_prompt"])
        return self.envelope, None


def envelope(**updates: object) -> TurnIntelligenceEnvelope:
    value: dict[str, object] = {
        "schema_version": "turn-intelligence-v1",
        "requested_tasks": ("topic", "speaker", "knowledge", "pending_action"),
        "topic": {
            "decision": "continue",
            "confidence": 0.91,
            "reason_code": "same_discussion",
        },
        "speaker": {
            "deployment_id": "ann",
            "confidence": 0.84,
            "reason_code": "best_context_fit",
        },
        "knowledge": {
            "route": "contextual",
            "confidence": 0.79,
            "reason_code": "carryover_needed",
        },
        "pending_action": {
            "continue_action": True,
            "tool_id": "image.generate",
            "confidence": 0.88,
            "reason_code": "retry_request",
        },
    }
    value.update(updates)
    return TurnIntelligenceEnvelope.model_validate(value)


def test_one_call_can_resolve_multiple_requested_gray_zones() -> None:
    gateway = FakeGateway(envelope())
    result = TurnIntelligenceService(gateway).decide(  # type: ignore[arg-type]
        requested_tasks=("topic", "speaker", "knowledge", "pending_action"),
        current_burst="刚才那个再试试看, Ann 你觉得呢?",
        active_topic="image generation",
        topic_evidence="E5 continuity gray zone",
        speaker_candidates=(("ann", "Ann", "eligible; top final candidate"),),
        knowledge_evidence="current=0.39 contextual=0.55",
        pending_tool_id="image.generate",
        pending_action_evidence="one already-authorized pending action",
    )

    assert gateway.calls == 1
    assert gateway.capability == "semantic_judge"
    assert result.topic is not None and result.topic.decision == "continue"
    assert result.speaker is not None and result.speaker.deployment_id == "ann"
    assert result.knowledge is not None and result.knowledge.route == "contextual"
    assert result.pending_action is not None and result.pending_action.continue_action is True
    assert all(item.accepted for item in result.status.values())
    assert "JSON Schema:" in gateway.system_prompt
    assert "no markdown" in gateway.system_prompt


def test_invalid_speaker_field_does_not_discard_valid_topic_or_knowledge() -> None:
    gateway = FakeGateway(
        envelope(
            speaker={
                "deployment_id": "ann",
                "confidence": "very sure",
                "reason_code": "bad_type",
            },
            pending_action=None,
        )
    )
    result = TurnIntelligenceService(gateway).decide(  # type: ignore[arg-type]
        requested_tasks=("topic", "speaker", "knowledge"),
        current_burst="继续刚才那个",
        active_topic="deployment",
        speaker_candidates=(("ann", "Ann", "eligible"),),
        knowledge_evidence="current=0.45 contextual=0.53",
    )

    assert gateway.calls == 1
    assert result.topic is not None
    assert result.knowledge is not None
    assert result.speaker is None
    assert result.status["topic"].accepted is True
    assert result.status["knowledge"].accepted is True
    assert result.status["speaker"].accepted is False
    assert result.status["speaker"].reason.startswith("schema_error:")
    assert result.status["pending_action"].reason == "not_requested"


def test_unknown_speaker_and_wrong_pending_tool_are_rejected_by_runtime() -> None:
    gateway = FakeGateway(
        envelope(
            requested_tasks=("speaker", "pending_action"),
            topic=None,
            knowledge=None,
            speaker={
                "deployment_id": "not-supplied",
                "confidence": 0.99,
                "reason_code": "invented_candidate",
            },
            pending_action={
                "continue_action": True,
                "tool_id": "dangerous.other.tool",
                "confidence": 0.99,
                "reason_code": "wrong_tool",
            },
        )
    )
    result = TurnIntelligenceService(gateway).decide(  # type: ignore[arg-type]
        requested_tasks=("speaker", "pending_action"),
        current_burst="再试一次",
        speaker_candidates=(("ann", "Ann", "eligible"),),
        pending_tool_id="image.generate",
        pending_action_evidence="one authorized action",
    )

    assert result.speaker is None
    assert result.pending_action is None
    assert result.status["speaker"].reason == "unknown_deployment"
    assert result.status["pending_action"].reason == "wrong_tool_id"


def test_no_requested_tasks_skips_utility_entirely() -> None:
    no_tasks = envelope(
        requested_tasks=(),
        topic=None,
        speaker=None,
        knowledge=None,
        pending_action=None,
    )
    gateway = FakeGateway(no_tasks)
    result = TurnIntelligenceService(gateway).decide(  # type: ignore[arg-type]
        requested_tasks=(),
        current_burst="clear turn",
    )

    assert gateway.calls == 0
    assert result.inference is None
    assert all(item.reason == "not_requested" for item in result.status.values())