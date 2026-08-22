from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr
from pytest import MonkeyPatch

from echo_masque.api import create_app
from echo_masque.api.routes import smart_participation_vnext
from echo_masque.config import Settings
from echo_masque.current_turn_belief_v3 import (
    CurrentTurnBeliefRevisionService,
    CurrentTurnClaimExtraction,
)

ADMIN_EMAIL = "participation-v3@example.com"
ADMIN_PASSWORD = "ParticipationV3Admin2026!"
CONNECTOR_SECRET = "participation-v3-connector-secret"


def settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        browser_tools_enabled=False,
        legacy_local_user_enabled=False,
        bootstrap_admin_email=ADMIN_EMAIL,
        bootstrap_admin_password=SecretStr(ADMIN_PASSWORD),
        bootstrap_admin_display_name="Participation V3 Admin",
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
        connector_shared_secret=SecretStr(CONNECTOR_SECRET),
    )


def _login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text


def _seed_smart_deployment(client: TestClient) -> tuple[str, str]:
    _login(client)
    character = client.post(
        "/api/characters",
        json={
            "target_id": "demo-stable",
            "display_name": "Ann",
            "subtitle": "Participation v3 fixture",
            "subject_type": "companion",
            "persona_summary": "Ann is a careful group-chat participant.",
            "traits": ["careful"],
            "tags": ["participation"],
            "expected_tone": "Concise and grounded.",
            "forbidden_behaviors": ["invent private memories"],
            "memory_summary": "Use supplied conversation evidence only.",
            "preferred_suites": ["identity_integrity"],
            "portrait_variant": "lavender",
        },
    )
    assert character.status_code == 201, character.text
    connection = client.post(
        "/api/connections",
        json={
            "platform": "discord",
            "display_name": "Participation Discord",
            "connection_mode": "managed",
            "external_account_id": "",
            "status": "connected",
            "metadata": {},
        },
    )
    assert connection.status_code == 201, connection.text
    deployment = client.post(
        "/api/deployments",
        json={
            "character_card_id": character.json()["id"],
            "connection_id": connection.json()["id"],
            "workspace_id": "guild-1",
            "workspace_name": "Participation Guild",
            "channel_id": "channel-1",
            "channel_name": "general",
            "thread_id": "",
            "thread_name": "",
            "participation_mode": "smart",
            "memory_scope": "channel_isolated",
            "version_label": "Current",
            "sticker_count": 0,
            "status": "active",
        },
    )
    assert deployment.status_code == 201, deployment.text
    return str(connection.json()["id"]), str(deployment.json()["id"])


def _resolve_payload(connection_id: str, deployment_id: str) -> dict[str, object]:
    return {
        "connection_id": connection_id,
        "guild_id": "guild-1",
        "channel_id": "channel-1",
        "message_id": "message-1",
        "author_id": "user-1",
        "message": "Ann, what do you think about this release plan?",
        "burst_id": "burst-1",
        "burst_messages": [
            {
                "message_id": "message-1",
                "author_id": "user-1",
                "author_display_name": "Juen",
                "text": "Ann, what do you think about this release plan?",
            }
        ],
        "candidates": [
            {
                "deployment_id": deployment_id,
                "eligible": True,
                "deterministic_score": 5.0,
                "minimum_score": 0.0,
                "signals": {"name_match": 1.0},
            }
        ],
    }


def _connector_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {CONNECTOR_SECRET}"}


def _assert_authoritative_empty_plan(body: dict[str, object], reason: str) -> None:
    assert body["resolver_version"] == "conversation-intelligence-v3"
    assert body["reason"] == reason
    assert body["speaker_plan_authoritative"] is True
    assert body["speaker_plan"] == []
    assert body["reply_targets"] == []
    assert body["context_sufficiency"] == {}


