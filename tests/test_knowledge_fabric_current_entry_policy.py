from __future__ import annotations

import pytest

from echo_masque.knowledge_fabric_current_entry_policy import (
    current_evidence_must_be_invalidated,
    may_reuse_current_evidence,
)


@pytest.mark.parametrize(
    ("status", "current_hash", "evidence_id", "incoming_hash", "expected"),
    [
        ("available", "same", "evidence-1", "same", True),
        ("available", "old", "evidence-1", "new", False),
        ("removed", "same", "evidence-1", "same", False),
        ("available", "same", None, "same", False),
    ],
)
def test_only_available_identical_entries_reuse_current_evidence(
    status: str,
    current_hash: str | None,
    evidence_id: str | None,
    incoming_hash: str,
    expected: bool,
) -> None:
    assert (
        may_reuse_current_evidence(
            current_status=status,
            current_content_sha256=current_hash,
            current_evidence_unit_id=evidence_id,
            incoming_content_sha256=incoming_hash,
        )
        is expected
    )


@pytest.mark.parametrize(
    ("status", "evidence_id", "expected"),
    [
        ("available", "evidence-1", True),
        ("available", None, False),
        ("removed", "evidence-1", False),
    ],
)
def test_only_available_prior_evidence_is_invalidated(
    status: str,
    evidence_id: str | None,
    expected: bool,
) -> None:
    assert (
        current_evidence_must_be_invalidated(status=status, evidence_unit_id=evidence_id)
        is expected
    )
