from __future__ import annotations

import pytest

from echo_masque.knowledge_fabric_character_policy import character_corpus_is_admitted


@pytest.mark.parametrize(
    ("effects", "expected"),
    [
        (frozenset(), False),
        (frozenset({"allow"}), True),
        (frozenset({"deny"}), False),
        (frozenset({"allow", "deny"}), False),
        (frozenset({"unknown"}), False),
    ],
)
def test_character_corpus_requires_explicit_allow_and_deny_precedence(
    effects: frozenset[str],
    expected: bool,
) -> None:
    assert character_corpus_is_admitted(effects) is expected