def test_connector_resolve_returns_complete_authoritative_v3_contract(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "resolve.db")))
    connection_id, deployment_id = _seed_smart_deployment(client)

    response = client.post(
        "/api/smart-participation/resolve",
        headers=_connector_headers(),
        json=_resolve_payload(connection_id, deployment_id),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["resolver_version"] == "conversation-intelligence-v3"
    assert body["speaker_plan_authoritative"] is True
    assert body["segmentation_used"] is True
    assert body["conversation_segments"]
    assert body["conversation_segments"][0]["id"]
    assert body["conversation_segments"][0]["message_ids"] == ["message-1"]
    assert body["speaker_plan"] == [
        {
            "deployment_id": deployment_id,
            "turn_role": "participant",
            "reason": "v3_evidence_score",
            "guidance": body["speaker_plan"][0]["guidance"],
        }
    ]
    assert body["reply_targets"][0]["deployment_id"] == deployment_id
    assert body["reply_targets"][0]["segment_id"] == body["conversation_segments"][0]["id"]
    assert body["context_sufficiency"][deployment_id] in {
        "sufficient",
        "insufficient_nonblocking",
        "unresolved",
    }
    assert body["media_grounding_level"] == "context_only"
    assert body["media_grounding_reason"] == "no_media_dependency"


def test_cross_destination_candidate_is_not_accepted(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "scope.db")))
    connection_id, deployment_id = _seed_smart_deployment(client)
    cases = (
        {"guild_id": "guild-other"},
        {"channel_id": "channel-other"},
        {"thread_id": "thread-other"},
    )

    for destination_override in cases:
        payload = _resolve_payload(connection_id, deployment_id)
        payload.update(destination_override)
        response = client.post(
            "/api/smart-participation/resolve",
            headers=_connector_headers(),
            json=payload,
        )

        assert response.status_code == 200, response.text
        _assert_authoritative_empty_plan(response.json(), "no_owner")


