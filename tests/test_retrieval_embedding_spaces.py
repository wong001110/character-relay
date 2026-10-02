from __future__ import annotations

from dataclasses import replace

import pytest
import test_knowledge_fabric_phase5 as fabric_tests
from sqlalchemy import select, update

from echo_masque.embedding_space import EmbeddingSpace
from echo_masque.knowledge_fabric_query import KnowledgeQueryEngine, KnowledgeQueryRequest
from echo_masque.persistence.knowledge_fabric_models import (
    KnowledgeEvidenceEmbeddingRecord,
    KnowledgeEvidenceRetrievalEntryRecord,
)

SPACE = EmbeddingSpace("test-provider", "test-model", 2, "1")


class Encoder:
    def __init__(self, space=SPACE, fail=False):
        self.space, self.fail, self.calls = space, fail, 0

    def embed_query(self, _query):
        self.calls += 1
        if self.fail:
            raise RuntimeError("PRIVATE_PROVIDER_ERROR_BODY")
        return [1.0, 0.0]

    def embed_passage(self, _text):
        raise AssertionError("a history query must not backfill passage vectors")


@pytest.fixture
def env(tmp_path):
    return fabric_tests._seed(tmp_path)


def query(env, encoder, query="Spark Knight", limit=4):
    _, fabric, _, indexes, _, scope, _, _ = env
    return KnowledgeQueryEngine(
        fabric_repository=fabric,
        index_repository=indexes,
        embedder=encoder,
    ).query(
        KnowledgeQueryRequest(
            server_scope_id=scope,
            query=query,
            mode="overview",
            candidate_limit=4,
            result_limit=limit,
        )
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("provider", "other-provider"),
        ("model", "other-model"),
        ("version", "2"),
        ("dimension", 3),
    ],
)
def test_incompatible_space_is_cold_even_with_same_model_name_and_never_calls_provider(
    env,
    field,
    value,
):
    encoder = Encoder(replace(SPACE, **{field: value}))
    result = query(env, encoder)
    assert result.dense_index_status == "cold"
    assert result.hits and all("dense" not in hit.channels for hit in result.hits)
    assert encoder.calls == 0
    assert encoder.space.namespace != SPACE.namespace


def test_sparse_sufficient_skips_provider_and_never_loads_local_model(env):
    encoder = Encoder()
    result = query(env, encoder, limit=1)
    assert result.hits and result.dense_index_status == "not_requested_sparse_sufficient"
    assert encoder.calls == 0


def test_warm_prepared_index_makes_one_query_not_passage_backfill(env):
    encoder = Encoder()
    result = query(env, encoder)
    assert encoder.calls == 1 and result.dense_index_status in {"ready", "partial"}
    assert any("dense" in hit.channels for hit in result.hits)


def test_provider_error_keeps_sparse_evidence_and_reports_unavailable_without_error_text(env):
    result = query(env, Encoder(fail=True))
    assert result.hits and result.dense_index_status == "unavailable"
    assert "PRIVATE_PROVIDER_ERROR_BODY" not in repr(result)


def test_stale_hash_or_legacy_model_row_is_not_a_matching_index(env):
    db, _, _, _indexes, _, _, _, _ = env
    with db.session() as session:
        session.execute(update(KnowledgeEvidenceEmbeddingRecord).values(source_hash="stale"))
        session.commit()
    encoder = Encoder()
    result = query(env, encoder)
    assert result.dense_index_status == "cold" and encoder.calls == 0
    with db.session() as session:
        row = session.scalar(select(KnowledgeEvidenceEmbeddingRecord))
        entry = session.get(KnowledgeEvidenceRetrievalEntryRecord, row.retrieval_entry_id)
        row.source_hash = entry.content_sha256
        row.embedding_model = "test-model"
        session.commit()
    assert query(env, encoder).dense_index_status == "cold" and encoder.calls == 0


@pytest.mark.parametrize(
    "vector", [[], [1.0], [True, 0], [float("nan"), 0], [float("inf"), 0], [0, 0], [1, 0, 0]]
)
def test_index_and_queries_reject_invalid_vectors(env, vector):
    db, fabric, _, indexes, _, scope, _, _ = env
    with db.session() as session:
        entry = session.scalar(select(KnowledgeEvidenceRetrievalEntryRecord))
        entry_id = entry.id
    corpus_ids = frozenset(item.corpus.id for item in fabric.list_effective_corpora(scope))
    with pytest.raises(ValueError):
        indexes.upsert_embedding(retrieval_entry_id=entry_id, space=SPACE, vector=vector)
    with pytest.raises(ValueError):
        indexes.search_dense(
            authorized_corpus_ids=corpus_ids, space=SPACE, query_vector=vector, candidate_limit=4
        )


def test_corrupt_stored_vector_cannot_be_returned_as_a_dense_hit(env):
    db, _, _, _, _, _, _, _ = env
    with db.session() as session:
        session.execute(update(KnowledgeEvidenceEmbeddingRecord).values(embedding_json="[NaN,0]"))
        session.commit()
    result = query(env, Encoder())
    assert result.hits and all("dense" not in item.channels for item in result.hits)


def test_revoked_corpus_after_search_is_removed_before_results(env, monkeypatch):
    _, fabric, _, indexes, *_ = env
    original = indexes.search_sparse

    def revoke_after_sparse(**kwargs):
        result = original(**kwargs)
        monkeypatch.setattr(fabric, "list_effective_corpora", lambda *_: [])
        return result

    monkeypatch.setattr(indexes, "search_sparse", revoke_after_sparse)
    assert query(env, None).hits == ()
