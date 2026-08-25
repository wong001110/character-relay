"""Pure safety, validator, and response decisions for public Website Source sync."""

from __future__ import annotations

from hashlib import sha256
from urllib.parse import urlsplit, urlunsplit

WEBSITE_PUBLIC_HTTPS_SOURCE_TYPE = "website_public_https"
ATOM_PUBLIC_HTTPS_SOURCE_TYPE = "atom_public_https"
_MAX_WEBSITE_RESPONSE_BYTES = 1_048_576
_MAX_WEBSITE_VALIDATOR_CHARACTERS = 512
_ALLOWED_CONTENT_TYPES = frozenset({"text/html", "text/markdown", "text/plain"})


class WebsiteSourceRejected(ValueError):
    """A Website Source does not satisfy the deliberately narrow first sync contract."""


def canonical_public_https_locator(locator: str) -> str:
    """Accept one credential-free public HTTPS page identity without query or fragment state."""

    try:
        parsed = urlsplit(locator)
        port = parsed.port
    except ValueError as exc:
        raise WebsiteSourceRejected("Website locator is invalid.") from exc
    if parsed.scheme != "https" or not parsed.hostname:
        raise WebsiteSourceRejected("Website locator must use HTTPS.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise WebsiteSourceRejected("Website locator contains unsupported authority or state.")
    if port not in {None, 443}:
        raise WebsiteSourceRejected("Website locator uses an unsupported port.")
    hostname = parsed.hostname.rstrip(".").casefold()
    if not hostname:
        raise WebsiteSourceRejected("Website locator is invalid.")
    path = parsed.path or "/"
    return urlunsplit(("https", hostname, path, "", ""))


def conditional_request_headers(*, etag: str | None, last_modified: str | None) -> dict[str, str]:
    """Build only safe conditional headers persisted for this exact Source."""

    headers: dict[str, str] = {"Accept": "text/html,text/markdown,text/plain;q=0.9"}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    return headers


def normalized_website_validator(value: str | None) -> str | None:
    """Retain only a bounded single-line response validator for a future conditional request."""

    if value is None:
        return None
    cleaned = value.strip()
    if (
        not cleaned
        or len(cleaned) > _MAX_WEBSITE_VALIDATOR_CHARACTERS
        or any(ord(character) < 32 for character in cleaned)
    ):
        raise WebsiteSourceRejected("Website response validator is invalid.")
    return cleaned


def website_response_error_code(
    *,
    status_code: int,
    content_type: str,
    content_size: int,
) -> str | None:
    """Return a bounded non-secret error code, or ``None`` for an ingestible 200 response."""

    if status_code == 304:
        return "not_modified"
    if status_code in {401, 403}:
        return "authorization_failed"
    if 300 <= status_code < 400:
        return "redirect_refused"
    if status_code != 200:
        return "http_failed"
    if content_size <= 0 or content_size > _MAX_WEBSITE_RESPONSE_BYTES:
        return "content_size_rejected"
    if content_type.casefold().split(";", maxsplit=1)[0].strip() not in _ALLOWED_CONTENT_TYPES:
        return "content_type_rejected"
    return None


def website_response_version_key(content: bytes) -> str:
    """Use exact response bytes for both immutable version identity and retry determinism."""

    return f"website:{sha256(content).hexdigest()}"


def website_response_idempotency_key(*, source_id: str, content: bytes) -> str:
    """Scope deterministic response identity to a Fabric Source without using its locator."""

    if not source_id.strip():
        raise WebsiteSourceRejected("Website Source identity is required.")
    return f"website:{sha256((source_id + '\0').encode() + content).hexdigest()}"


__all__ = [
    "ATOM_PUBLIC_HTTPS_SOURCE_TYPE",
    "WEBSITE_PUBLIC_HTTPS_SOURCE_TYPE",
    "WebsiteSourceRejected",
    "canonical_public_https_locator",
    "conditional_request_headers",
    "normalized_website_validator",
    "website_response_error_code",
    "website_response_idempotency_key",
    "website_response_version_key",
]
