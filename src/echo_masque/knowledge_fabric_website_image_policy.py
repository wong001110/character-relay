"""Pure admission rules for image candidates embedded in Website Collection pages.

These rules intentionally produce only candidates.  A synchronizer must still validate the
network destination before each fetch, persist admitted bytes in private object storage, and bind
the resulting artifact to the page's canonical document/evidence.  An HTML ``img`` element never
by itself makes remote media trusted Knowledge.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from echo_masque.knowledge_fabric_external_policy import (
    WebsiteSourceRejected,
    canonical_public_https_locator,
)

MAX_COLLECTION_IMAGE_CANDIDATES_PER_PAGE = 16
MAX_COLLECTION_IMAGE_BYTES = 8 * 1024 * 1024
_ALLOWED_IMAGE_CONTENT_TYPES = frozenset(
    {"image/gif", "image/jpeg", "image/png", "image/webp"}
)


class WebsiteCollectionImageRejected(ValueError):
    """A page image candidate or its eventual response violates the public-web contract."""


@dataclass(frozen=True, slots=True)
class WebsiteCollectionImageCandidate:
    """One deterministic embedded-image candidate, without any fetched image bytes."""

    locator: str
    structural_path: str
    alt_text: str


def discover_collection_image_candidates(
    *,
    page_locator: str,
    content: bytes,
    maximum_candidates: int = MAX_COLLECTION_IMAGE_CANDIDATES_PER_PAGE,
) -> tuple[WebsiteCollectionImageCandidate, ...]:
    """Extract a bounded, first-occurrence set of public same-origin ``img[src]`` candidates.

    Query-bearing, credential-bearing, cross-origin, data, and malformed URLs are intentionally
    omitted.  ``srcset`` and site-specific lazy-loading attributes are not interpreted: their
    selection semantics belong to a browser or a source-native adapter, neither of which is part
    of the generic public-web acquisition contract.
    """

    if maximum_candidates < 0:
        raise WebsiteCollectionImageRejected("Image candidate maximum cannot be negative.")
    if maximum_candidates == 0:
        return ()
    page = canonical_public_https_locator(page_locator)
    try:
        decoded = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WebsiteCollectionImageRejected("Website collection page is not UTF-8 HTML.") from exc
    parser = _CollectionImageParser()
    parser.feed(decoded)
    parser.close()
    page_host = urlsplit(page).hostname
    assert page_host is not None

    candidates: list[WebsiteCollectionImageCandidate] = []
    admitted_locators: set[str] = set()
    for ordinal, source, alt_text in parser.images:
        locator = _admit_same_origin_image(page=page, page_host=page_host, source=source)
        if locator is None or locator in admitted_locators:
            continue
        admitted_locators.add(locator)
        candidates.append(
            WebsiteCollectionImageCandidate(
                locator=locator,
                structural_path=f"image:{ordinal}",
                alt_text=_bounded_alt_text(alt_text),
            )
        )
        if len(candidates) >= maximum_candidates:
            break
    return tuple(candidates)


def website_collection_image_response_error_code(
    *,
    status_code: int,
    content_type: str,
    content: bytes,
) -> str | None:
    """Return a stable safe error code, or ``None`` for an admitted raster response.

    The declared type and byte signature must agree so a server cannot relabel arbitrary binary
    content as an image.  SVG is deliberately excluded: it is an active document format, not a
    bounded raster visual-reference artifact.
    """

    if status_code == 304:
        return "not_modified"
    if status_code in {401, 403}:
        return "authorization_failed"
    if 300 <= status_code < 400:
        return "redirect_refused"
    if status_code != 200:
        return "http_failed"
    if not content or len(content) > MAX_COLLECTION_IMAGE_BYTES:
        return "content_size_rejected"
    declared_type = content_type.casefold().split(";", maxsplit=1)[0].strip()
    if declared_type not in _ALLOWED_IMAGE_CONTENT_TYPES:
        return "content_type_rejected"
    if _sniff_raster_content_type(content) != declared_type:
        return "content_type_mismatch"
    return None


def _admit_same_origin_image(*, page: str, page_host: str, source: str) -> str | None:
    absolute = urljoin(page, source)
    try:
        candidate = canonical_public_https_locator(absolute)
    except WebsiteSourceRejected:
        return None
    if urlsplit(candidate).hostname != page_host:
        return None
    return candidate


def _bounded_alt_text(value: str) -> str:
    return " ".join(value.split())[:500]


def _sniff_raster_content_type(content: bytes) -> str | None:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


class _CollectionImageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.images: list[tuple[int, str, str]] = []
        self._image_count = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "img":
            return
        ordinal = self._image_count
        self._image_count += 1
        attributes = {name.casefold(): value for name, value in attrs}
        source = attributes.get("src")
        if not source:
            return
        self.images.append((ordinal, source, attributes.get("alt") or ""))


__all__ = [
    "MAX_COLLECTION_IMAGE_BYTES",
    "MAX_COLLECTION_IMAGE_CANDIDATES_PER_PAGE",
    "WebsiteCollectionImageCandidate",
    "WebsiteCollectionImageRejected",
    "discover_collection_image_candidates",
    "website_collection_image_response_error_code",
]
