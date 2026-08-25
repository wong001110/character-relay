"""Pure bounded transport decisions for Atom 1.0 Source snapshots."""

_MAX_ATOM_RESPONSE_BYTES = 1_048_576
_ALLOWED_ATOM_CONTENT_TYPES = frozenset({"application/atom+xml", "application/xml", "text/xml"})


def atom_response_error_code(
    *,
    status_code: int,
    content_type: str,
    content_size: int,
) -> str | None:
    if status_code == 304:
        return "not_modified"
    if status_code in {401, 403}:
        return "authorization_failed"
    if 300 <= status_code < 400:
        return "redirect_refused"
    if status_code != 200:
        return "http_failed"
    if content_size <= 0 or content_size > _MAX_ATOM_RESPONSE_BYTES:
        return "content_size_rejected"
    if content_type.casefold().split(";", maxsplit=1)[0].strip() not in _ALLOWED_ATOM_CONTENT_TYPES:
        return "content_type_rejected"
    return None


__all__ = ["atom_response_error_code"]
