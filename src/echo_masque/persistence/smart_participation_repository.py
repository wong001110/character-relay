"""Persistence operations for Smart Participation profiles and Playground feedback."""

import json
from uuid import uuid4

from sqlalchemy import select

from echo_masque.persistence.database import Database
from echo_masque.persistence.models import CharacterCardRecord
from echo_masque.persistence.smart_participation_models import (
    SmartParticipationFeedbackRecord,
    SmartParticipationProfileRecord,
)


def _normalized_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(item.strip() for item in values if item.strip()))


def encode_strings(values: list[str]) -> str:
    return json.dumps(_normalized_strings(values), ensure_ascii=False)


def decode_strings(value: str) -> list[str]:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(decoded, list):
        return []
    return _normalized_strings([item for item in decoded if isinstance(item, str)])


class SmartParticipationRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def _require_character(self, character_card_id: str, owner_id: str) -> None:
        with self.database.session() as session:
            character = session.get(CharacterCardRecord, character_card_id)
            if character is None or character.owner_id != owner_id:
                raise KeyError("character")

    def get_profile(
        self,
        character_card_id: str,
        owner_id: str,
    ) -> SmartParticipationProfileRecord | None:
        with self.database.session() as session:
            record = session.get(SmartParticipationProfileRecord, character_card_id)
            if record is None or record.owner_id != owner_id:
                return None
            return record

    def upsert_profile(
        self,
        *,
        character_card_id: str,
        owner_id: str,
        enabled: bool,
        style: str,
        group_role: str,
        topics: list[str],
        keywords: list[str],
        trigger_phrases: list[str],
        avoid_phrases: list[str],
        cooldown_seconds: int,
        preferred_follow_up_character_card_id: str,
        follow_up_window_seconds: int,
    ) -> SmartParticipationProfileRecord:
        self._require_character(character_card_id, owner_id)
        preferred = preferred_follow_up_character_card_id.strip()
        if preferred:
            if preferred == character_card_id:
                raise ValueError("A character cannot follow itself.")
            self._require_character(preferred, owner_id)
        if group_role != "secondary":
            preferred = ""

        with self.database.session() as session:
            record = session.get(SmartParticipationProfileRecord, character_card_id)
            if record is None:
                record = SmartParticipationProfileRecord(
                    character_card_id=character_card_id,
                    owner_id=owner_id,
                )
                session.add(record)
            elif record.owner_id != owner_id:
                raise KeyError("character")
            record.enabled = enabled
            record.style = style
            record.group_role = group_role
            record.topics_json = encode_strings(topics)
            record.keywords_json = encode_strings(keywords)
            record.trigger_phrases_json = encode_strings(trigger_phrases)
            record.avoid_phrases_json = encode_strings(avoid_phrases)
            record.cooldown_seconds = cooldown_seconds
            record.preferred_follow_up_character_card_id = preferred
            record.follow_up_window_seconds = follow_up_window_seconds
            session.commit()
            session.refresh(record)
            return record

    def list_profiles_for_owner(self, owner_id: str) -> list[SmartParticipationProfileRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(SmartParticipationProfileRecord)
                    .where(SmartParticipationProfileRecord.owner_id == owner_id)
                    .order_by(SmartParticipationProfileRecord.updated_at.desc())
                )
            )

    def record_feedback(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        message: str,
        previous_character_card_id: str,
        predicted_decision: str,
        predicted_reason: str,
        score: float,
        minimum_score: float,
        signals: dict[str, object],
        feedback_label: str,
    ) -> SmartParticipationFeedbackRecord:
        self._require_character(character_card_id, owner_id)
        previous = previous_character_card_id.strip()
        if previous:
            self._require_character(previous, owner_id)
        record = SmartParticipationFeedbackRecord(
            id=str(uuid4()),
            owner_id=owner_id,
            character_card_id=character_card_id,
            message=message,
            previous_character_card_id=previous,
            predicted_decision=predicted_decision,
            predicted_reason=predicted_reason,
            score=score,
            minimum_score=minimum_score,
            signals_json=json.dumps(signals, ensure_ascii=False),
            feedback_label=feedback_label,
        )
        with self.database.session() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return record
