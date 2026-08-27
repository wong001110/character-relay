"""DTD-free, same-origin sitemap discovery decisions for Site Collection Sources."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from defusedxml import ElementTree  # type: ignore[import-untyped]

from echo_masque.knowledge_fabric_external_policy import (
    WebsiteSourceRejected,
    canonical_public_https_locator,
)

MAX_SITEMAP_DOCUMENTS = 20
MAX_SITEMAP_PAGES = 1_000
MAX_SITEMAP_RESPONSE_BYTES = 1_048_576


class WebsiteSitemapRejected(ValueError):
    """A sitemap is unsafe, malformed, cross-origin, or outside the bounded contract."""


def sitemap_response_error_code(
    *, status_code: int, content_type: str, content_size: int
) -> str | None:
    """Admit one small XML sitemap document before parsing it."""

    if status_code != 200:
        return "status_rejected"
    normalized_type = content_type.casefold().split(";", maxsplit=1)[0].strip()
    allowed_content_types = {
        "application/xml",
        "text/xml",
        "application/xhtml+xml",
        "text/plain",
    }
    if normalized_type not in allowed_content_types:
        return "content_type_rejected"
    if content_size <= 0 or content_size > MAX_SITEMAP_RESPONSE_BYTES:
        return "content_size_rejected"
    return None


@dataclass(frozen=True, slots=True)
class WebsiteSitemapManifest:
    pages: tuple[str, ...]
    child_sitemaps: tuple[str, ...]


def default_sitemap_locator(root_locator: str) -> str:
    root = canonical_public_https_locator(root_locator)
    parsed = urlsplit(root)
    assert parsed.hostname is not None
    return urlunsplit(("https", parsed.hostname, "/sitemap.xml", "", ""))


def parse_sitemap(
    *, sitemap_locator: str, content: bytes, root_locator: str
) -> WebsiteSitemapManifest:
    """Parse one sitemap document without following links or accepting another origin."""

    if b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
        raise WebsiteSitemapRejected("Sitemap may not declare DTD or entities.")
    try:
        root = ElementTree.fromstring(content)
    except (ElementTree.ParseError, ValueError) as exc:
        raise WebsiteSitemapRejected("Sitemap is not valid XML.") from exc
    root_host = urlsplit(canonical_public_https_locator(root_locator)).hostname
    assert root_host is not None
    tag = _local_name(root.tag)
    if tag == "urlset":
        pages = _admit_locators(root, "url", root_host)
        return WebsiteSitemapManifest(pages=pages, child_sitemaps=())
    if tag == "sitemapindex":
        children = _admit_locators(root, "sitemap", root_host)
        return WebsiteSitemapManifest(pages=(), child_sitemaps=children)
    raise WebsiteSitemapRejected("Sitemap root must be urlset or sitemapindex.")


def _admit_locators(root: ElementTree.Element, item_name: str, root_host: str) -> tuple[str, ...]:
    locators: set[str] = set()
    for item in root:
        if _local_name(item.tag) != item_name:
            continue
        location = next(
            (
                "".join(child.itertext()).strip()
                for child in item
                if _local_name(child.tag) == "loc"
            ),
            "",
        )
        try:
            locator = canonical_public_https_locator(location)
        except WebsiteSourceRejected as exc:
            raise WebsiteSitemapRejected(
                "Sitemap locator is not an admitted public HTTPS URL."
            ) from exc
        if urlsplit(locator).hostname != root_host:
            raise WebsiteSitemapRejected("Sitemap locator must be same-origin.")
        locators.add(locator)
        if len(locators) > (MAX_SITEMAP_PAGES if item_name == "url" else MAX_SITEMAP_DOCUMENTS):
            raise WebsiteSitemapRejected("Sitemap exceeds the collection limit.")
    return tuple(sorted(locators))


def _local_name(tag: str) -> str:
    return tag.rsplit("}", maxsplit=1)[-1]


__all__ = [
    "MAX_SITEMAP_DOCUMENTS",
    "MAX_SITEMAP_PAGES",
    "MAX_SITEMAP_RESPONSE_BYTES",
    "WebsiteSitemapManifest",
    "WebsiteSitemapRejected",
    "default_sitemap_locator",
    "parse_sitemap",
    "sitemap_response_error_code",
]
