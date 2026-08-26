"""Pure, fail-closed decisions for persisted Character corpus admission."""

from __future__ import annotations

CHARACTER_CORPUS_ALLOW = "allow"
CHARACTER_CORPUS_DENY = "deny"
CHARACTER_CORPUS_EFFECTS = frozenset({CHARACTER_CORPUS_ALLOW, CHARACTER_CORPUS_DENY})


def character_corpus_is_admitted(effects: frozenset[str]) -> bool:
    """Deny wins; absence of an explicit allow stays unknown to the Character."""

    return CHARACTER_CORPUS_DENY not in effects and CHARACTER_CORPUS_ALLOW in effects


__all__ = [
    "CHARACTER_CORPUS_ALLOW",
    "CHARACTER_CORPUS_DENY",
    "CHARACTER_CORPUS_EFFECTS",
    "character_corpus_is_admitted",
]
