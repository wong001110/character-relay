"""Deterministic guardrails for externally compared visual references."""

from __future__ import annotations

from typing import Final

FICTIONAL_CHARACTER_ENTITY_TYPE: Final = "fictional_character"
MAX_EXTERNAL_COMPARISON_REFERENCES: Final = 5
EXTERNAL_COMPARISON_CONFIDENCE_THRESHOLD: Final = 0.96


def external_comparison_is_authorizable(*, entity_type: str) -> bool:
    """Return whether an entity may opt in to external visual comparison."""
    return entity_type == FICTIONAL_CHARACTER_ENTITY_TYPE


def external_comparison_is_resolved(
    *,
    matched_reference_index: int | None,
    reference_count: int,
    confidence: float,
) -> bool:
    """Accept only an in-range, high-confidence result from the anonymous comparison."""
    return (
        matched_reference_index is not None
        and 0 <= matched_reference_index < reference_count
        and confidence >= EXTERNAL_COMPARISON_CONFIDENCE_THRESHOLD
    )
