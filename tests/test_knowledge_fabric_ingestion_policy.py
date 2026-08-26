import pytest

from echo_masque.knowledge_fabric_ingestion_policy import (
    JOB_COMPLETED,
    JOB_FAILED,
    JOB_QUEUED,
    JOB_RUNNING,
    deterministic_artifact_key,
    job_is_terminal,
    may_claim_ingestion_job,
    may_requeue_ingestion_job,
    source_version_hash_matches,
)


def test_job_claim_and_restart_policy_fails_closed() -> None:
    assert may_claim_ingestion_job(JOB_QUEUED)
    assert may_claim_ingestion_job(JOB_FAILED)
    assert not may_claim_ingestion_job(JOB_RUNNING)
    assert not may_claim_ingestion_job(JOB_COMPLETED)
    assert may_requeue_ingestion_job(JOB_RUNNING)
    assert not may_requeue_ingestion_job(JOB_FAILED)
    assert job_is_terminal(JOB_COMPLETED)
    assert job_is_terminal(JOB_FAILED)
    assert not job_is_terminal(JOB_QUEUED)


def test_source_version_hash_equality_is_the_only_idempotency_match() -> None:
    assert source_version_hash_matches(existing_hash="a" * 64, incoming_hash="a" * 64)
    assert not source_version_hash_matches(existing_hash="a" * 64, incoming_hash="b" * 64)


def test_content_addressed_object_key_rejects_invalid_scope_or_hash() -> None:
    assert deterministic_artifact_key(
        prefix="knowledge-fabric/",
        source_id="source-1",
        content_sha256="a" * 64,
    ) == f"knowledge-fabric/source-1/aa/{'a' * 64}"
    assert deterministic_artifact_key(
        prefix="/X/knowledge-fabric/X/",
        source_id="source-1",
        content_sha256="a" * 64,
    ) == f"X/knowledge-fabric/X/source-1/aa/{'a' * 64}"
    with pytest.raises(ValueError, match="identity"):
        deterministic_artifact_key(
            prefix="knowledge-fabric",
            source_id="../source",
            content_sha256="a" * 64,
        )
    with pytest.raises(ValueError, match="SHA-256"):
        deterministic_artifact_key(
            prefix="knowledge-fabric",
            source_id="source-1",
            content_sha256="not-a-hash",
        )
