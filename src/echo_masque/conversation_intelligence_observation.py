"""Read models for Conversation Intelligence observability.

These projections explain derived Topic/Learned-State behavior without becoming runtime authority.
They intentionally reuse persisted evidence and canonical Discord message routes rather than
inferring social identities from display names.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from echo_masque.character_learned_state import CharacterLearnedStateService
from echo_masque.conversation_topic_lifecycle import ACTIVE_TO_COOLING
from echo_masque.persistence.character_learned_state_event_models import (
    CharacterLearnedStateEventRecord,
)
from echo_masque.persistence.conversation_topic_decision_models import (
    ConversationTopicDecisionRecord,
)
from echo_masque.persistence.conversation_topic_models import ConversationTopicRecord
from echo_masque.persistence.conversation_topic_repository import ConversationTopicRepository
from echo_masque.persistence.database import Database
from echo_masque.persistence.discord_identity_repository import DiscordIdentityRepository
from echo_masque.persistence.repository import Repository

_LEARNING_RATE = 0.25
_STATE_HALF_LIFE_SECONDS = {
    "interest": 30 * 24 * 60 * 60,
    "expertise": 60 * 24 * 60 * 60,
    "stance": 30 * 24 * 60 * 60,
    "relationship": 90 * 24 * 60 * 60,
    "conversation_ownership": 30 * 60,
    "salience": 6 * 60 * 60,
    "participation_fatigue": 2 * 60 * 60,
}


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _decay(value: float, elapsed_seconds: float, half_life_seconds: int) -> float:
    if elapsed_seconds <= 0:
        return value
    return value * math.pow(0.5, elapsed_seconds / max(1, half_life_seconds))


def _clamp(value: float, minimum: float = -1.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _default_discord_avatar_url(user_id: str) -> str:
    try:
        bucket = (int(user_id) >> 22) % 6
    except ValueError:
        return ""
    return f"https://cdn.discordapp.com/embed/avatars/{bucket}.png"


@dataclass(frozen=True, slots=True)
class TopicOverview:
    total: int
    active: int
    cooling: int
    closed: int
    archived: int
    stale_active: int
    channel_count: int


@dataclass(frozen=True, slots=True)
class CharacterMindEvent:
    id: str
    state_type: str
    subject_type: str
    subject_key: str
    delta: float
    evidence_confidence: float
    value_before: float
    value_after: float
    confidence_before: float
    confidence_after: float
    contradiction: bool
    source_type: str
    source_message_id: str
    source_burst_id: str
    reason_code: str
    connection_id: str
    guild_id: str
    channel_id: str
    topic_id: str
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class SocialNeighbor:
    subject_key: str
    subject_type: str
    label: str
    avatar_url: str
    discord_user_id: str
    is_bot: bool
    character_card_id: str
    value: float
    confidence: float
    evidence_count: int
    last_evidence_at: datetime
    trend: str


@dataclass(frozen=True, slots=True)
class InterestState:
    subject_key: str
    subject_type: str
    value: float
    confidence: float
    evidence_count: int
    last_evidence_at: datetime
    trend: str


@dataclass(frozen=True, slots=True)
class _ReplayState:
    value: float
    confidence: float
    evidence_count: int
    last_at: datetime
    recent_delta: float


class ConversationIntelligenceObservationService:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.topics = ConversationTopicRepository(database)
        self.learned = CharacterLearnedStateService(database)
        self.identities = DiscordIdentityRepository(database)
        self.repository = Repository(database)

    def topic_overview(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        now: datetime | None = None,
    ) -> TopicOverview:
        current = _aware(now) if now is not None else datetime.now(UTC)
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(ConversationTopicRecord)
                    .where(
                        ConversationTopicRecord.owner_id == owner_id,
                        ConversationTopicRecord.platform == "discord",
                        ConversationTopicRecord.connection_id == connection_id,
                        ConversationTopicRecord.guild_id == guild_id,
                    )
                    .order_by(ConversationTopicRecord.last_active_at.desc())
                    .limit(5000)
                )
            )
        # Apply the same lazy lifecycle policy used by runtime reads so Portal observation and
        # runtime authority cannot disagree about whether a stale Topic is still active.
        records = [self.topics._advance_lifecycle(item, now=current) for item in records]
        counts = {"active": 0, "cooling": 0, "closed": 0, "archived": 0}
        stale_active = 0
        channels: set[tuple[str, str]] = set()
        for item in records:
            counts[item.status] = counts.get(item.status, 0) + 1
            channels.add((item.channel_id, item.thread_id))
            if (
                item.status == "active"
                and current - _aware(item.last_active_at) >= ACTIVE_TO_COOLING
            ):
                # This normally means a live pending action deliberately held the Topic open.
                stale_active += 1
        return TopicOverview(
            total=len(records),
            active=counts.get("active", 0),
            cooling=counts.get("cooling", 0),
            closed=counts.get("closed", 0),
            archived=counts.get("archived", 0),
            stale_active=stale_active,
            channel_count=len(channels),
        )

    def topic_decisions(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
        limit: int = 100,
    ) -> list[ConversationTopicDecisionRecord]:
        return self.topics.decisions.recent_for_scope(
            owner_id=owner_id,
            platform="discord",
            connection_id=connection_id,
            guild_id=guild_id,
            channel_id=channel_id,
            thread_id=thread_id,
            limit=limit,
        )

    def character_history(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        connection_id: str,
        guild_id: str,
        state_types: tuple[str, ...] = (),
        limit: int = 200,
    ) -> tuple[CharacterMindEvent, ...]:
        valid_types = tuple(
            item
            for item in state_types
            if item in _STATE_HALF_LIFE_SECONDS
        )
        records = self.learned.list_events_for_character(
            owner_id=owner_id,
            character_card_id=character_card_id,
            connection_id=connection_id,
            guild_id=guild_id,
            state_types=valid_types,  # type: ignore[arg-type]
            limit=limit,
        )
        return tuple(
            CharacterMindEvent(
                id=item.id,
                state_type=item.state_type,
                subject_type=item.subject_type,
                subject_key=item.subject_key,
                delta=item.delta,
                evidence_confidence=item.evidence_confidence,
                value_before=item.value_before,
                value_after=item.value_after,
                confidence_before=item.confidence_before,
                confidence_after=item.confidence_after,
                contradiction=item.contradiction,
                source_type=item.source_type,
                source_message_id=item.source_message_id,
                source_burst_id=item.source_burst_id,
                reason_code=item.reason_code,
                connection_id=item.connection_id,
                guild_id=item.guild_id,
                channel_id=item.channel_id,
                topic_id=item.topic_id,
                recorded_at=_aware(item.recorded_at),
            )
            for item in records
        )

    @staticmethod
    def _replay(
        events: list[CharacterLearnedStateEventRecord],
        *,
        state_type: str,
        now: datetime,
    ) -> dict[str, _ReplayState]:
        half_life = _STATE_HALF_LIFE_SECONDS[state_type]
        grouped: dict[str, list[CharacterLearnedStateEventRecord]] = {}
        for event in events:
            grouped.setdefault(event.subject_key, []).append(event)
        result: dict[str, _ReplayState] = {}
        for subject_key, values in grouped.items():
            ordered = sorted(values, key=lambda item: _aware(item.recorded_at))
            value = 0.0
            confidence = 0.0
            last_at = _aware(ordered[0].recorded_at)
            recent_delta = 0.0
            for event in ordered:
                at = _aware(event.recorded_at)
                elapsed = max(0.0, (at - last_at).total_seconds())
                value = _decay(value, elapsed, half_life)
                confidence = _decay(confidence, elapsed, half_life)
                value = _clamp(
                    value + event.delta * event.evidence_confidence * _LEARNING_RATE
                )
                confidence = _clamp(
                    confidence + event.evidence_confidence * _LEARNING_RATE,
                    0.0,
                    1.0,
                )
                recent_delta = event.delta * event.evidence_confidence
                last_at = at
            elapsed = max(0.0, (now - last_at).total_seconds())
            result[subject_key] = _ReplayState(
                value=round(_decay(value, elapsed, half_life), 6),
                confidence=round(_decay(confidence, elapsed, half_life), 6),
                evidence_count=len(ordered),
                last_at=last_at,
                recent_delta=recent_delta,
            )
        return result

    def _events_for_state(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        connection_id: str,
        guild_id: str,
        state_type: str,
        limit: int = 1000,
    ) -> list[CharacterLearnedStateEventRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(CharacterLearnedStateEventRecord)
                    .where(
                        CharacterLearnedStateEventRecord.owner_id == owner_id,
                        CharacterLearnedStateEventRecord.character_card_id
                        == character_card_id,
                        CharacterLearnedStateEventRecord.connection_id == connection_id,
                        CharacterLearnedStateEventRecord.guild_id == guild_id,
                        CharacterLearnedStateEventRecord.state_type == state_type,
                    )
                    .order_by(CharacterLearnedStateEventRecord.recorded_at.asc())
                    .limit(max(1, min(limit, 5000)))
                )
            )

    def _participant_labels(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
    ) -> dict[str, str]:
        with self.database.session() as session:
            topics = list(
                session.scalars(
                    select(ConversationTopicRecord)
                    .where(
                        ConversationTopicRecord.owner_id == owner_id,
                        ConversationTopicRecord.platform == "discord",
                        ConversationTopicRecord.connection_id == connection_id,
                        ConversationTopicRecord.guild_id == guild_id,
                    )
                    .order_by(ConversationTopicRecord.last_active_at.desc())
                    .limit(100)
                )
            )
        labels: dict[str, str] = {}
        for topic in topics:
            try:
                participants = json.loads(topic.participants_json)
            except json.JSONDecodeError:
                continue
            if not isinstance(participants, list):
                continue
            for raw in participants:
                if not isinstance(raw, dict):
                    continue
                user_id = raw.get("user_id")
                display_name = raw.get("display_name")
                if (
                    isinstance(user_id, str)
                    and user_id
                    and isinstance(display_name, str)
                    and display_name.strip()
                    and user_id not in labels
                ):
                    labels[user_id] = display_name.strip()[:160]
        return labels

    def social_ego_graph(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        connection_id: str,
        guild_id: str,
        now: datetime | None = None,
    ) -> tuple[SocialNeighbor, ...]:
        current = _aware(now) if now is not None else datetime.now(UTC)
        events = self._events_for_state(
            owner_id=owner_id,
            character_card_id=character_card_id,
            connection_id=connection_id,
            guild_id=guild_id,
            state_type="relationship",
        )
        replayed = self._replay(events, state_type="relationship", now=current)
        participant_labels = self._participant_labels(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
        )
        latest_event = {
            key: max(
                (item for item in events if item.subject_key == key),
                key=lambda item: _aware(item.recorded_at),
            )
            for key in replayed
        }
        values: list[SocialNeighbor] = []
        for subject_key, state in replayed.items():
            event = latest_event[subject_key]
            route = (
                self.identities.resolve_message_route(
                    connection_id=connection_id,
                    message_id=event.source_message_id,
                )
                if event.source_message_id
                else None
            )
            if route is not None and route.character_card_id != character_card_id:
                card = self.repository.get_character_card(route.character_card_id, owner_id)
                deployment_identity = self.identities.get_identity(route.deployment_id, owner_id)
                deployment_label = (
                    deployment_identity.display_name.strip()
                    if deployment_identity is not None
                    else ""
                )
                label = (
                    deployment_label
                    or (card.display_name if card is not None else "")
                    or route.character_card_id
                )
                avatar_url = (
                    deployment_identity.avatar_url.strip()
                    if deployment_identity is not None
                    else ""
                )
                if not avatar_url and card is not None:
                    avatar_url = f"/api/characters/portraits/{card.id}"
                subject_type = "character"
                canonical_key = f"character:{route.character_card_id}"
                target_card_id = route.character_card_id
                discord_user_id = ""
                is_bot = True
            else:
                discord_user_id = subject_key.removeprefix("actor:")
                identity = self.identities.get_guild_actor_identity(
                    owner_id=owner_id,
                    connection_id=connection_id,
                    guild_id=guild_id,
                    user_id=discord_user_id,
                )
                if identity is not None:
                    label = (
                        identity.guild_display_name.strip()
                        or identity.global_display_name.strip()
                        or identity.username.strip()
                        or participant_labels.get(discord_user_id, "")
                        or discord_user_id
                    )
                    avatar_url = identity.avatar_url.strip()
                    is_bot = identity.is_bot
                else:
                    label = participant_labels.get(discord_user_id, "") or discord_user_id
                    avatar_url = ""
                    is_bot = False
                if not avatar_url:
                    avatar_url = _default_discord_avatar_url(discord_user_id)
                subject_type = "actor"
                canonical_key = subject_key
                target_card_id = ""
            trend = (
                "rising"
                if state.recent_delta > 0.05
                else "falling"
                if state.recent_delta < -0.05
                else "steady"
            )
            values.append(
                SocialNeighbor(
                    subject_key=canonical_key,
                    subject_type=subject_type,
                    label=label,
                    avatar_url=avatar_url,
                    discord_user_id=discord_user_id,
                    is_bot=is_bot,
                    character_card_id=target_card_id,
                    value=state.value,
                    confidence=state.confidence,
                    evidence_count=state.evidence_count,
                    last_evidence_at=state.last_at,
                    trend=trend,
                )
            )
        values.sort(key=lambda item: (abs(item.value), item.confidence), reverse=True)
        return tuple(values)

    def current_interests(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        connection_id: str,
        guild_id: str,
        now: datetime | None = None,
    ) -> tuple[InterestState, ...]:
        current = _aware(now) if now is not None else datetime.now(UTC)
        events = self._events_for_state(
            owner_id=owner_id,
            character_card_id=character_card_id,
            connection_id=connection_id,
            guild_id=guild_id,
            state_type="interest",
        )
        replayed = self._replay(events, state_type="interest", now=current)
        values = [
            InterestState(
                subject_key=key,
                subject_type="topic" if key.startswith("topic:") else "concept",
                value=state.value,
                confidence=state.confidence,
                evidence_count=state.evidence_count,
                last_evidence_at=state.last_at,
                trend=(
                    "rising"
                    if state.recent_delta > 0.05
                    else "falling"
                    if state.recent_delta < -0.05
                    else "steady"
                ),
            )
            for key, state in replayed.items()
        ]
        values.sort(key=lambda item: (abs(item.value), item.confidence), reverse=True)
        return tuple(values)


__all__ = [
    "CharacterMindEvent",
    "ConversationIntelligenceObservationService",
    "InterestState",
    "SocialNeighbor",
    "TopicOverview",
]
