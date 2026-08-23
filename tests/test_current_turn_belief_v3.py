from __future__ import annotations

from pathlib import Path
from typing import cast

from echo_masque.belief_revision_v3 import BeliefRevisionService
from echo_masque.current_turn_belief_v3 import (
    CurrentTurnBeliefRevisionService,
    CurrentTurnClaimDecision,
)
from echo_masque.persistence import Database
from echo_masque.persistence.belief_repository import BeliefRepository


class _Utility:
    def __init__(self, decision: CurrentTurnClaimDecision) -> None:
        self.decision = decision
        self.prompts: list[str] = []

    def invoke(self, _capability: str, _schema: object, **kwargs: object) -> tuple[object, None]:
        self.prompts.append(str(kwargs["user_prompt"]))
        return self.decision, None


def _service(tmp_path: Path, decision: CurrentTurnClaimDecision) -> tuple[
    Database, BeliefRepository, CurrentTurnBeliefRevisionService, _Utility
]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    database = Database(f"sqlite:///{tmp_path / 'beliefs.db'}")
    database.initialize()
    repository = BeliefRepository(database)
    utility = _Utility(decision)
    service = CurrentTurnBeliefRevisionService(
        repository=repository,
        gateway=cast(object, utility),
    )
    return database, repository, service, utility


def _apply(
    service: CurrentTurnBeliefRevisionService,
    extraction: object,
    *,
    character_card_id: str = "character-1",
    guild_id: str = "guild-1",
    message_id: str = "message-1",
    burst_id: str = "burst-1",
) -> object:
    return service.apply_to_character(
        extraction=extraction,  # type: ignore[arg-type]
        owner_id="owner-1",
        character_card_id=character_card_id,
        connection_id="connection-1",
        guild_id=guild_id,
        speaker_ref="user-1",
        source_message_id=message_id,
        evidence_message_ids=(message_id, "message-context"),
        burst_id=burst_id,
    )


def test_explicit_claim_is_created_then_reused_with_bounded_scope(tmp_path: Path) -> None:
    _database, repository, service, utility = _service(
        tmp_path,
        CurrentTurnClaimDecision(
            is_claim=True,
            is_correction=False,
            predicate="food.preference",
            value_text="coffee",
            domain="personal",
            confidence=0.91,
        ),
    )
    extraction = service.extract_self_claim(
        speaker_ref="user-1",
        text="I prefer coffee.",
        burst_context=("user-1 [message-0]: We were discussing drinks.",),
    )
    first = _apply(service, extraction)
    second = _apply(service, extraction, message_id="message-2")

    assert first is not None and first.action == "created"
    assert second is not None and second.action == "reinforced"
    beliefs = repository.active_for_claim(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        subject_ref="user-1",
        predicate="food.preference",
        character_card_id="character-1",
    )
    assert len(beliefs) == 1
    assert beliefs[0].scope == "character_server"
    assert set(beliefs[0].evidence_refs) == {
        "message:message-1",
        "message:message-context",
        "burst:burst-1",
        "message:message-2",
    }
    assert "message-0" in utility.prompts[0] and "Burst context" in utility.prompts[0]


def test_question_reaction_and_low_confidence_claims_do_not_write(tmp_path: Path) -> None:
    for index, decision in enumerate(
        (
            CurrentTurnClaimDecision(is_claim=False, is_correction=False, confidence=0.99),
            CurrentTurnClaimDecision(is_claim=False, is_correction=False, confidence=0.99),
            CurrentTurnClaimDecision(
                is_claim=True,
                is_correction=False,
                predicate="food.preference",
                value_text="coffee",
                confidence=0.4,
            ),
        )
    ):
        _database, repository, service, _utility = _service(tmp_path / str(index), decision)
        extraction = service.extract_self_claim(
            speaker_ref="user-1",
            text=("Do I prefer coffee?" if index == 0 else "👍" if index == 1 else "Maybe coffee."),
        )
        assert _apply(service, extraction) is None
        assert repository.recall(
            owner_id="owner-1",
            connection_id="connection-1",
            guild_id="guild-1",
            character_card_id="character-1",
        ) == ()


