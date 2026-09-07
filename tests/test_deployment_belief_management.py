from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.config import Settings
from echo_masque.persistence.belief_repository import BeliefRepository
from echo_masque.persistence.conversation_runtime_repository import ConversationRuntimeRepository

ADMIN_EMAIL = "belief-admin@example.com"
ADMIN_PASSWORD = "BeliefAdmin2026!"


def _settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        bootstrap_admin_email=ADMIN_EMAIL,
        bootstrap_admin_password=SecretStr(ADMIN_PASSWORD),
        bootstrap_admin_display_name="Belief Admin",
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
    )


def _login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200, response.text


def _deployment(client: TestClient) -> dict[str, str]:
    character = client.post(
        "/api/characters/prompt-model",
        json={
            "display_name": "Ann",
            "subtitle": "Scoped memory character",
            "subject_type": "companion",
            "persona_summary": "A careful companion.",
            "traits": ["careful"],
            "tags": ["memory"],
            "expected_tone": "Concise.",
            "forbidden_behaviors": ["invent memory"],
            "memory_summary": "Keep server memory scoped.",
            "preferred_suites": ["false_memory"],
            "portrait_variant": "lavender",
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-v4-flash",
            "system_prompt": "You are Ann.",
            "temperature": 0.4,
            "api_key": "test-provider-key",
        },
    )
    assert character.status_code == 201, character.text
    connection = client.post(
        "/api/connections",
        json={
            "platform": "discord",
            "display_name": "Scoped Discord",
            "connection_mode": "managed",
            "external_account_id": "bot-scoped",
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
            "workspace_name": "Guild One",
            "channel_id": "channel-1",
            "channel_name": "#memory",
            "thread_id": "",
            "thread_name": "",
            "participation_mode": "mention_and_reply",
            "memory_scope": "channel_isolated",
            "version_label": "v1",
            "sticker_count": 0,
            "status": "paused",
        },
    )
    assert deployment.status_code == 201, deployment.text
    return {
        "id": deployment.json()["id"],
        "character": character.json()["id"],
        "connection": connection.json()["id"],
    }


def _belief(
    repository: BeliefRepository,
    *,
    owner_id: str,
    character_id: str,
    connection_id: str,
    guild_id: str = "guild-1",
    value: str = "tea",
    authored: bool = False,
) -> object:
    return repository.create(
        owner_id=owner_id,
        character_card_id=character_id,
        connection_id=connection_id,
        guild_id=guild_id,
        subject_entity_id="",
        subject_ref="actor-1",
        predicate="food.preference",
        value_text=value,
        scope="character_server",
        authority_class="conversation",
        authority_score=0.6,
        origin="conversation",
        confidence=0.8,
        importance=0.6,
        status="active",
        evidence_refs=("message:source-1",),
        authored=authored,
    )


def test_owner_can_review_correct_and_forget_without_cross_scope_or_source_deletion(
    tmp_path: Path,
) -> None:
    app = create_app(_settings(tmp_path / "belief-management.db"))
    client = TestClient(app)
    _login(client)
    deployment = _deployment(client)
    owner = app.state.auth_repository.get_user_by_email(ADMIN_EMAIL)
    assert owner is not None
    beliefs = BeliefRepository(app.state.deployment_repository.database)
    target = _belief(
        beliefs,
        owner_id=owner.id,
        character_id=deployment["character"],
        connection_id=deployment["connection"],
    )
    global_same_claim = _belief(
        beliefs,
        owner_id=owner.id,
        character_id="",
        connection_id=deployment["connection"],
        value="coffee",
    )
    other_scope = _belief(
        beliefs,
        owner_id=owner.id,
        character_id=deployment["character"],
        connection_id=deployment["connection"],
        guild_id="guild-2",
    )
    runtime = ConversationRuntimeRepository(app.state.deployment_repository.database)
    episode = runtime.append_episode_segment(
        owner_id=owner.id,
        connection_id=deployment["connection"],
        guild_id="guild-1",
        channel_id="channel-1",
        discord_thread_id="",
        conversation_thread_id="memory-thread",
        segment_id="memory-segment",
        source_message_ids=("source-1",),
        participant_ids=("actor-1",),
        summary="The source history remains intact.",
    )

    reviewed = client.get(f"/api/deployments/{deployment['id']}/beliefs/{target.id}")
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["evidence_refs"] == ["message:source-1"]
    assert client.get(
        f"/api/deployments/{deployment['id']}/beliefs/{other_scope.id}"
    ).status_code == 404

    corrected = client.post(
        f"/api/deployments/{deployment['id']}/beliefs/{target.id}/correct",
        json={"value_text": "coffee", "domain": "personal", "reason": "Owner correction"},
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["action"] == "superseded"
    assert corrected.json()["belief"]["supersedes_belief_id"] == target.id
    assert beliefs.get_for_deployment_scope(
        owner_id=owner.id,
        belief_id=global_same_claim.id,
        character_card_id="",
        connection_id=deployment["connection"],
        guild_id="guild-1",
    ).status == "active"

    authored = _belief(
        beliefs,
        owner_id=owner.id,
        character_id=deployment["character"],
        connection_id=deployment["connection"],
        value="owner-authored note",
        authored=True,
    )
    rejected_authored = client.post(
        f"/api/deployments/{deployment['id']}/beliefs/{authored.id}/reject",
        json={"reason": "This cannot be auto-rejected."},
    )
    assert rejected_authored.status_code == 409

    forgotten = client.post(
        f"/api/deployments/{deployment['id']}/beliefs/{authored.id}/forget",
        json={"reason": "Owner requests removal from future recall."},
    )
    assert forgotten.status_code == 200, forgotten.text
    assert forgotten.json()["belief"]["status"] == "rejected"
    # Forgetting changes recall eligibility only.  It does not delete the underlying Episode or
    # raw-message reference that records why the old belief had existed.
    assert runtime.search_episodes(
        owner_id=owner.id,
        connection_id=deployment["connection"],
        guild_id="guild-1",
        query_terms=("source",),
    )[0].id == episode.id


def test_scope_endpoint_does_not_accept_a_random_belief_identifier(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path / "belief-scope.db"))
    client = TestClient(app)
    _login(client)
    deployment = _deployment(client)

    response = client.post(
        f"/api/deployments/{deployment['id']}/beliefs/{uuid4()}/forget",
        json={"reason": "Not a scoped belief."},
    )
    assert response.status_code == 404
