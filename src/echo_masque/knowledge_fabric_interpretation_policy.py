"""Pure lifecycle rules for corpus-bound Knowledge Fabric interpretations."""

from __future__ import annotations

RESOLUTION_ACTIVE = "active"
RESOLUTION_REJECTED = "rejected"
RESOLUTION_SUPERSEDED = "superseded"
RESOLUTION_STATUSES = frozenset(
    {RESOLUTION_ACTIVE, RESOLUTION_REJECTED, RESOLUTION_SUPERSEDED}
)
INTERPRETATION_STATUSES = frozenset(
    {"active", "disputed", "unresolved", "superseded", "rejected"}
)


def resolution_status_is_valid(status: str) -> bool:
    """Only explicit resolution states may be persisted."""

    return status in RESOLUTION_STATUSES


def may_replace_active_resolution(
    *,
    existing_canonical_id: str,
    next_canonical_id: str,
) -> bool:
    """A reassignment creates a successor; it never mutates identity in place."""

    return bool(
        existing_canonical_id
        and next_canonical_id
        and existing_canonical_id != next_canonical_id
    )


def interpretation_status_is_valid(status: str) -> bool:
    """Keep support, dispute, and unresolved corpus interpretations representable."""

    return status in INTERPRETATION_STATUSES


def world_interpretation_promotes_to_belief() -> bool:
    """Imported corpus interpretation never writes Character Belief automatically."""

    return False


__all__ = [
    "INTERPRETATION_STATUSES",
    "RESOLUTION_ACTIVE",
    "RESOLUTION_REJECTED",
    "RESOLUTION_STATUSES",
    "RESOLUTION_SUPERSEDED",
    "interpretation_status_is_valid",
    "may_replace_active_resolution",
    "resolution_status_is_valid",
    "world_interpretation_promotes_to_belief",
]
