"""Profile and analysis boundary for explicitly approved rendered site collections.

The ordinary Site Collection synchronizer is intentionally static-first.  Some public sites are
client-rendered applications, though, and expose no useful sitemap or server-rendered links.  This
module keeps the opt-in rendering decision in a small, reviewable Source profile rather than
encoding site-specific behaviour in the worker.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlsplit

from echo_masque.knowledge_fabric_external_policy import (
    WebsiteSourceRejected,
    canonical_public_https_locator,
    website_response_error_code,
)
from echo_masque.knowledge_fabric_website_sync import WebsiteFetcher

RENDERER_PROFILE_KEY = "collection_renderer"
RENDER_HOSTS_PROFILE_KEY = "collection_render_hosts"
RENDER_PAGE_LIMIT_PROFILE_KEY = "collection_render_page_limit"
RENDER_DEPTH_PROFILE_KEY = "collection_render_max_depth"
RENDERER_BROWSER = "browser"
MAX_RENDERED_COLLECTION_HOSTS = 8
MAX_RENDERED_COLLECTION_PAGES = 100
MAX_RENDERED_COLLECTION_DEPTH = 3
DEFAULT_RENDERED_COLLECTION_PAGE_LIMIT = 50
DEFAULT_RENDERED_COLLECTION_DEPTH = 1


class RenderedCollectionRejected(ValueError):
    """A requested rendered-collection profile is invalid or outside its approval boundary."""


@dataclass(frozen=True, slots=True)
class RenderedCollectionProfile:
    """One persisted, bounded browser acquisition decision for a Source."""

    enabled: bool
    allowed_hosts: frozenset[str]
    page_limit: int
    max_depth: int


@dataclass(frozen=True, slots=True)
class RenderedCollectionAnalysis:
    """Redaction-safe candidate hosts observed in a Source's public bootstrap document."""

    source_id: str
    candidate_hosts: tuple[str, ...]


def rendered_collection_profile(
    *,
    locator: str,
    parser_profile_json: str,
) -> RenderedCollectionProfile:
    """Parse a Source profile without treating registration as renderer consent."""

    root = canonical_public_https_locator(locator)
    root_host = _hostname(root)
    profile = _profile_mapping(parser_profile_json)
    enabled = profile.get(RENDERER_PROFILE_KEY) == RENDERER_BROWSER
    if not enabled:
        return RenderedCollectionProfile(
            enabled=False,
            allowed_hosts=frozenset({root_host}),
            page_limit=DEFAULT_RENDERED_COLLECTION_PAGE_LIMIT,
            max_depth=DEFAULT_RENDERED_COLLECTION_DEPTH,
        )
    hosts = _profile_hosts(profile.get(RENDER_HOSTS_PROFILE_KEY, ""))
    page_limit = _bounded_profile_integer(
        profile.get(RENDER_PAGE_LIMIT_PROFILE_KEY),
        default=DEFAULT_RENDERED_COLLECTION_PAGE_LIMIT,
        minimum=1,
        maximum=MAX_RENDERED_COLLECTION_PAGES,
        name="Rendered collection page limit",
    )
    max_depth = _bounded_profile_integer(
        profile.get(RENDER_DEPTH_PROFILE_KEY),
        default=DEFAULT_RENDERED_COLLECTION_DEPTH,
        minimum=0,
        maximum=MAX_RENDERED_COLLECTION_DEPTH,
        name="Rendered collection max depth",
    )
    return RenderedCollectionProfile(
        enabled=True,
        allowed_hosts=frozenset({root_host, *hosts}),
        page_limit=page_limit,
        max_depth=max_depth,
    )


def configured_rendered_collection_profile(
    *,
    current_profile_json: str,
    enabled: bool,
    allowed_hosts: tuple[str, ...],
    page_limit: int,
    max_depth: int,
) -> str:
    """Replace only the rendered-collection settings and preserve unrelated parser directives."""

    profile = _profile_mapping(current_profile_json)
    if not enabled:
        for key in (
            RENDERER_PROFILE_KEY,
            RENDER_HOSTS_PROFILE_KEY,
            RENDER_PAGE_LIMIT_PROFILE_KEY,
            RENDER_DEPTH_PROFILE_KEY,
        ):
            profile.pop(key, None)
        return json.dumps(profile, sort_keys=True, separators=(",", ":"))
    hosts = _normalized_hosts(allowed_hosts)
    profile.update(
        {
            RENDERER_PROFILE_KEY: RENDERER_BROWSER,
            RENDER_HOSTS_PROFILE_KEY: ",".join(hosts),
            RENDER_PAGE_LIMIT_PROFILE_KEY: str(
                _bounded_profile_integer(
                    str(page_limit),
                    default=DEFAULT_RENDERED_COLLECTION_PAGE_LIMIT,
                    minimum=1,
                    maximum=MAX_RENDERED_COLLECTION_PAGES,
                    name="Rendered collection page limit",
                )
            ),
            RENDER_DEPTH_PROFILE_KEY: str(
                _bounded_profile_integer(
                    str(max_depth),
                    default=DEFAULT_RENDERED_COLLECTION_DEPTH,
                    minimum=0,
                    maximum=MAX_RENDERED_COLLECTION_DEPTH,
                    name="Rendered collection max depth",
                )
            ),
        }
    )
    return json.dumps(profile, sort_keys=True, separators=(",", ":"))


