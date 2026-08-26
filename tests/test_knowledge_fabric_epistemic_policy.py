from echo_masque.knowledge_fabric_epistemic_policy import (
    DenyAllCharacterEpistemicPolicy,
    evidence_may_enter_character_context,
)
from echo_masque.knowledge_fabric_query import KnowledgeQueryHit


class _RecordingAllowEvidence:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, str]] = []

    def allows(
        self,
        *,
        deployment_id: str,
        character_card_id: str,
        corpus_id: str,
        authority_profile: str,
    ) -> bool:
        self.calls.append(
            (deployment_id, character_card_id, corpus_id, authority_profile)
        )
        return True


def _evidence(*, corpus_id: str = "corpus-a") -> KnowledgeQueryHit:
    return KnowledgeQueryHit(
        evidence_unit_id="evidence-a",
        corpus_id=corpus_id,
        source_version_id="source-version-a",
        evidence_locator="private://not-exposed",
        document_title="Title",
        text_content="Body",
        authority_profile="canonical",
        channels=("sparse",),
    )


def test_default_policy_denies_all_character_knowledge() -> None:
    policy = DenyAllCharacterEpistemicPolicy()

    assert not policy.allows(
        deployment_id="deployment-a",
        character_card_id="character-a",
        corpus_id="corpus-a",
        authority_profile="canonical",
    )
    assert not evidence_may_enter_character_context(
        policy=policy,
        deployment_id="deployment-a",
        character_card_id="character-a",
        evidence=_evidence(),
    )


def test_character_evidence_requires_a_nonempty_corpus_and_explicit_policy_admission() -> None:
    policy = _RecordingAllowEvidence()

    assert evidence_may_enter_character_context(
        policy=policy,
        deployment_id="deployment-a",
        character_card_id="character-a",
        evidence=_evidence(),
    )
    assert policy.calls == [("deployment-a", "character-a", "corpus-a", "canonical")]
    assert not evidence_may_enter_character_context(
        policy=policy,
        deployment_id="deployment-a",
        character_card_id="character-a",
        evidence=_evidence(corpus_id=""),
    )
    assert policy.calls == [("deployment-a", "character-a", "corpus-a", "canonical")]
