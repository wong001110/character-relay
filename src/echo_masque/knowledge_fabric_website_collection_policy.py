"""Bounded, same-origin admission rules for a public website collection."""

from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from echo_masque.knowledge_fabric_external_policy import (
    WebsiteSourceRejected,
    canonical_public_https_locator,
)

MAX_COLLECTION_PAGES = 50


class WebsiteCollectionRejected(ValueError):
    """A collection discovery result exceeds its deliberately small public-web contract."""


def discover_collection_page_locators(*, root_locator: str, content: bytes) -> tuple[str, ...]:
    """Return a deterministic, same-origin root-plus-link set without following navigation.

    The synchronizer fetches this single, bounded set.  It does not recursively crawl links,
    follow redirects, or admit query-bearing/credential-bearing URLs.
    """

    root = canonical_public_https_locator(root_locator)
    try:
        decoded = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WebsiteCollectionRejected("Website collection root is not UTF-8 HTML.") from exc
    parser = _CollectionLinkParser()
    parser.feed(decoded)
    root_host = urlsplit(root).hostname
    assert root_host is not None
    locators = {root}
    for href in parser.hrefs:
        candidate = _admit_same_origin_link(root=root, root_host=root_host, href=href)
        if candidate is not None:
            locators.add(candidate)
        if len(locators) > MAX_COLLECTION_PAGES:
            raise WebsiteCollectionRejected("Website collection has too many discovered pages.")
    return tuple(sorted(locators))


def _admit_same_origin_link(*, root: str, root_host: str, href: str) -> str | None:
    absolute = urljoin(root, href)
    try:
        candidate = canonical_public_https_locator(absolute)
    except WebsiteSourceRejected:
        return None
    if urlsplit(candidate).hostname != root_host:
        return None
    return candidate


class _CollectionLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "a":
            return
        for name, value in attrs:
            if name.casefold() == "href" and value:
                self.hrefs.append(value)
                return


__all__ = [
    "MAX_COLLECTION_PAGES",
    "WebsiteCollectionRejected",
    "discover_collection_page_locators",
]