def test_candidate_scope_repository_failure_is_authoritative_silent_plan(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    app = create_app(settings(tmp_path / "scope-repository-failure.db"))
    client = TestClient(app)
    connection_id, deployment_id = _seed_smart_deployment(client)

    def fail_repository(**_: object) -> object:
        raise RuntimeError("deployment repository unavailable")

    monkeypatch.setattr(
        app.state.deployment_repository,
        "list_connector_deployments",
        fail_repository,
    )
    response = client.post(
        "/api/smart-participation/resolve",
        headers=_connector_headers(),
        json=_resolve_payload(connection_id, deployment_id),
    )

    assert response.status_code == 200, response.text
    _assert_authoritative_empty_plan(response.json(), "candidate_scope_resolution_failed")


def test_candidate_semantic_failure_is_authoritative_silent_plan(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    app = create_app(settings(tmp_path / "candidate-evidence-failure.db"))
    client = TestClient(app)
    connection_id, deployment_id = _seed_smart_deployment(client)

    def fail_semantics(**_: object) -> object:
        raise RuntimeError("semantic evidence unavailable")

    monkeypatch.setattr(app.state.semantic_participation_service, "score", fail_semantics)
    response = client.post(
        "/api/smart-participation/resolve",
        headers=_connector_headers(),
        json=_resolve_payload(connection_id, deployment_id),
    )

    assert response.status_code == 200, response.text
    _assert_authoritative_empty_plan(response.json(), "candidate_evidence_failed")


def test_conversation_structure_failure_is_authoritative_silent_plan(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    app = create_app(settings(tmp_path / "structure-failure.db"))
    client = TestClient(app)
    connection_id, deployment_id = _seed_smart_deployment(client)
    primed = client.post(
        "/api/smart-participation/resolve",
        headers=_connector_headers(),
        json=_resolve_payload(connection_id, deployment_id),
    )
    assert primed.status_code == 200, primed.text

    def fail_structure(**_: object) -> object:
        raise RuntimeError("structure unavailable")

    monkeypatch.setattr(app.state.conversation_structure_resolver_v3, "resolve", fail_structure)
    response = client.post(
        "/api/smart-participation/resolve",
        headers=_connector_headers(),
        json=_resolve_payload(connection_id, deployment_id),
    )

    assert response.status_code == 200, response.text
    _assert_authoritative_empty_plan(response.json(), "conversation_structure_failed")


def test_belief_revision_failure_is_authoritative_silent_plan(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    app = create_app(settings(tmp_path / "belief-failure.db"))
    client = TestClient(app)
    connection_id, deployment_id = _seed_smart_deployment(client)

    def fail_extraction(**_: object) -> object:
        raise RuntimeError("belief revision unavailable")

    monkeypatch.setattr(
        CurrentTurnBeliefRevisionService,
        "extract_self_claim",
        fail_extraction,
    )
    response = client.post(
        "/api/smart-participation/resolve",
        headers=_connector_headers(),
        json=_resolve_payload(connection_id, deployment_id),
    )

    assert response.status_code == 200, response.text
    _assert_authoritative_empty_plan(response.json(), "belief_revision_failed")


def test_correction_extraction_utility_usage_remains_visible(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    app = create_app(settings(tmp_path / "belief-utility.db"))
    client = TestClient(app)
    connection_id, deployment_id = _seed_smart_deployment(client)

    def utility_extraction(**_: object) -> CurrentTurnClaimExtraction:
        return CurrentTurnClaimExtraction(
            decision=None,
            utility_used=True,
            reason="claim_not_safe_to_persist",
        )

    monkeypatch.setattr(
        app.state.character_turn_context_v3_service.corrections,
        "extract_self_claim",
        utility_extraction,
    )
    response = client.post(
        "/api/smart-participation/resolve",
        headers=_connector_headers(),
        json=_resolve_payload(connection_id, deployment_id),
    )

    assert response.status_code == 200, response.text
    assert response.json()["utility_used"] is True


def test_context_resolver_failure_is_authoritative_silent_plan(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    app = create_app(settings(tmp_path / "context-failure.db"))
    client = TestClient(app)
    connection_id, deployment_id = _seed_smart_deployment(client)
    primed = client.post(
        "/api/smart-participation/resolve",
        headers=_connector_headers(),
        json=_resolve_payload(connection_id, deployment_id),
    )
    assert primed.status_code == 200, primed.text

    def fail_context(**_: object) -> object:
        raise RuntimeError("context unavailable")

    monkeypatch.setattr(app.state.context_resolver_v3, "resolve", fail_context)
    response = client.post(
        "/api/smart-participation/resolve",
        headers=_connector_headers(),
        json=_resolve_payload(connection_id, deployment_id),
    )

    assert response.status_code == 200, response.text
    _assert_authoritative_empty_plan(response.json(), "context_resolution_failed")


def test_participation_planner_failure_is_authoritative_silent_plan(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    app = create_app(settings(tmp_path / "planner-failure.db"))
    client = TestClient(app)
    connection_id, deployment_id = _seed_smart_deployment(client)
    primed = client.post(
        "/api/smart-participation/resolve",
        headers=_connector_headers(),
        json=_resolve_payload(connection_id, deployment_id),
    )
    assert primed.status_code == 200, primed.text

    def fail_planner(**_: object) -> object:
        raise RuntimeError("planner unavailable")

    monkeypatch.setattr(
        app.state.participation_planner_v3,
        "plan",
        fail_planner,
    )
    response = client.post(
        "/api/smart-participation/resolve",
        headers=_connector_headers(),
        json=_resolve_payload(connection_id, deployment_id),
    )

    assert response.status_code == 200, response.text
    _assert_authoritative_empty_plan(response.json(), "participation_planner_failed")


def test_reply_target_persistence_failure_keeps_authoritative_plan(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    app = create_app(settings(tmp_path / "persistence-failure.db"))
    client = TestClient(app)
    connection_id, deployment_id = _seed_smart_deployment(client)

    def fail_persistence(**_: object) -> None:
        raise RuntimeError("reply target persistence unavailable")

    monkeypatch.setattr(
        smart_participation_vnext,
        "_persist_reply_targets",
        fail_persistence,
    )
    response = client.post(
        "/api/smart-participation/resolve",
        headers=_connector_headers(),
        json=_resolve_payload(connection_id, deployment_id),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["speaker_plan_authoritative"] is True
    assert body["speaker_plan"][0]["deployment_id"] == deployment_id
    assert body["reply_targets"][0]["deployment_id"] == deployment_id