def test_claim_scope_isolated_by_character_and_guild(tmp_path: Path) -> None:
    _database, repository, service, _utility = _service(
        tmp_path,
        CurrentTurnClaimDecision(
            is_claim=True,
            is_correction=False,
            predicate="profile.location",
            value_text="Kuala Lumpur",
            domain="personal",
            confidence=0.9,
        ),
    )
    _apply(
        service,
        service.extract_self_claim(speaker_ref="user-1", text="I live in Kuala Lumpur."),
    )

    assert repository.active_for_claim(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        subject_ref="user-1",
        predicate="profile.location",
        character_card_id="character-2",
    ) == ()
    assert repository.active_for_claim(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-2",
        subject_ref="user-1",
        predicate="profile.location",
        character_card_id="character-1",
    ) == ()


def test_conflicting_claims_preserve_supersede_shield_or_dispute(tmp_path: Path) -> None:
    _database, repository, service, _utility = _service(
        tmp_path,
        CurrentTurnClaimDecision(
            is_claim=True,
            is_correction=True,
            predicate="food.preference",
            value_text="coffee",
            domain="personal",
            confidence=0.93,
        ),
    )
    revision = BeliefRevisionService(repository)
    original = revision.apply_claim(
        owner_id="owner-1", character_card_id="character-1", connection_id="connection-1",
        guild_id="guild-1", subject_entity_id="", subject_ref="user-1",
        predicate="food.preference", value_text="tea", domain="personal", source="self_report",
        evidence_refs=("message:old",), source_message_id="old", importance=0.5,
    )
    replacement = _apply(
        service,
        service.extract_self_claim(speaker_ref="user-1", text="Actually, I prefer coffee."),
        message_id="new",
    )

    assert original.action == "created"
    assert replacement is not None and replacement.action == "superseded"
    assert replacement.shield.blocked_belief_ids == (original.belief.id,)  # type: ignore[union-attr]

    disputed = revision.apply_claim(
        owner_id="owner-1", character_card_id="character-1", connection_id="connection-1",
        guild_id="guild-1", subject_entity_id="", subject_ref="user-1",
        predicate="canon.favorite", value_text="A", domain="canonical", source="official_source",
        evidence_refs=("message:canon-a",), source_message_id="canon-a", importance=0.5,
    )
    conflict = revision.apply_claim(
        owner_id="owner-1", character_card_id="character-1", connection_id="connection-1",
        guild_id="guild-1", subject_entity_id="", subject_ref="user-1",
        predicate="canon.favorite", value_text="B", domain="canonical", source="self_report",
        evidence_refs=("message:canon-b",), source_message_id="canon-b", importance=0.5,
    )
    assert disputed.action == "created"
    assert conflict.action == "disputed"
    assert conflict.belief is not None and conflict.belief.status == "disputed"


def test_repeated_burst_source_is_idempotent(tmp_path: Path) -> None:
    _database, repository, service, _utility = _service(
        tmp_path,
        CurrentTurnClaimDecision(
            is_claim=True,
            is_correction=False,
            predicate="food.preference",
            value_text="coffee",
            domain="personal",
            confidence=0.9,
        ),
    )
    extraction = service.extract_self_claim(speaker_ref="user-1", text="I prefer coffee.")
    first = _apply(service, extraction, message_id="same-message", burst_id="same-burst")
    repeated = _apply(service, extraction, message_id="same-message", burst_id="same-burst")

    assert first is not None and first.action == "created"
    assert repeated is not None and repeated.action == "ignored"
    beliefs = repository.active_for_claim(
        owner_id="owner-1", connection_id="connection-1", guild_id="guild-1",
        subject_ref="user-1", predicate="food.preference", character_card_id="character-1",
    )
    assert len(beliefs) == 1
