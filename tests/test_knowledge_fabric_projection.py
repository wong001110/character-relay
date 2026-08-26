from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256

from sqlalchemy import select

from echo_masque.knowledge_fabric_ingestion import (
    KnowledgeFabricIngestionService,
    SourceSnapshotIngestionRequest,
)
from echo_masque.knowledge_fabric_projection_policy import source_projection_is_current
from echo_masque.knowledge_object_storage import StoredKnowledgeObject
from echo_masque.persistence.database import Database
from echo_masque.persistence.knowledge_fabric_content_repository import (
    CanonicalBlockInput,
    CanonicalDocumentInput,
    KnowledgeFabricContentRepository,
)
from echo_masque.persistence.knowledge_fabric_models import (
    KnowledgeCorpusRecord,
    KnowledgeProjectionDependencyRecord,
    KnowledgeProjectionRecord,
)
from echo_masque.persistence.knowledge_fabric_projection_repository import (
    SOURCE_OVERVIEW_PROJECTION,
    KnowledgeFabricProjectionRepository,
)
from echo_masque.persistence.knowledge_fabric_repository import KnowledgeFabricRepository


@dataclass
class _PrivateStorage:
    values: dict[str, bytes]

    def put_private(
        self,
        *,
        object_key: str,
        content: bytes,
        content_type: str,
        metadata: Mapping[str, str],
    ) -> StoredKnowledgeObject:
        del metadata
        self.values[object_key] = content
        return StoredKnowledgeObject(
            provider="cloudflare_r2",
            bucket="private",
            object_key=object_key,
            content_sha256=sha256(content).hexdigest(),
            byte_size=len(content),
            content_type=content_type,
        )

    def get_private(self, *, object_key: str) -> bytes:
        return self.values[object_key]

    def delete_private(self, *, object_key: str) -> bool:
        return self.values.pop(object_key, None) is not None


def test_source_projection_current_requires_matching_hash_and_fresh_state() -> None:
    assert source_projection_is_current(
        projection_source_hash="same",
        current_source_hash="same",
        stale=False,
    )
    assert not source_projection_is_current(
        projection_source_hash="same",
        current_source_hash="same",
        stale=True,
    )
    assert not source_projection_is_current(
        projection_source_hash="old",
        current_source_hash="new",
        stale=False,
    )


def _snapshot(
    *,
    source_id: str,
    version_key: str,
    delivery_key: str,
    text: str,
) -> SourceSnapshotIngestionRequest:
    return SourceSnapshotIngestionRequest(
        source_id=source_id,
        version_key=version_key,
        idempotency_key=delivery_key,
        artifact_content=text.encode("utf-8"),
        artifact_content_type="text/markdown",
        published_at=datetime(2026, 8, 25, tzinfo=UTC),
        documents=(
            CanonicalDocumentInput(
                canonical_locator="https://example.test/handbook",
                title="Handbook",
                mime_type="text/markdown",
                blocks=(
                    CanonicalBlockInput(
                        structural_path="paragraph:0",
                        block_type="paragraph",
                        ordinal=0,
                        text_content=text,
                    ),
                ),
            ),
        ),
    )


def _seed(tmp_path, *, user_owned: bool = False):
    database = Database(f"sqlite:///{tmp_path / 'phase7-projections.db'}")
    database.initialize()
    storage = _PrivateStorage(values={})
    fabric = KnowledgeFabricRepository(database, object_storage=storage)
    if user_owned:
        with database.session() as session:
            session.add(
                KnowledgeCorpusRecord(
                    id="user-corpus",
                    name="User corpus",
                    owner_type="user",
                    owner_id="user-1",
                    visibility="private",
                    default_authority_profile="standard",
                    status="active",
                )
            )
            session.commit()
        corpus_id = "user-corpus"
    else:
        corpus_id = fabric.create_system_global_corpus(
            name="Fabric source",
            description="",
            default_authority_profile="standard",
            status="active",
        ).id
    source = fabric.create_source(
        corpus_id=corpus_id,
        source_type="manual_text",
        locator="https://example.test/handbook",
        access_profile_json="{}",
        parser_profile_json="{}",
        sync_policy_json="{}",
        freshness_policy_json="{}",
        authority_profile="canonical",
    )
    content = KnowledgeFabricContentRepository(database, object_storage=storage)
    ingest = KnowledgeFabricIngestionService(content, storage, object_key_prefix="knowledge-fabric")
    return database, fabric, content, ingest, source, corpus_id


def test_source_projection_is_lazy_deterministic_and_stale_on_new_snapshot(tmp_path) -> None:
    database, _fabric, content, ingest, source, corpus_id = _seed(tmp_path)
    first_version = ingest.ingest_snapshot(
        _snapshot(
            source_id=source.id,
            version_key="one",
            delivery_key="one",
            text="The first approved operating handbook.",
        )
    )
    first_evidence = content.list_evidence_units(first_version.id)[0]
    projections = KnowledgeFabricProjectionRepository(database)

    first = projections.get_source_overview(source.id)

    assert first is not None
    assert first.corpus_id == corpus_id
    assert first.projection_type == SOURCE_OVERVIEW_PROJECTION
    assert first.subject_ref_id == source.id
    assert first.source_hash == first_version.source_hash
    assert first.stale is False
    assert first.text_content == "[Handbook]\nThe first approved operating handbook."
    assert first.provenance == (
        type(first.provenance[0])(
            source_version_id=first_version.id,
            evidence_unit_id=first_evidence.id,
            source_hash=first_version.source_hash,
            content_sha256=first_evidence.content_sha256,
        ),
    )

    second_version = ingest.ingest_snapshot(
        _snapshot(
            source_id=source.id,
            version_key="two",
            delivery_key="two",
            text="The second approved operating handbook.",
        )
    )
    second_evidence = content.list_evidence_units(second_version.id)[0]
    with database.session() as session:
        stale = session.get(KnowledgeProjectionRecord, first.id)
        assert stale is not None
        assert stale.stale is True

    rebuilt = projections.get_source_overview(source.id)

    assert rebuilt is not None
    assert rebuilt.id == first.id
    assert rebuilt.stale is False
    assert rebuilt.source_hash == second_version.source_hash
    assert rebuilt.provenance[0].source_version_id == second_version.id
    assert rebuilt.provenance[0].evidence_unit_id == second_evidence.id
    assert rebuilt.provenance[0].content_sha256 == second_evidence.content_sha256
    assert "second approved" in rebuilt.text_content
    assert "first approved" not in rebuilt.text_content


def test_owner_deletion_removes_projection_dependencies_before_evidence(tmp_path) -> None:
    database, fabric, _content, ingest, source, _corpus_id = _seed(tmp_path, user_owned=True)
    ingest.ingest_snapshot(
        _snapshot(
            source_id=source.id,
            version_key="one",
            delivery_key="one",
            text="User-owned handbook.",
        )
    )
    projection = KnowledgeFabricProjectionRepository(database).get_source_overview(source.id)
    assert projection is not None

    counts = fabric.delete_owner("user-1")

    assert counts["knowledge_fabric_projections"] == 1
    assert counts["knowledge_fabric_projection_dependencies"] == 1
    with database.session() as session:
        assert session.get(KnowledgeProjectionRecord, projection.id) is None
        assert session.scalars(select(KnowledgeProjectionDependencyRecord)).all() == []
