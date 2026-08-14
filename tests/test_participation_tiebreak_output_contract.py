from __future__ import annotations

from echo_masque.config import Settings
from echo_masque.participation_tiebreak import (
    ParticipationTieBreakService,
    ParticipationTieCandidate,
)
from echo_masque.persistence import Database
from echo_masque.persistence.repository import Repository
from echo_masque.turn_intelligence import TurnIntelligenceEnvelope


class CapturingGateway:
    def __init__(self, deployment_id: str = "deployment-a", confidence: float = 0.91) -> None:
        self.calls = 0
        self.system_prompt = ""
        self.user_prompt = ""
        self.deployment_id = deployment_id
        self.confidence = confidence

    def invoke(self, capability: str, schema: object, **kwargs: object) -> tuple[object, object]:
        assert capability == "participation_tiebreak"
        assert schema is TurnIntelligenceEnvelope
        self.calls += 1
        self.system_prompt = str(kwargs["system_prompt"])
        self.user_prompt = str(kwargs["user_prompt"])
        return (
            TurnIntelligenceEnvelope(
                schema_version="turn-intelligence-v1",
                requested_tasks=("speaker",),
                topic=None,
                speaker={
                    "deployment_id": self.deployment_id,
                    "confidence": self.confidence,
                    "reason_code": "best_semantic_fit",
                },
                knowledge=None,
                pending_action=None,
            ),
            object(),
        )


def _service(gateway: CapturingGateway) -> ParticipationTieBreakService:
    database = Database("sqlite://")
    database.initialize()
    settings = Settings(
        environment="test",
        database_url="sqlite://",
        semantic_embedding_runtime_enabled=False,
    )
    return ParticipationTieBreakService(
        Repository(database),
        settings,
        utility_gateway=gateway,  # type: ignore[arg-type]
    )


def _candidates() -> list[ParticipationTieCandidate]:
    return [
        ParticipationTieCandidate(
            deployment_id="deployment-a",
            character_card_id="card-a",
            display_name="Ning",
            semantic_summary="Quiet designer who likes rain and atmospheric details.",
            relevance=0.786976,
        ),
        ParticipationTieCandidate(
            deployment_id="deployment-b",
            character_card_id="card-b",
            display_name="Ann",
            semantic_summary="Quiet engineer who likes rain and ambient environments.",
            relevance=0.786739,
        ),
    ]


def test_participation_tiebreak_uses_exact_turn_intelligence_contract() -> None:
    gateway = CapturingGateway()
    result = _service(gateway).apply(
        message="這大雷雨的還有太陽",
        candidates=_candidates(),
    )

    assert result.used is True
    assert gateway.calls == 1
    assert "turn-intelligence-v1" in gateway.system_prompt
    assert "deployment_id, confidence, reason_code" in gateway.system_prompt
    assert "Use an empty deployment_id to abstain" in gateway.system_prompt
    assert "no markdown" in gateway.system_prompt
    assert "requested_tasks=speaker" in gateway.user_prompt
    assert "deployment_id=deployment-a" in gateway.user_prompt
    assert "deployment_id=deployment-b" in gateway.user_prompt


def test_participation_tiebreak_contract_allows_explicit_abstention() -> None:
    gateway = CapturingGateway(deployment_id="", confidence=0.40)
    result = _service(gateway).apply(message="weather", candidates=_candidates())

    assert gateway.calls == 1
    assert result.used is False
    assert result.reason == "utility_rejected"
    assert "Use an empty deployment_id to abstain" in gateway.system_prompt
