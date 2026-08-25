"""Deterministic lifecycle rules for immutable Knowledge Fabric ingestion."""

from __future__ import annotations

import re

JOB_QUEUED = "queued"
JOB_RUNNING = "running"
JOB_COMPLETED = "completed"
JOB_FAILED = "failed"
JOB_STATES = frozenset({JOB_QUEUED, JOB_RUNNING, JOB_COMPLETED, JOB_FAILED})
JOB_TERMINAL_STATES = frozenset({JOB_COMPLETED, JOB_FAILED})

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def job_is_terminal(status: str) -> bool:
    """Return whether a job cannot be claimed until an explicit retry/requeue."""

    return status in JOB_TERMINAL_STATES


def may_claim_ingestion_job(status: str) -> bool:
    """Only queued or explicitly failed work may start another attempt."""

    return status in {JOB_QUEUED, JOB_FAILED}


def may_requeue_ingestion_job(status: str) -> bool:
    """A restart recovery only requeues work that was interrupted while running."""

    return status == JOB_RUNNING


def source_version_hash_matches(*, existing_hash: str, incoming_hash: str) -> bool:
    """Make duplicate source-version delivery idempotent, never an overwrite."""

    return existing_hash == incoming_hash


def deterministic_artifact_key(*, prefix: str, source_id: str, content_sha256: str) -> str:
    """Use content addressing so repeated upload attempts target one private object."""

    normalized_prefix = prefix.strip("/")
    if not normalized_prefix or "/" in source_id or not source_id:
        raise ValueError("Knowledge artifact identity is invalid.")
    if _SHA256.fullmatch(content_sha256) is None:
        raise ValueError("Knowledge artifact content hash must be SHA-256.")
    return f"{normalized_prefix}/{source_id}/{content_sha256[:2]}/{content_sha256}"


__all__ = [
    "JOB_COMPLETED",
    "JOB_FAILED",
    "JOB_QUEUED",
    "JOB_RUNNING",
    "JOB_STATES",
    "JOB_TERMINAL_STATES",
    "deterministic_artifact_key",
    "job_is_terminal",
    "may_claim_ingestion_job",
    "may_requeue_ingestion_job",
    "source_version_hash_matches",
]
