"""Pure validity rules for disposable Knowledge Fabric Projections."""

from __future__ import annotations


def source_projection_is_current(
    *,
    projection_source_hash: str,
    current_source_hash: str,
    stale: bool,
) -> bool:
    """A view is usable only when its source snapshot still matches and is not stale."""

    return not stale and projection_source_hash == current_source_hash


__all__ = ["source_projection_is_current"]
