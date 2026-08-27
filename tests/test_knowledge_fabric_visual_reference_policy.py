from __future__ import annotations

import pytest

from echo_masque.knowledge_fabric_visual_reference_policy import (
    EXTERNAL_COMPARISON_CONFIDENCE_THRESHOLD,
    FICTIONAL_CHARACTER_ENTITY_TYPE,
    external_comparison_is_authorizable,
    external_comparison_is_resolved,
)


def test_external_comparison_is_limited_to_fictional_characters() -> None:
    assert external_comparison_is_authorizable(
        entity_type=FICTIONAL_CHARACTER_ENTITY_TYPE
    )
    assert not external_comparison_is_authorizable(entity_type="real_person")
    assert not external_comparison_is_authorizable(entity_type="character")


@pytest.mark.parametrize(
    ("matched_reference_index", "reference_count", "confidence", "expected"),
    [
        (0, 1, EXTERNAL_COMPARISON_CONFIDENCE_THRESHOLD, True),
        (1, 2, 0.99, True),
        (None, 1, 1.0, False),
        (-1, 1, 1.0, False),
        (1, 1, 1.0, False),
        (0, 1, EXTERNAL_COMPARISON_CONFIDENCE_THRESHOLD - 0.01, False),
    ],
)
def test_external_comparison_requires_an_in_range_high_confidence_match(
    matched_reference_index: int | None,
    reference_count: int,
    confidence: float,
    expected: bool,
) -> None:
    assert (
        external_comparison_is_resolved(
            matched_reference_index=matched_reference_index,
            reference_count=reference_count,
            confidence=confidence,
        )
        is expected
    )
