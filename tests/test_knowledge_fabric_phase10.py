from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select

from echo_masque.api import create_app
from echo_masque.config import Settings
from echo_masque.knowledge_fabric_epistemic_policy import PersistedCharacterEpistemicPolicy
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.knowledge_fabric_repository import KnowledgeFabricRepository
from echo_masque.persistence.models import AuditEventRecord


def _settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        public_registration_enabled=True,
        bootstrap_admin_email="phase10-super@example.test",
        bootstrap_admin_password=SecretStr("KnowledgeFabric2026!"),
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
        request_limit_per_minute=1000,
    )


def _login(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": "KnowledgeFabric2026!"},
    )
    assert response.status_code == 200, response.text


def _deployment(
    *,
    identifier: str,
    character_card_id: str,
    workspace_id: str = "workspace-a",
) -> CharacterDeploymentRecord:
    return CharacterDeploymentRecord(
        id=identifier,
        owner_id="owner-a",
        character_card_id=character_card_id,
        connection_id="connection-a",
        platform="discord",
        workspace_id=workspace_id,
        channel_id=f"channel-{identifier}",
        channel_name="Channel",
    )


def test_persisted_character_policy_is_scope_bound_default_deny_and_card_specific(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{tmp_path / 'phase10.db'}")
    database.initialize()
    fabric = KnowledgeFabricRepository(database)
    scope = fabric.ensure_server_scope(
        platform="discord", connection_id="connection-a", workspace_id="workspace-a"
    )
    corpus = fabric.create_server_local_corpus(
        server_scope_id=scope.id,
        name="Local canon",
        description="",
        default_authority_profile="standard",
        status="active",
    )
    with database.session() as session:
        session.add_all(
            [
                _deployment(identifier="deployment-a", character_card_id="card-a"),
                _deployment(identifier="deployment-b", character_card_id="card-b"),
                _deployment(
                    identifier="deployment-foreign",
                    character_card_id="card-foreign",
                    workspace_id="workspace-b",
                ),
            ]
        )
        session.commit()

    policy = PersistedCharacterEpistemicPolicy(fabric)
    assert not policy.allows(
        deployment_id="deployment-a",
        character_card_id="card-a",
        corpus_id=corpus.id,
        authority_profile="unapproved-domain-is-not-a-policy-input",
    )
    allow = fabric.set_character_corpus_policy(
        server_scope_id=scope.id,
        deployment_id="deployment-a",
        corpus_id=corpus.id,
        effect="allow",
    )
    assert allow is not None
    assert allow.character_card_id == "card-a"
    assert policy.allows(
        deployment_id="deployment-a",
        character_card_id="card-a",
        corpus_id=corpus.id,
        authority_profile="standard",
    )
    assert not policy.allows(
        deployment_id="deployment-b",
        character_card_id="card-b",
        corpus_id=corpus.id,
        authority_profile="standard",
    )
    denied = fabric.set_character_corpus_policy(
        server_scope_id=scope.id,
        deployment_id="deployment-a",
        corpus_id=corpus.id,
        effect="deny",
    )
    assert denied is not None
    assert denied.id == allow.id
    assert not policy.allows(
        deployment_id="deployment-a",
        character_card_id="card-a",
        corpus_id=corpus.id,
        authority_profile="standard",
    )
    assert fabric.set_character_corpus_policy(
        server_scope_id=scope.id,
        deployment_id="deployment-foreign",
        corpus_id=corpus.id,
        effect="allow",
    ) is None
    with pytest.raises(ValueError, match="Unknown Character corpus policy effect"):
        fabric.set_character_corpus_policy(
            server_scope_id=scope.id,
            deployment_id="deployment-a",
            corpus_id=corpus.id,
            effect="maybe",
        )


def test_scope_administrator_can_author_character_policy_and_audit_is_recorded(
    tmp_path: Path,
) -> None:
    app = create_app(_settings(tmp_path / "phase10-api.db"))
    super_admin = TestClient(app)
    manager = TestClient(app)
    _login(super_admin, "phase10-super@example.test")
    registration = manager.post(
        "/api/auth/register",
        json={
            "email": "phase10-manager@example.test",
            "display_name": "Phase 10 manager",
            "password": "KnowledgeFabric2026!",
        },
    )
    assert registration.status_code == 201, registration.text
    manager_id = registration.json()["user"]["id"]
    _login(manager, "phase10-manager@example.test")
    scope_response = super_admin.post(
        "/api/knowledge-fabric/admin/server-scopes",
        json={
            "platform": "discord",
            "connection_id": "connection-a",
            "workspace_id": "workspace-a",
        },
    )
    assert scope_response.status_code == 201, scope_response.text
    scope_id = scope_response.json()["id"]
    corpus_response = super_admin.post(
        "/api/knowledge-fabric/admin/corpora",
        json={"name": "World canon", "description": ""},
    )
    assert corpus_response.status_code == 201, corpus_response.text
    corpus_id = corpus_response.json()["id"]
    membership = super_admin.put(
        f"/api/knowledge-fabric/admin/server-scopes/{scope_id}/administrators/{manager_id}"
    )
    assert membership.status_code == 200, membership.text
    grant = manager.put(
        f"/api/knowledge-fabric/server-scopes/{scope_id}/global-corpora/{corpus_id}/grant",
        json={"enabled": True},
    )
    assert grant.status_code == 200, grant.text
    with app.state.database.session() as session:
        session.add(_deployment(identifier="deployment-a", character_card_id="card-a"))
        session.commit()

    response = manager.put(
        f"/api/knowledge-fabric/server-scopes/{scope_id}/deployments/deployment-a/"
        f"corpora/{corpus_id}/epistemic-policy",
        json={"effect": "allow"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["character_card_id"] == "card-a"
    assert response.json()["effect"] == "allow"
    listed = manager.get(
        f"/api/knowledge-fabric/server-scopes/{scope_id}/character-corpus-policies"
    )
    assert listed.status_code == 200, listed.text
    assert [item["corpus_id"] for item in listed.json()] == [corpus_id]
    with app.state.database.session() as session:
        actions = list(
            session.scalars(
                select(AuditEventRecord.action).where(
                    AuditEventRecord.action == "knowledge_fabric.character_corpus_policy_updated"
                )
            )
        )
    assert actions == ["knowledge_fabric.character_corpus_policy_updated"]
