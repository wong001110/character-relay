from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from os import environ
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from echo_masque.knowledge_fabric_ingestion import (
    KnowledgeFabricIngestionService,
    SourceSnapshotIngestionRequest,
)
from echo_masque.knowledge_fabric_query import KnowledgeQueryEngine, KnowledgeQueryRequest
from echo_masque.knowledge_object_storage import StoredKnowledgeObject
from echo_masque.persistence.database import Database
from echo_masque.persistence.knowledge_fabric_content_repository import (
    CanonicalBlockInput,
    CanonicalDocumentInput,
    KnowledgeFabricContentRepository,
)
from echo_masque.persistence.knowledge_fabric_index_repository import (
    KnowledgeFabricIndexRepository,
    KnowledgeIndexCandidate,
)
from echo_masque.persistence.knowledge_fabric_interpretation_repository import (
    KnowledgeFabricInterpretationRepository,
)
from echo_masque.persistence.knowledge_fabric_models import (
    KnowledgeCorpusRecord,
    KnowledgeEvidenceEmbeddingRecord,
    KnowledgeEvidenceRetrievalEntryRecord,
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


@dataclass
class _SpyIndexes:
    delegate: KnowledgeFabricIndexRepository
    requested_corpus_sets: list[frozenset[str]]

    def search_sparse(self, **kwargs: object) -> list[KnowledgeIndexCandidate]:
        corpus_ids = kwargs["authorized_corpus_ids"]
        assert isinstance(corpus_ids, frozenset)
        self.requested_corpus_sets.append(corpus_ids)
        return self.delegate.search_sparse(**kwargs)  # type: ignore[arg-type]

    def search_dense(self, **kwargs: object) -> list[KnowledgeIndexCandidate]:
        corpus_ids = kwargs["authorized_corpus_ids"]
        assert isinstance(corpus_ids, frozenset)
        self.requested_corpus_sets.append(corpus_ids)
        return self.delegate.search_dense(**kwargs)  # type: ignore[arg-type]

    def search_entity_graph(self, **kwargs: object) -> list[KnowledgeIndexCandidate]:
        corpus_ids = kwargs["authorized_corpus_ids"]
        assert isinstance(corpus_ids, frozenset)
        self.requested_corpus_sets.append(corpus_ids)
        return self.delegate.search_entity_graph(**kwargs)  # type: ignore[arg-type]


@dataclass(frozen=True)
class _Embedder:
    model_name: str = "test-model"

    def embed_query(self, text: str) -> list[float]:
        del text
        return [1.0, 0.0]


def _ingest(
    *,
    fabric: KnowledgeFabricRepository,
    content: KnowledgeFabricContentRepository,
    storage: _PrivateStorage,
    corpus_id: str,
    key: str,
    text: str,
) -> str:
    source = fabric.create_source(
        corpus_id=corpus_id,
        source_type="manual_text",
        locator=f"https://example.test/{key}",
        access_profile_json="{}",
        parser_profile_json="{}",
        sync_policy_json="{}",
        freshness_policy_json="{}",
        authority_profile="standard",
    )
    version = KnowledgeFabricIngestionService(
        content,
        storage,
        object_key_prefix="knowledge-fabric",
    ).ingest_snapshot(
        SourceSnapshotIngestionRequest(
            source_id=source.id,
            version_key="one",
            idempotency_key=f"delivery-{key}",
            artifact_content=text.encode(),
            artifact_content_type="text/markdown",
            published_at=datetime(2026, 8, 25, tzinfo=UTC),
            documents=(
                CanonicalDocumentInput(
                    canonical_locator=source.locator,
                    title=key,
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
    )
    return content.list_evidence_units(version.id)[0].id


def _seed(tmp_path: Path) -> tuple[
    Database,
    KnowledgeFabricRepository,
    KnowledgeFabricContentRepository,
    KnowledgeFabricIndexRepository,
    _PrivateStorage,
    str,
    str,
    str,
]:
    database = Database(f"sqlite:///{tmp_path / 'phase5.db'}")
    database.initialize()
    storage = _PrivateStorage(values={})
    fabric = KnowledgeFabricRepository(database, object_storage=storage)
    content = KnowledgeFabricContentRepository(database, object_storage=storage)
    indexes = KnowledgeFabricIndexRepository(database)
    first_scope = fabric.ensure_server_scope(
        platform="discord",
        connection_id="connection-1",
        workspace_id="guild-a",
    )
    second_scope = fabric.ensure_server_scope(
        platform="discord",
        connection_id="connection-1",
        workspace_id="guild-b",
    )
    global_corpus = fabric.create_system_global_corpus(
        name="Global",
        description="",
        default_authority_profile="standard",
        status="active",
    )
    private_corpus = fabric.create_system_global_corpus(
        name="Private",
        description="",
        default_authority_profile="standard",
        status="active",
    )
    local_corpus = fabric.create_server_local_corpus(
        server_scope_id=first_scope.id,
        name="Local",
        description="",
        default_authority_profile="standard",
        status="active",
    )
    fabric.set_server_global_grant(
        server_scope_id=first_scope.id,
        corpus_id=global_corpus.id,
        enabled=True,
    )
    global_evidence = _ingest(
        fabric=fabric,
        content=content,
        storage=storage,
        corpus_id=global_corpus.id,
        key="global",
        text="Klee is the Spark Knight.",
    )
    private_evidence = _ingest(
        fabric=fabric,
        content=content,
        storage=storage,
        corpus_id=private_corpus.id,
        key="private",
        text="Forbidden crown secret secret secret.",
    )
    _ingest(
        fabric=fabric,
        content=content,
        storage=storage,
        corpus_id=local_corpus.id,
        key="local",
        text="Local festival guide.",
    )
    for evidence_id in (global_evidence, private_evidence):
        entry = indexes.upsert_retrieval_entry(evidence_id)
        indexes.upsert_embedding(
            retrieval_entry_id=entry.id,
            embedding_model="test-model",
            vector=[1.0, 0.0],
        )
    return (
        database,
        fabric,
        content,
        indexes,
        storage,
        first_scope.id,
        second_scope.id,
        global_evidence,
    )


def _destructive_postgres_test_url() -> str:
    postgres_url = environ.get("ECHO_MASQUE_TEST_POSTGRES_URL")
    if not postgres_url:
        pytest.skip("ECHO_MASQUE_TEST_POSTGRES_URL is not configured")
    parsed = make_url(postgres_url)
    if parsed.get_backend_name() != "postgresql" or parsed.database != "echo_masque_test":
        pytest.fail("Phase 5 PostgreSQL tests require the dedicated echo_masque_test database.")
    if environ.get("ECHO_MASQUE_ALLOW_DESTRUCTIVE_POSTGRES_TESTS") != "yes":
        pytest.fail(
            "Set ECHO_MASQUE_ALLOW_DESTRUCTIVE_POSTGRES_TESTS=yes to reset the test schema."
        )
    return postgres_url


def test_query_filters_corpora_before_every_channel_and_does_not_leak_private_metadata(
    tmp_path: Path,
) -> None:
    _, fabric, _, indexes, _, first_scope_id, second_scope_id, _ = _seed(tmp_path)
    spy = _SpyIndexes(delegate=indexes, requested_corpus_sets=[])
    engine = KnowledgeQueryEngine(
        fabric_repository=fabric,
        index_repository=spy,  # type: ignore[arg-type]
        embedder=_Embedder(),
    )

    result = engine.query(
        KnowledgeQueryRequest(
            server_scope_id=first_scope_id,
            query="secret",
            mode="overview",
            candidate_limit=4,
            result_limit=4,
        )
    )

    effective_ids = {item.corpus.id for item in fabric.list_effective_corpora(first_scope_id)}
    assert spy.requested_corpus_sets
    assert all(item == frozenset(effective_ids) for item in spy.requested_corpus_sets)
    assert all("Forbidden" not in item.document_title for item in result.hits)
    assert all("Forbidden" not in item.text_content for item in result.hits)
    assert all(item.corpus_id in effective_ids for item in result.hits)
    assert engine.query(
        KnowledgeQueryRequest(
            server_scope_id=second_scope_id,
            query="secret",
            mode="overview",
            candidate_limit=4,
            result_limit=4,
        )
    ).hits == ()


def test_exact_relational_current_and_temporal_queries_keep_source_provenance(
    tmp_path: Path,
) -> None:
    database, fabric, _, indexes, _, scope_id, _, evidence_id = _seed(tmp_path)
    entry = indexes.upsert_retrieval_entry(evidence_id)
    interpretations = KnowledgeFabricInterpretationRepository(database)
    corpus_id = entry.corpus_id
    entity = interpretations.create_canonical_entity(
        corpus_id=corpus_id,
        entity_type="character",
        canonical_name="Klee",
    )
    interpretations.create_assertion(
        corpus_id=corpus_id,
        subject_entity_id=entity.id,
        predicate="title",
        object_value="Spark Knight",
        evidence_unit_ids=(evidence_id,),
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        valid_to=datetime(2026, 9, 1, tzinfo=UTC),
    )
    engine = KnowledgeQueryEngine(fabric_repository=fabric, index_repository=indexes)

    exact = engine.query(
        KnowledgeQueryRequest(
            server_scope_id=scope_id,
            query="Spark Knight",
            mode="exact",
            candidate_limit=4,
            result_limit=2,
        )
    )
    assert len(exact.hits) == 1
    assert exact.hits[0].evidence_unit_id == evidence_id
    assert exact.hits[0].evidence_locator.endswith("#paragraph:0")
    assert exact.hits[0].channels == ("sparse",)

    relational = engine.query(
        KnowledgeQueryRequest(
            server_scope_id=scope_id,
            query="Klee",
            mode="relational",
            candidate_limit=4,
            result_limit=2,
            as_of=datetime(2026, 8, 25, tzinfo=UTC),
        )
    )
    assert relational.hits[0].evidence_unit_id == evidence_id
    assert "entity" in relational.hits[0].channels
    expired = indexes.search_entity_graph(
        authorized_corpus_ids=frozenset({corpus_id}),
        query="Klee",
        as_of=datetime(2026, 9, 1, tzinfo=UTC),
        candidate_limit=4,
    )
    assert expired == []
    related_entity = interpretations.create_canonical_entity(
        corpus_id=corpus_id,
        entity_type="character",
        canonical_name="Diona",
    )
    interpretations.add_graph_relation(
        corpus_id=corpus_id,
        source_ref_type="canonical_entity",
        source_ref_id=entity.id,
        relation_type="KNOWS",
        target_ref_type="canonical_entity",
        target_ref_id=related_entity.id,
        evidence_unit_ids=(evidence_id,),
    )
    graph = indexes.search_entity_graph(
        authorized_corpus_ids=frozenset({corpus_id}),
        query="Klee",
        as_of=datetime(2026, 9, 1, tzinfo=UTC),
        candidate_limit=4,
    )
    assert [item.evidence_unit_id for item in graph] == [evidence_id]

    current = engine.query(
        KnowledgeQueryRequest(
            server_scope_id=scope_id,
            query="Klee",
            mode="current",
            candidate_limit=4,
            result_limit=2,
        )
    )
    assert current.freshness_status == "insufficient"


def test_index_lifecycle_deletes_derived_entries_before_user_corpus_evidence(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{tmp_path / 'phase5-lifecycle.db'}")
    database.initialize()
    storage = _PrivateStorage(values={})
    fabric = KnowledgeFabricRepository(database, object_storage=storage)
    content = KnowledgeFabricContentRepository(database, object_storage=storage)
    indexes = KnowledgeFabricIndexRepository(database)
    corpus = KnowledgeCorpusRecord(
        id="user-corpus",
        name="User",
        owner_type="user",
        owner_id="user-1",
        visibility="private",
        default_authority_profile="standard",
        status="active",
    )
    with database.session() as session:
        session.add(corpus)
        session.commit()
    evidence_id = _ingest(
        fabric=fabric,
        content=content,
        storage=storage,
        corpus_id=corpus.id,
        key="user",
        text="User-only evidence.",
    )
    entry = indexes.upsert_retrieval_entry(evidence_id)
    embedding = indexes.upsert_embedding(
        retrieval_entry_id=entry.id,
        embedding_model="test-model",
        vector=[1.0, 0.0],
    )

    counts = fabric.delete_owner("user-1")

    assert counts["knowledge_fabric_retrieval_entries"] == 1
    assert counts["knowledge_fabric_evidence_embeddings"] == 1
    with database.session() as session:
        assert session.get(KnowledgeEvidenceRetrievalEntryRecord, entry.id) is None
        assert session.get(KnowledgeEvidenceEmbeddingRecord, embedding.id) is None


def test_postgresql_fts_and_dense_channels_when_explicit_test_database_is_available() -> None:
    postgres_url = _destructive_postgres_test_url()
    database = Database(postgres_url)
    with database.engine.begin() as connection:
        connection.exec_driver_sql("DROP SCHEMA public CASCADE")
        connection.exec_driver_sql("CREATE SCHEMA public")
    database.initialize()

    storage = _PrivateStorage(values={})
    fabric = KnowledgeFabricRepository(database, object_storage=storage)
    content = KnowledgeFabricContentRepository(database, object_storage=storage)
    indexes = KnowledgeFabricIndexRepository(database)
    scope = fabric.ensure_server_scope(
        platform="discord",
        connection_id="connection-postgres",
        workspace_id="guild-postgres",
    )
    corpus = fabric.create_system_global_corpus(
        name="PostgreSQL query corpus",
        description="",
        default_authority_profile="standard",
        status="active",
    )
    fabric.set_server_global_grant(
        server_scope_id=scope.id,
        corpus_id=corpus.id,
        enabled=True,
    )
    evidence_id = _ingest(
        fabric=fabric,
        content=content,
        storage=storage,
        corpus_id=corpus.id,
        key="postgres",
        text="Klee is the Spark Knight.",
    )
    entry = indexes.upsert_retrieval_entry(evidence_id)
    indexes.upsert_embedding(
        retrieval_entry_id=entry.id,
        embedding_model="test-model",
        vector=[1.0, 0.0],
    )

    result = KnowledgeQueryEngine(
        fabric_repository=fabric,
        index_repository=indexes,
        embedder=_Embedder(),
    ).query(
        KnowledgeQueryRequest(
            server_scope_id=scope.id,
            query="Klee",
            mode="overview",
            candidate_limit=4,
            result_limit=2,
        )
    )

    assert len(result.hits) == 1
    assert result.hits[0].evidence_unit_id == evidence_id
    assert result.hits[0].channels == ("sparse", "dense")
    with database.engine.connect() as connection:
        assert connection.execute(
            text(
                "SELECT embedding IS NOT NULL FROM knowledge_evidence_embeddings "
                "WHERE retrieval_entry_id = :entry_id"
            ),
            {"entry_id": entry.id},
        ).scalar_one() is True
