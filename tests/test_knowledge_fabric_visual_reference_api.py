from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select

from echo_masque.api import create_app
from echo_masque.config import Settings
from echo_masque.knowledge_fabric_ingestion import (
    SourceSnapshotAssetInput,
    SourceSnapshotIngestionRequest,
)
from echo_masque.knowledge_object_storage import StoredKnowledgeObject
from echo_masque.persistence.knowledge_fabric_content_repository import (
    CanonicalBlockInput,
    CanonicalDocumentInput,
)
from echo_masque.persistence.knowledge_fabric_interpretation_repository import (
    KnowledgeFabricInterpretationRepository,
)
from echo_masque.persistence.knowledge_fabric_models import (
    KnowledgeCanonicalDocumentRecord,
    KnowledgeObjectArtifactRecord,
)
from echo_masque.persistence.models import AuditEventRecord

PASSWORD = "VisualReference2026!"
SUPER_EMAIL = "visual-reference-super@example.com"


@dataclass
class _Storage:
    objects: dict[str, bytes] = field(default_factory=dict)

    def put_private(
        self,
        *,
        object_key: str,
        content: bytes,
        content_type: str,
        metadata: Mapping[str, str],
    ) -> StoredKnowledgeObject:
        del metadata
        self.objects[object_key] = content
        return StoredKnowledgeObject(
            provider="test",
            bucket="private",
            object_key=object_key,
            content_sha256=sha256(content).hexdigest(),
            byte_size=len(content),
            content_type=content_type,
        )

    def get_private(self, *, object_key: str) -> bytes:
        return self.objects[object_key]

    def delete_private(self, *, object_key: str) -> bool:
        return self.objects.pop(object_key, None) is not None


def _settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        public_registration_enabled=True,
        bootstrap_admin_email=SUPER_EMAIL,
        bootstrap_admin_password=SecretStr(PASSWORD),
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
        request_limit_per_minute=1000,
    )


def _login(client: TestClient, email: str) -> None:
    response = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text


def _register_and_login(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "display_name": "Visual Reference Operator",
            "password": PASSWORD,
        },
    )
    assert response.status_code == 201, response.text
    _login(client, email)


def _provenance_ids(app: FastAPI, *, corpus_id: str, source_id: str) -> tuple[str, str, str]:
    ingestion = app.state.knowledge_fabric_ingestion_service
    content = app.state.knowledge_fabric_content_repository
    database = app.state.database
    version = ingestion.ingest_snapshot(
        SourceSnapshotIngestionRequest(
            source_id=source_id,
            version_key="amber-v1",
            idempotency_key="amber-v1",
            artifact_content=b"private amber portrait",
            artifact_content_type="image/webp",
            published_at=datetime(2026, 8, 27, tzinfo=UTC),
            documents=(
                CanonicalDocumentInput(
                    canonical_locator="https://example.test/amber",
                    title="Amber",
                    mime_type="text/plain",
                    blocks=(
                        CanonicalBlockInput(
                            structural_path="page:0",
                            block_type="page",
                            ordinal=0,
                            text_content="Amber is an Outrider.",
                        ),
                    ),
                ),
            ),
        )
    )
    evidence = content.list_evidence_units(version.id)[0]
    with database.session() as session:
        document = session.scalar(
            select(KnowledgeCanonicalDocumentRecord).where(
                KnowledgeCanonicalDocumentRecord.source_version_id == version.id
            )
        )
        artifact = session.scalar(
            select(KnowledgeObjectArtifactRecord).where(
                KnowledgeObjectArtifactRecord.source_id == source_id
            )
        )
    assert document is not None
    assert artifact is not None
    asset = content.create_asset_reference(
        document_id=document.id,
        artifact_id=artifact.id,
        asset_type="image",
        structural_path="image:0",
    )
    entity = KnowledgeFabricInterpretationRepository(database).create_canonical_entity(
        corpus_id=corpus_id,
        entity_type="character",
        canonical_name="Amber",
        aliases=("安柏",),
    )
    return entity.id, evidence.id, asset.id


