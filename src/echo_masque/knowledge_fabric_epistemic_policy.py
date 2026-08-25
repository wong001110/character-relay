"""Fail-closed Character epistemic admission for Knowledge Fabric evidence.

Phase 6 establishes the runtime boundary. Phase 10 supplies persisted authored corpus admission;
timeline, spoiler, perspective, and domain schemas remain separately unapproved.
"""

from __future__ import annotations

from typing import Protocol

from echo_masque.knowledge_fabric_query import KnowledgeQueryHit
from echo_masque.persistence.knowledge_fabric_repository import KnowledgeFabricRepository


class CharacterEpistemicPolicy(Protocol):
    """Decide whether one server-authorized Evidence Unit is in-character knowledge."""

    def allows(
        self,
        *,
        deployment_id: str,
        character_card_id: str,
        corpus_id: str,
        authority_profile: str,
    ) -> bool: ...


class DenyAllCharacterEpistemicPolicy:
    """Safe runtime default until an authored Phase 10 policy is configured."""

    def allows(
        self,
        *,
        deployment_id: str,
        character_card_id: str,
        corpus_id: str,
        authority_profile: str,
    ) -> bool:
        del deployment_id, character_card_id, corpus_id, authority_profile
        return False


class PersistedCharacterEpistemicPolicy:
    """Use only explicit, server-scope-bound authored corpus decisions."""

    def __init__(self, repository: KnowledgeFabricRepository) -> None:
        self.repository = repository

    def allows(
        self,
        *,
        deployment_id: str,
        character_card_id: str,
        corpus_id: str,
        authority_profile: str,
    ) -> bool:
        del authority_profile
        return self.repository.character_corpus_is_admitted(
            deployment_id=deployment_id,
            character_card_id=character_card_id,
            corpus_id=corpus_id,
        )


def evidence_may_enter_character_context(
    *,
    policy: CharacterEpistemicPolicy,
    deployment_id: str,
    character_card_id: str,
    evidence: KnowledgeQueryHit,
) -> bool:
    """Require explicit Character admission after server authorization and before prompting."""

    return bool(
        evidence.corpus_id
        and policy.allows(
            deployment_id=deployment_id,
            character_card_id=character_card_id,
            corpus_id=evidence.corpus_id,
            authority_profile=evidence.authority_profile,
        )
    )


__all__ = [
    "CharacterEpistemicPolicy",
    "DenyAllCharacterEpistemicPolicy",
    "PersistedCharacterEpistemicPolicy",
    "evidence_may_enter_character_context",
]
