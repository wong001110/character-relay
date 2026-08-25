from __future__ import annotations

from datetime import UTC, datetime

import pytest

from echo_masque.knowledge_fabric_atom_adapter import (
    AtomResponseInput,
    AtomResponseRejected,
    KnowledgeFabricAtomAdapter,
)
from echo_masque.knowledge_fabric_atom_policy import atom_response_error_code


def _input(content: bytes) -> AtomResponseInput:
    return AtomResponseInput(
        source_id="source-1",
        locator="https://example.test/feed",
        content=content,
        content_type="application/atom+xml; charset=utf-8",
        fetched_at=datetime(2026, 8, 26, tzinfo=UTC),
    )


def test_atom_adapter_preserves_safe_entry_evidence_without_following_links() -> None:
    snapshot = KnowledgeFabricAtomAdapter().build_snapshot(
        _input(
            b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">'
            b"<title>News</title><entry><id>tag:example.test,2026:1</id><title>First</title>"
            b"<summary>Useful update.</summary><link href=\"https://example.test/post/1\"/>"
            b"</entry></feed>"
        )
    )
    assert snapshot.version_key.startswith("atom:")
    assert len(snapshot.documents) == 1
    document = snapshot.documents[0]
    assert document.title == "First"
    assert document.blocks[0].text_content == "Useful update."
    assert document.blocks[0].coordinates["entry_link"] == "https://example.test/post/1"


@pytest.mark.parametrize(
    "content",
    [
        b"<!DOCTYPE feed><feed/>",
        b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>x</id></entry></feed>',
        b"<feed />",
    ],
)
def test_atom_adapter_rejects_unsafe_or_non_usable_feed(content: bytes) -> None:
    with pytest.raises(AtomResponseRejected):
        KnowledgeFabricAtomAdapter().build_snapshot(_input(content))


def test_atom_response_contract_is_bounded_and_content_type_specific() -> None:
    cases = (
        (304, "", 0, "not_modified"),
        (401, "application/atom+xml", 1, "authorization_failed"),
        (403, "application/atom+xml", 1, "authorization_failed"),
        (404, "application/atom+xml", 1, "http_failed"),
        (300, "application/atom+xml", 1, "redirect_refused"),
        (302, "application/atom+xml", 1, "redirect_refused"),
        (400, "application/atom+xml", 1, "http_failed"),
        (200, "application/atom+xml", 0, "content_size_rejected"),
        (200, "application/atom+xml", 1_048_577, "content_size_rejected"),
        (200, "text/html", 1, "content_type_rejected"),
        (200, "APPLICATION/ATOM+XML; charset=utf-8", 1, None),
        (200, "application/atom+xml; charset=utf-8; revision=1", 1, None),
        (200, "application/xml", 1_048_576, None),
    )
    for status_code, content_type, content_size, expected in cases:
        assert atom_response_error_code(
            status_code=status_code,
            content_type=content_type,
            content_size=content_size,
        ) == expected
