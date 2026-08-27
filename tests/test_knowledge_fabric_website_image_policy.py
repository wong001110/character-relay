from __future__ import annotations

import pytest

from echo_masque.knowledge_fabric_website_image_policy import (
    MAX_COLLECTION_IMAGE_BYTES,
    WebsiteCollectionImageRejected,
    discover_collection_image_candidates,
    website_collection_image_response_error_code,
)


def test_image_candidates_are_bounded_same_origin_and_structurally_addressable() -> None:
    page = """
    <html><body>
      <img src="/images/amber.webp" alt=" Amber\n the Outrider ">
      <img src="https://example.test/images/amber.webp" alt="duplicate">
      <img src="https://other.test/images/lumine.png" alt="cross origin">
      <img src="/images/mona.png?cache=1" alt="query rejected">
      <img src="data:image/png;base64,AAA" alt="inline rejected">
      <img data-src="/images/lazy.png" alt="not a generic contract">
      <img src="/images/lumine.png" alt="Lumíne">
    </body></html>
    """.encode()

    candidates = discover_collection_image_candidates(
        page_locator="https://example.test/wiki/amber",
        content=page,
    )

    assert [(item.locator, item.structural_path, item.alt_text) for item in candidates] == [
        ("https://example.test/images/amber.webp", "image:0", "Amber the Outrider"),
        ("https://example.test/images/lumine.png", "image:6", "Lumíne"),
    ]


def test_image_candidates_stop_at_requested_budget_and_reject_invalid_inputs() -> None:
    page = b"<img src='/a.png'><img src='/b.png'><img src='/c.png'>"

    candidates = discover_collection_image_candidates(
        page_locator="https://example.test/wiki",
        content=page,
        maximum_candidates=2,
    )
    assert [item.locator for item in candidates] == [
        "https://example.test/a.png",
        "https://example.test/b.png",
    ]
    assert discover_collection_image_candidates(
        page_locator="https://example.test/wiki", content=page, maximum_candidates=0
    ) == ()
    with pytest.raises(WebsiteCollectionImageRejected, match="maximum"):
        discover_collection_image_candidates(
            page_locator="https://example.test/wiki", content=page, maximum_candidates=-1
        )
    with pytest.raises(WebsiteCollectionImageRejected, match="UTF-8"):
        discover_collection_image_candidates(
            page_locator="https://example.test/wiki", content=b"\xff"
        )


@pytest.mark.parametrize(
    ("content_type", "content"),
    [
        ("image/png", b"\x89PNG\r\n\x1a\nprivate"),
        ("image/jpeg; charset=binary", b"\xff\xd8\xffprivate"),
        ("image/gif", b"GIF89aprivate"),
        ("image/webp", b"RIFF1234WEBPprivate"),
    ],
)
def test_image_response_requires_matching_declared_type_and_raster_signature(
    content_type: str, content: bytes
) -> None:
    assert (
        website_collection_image_response_error_code(
            status_code=200, content_type=content_type, content=content
        )
        is None
    )


@pytest.mark.parametrize(
    ("status_code", "content_type", "content", "expected"),
    [
        (304, "image/png", b"", "not_modified"),
        (403, "image/png", b"", "authorization_failed"),
        (302, "image/png", b"", "redirect_refused"),
        (404, "image/png", b"", "http_failed"),
        (200, "image/svg+xml", b"<svg/>", "content_type_rejected"),
        (200, "image/png", b"not an image", "content_type_mismatch"),
        (200, "image/jpeg", b"\x89PNG\r\n\x1a\nprivate", "content_type_mismatch"),
    ],
)
def test_image_response_rejects_unsafe_or_unverifiable_content(
    status_code: int, content_type: str, content: bytes, expected: str
) -> None:
    assert website_collection_image_response_error_code(
        status_code=status_code, content_type=content_type, content=content
    ) == expected


def test_image_response_rejects_response_larger_than_the_image_budget() -> None:
    content = b"\x89PNG\r\n\x1a\n" + b"x" * MAX_COLLECTION_IMAGE_BYTES

    assert website_collection_image_response_error_code(
        status_code=200, content_type="image/png", content=content
    ) == "content_size_rejected"
