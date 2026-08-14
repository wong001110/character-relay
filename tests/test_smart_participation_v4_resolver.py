from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi import FastAPI, HTTPException
from pydantic import SecretStr
from starlette.requests import Request

from echo_masque.api.routes.smart_participation_v4 import resolve_smart_participation_v4
from echo_masque.api.smart_participation_v4_schemas import (
    SmartParticipationBurstMessage,
    SmartParticipationResolveCandidate,
    SmartParticipationResolveRequest,
)
from echo_masque.config import Settings
from echo_masque.semantic_participation import SemanticParticipationScore


@dataclass
class FakeDeployment:
    id: str
    owner_id: str
    character_card_id: str
    participation_mode: str


class FakeDeploymentRepository:
    def __init__(self, records: list[FakeDeployment]) -> None:
        self.records = records
        self.calls: list[tuple[str, str]] = []

    def list_connector_deployments(
        self,
        *,
        platform: str,
        connection_id: str,
    ) -> list[FakeDeployment]:
        self.calls.append((platform, connection_id))
        return self.records


class FakeSemanticService:
    enabled = True

    def __init__(self) -> None:
        self.message = ""
        self.deployments: list[tuple[str, str, str]] = []

    def score(
        self,
        *,
        message: str,
        deployments: list[tuple[str, str, str]],
    ) -> tuple[str, int, list[SemanticParticipationScore]]:
        self.message = message
        self.deployments = deployments
        return (
            "fake-e5",
            3,
            [
                SemanticParticipationScore(
                    deployment_id=deployment_id,
                    character_card_id=character_card_id,
                    relevance=0.81,
                    profile_ready=True,
                )
                for deployment_id, _owner_id, character_card_id in deployments
            ],
        )


def request_for(
    deployments: FakeDeploymentRepository,
    semantic: FakeSemanticService,
) -> Request:
    app = FastAPI()
    app.state.settings = Settings(
        environment="test",
        connector_shared_secret=SecretStr("connector-secret"),
    )
    app.state.deployment_repository = deployments
    app.state.semantic_participation_service = semantic
    return Request({"type": "http", "app": app, "headers": []})


def test_resolver_scores_only_connector_eligible_smart_candidates() -> None:
    records = FakeDeploymentRepository(
        [
            FakeDeployment("ann", "owner-1", "card-ann", "smart"),
            FakeDeployment("ning", "owner-1", "card-ning", "smart"),
            FakeDeployment("zhi", "owner-1", "card-zhi", "mention_only"),
        ]
    )
    semantic = FakeSemanticService()
    payload = SmartParticipationResolveRequest(
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        message_id="message-2",
        author_id="user-1",
        burst_id="burst-1",
        burst_messages=[
            SmartParticipationBurstMessage(
                message_id="message-1",
                author_id="user-1",
                author_display_name="Alice",
                text="I think",
            ),
            SmartParticipationBurstMessage(
                message_id="message-2",
                author_id="user-1",
                author_display_name="Alice",
                text="the photography topic is interesting",
            ),
        ],
        candidates=[
            SmartParticipationResolveCandidate(
                deployment_id="ann",
                eligible=True,
                deterministic_score=4,
                minimum_score=5,
            ),
            SmartParticipationResolveCandidate(
                deployment_id="ning",
                eligible=False,
                deterministic_score=3,
                minimum_score=5,
            ),
            SmartParticipationResolveCandidate(
                deployment_id="zhi",
                eligible=True,
                deterministic_score=7,
                minimum_score=5,
            ),
        ],
    )

    result = resolve_smart_participation_v4(
        payload,
        request_for(records, semantic),
        "Bearer connector-secret",
    )

    assert records.calls == [("discord", "connection-1")]
    assert semantic.deployments == [("ann", "owner-1", "card-ann")]
    assert semantic.message == "Alice: I think\nAlice: the photography topic is interesting"
    assert result.available is True
    assert result.burst_id == "burst-1"
    assert result.burst_message_count == 2
    assert result.graph_used is False
    assert result.learned_state_used is False
    assert result.utility_used is False
    assert result.speaker_plan == []
    by_id = {item.deployment_id: item for item in result.candidates}
    assert by_id["ann"].raw_e5_relevance == 0.81
    assert by_id["ann"].profile_ready is True
    assert by_id["ning"].raw_e5_relevance == 0.0
    assert by_id["zhi"].raw_e5_relevance == 0.0


def test_resolver_does_not_expose_unknown_deployment_metadata() -> None:
    records = FakeDeploymentRepository(
        [FakeDeployment("ann", "owner-1", "card-ann", "smart")]
    )
    semantic = FakeSemanticService()
    payload = SmartParticipationResolveRequest(
        connection_id="connection-1",
        message="ordinary group message",
        candidates=[
            SmartParticipationResolveCandidate(
                deployment_id="not-on-this-connector",
                eligible=True,
            )
        ],
    )

    result = resolve_smart_participation_v4(
        payload,
        request_for(records, semantic),
        "Bearer connector-secret",
    )

    assert result.available is False
    assert result.reason == "no_eligible_smart_deployments"
    assert semantic.deployments == []
    assert result.candidates[0].character_card_id == ""
    assert result.candidates[0].profile_ready is False


def test_resolver_rejects_invalid_connector_credential() -> None:
    records = FakeDeploymentRepository([])
    semantic = FakeSemanticService()
    payload = SmartParticipationResolveRequest(
        connection_id="connection-1",
        message="hello",
        candidates=[SmartParticipationResolveCandidate(deployment_id="ann")],
    )

    with pytest.raises(HTTPException) as caught:
        resolve_smart_participation_v4(
            payload,
            request_for(records, semantic),
            "Bearer wrong-secret",
        )

    assert caught.value.status_code == 401