def test_super_admin_visual_reference_api_is_corpus_bound_and_revocable(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path / "visual-reference-api.db"))
    storage = _Storage()
    app.state.knowledge_fabric_ingestion_service.object_storage = storage
    app.state.knowledge_fabric_content_repository.object_storage = storage
    app.state.knowledge_fabric_repository.object_storage = storage
    admin = TestClient(app)
    ordinary = TestClient(app)
    _login(admin, SUPER_EMAIL)
    _register_and_login(ordinary, "visual-reference-ordinary@example.com")

    corpus_response = admin.post(
        "/api/knowledge-fabric/admin/corpora",
        json={"name": "Teyvat", "description": "Global canon"},
    )
    assert corpus_response.status_code == 201, corpus_response.text
    corpus_id = corpus_response.json()["id"]
    source_response = admin.post(
        f"/api/knowledge-fabric/admin/corpora/{corpus_id}/sources",
        json={"source_type": "manual_text", "locator": "https://example.test/amber"},
    )
    assert source_response.status_code == 201, source_response.text
    entity_id, evidence_id, asset_id = _provenance_ids(
        app,
        corpus_id=corpus_id,
        source_id=source_response.json()["id"],
    )
    endpoint = f"/api/knowledge-fabric/admin/corpora/{corpus_id}/visual-references"
    payload = {
        "canonical_entity_id": entity_id,
        "evidence_unit_id": evidence_id,
        "asset_id": asset_id,
        "descriptor": {"outfit": "red", "weapon": "bow"},
    }

    assert ordinary.post(endpoint, json=payload).status_code == 403
    other_corpus = admin.post(
        "/api/knowledge-fabric/admin/corpora",
        json={"name": "Other", "description": "Different global corpus"},
    )
    assert other_corpus.status_code == 201, other_corpus.text
    assert (
        admin.post(
            f"/api/knowledge-fabric/admin/corpora/{other_corpus.json()['id']}/visual-references",
            json=payload,
        ).status_code
        == 422
    )
    created = admin.post(endpoint, json=payload)
    assert created.status_code == 201, created.text
    reference = created.json()
    assert reference["corpus_id"] == corpus_id
    assert reference["canonical_entity_id"] == entity_id
    assert reference["evidence_unit_id"] == evidence_id
    assert reference["asset_id"] == asset_id
    assert reference["descriptor"] == payload["descriptor"]
    assert reference["status"] == "active"
    assert "object_key" not in reference
    assert "artifact_url" not in reference

    listed = admin.get(endpoint)
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()] == [reference["id"]]
    assert ordinary.get(endpoint).status_code == 403

    revoked = admin.delete(f"{endpoint}/{reference['id']}")
    assert revoked.status_code == 204, revoked.text
    assert admin.get(endpoint).json() == []
    assert admin.delete(f"{endpoint}/{reference['id']}").status_code == 404
    with app.state.database.session() as session:
        actions = set(
            session.scalars(
                select(AuditEventRecord.action).where(
                    AuditEventRecord.resource_id == reference["id"]
                )
            )
        )
    assert actions == {
        "knowledge_fabric.visual_reference_approved",
        "knowledge_fabric.visual_reference_revoked",
    }


def test_super_admin_can_onboard_image_candidate_without_storage_disclosure(
    tmp_path: Path,
) -> None:
    app = create_app(_settings(tmp_path / "visual-reference-onboarding.db"))
    storage = _Storage()
    app.state.knowledge_fabric_ingestion_service.object_storage = storage
    app.state.knowledge_fabric_content_repository.object_storage = storage
    app.state.knowledge_fabric_repository.object_storage = storage
    admin = TestClient(app)
    _login(admin, SUPER_EMAIL)

    corpus = admin.post(
        "/api/knowledge-fabric/admin/corpora",
        json={"name": "Teyvat", "description": "Global canon"},
    )
    assert corpus.status_code == 201, corpus.text
    corpus_id = corpus.json()["id"]
    source = admin.post(
        f"/api/knowledge-fabric/admin/corpora/{corpus_id}/sources",
        json={"source_type": "manual_text", "locator": "https://example.test/amber"},
    )
    assert source.status_code == 201, source.text
    version = app.state.knowledge_fabric_ingestion_service.ingest_snapshot(
        SourceSnapshotIngestionRequest(
            source_id=source.json()["id"],
            version_key="amber-onboarding-v1",
            idempotency_key="amber-onboarding-v1",
            artifact_content=b"Amber page text",
            artifact_content_type="text/plain",
            published_at=datetime(2026, 8, 27, tzinfo=UTC),
            documents=(
                CanonicalDocumentInput(
                    canonical_locator="https://example.test/amber",
                    title="Amber",
                    mime_type="text/plain",
                    blocks=(
                        CanonicalBlockInput(
                            structural_path="page:0",
                            block_type="page",
                            ordinal=0,
                            text_content="Amber is an Outrider.",
                        ),
                    ),
                ),
            ),
            assets=(
                SourceSnapshotAssetInput(
                    document_locator="https://example.test/amber",
                    structural_path="image:0",
                    asset_type="image",
                    artifact_content=b"\x89PNG\r\n\x1a\nprivate amber art",
                    artifact_content_type="image/png",
                    evidence_locator="https://example.test/amber#image:0",
                    text_content="Amber official portrait",
                    coordinates={"alt": "Amber official portrait"},
                ),
            ),
        )
    )
    assert version.status == "available"

    candidates_endpoint = f"/api/knowledge-fabric/admin/corpora/{corpus_id}/image-assets"
    candidates = admin.get(candidates_endpoint)
    assert candidates.status_code == 200, candidates.text
    assert len(candidates.json()) == 1
    candidate = candidates.json()[0]
    assert candidate["caption"] == "Amber official portrait"
    assert "object_key" not in candidate
    assert "content_sha256" not in candidate

    entities_endpoint = f"/api/knowledge-fabric/admin/corpora/{corpus_id}/canonical-entities"
    entity = admin.post(
        entities_endpoint,
        json={
            "entity_type": "fictional_character",
            "canonical_name": "Amber",
            "aliases": ["安柏"],
        },
    )
    assert entity.status_code == 201, entity.text
    assert admin.get(entities_endpoint).json()[0]["id"] == entity.json()["id"]

    approved = admin.post(
        f"/api/knowledge-fabric/admin/corpora/{corpus_id}/visual-references",
        json={
            "canonical_entity_id": entity.json()["id"],
            "evidence_unit_id": candidate["evidence_unit_id"],
            "asset_id": candidate["asset_id"],
            "descriptor": {"caption": candidate["caption"]},
            "comparison_authorized": True,
        },
    )
    assert approved.status_code == 201, approved.text
    assert approved.json()["comparison_authorized"] is True
    assert "comparison_authorized" not in approved.json()["descriptor"]