def extract_render_candidate_hosts(*, root_locator: str, content: bytes) -> tuple[str, ...]:
    """Return public preconnect/dns-prefetch hosts declared by an admitted HTML bootstrap page."""

    root_host = _hostname(canonical_public_https_locator(root_locator))
    try:
        decoded = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RenderedCollectionRejected(
            "Rendered collection bootstrap is not UTF-8 HTML."
        ) from exc
    parser = _RenderHostParser()
    parser.feed(decoded)
    candidates: set[str] = set()
    for href in parser.hrefs:
        try:
            candidate = canonical_public_https_locator(href)
        except WebsiteSourceRejected:
            continue
        host = _hostname(candidate)
        if host != root_host:
            candidates.add(host)
        if len(candidates) > MAX_RENDERED_COLLECTION_HOSTS:
            raise RenderedCollectionRejected(
                "Rendered collection declares too many external hosts."
            )
    return tuple(sorted(candidates))


class KnowledgeFabricRenderedCollectionAnalyzer:
    """Read one public bootstrap page to propose, but never activate, renderer host candidates."""

    def __init__(self, fetcher: WebsiteFetcher) -> None:
        self.fetcher = fetcher

    async def analyze(self, *, source_id: str, locator: str) -> RenderedCollectionAnalysis:
        root = canonical_public_https_locator(locator)
        if root != locator:
            raise RenderedCollectionRejected("Rendered collection locator is not canonical.")
        try:
            response = await self.fetcher.fetch(
                url=root,
                headers={"Accept": "text/html"},
            )
        except Exception as exc:
            raise RenderedCollectionRejected("Public bootstrap page could not be read.") from exc
        error = website_response_error_code(
            status_code=response.status_code,
            content_type=response.headers.get("content-type", ""),
            content_size=len(response.content),
        )
        if error is not None:
            raise RenderedCollectionRejected("Public bootstrap page is not admissible.")
        return RenderedCollectionAnalysis(
            source_id=source_id,
            candidate_hosts=extract_render_candidate_hosts(
                root_locator=root,
                content=response.content,
            ),
        )


def _profile_mapping(raw: str) -> dict[str, str]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RenderedCollectionRejected("Source parser profile is invalid.") from exc
    if not isinstance(parsed, dict) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in parsed.items()
    ):
        raise RenderedCollectionRejected("Source parser profile is invalid.")
    return dict(parsed)


def _profile_hosts(value: str) -> tuple[str, ...]:
    if not value.strip():
        return ()
    return _normalized_hosts(tuple(part for part in value.split(",") if part.strip()))


def _normalized_hosts(values: tuple[str, ...]) -> tuple[str, ...]:
    hosts: set[str] = set()
    for value in values:
        candidate = value.strip().rstrip(".").casefold()
        if not candidate or any(character in candidate for character in "/:@?#"):
            raise RenderedCollectionRejected("Rendered collection host is invalid.")
        try:
            host = _hostname(canonical_public_https_locator(f"https://{candidate}/"))
        except WebsiteSourceRejected as exc:
            raise RenderedCollectionRejected("Rendered collection host is invalid.") from exc
        hosts.add(host)
    if len(hosts) > MAX_RENDERED_COLLECTION_HOSTS:
        raise RenderedCollectionRejected("Rendered collection allows too many hosts.")
    return tuple(sorted(hosts))


def _bounded_profile_integer(
    value: str | None,
    *,
    default: int,
    minimum: int,
    maximum: int,
    name: str,
) -> int:
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise RenderedCollectionRejected(f"{name} is invalid.") from exc
    if parsed < minimum or parsed > maximum:
        raise RenderedCollectionRejected(f"{name} is outside the approved range.")
    return parsed


def _hostname(locator: str) -> str:
    hostname = urlsplit(locator).hostname
    if hostname is None:
        raise RenderedCollectionRejected("Rendered collection host is invalid.")
    return hostname.casefold().rstrip(".")


class _RenderHostParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "link":
            return
        values = {key.casefold(): (value or "") for key, value in attrs}
        rel = set(values.get("rel", "").casefold().split())
        href = values.get("href", "")
        if href and rel.intersection({"preconnect", "dns-prefetch"}):
            self.hrefs.append(href)


__all__ = [
    "DEFAULT_RENDERED_COLLECTION_DEPTH",
    "DEFAULT_RENDERED_COLLECTION_PAGE_LIMIT",
    "MAX_RENDERED_COLLECTION_DEPTH",
    "MAX_RENDERED_COLLECTION_HOSTS",
    "MAX_RENDERED_COLLECTION_PAGES",
    "KnowledgeFabricRenderedCollectionAnalyzer",
    "RenderedCollectionAnalysis",
    "RenderedCollectionProfile",
    "RenderedCollectionRejected",
    "configured_rendered_collection_profile",
    "extract_render_candidate_hosts",
    "rendered_collection_profile",
]
