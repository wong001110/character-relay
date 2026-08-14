from __future__ import annotations

from echo_masque.config import Settings
from echo_masque.participation_tiebreak import (
    ParticipationTieBreakService,
    ParticipationTieCandidate,
)
from echo_masque.persistence import Database
from echo_masque.persistence.repository import Repository
from echo_masque.utility_gateway_contracts import ParticipationUtilityDecision


class CapturingGateway:
    def __init__(self) -> None:
        self.calls = 0
        self.system_prompt = ""

    def invoke(self, capability: str, schema: object, **kwargs: object) -> tuple[object, object]:
        assert capability == "participation_tiebreak"
        assert schema is ParticipationUtilityDecision
        self.calls += 1
        self.system_prompt = str(kwargs["system_prompt"])
        return (
            ParticipationUtilityDecision(
                deployment_id="deployment-a",
                confidence=0.91,
                reason_code="best_semantic_fit",
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


def test_participation_tiebreak_declares_exact_json_contract_to_first_provider() -> None:
    gateway = CapturingGateway()
    result = _service(gateway).apply(
        message="這大雷雨的還有太陽",
        candidates=_candidates(),
    )

    assert result.used is True
    assert gateway.calls == 1
    assert '"deployment_id"' in gateway.system_prompt
    assert '"confidence"' in gateway.system_prompt
    assert '"reason_code"' in gateway.system_prompt
    assert "no markdown or prose" in gateway.system_prompt
    assert "Never use selected_deployment_id, best_deployment_id" in gateway.system_prompt


def test_participation_tiebreak_contract_allows_explicit_abstention() -> None:
    gateway = CapturingGateway()
    _service(gateway).apply(message="weather", candidates=_candidates())

    assert 'deployment_id=""' in gateway.system_prompt
    assert "confidence below 0.72" in gateway.system_prompt
