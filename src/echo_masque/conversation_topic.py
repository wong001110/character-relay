"""Semantic conversation topic memory and structured pending-action state."""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import TYPE_CHECKING, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from echo_masque.config import Settings, get_settings
from echo_masque.expression_retrieval import semantic_tokens
from echo_masque.persistence.conversation_topic_models import ConversationTopicRecord
from echo_masque.persistence.conversation_topic_repository import ConversationTopicRepository
from echo_masque.persistence.semantic_vector_repository import SemanticVectorRepository
from echo_masque.semantic_participation import (
    FastEmbedSemanticEncoder,
    SemanticEmbeddingUnavailable,
    SemanticEncoder,
    _cosine,
)

if TYPE_CHECKING:
    from echo_masque.api.connector_schemas import DiscordInboundMessage

_TOPIC_VECTOR_NAMESPACE = "conversation-topic"
_TOPIC_CONTINUITY_MINIMUM = 0.42
_TOPIC_SPARSE_CONTINUITY_MINIMUM = 0.18
_STALE_TOPIC_CONTINUITY_MINIMUM = 0.56
_STALE_TOPIC_SPARSE_CONTINUITY_MINIMUM = 0.28
_CONTINUATION_ACT_MINIMUM = 0.48
_SWITCH_ACT_MINIMUM = 0.56
_SWITCH_ACT_MARGIN = 0.05
_FRESH_CONTEXT_WINDOW = timedelta(minutes=30)
_STALE_TOPIC_AFTER = timedelta(hours=6)
_CAPSULE_MAX_CHARS = 1400
_CAPSULE_MAX_LINES = 6
_KEYWORD_LIMIT = 24
_PARTICIPANT_LIMIT = 20
_PENDING_ACTION_LIMIT = 12
_DEFAULT_PENDING_TTL = timedelta(hours=6)
_URL_PATTERN = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)

TopicStatus = Literal["active", "cooling", "closed", "archived"]
PendingActionState = Literal[
    "pending",
    "blocked_unavailable",
    "retry_requested",
    "completed",
    "cancelled",
    "expired",
    "failed",
]

_CONVERSATION_ACT_PROFILES: dict[str, str] = {
    "continue_previous_topic": (
        "Continue the same previous topic or task without changing subject. Examples: continue, "
        "go on, and then, what next, 继续, 接着, 然后呢, 那继续说."
    ),
    "retry_previous_action": (
        "Retry the previous failed, blocked, unavailable, or unfinished action after conditions "
        "may have changed. Examples: try again, retry now, do it again, 再试试, 再来一次, "
        "现在再试, 权限好了再试."
    ),
    "cancel_previous_action": (
        "Cancel, stop, abandon, or forget the previous pending action. Examples: cancel that, "
        "never mind, stop it, 算了, 取消刚才那个, 不用了."
    ),
    "clarify_previous_message": (
        "Clarify, correct, or add missing details to the immediately previous request while "
        "staying on the same topic. Examples: I mean, specifically, correction, 我的意思是, "
        "补充一下, 更准确地说."
    ),
    "switch_topic": (
        "Start a new unrelated subject and leave the previous topic behind. Examples: new topic, "
        "different question, by the way something else, 换个话题, 另外一件事, 说点别的."
    ),
}


def _topic_subject_text(value: str) -> str:
    """Remove transport/link boilerplate before semantic Topic comparison."""

    compact = " ".join(value.split())
    without_urls = _URL_PATTERN.sub(" ", compact)
    return " ".join(without_urls.split())[:4000]


def _topic_evidence_text(value: str) -> str:
    """Return user-authored subject evidence, never the URL transport itself."""

    compact = " ".join(value.split())[:4000]
    if not compact:
        return ""
    if _URL_PATTERN.search(compact):
        subject = _topic_subject_text(compact)
        return subject if semantic_tokens(subject) else ""
    return compact


class ConversationPendingAction(BaseModel):
    """Structured continuation state; raw Tool arguments and secrets are never persisted."""

    model_config = ConfigDict(extra="forbid")

    tool_id: str = Field(min_length=1, max_length=120)
    state: PendingActionState
    requested_by_user_id: str = Field(min_length=1, max_length=200)
    target_character_card_id: str = Field(default="", max_length=64)
    deployment_id: str = Field(default="", max_length=64)
    source_message_id: str = Field(default="", max_length=200)
    intent_summary: str = Field(default="", max_length=500)
    created_at: datetime
    updated_at: datetime
    expires_at: datetime


class ConversationTopicSnapshot(BaseModel):
    """Bounded runtime view of one persisted conversation topic."""

    model_config = ConfigDict(extra="forbid")

    id: str
    owner_id: str
    platform: str
    connection_id: str
    guild_id: str
    channel_id: str
    thread_id: str
    topic_label: str
    summary: str
    keywords: list[str] = Field(default_factory=list, max_length=_KEYWORD_LIMIT)
    open_loops: list[str] = Field(default_factory=list, max_length=20)
    pending_actions: list[ConversationPendingAction] = Field(
        default_factory=list,
        max_length=_PENDING_ACTION_LIMIT,
    )
    participants: list[dict[str, str]] = Field(default_factory=list, max_length=_PARTICIPANT_LIMIT)
    status: TopicStatus
    message_count: int
    capsule_version: int
    last_message_id: str
    started_at: datetime
    last_active_at: datetime
    closed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ConversationActScores:
    continue_previous_topic: float = 0.0
    retry_previous_action: float = 0.0
    cancel_previous_action: float = 0.0
    clarify_previous_message: float = 0.0
    switch_topic: float = 0.0

    @property
    def continuation(self) -> float:
        return max(
            self.continue_previous_topic,
            self.retry_previous_action,
            self.cancel_previous_action,
            self.clarify_previous_message,
        )


@dataclass(frozen=True, slots=True)
class TopicContinuityDecision:
    same_topic: bool
    topic_similarity: float
    sparse_similarity: float
    acts: ConversationActScores
    reason: str


class ConversationTopicMemoryService:
    """Maintain deterministic topic capsules with semantic continuity classification."""

    _act_vectors: ClassVar[dict[tuple[str, int, str], list[float]]] = {}
    _act_vector_lock: ClassVar[Lock] = Lock()

    def __init__(
        self,
        repository: ConversationTopicRepository,
        *,
        settings: Settings | None = None,
        encoder: SemanticEncoder | None = None,
        semantic_enabled: bool | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings or get_settings()
        self._encoder = encoder
        self._semantic_enabled = (
            semantic_enabled
            if semantic_enabled is not None
            else self.settings.semantic_embedding_runtime_enabled
        )
        self._vectors = SemanticVectorRepository(repository.database)

    def _get_encoder(self) -> SemanticEncoder:
        if self._encoder is None:
            self._encoder = FastEmbedSemanticEncoder(
                model_name=self.settings.semantic_embedding_model,
                model_file=self.settings.semantic_embedding_model_file,
                cache_dir=self.settings.semantic_embedding_cache_dir,
                dimension=self.settings.semantic_embedding_dimension,
            )
        return self._encoder

    @staticmethod
    def _decode_list(value: str) -> list[object]:
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return []
        return parsed if isinstance(parsed, list) else []

    @classmethod
    def _pending_actions(cls, record: ConversationTopicRecord) -> list[ConversationPendingAction]:
        results: list[ConversationPendingAction] = []
        for item in cls._decode_list(record.pending_actions_json):
            if not isinstance(item, dict):
                continue
            try:
                results.append(ConversationPendingAction.model_validate(item))
            except ValueError:
                continue
        return results[:_PENDING_ACTION_LIMIT]

    @classmethod
    def snapshot(cls, record: ConversationTopicRecord) -> ConversationTopicSnapshot:
        keywords = [str(item)[:120] for item in cls._decode_list(record.keywords_json) if str(item)]
        loops = [str(item)[:500] for item in cls._decode_list(record.open_loops_json) if str(item)]
        participants: list[dict[str, str]] = []
        for item in cls._decode_list(record.participants_json):
            if not isinstance(item, dict):
                continue
            user_id = str(item.get("user_id", ""))[:200]
            display_name = str(item.get("display_name", ""))[:160]
            if user_id:
                participants.append({"user_id": user_id, "display_name": display_name})
        return ConversationTopicSnapshot(
            id=record.id,
            owner_id=record.owner_id,
            platform=record.platform,
            connection_id=record.connection_id,
            guild_id=record.guild_id,
            channel_id=record.channel_id,
            thread_id=record.thread_id,
            topic_label=record.topic_label,
            summary=record.summary,
            keywords=keywords[:_KEYWORD_LIMIT],
            open_loops=loops[:20],
            pending_actions=cls._pending_actions(record),
            participants=participants[:_PARTICIPANT_LIMIT],
            status=record.status,  # type: ignore[arg-type]
            message_count=record.message_count,
            capsule_version=record.capsule_version,
            last_message_id=record.last_message_id,
            started_at=record.started_at,
            last_active_at=record.last_active_at,
            closed_at=record.closed_at,
        )

    @staticmethod
    def _topic_semantic_text(record: ConversationTopicRecord) -> str:
        """Return the stable semantic identity for a Topic.

        Rolling summary/keywords intentionally do not participate here. They are recent context and
        may contain an accidentally absorbed message; using them as identity creates a positive
        feedback loop where one bad classification makes later unrelated messages look more similar.
        """

        identity = _topic_subject_text(record.topic_label) or record.topic_label
        return f"Topic identity: {identity}"[:2000]

    def _topic_vector(self, record: ConversationTopicRecord, encoder: SemanticEncoder) -> list[float]:
        semantic_text = self._topic_semantic_text(record)
        source_hash = self._vectors.source_hash(
            semantic_text,
            encoder.model_name,
            encoder.dimension,
        )
        cached = self._vectors.get(
            owner_id=record.owner_id,
            namespace=_TOPIC_VECTOR_NAMESPACE,
            resource_id=record.id,
            model_name=encoder.model_name,
            dimension=encoder.dimension,
            source_hash=source_hash,
        )
        if cached is not None:
            return cached
        vector = encoder.embed_passage(semantic_text)
        self._vectors.upsert(
            owner_id=record.owner_id,
            namespace=_TOPIC_VECTOR_NAMESPACE,
            resource_id=record.id,
            semantic_text=semantic_text,
            model_name=encoder.model_name,
            dimension=encoder.dimension,
            vector=vector,
        )
        return vector

    @classmethod
    def _act_vector(cls, act: str, encoder: SemanticEncoder) -> list[float]:
        key = (encoder.model_name, encoder.dimension, act)
        cached = cls._act_vectors.get(key)
        if cached is not None:
            return cached
        text = _CONVERSATION_ACT_PROFILES[act]
        with cls._act_vector_lock:
            cached = cls._act_vectors.get(key)
            if cached is not None:
                return cached
            vector = encoder.embed_passage(text)
            cls._act_vectors[key] = vector
            return vector

    @staticmethod
    def _sparse_similarity(text: str, record: ConversationTopicRecord) -> float:
        """Compare stable subject text, excluding shared URL transport tokens."""

        left = Counter(semantic_tokens(_topic_subject_text(text)))
        right = Counter(semantic_tokens(_topic_subject_text(record.topic_label)))
        if not left or not right:
            return 0.0
        dot = sum(value * right.get(key, 0) for key, value in left.items())
        left_norm = math.sqrt(sum(value * value for value in left.values()))
        right_norm = math.sqrt(sum(value * value for value in right.values()))
        if not left_norm or not right_norm:
            return 0.0
        return dot / (left_norm * right_norm)

    @staticmethod
    def _idle_for(active: ConversationTopicRecord, current: datetime) -> timedelta:
        last_active = active.last_active_at
        if last_active.tzinfo is None:
            last_active = last_active.replace(tzinfo=UTC)
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        return max(current - last_active, timedelta(0))

    def classify_continuity(
        self,
        *,
        text: str,
        active: ConversationTopicRecord,
        now: datetime | None = None,
    ) -> TopicContinuityDecision:
        current = now or datetime.now(UTC)
        normalized = " ".join(text.split())[:4000]
        subject_text = _topic_evidence_text(normalized)
        sparse = self._sparse_similarity(subject_text, active)
        idle_for = self._idle_for(active, current)
        stale = idle_for >= _STALE_TOPIC_AFTER
        topic_minimum = (
            _STALE_TOPIC_CONTINUITY_MINIMUM if stale else _TOPIC_CONTINUITY_MINIMUM
        )
        sparse_minimum = (
            _STALE_TOPIC_SPARSE_CONTINUITY_MINIMUM
            if stale
            else _TOPIC_SPARSE_CONTINUITY_MINIMUM
        )

        if not normalized:
            return TopicContinuityDecision(
                same_topic=True,
                topic_similarity=0.0,
                sparse_similarity=sparse,
                acts=ConversationActScores(),
                reason="empty_message_keeps_active_topic",
            )
        if _URL_PATTERN.search(normalized) and not subject_text:
            return TopicContinuityDecision(
                same_topic=True,
                topic_similarity=0.0,
                sparse_similarity=0.0,
                acts=ConversationActScores(),
                reason="unresolved_link_without_topic_evidence",
            )
        if not self._semantic_enabled:
            return TopicContinuityDecision(
                same_topic=sparse >= sparse_minimum,
                topic_similarity=0.0,
                sparse_similarity=sparse,
                acts=ConversationActScores(),
                reason="semantic_disabled_sparse_fallback",
            )

        try:
            encoder = self._get_encoder()
            query_vector = encoder.embed_query(subject_text)
            topic_similarity = _cosine(query_vector, self._topic_vector(active, encoder))
            act_values = {
                name: _cosine(query_vector, self._act_vector(name, encoder))
                for name in _CONVERSATION_ACT_PROFILES
            }
            acts = ConversationActScores(**act_values)
        except (SemanticEmbeddingUnavailable, ValueError, RuntimeError):
            return TopicContinuityDecision(
                same_topic=sparse >= sparse_minimum,
                topic_similarity=0.0,
                sparse_similarity=sparse,
                acts=ConversationActScores(),
                reason="semantic_unavailable_sparse_fallback",
            )

        identity_match = topic_similarity >= topic_minimum or sparse >= sparse_minimum
        fresh_contextual_continuation = (
            idle_for <= _FRESH_CONTEXT_WINDOW
            and acts.continuation >= _CONTINUATION_ACT_MINIMUM
        )
        switch_wins = (
            acts.switch_topic >= _SWITCH_ACT_MINIMUM
            and acts.switch_topic >= acts.continuation + _SWITCH_ACT_MARGIN
            and not identity_match
        )

        if switch_wins:
            same_topic = False
            reason = "semantic_switch_topic"
        elif identity_match:
            same_topic = True
            reason = "semantic_identity_continuation"
        elif fresh_contextual_continuation:
            same_topic = True
            reason = "fresh_contextual_continuation"
        elif stale and acts.continuation >= _CONTINUATION_ACT_MINIMUM:
            same_topic = False
            reason = "stale_topic_requires_identity"
        else:
            same_topic = False
            reason = "semantic_new_topic"
        return TopicContinuityDecision(
            same_topic=same_topic,
            topic_similarity=round(topic_similarity, 6),
            sparse_similarity=round(sparse, 6),
            acts=acts,
            reason=reason,
        )

    @staticmethod
    def _label(text: str) -> str:
        compact = " ".join(text.split())
        return compact[:220] or "Conversation topic"

    @staticmethod
    def _keywords(existing: list[str], text: str) -> list[str]:
        merged = list(existing)
        for token in semantic_tokens(text):
            clean = token.strip()[:120]
            if len(clean) < 2 or clean in merged:
                continue
            merged.append(clean)
        return merged[-_KEYWORD_LIMIT:]

    @staticmethod
    def _append_summary(summary: str, author_display_name: str, text: str) -> str:
        compact = " ".join(text.split())[:700]
        if not compact:
            return summary[:_CAPSULE_MAX_CHARS]
        line = f"{author_display_name}: {compact}" if author_display_name else compact
        lines = [item for item in summary.splitlines() if item.strip()]
        if not lines or lines[-1] != line:
            lines.append(line)
        return "\n".join(lines[-_CAPSULE_MAX_LINES:])[-_CAPSULE_MAX_CHARS:]

    @staticmethod
    def _participants(
        existing: list[dict[str, str]],
        user_id: str,
        display_name: str,
    ) -> list[dict[str, str]]:
        results = [dict(item) for item in existing if item.get("user_id") != user_id]
        if user_id:
            results.append({"user_id": user_id[:200], "display_name": display_name[:160]})
        return results[-_PARTICIPANT_LIMIT:]

    def active_for_turn(
        self,
        *,
        owner_id: str,
        payload: DiscordInboundMessage,
        platform: str = "discord",
    ) -> ConversationTopicSnapshot | None:
        record = self.repository.active_for_scope(
            owner_id=owner_id,
            platform=platform,
            connection_id=payload.connection_id,
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            thread_id=payload.thread_id,
        )
        return self.snapshot(record) if record is not None else None

    def observe_turn(
        self,
        *,
        owner_id: str,
        payload: DiscordInboundMessage,
        platform: str = "discord",
        now: datetime | None = None,
    ) -> ConversationTopicSnapshot | None:
        current = now or datetime.now(UTC)
        text = " ".join(payload.text.split())[:4000]
        topic_text = _topic_evidence_text(text)
        active = self.repository.active_for_scope(
            owner_id=owner_id,
            platform=platform,
            connection_id=payload.connection_id,
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            thread_id=payload.thread_id,
        )
        if active is not None and active.last_message_id == payload.message_id:
            return self.snapshot(active)
        if not text:
            return self.snapshot(active) if active is not None else None
        if _URL_PATTERN.search(text) and not topic_text:
            # A URL is transport, not semantic evidence. Until its content is actually inspected,
            # do not invent a Topic, mutate the active capsule, or refresh the active lifecycle.
            return self.snapshot(active) if active is not None else None

        if active is None:
            participants = self._participants([], payload.author_id, payload.author_display_name)
            record = self.repository.create(
                owner_id=owner_id,
                platform=platform,
                connection_id=payload.connection_id,
                guild_id=payload.guild_id,
                channel_id=payload.channel_id,
                thread_id=payload.thread_id,
                topic_label=self._label(topic_text),
                summary=self._append_summary("", payload.author_display_name, topic_text),
                keywords_json=json.dumps(self._keywords([], topic_text), ensure_ascii=False),
                open_loops_json="[]",
                pending_actions_json="[]",
                participants_json=json.dumps(participants, ensure_ascii=False),
                last_message_id=payload.message_id,
                now=current,
            )
            return self.snapshot(record)

        continuity = self.classify_continuity(text=topic_text, active=active, now=current)
        if not continuity.same_topic:
            self.repository.set_status(
                topic_id=active.id,
                owner_id=owner_id,
                status="cooling",
                now=current,
            )
            participants = self._participants([], payload.author_id, payload.author_display_name)
            record = self.repository.create(
                owner_id=owner_id,
                platform=platform,
                connection_id=payload.connection_id,
                guild_id=payload.guild_id,
                channel_id=payload.channel_id,
                thread_id=payload.thread_id,
                topic_label=self._label(topic_text),
                summary=self._append_summary("", payload.author_display_name, topic_text),
                keywords_json=json.dumps(self._keywords([], topic_text), ensure_ascii=False),
                open_loops_json="[]",
                pending_actions_json="[]",
                participants_json=json.dumps(participants, ensure_ascii=False),
                last_message_id=payload.message_id,
                now=current,
            )
            return self.snapshot(record)

        snapshot = self.snapshot(active)
        updated = self.repository.update_capsule(
            topic_id=active.id,
            owner_id=owner_id,
            topic_label=active.topic_label,
            summary=self._append_summary(active.summary, payload.author_display_name, topic_text),
            keywords_json=json.dumps(self._keywords(snapshot.keywords, topic_text), ensure_ascii=False),
            open_loops_json=json.dumps(snapshot.open_loops, ensure_ascii=False),
            pending_actions_json=json.dumps(
                [item.model_dump(mode="json") for item in snapshot.pending_actions],
                ensure_ascii=False,
            ),
            participants_json=json.dumps(
                self._participants(
                    snapshot.participants,
                    payload.author_id,
                    payload.author_display_name,
                ),
                ensure_ascii=False,
            ),
            last_message_id=payload.message_id,
            increment_message_count=True,
            now=current,
        )
        return self.snapshot(updated)

    def record_pending_action(
        self,
        *,
        topic_id: str,
        owner_id: str,
        tool_id: str,
        state: PendingActionState,
        requested_by_user_id: str,
        target_character_card_id: str,
        deployment_id: str,
        source_message_id: str,
        intent_summary: str,
        now: datetime | None = None,
        ttl: timedelta = _DEFAULT_PENDING_TTL,
    ) -> ConversationPendingAction:
        current = now or datetime.now(UTC)
        record = self.repository.get(topic_id, owner_id)
        if record is None:
            raise KeyError("topic")
        snapshot = self.snapshot(record)
        key = (tool_id, requested_by_user_id, target_character_card_id, deployment_id)
        retained = [
            item
            for item in snapshot.pending_actions
            if (
                item.tool_id,
                item.requested_by_user_id,
                item.target_character_card_id,
                item.deployment_id,
            )
            != key
        ]
        action = ConversationPendingAction(
            tool_id=tool_id,
            state=state,
            requested_by_user_id=requested_by_user_id,
            target_character_card_id=target_character_card_id,
            deployment_id=deployment_id,
            source_message_id=source_message_id,
            intent_summary=" ".join(intent_summary.split())[:500],
            created_at=current,
            updated_at=current,
            expires_at=current + ttl,
        )
        retained.append(action)
        self.repository.update_capsule(
            topic_id=topic_id,
            owner_id=owner_id,
            topic_label=record.topic_label,
            summary=record.summary,
            keywords_json=record.keywords_json,
            open_loops_json=record.open_loops_json,
            pending_actions_json=json.dumps(
                [item.model_dump(mode="json") for item in retained[-_PENDING_ACTION_LIMIT:]],
                ensure_ascii=False,
            ),
            participants_json=record.participants_json,
            last_message_id=record.last_message_id,
            increment_message_count=False,
            now=current,
        )
        return action

    def pending_for_actor(
        self,
        *,
        snapshot: ConversationTopicSnapshot,
        requested_by_user_id: str,
        target_character_card_id: str,
        deployment_id: str,
        now: datetime | None = None,
    ) -> tuple[ConversationPendingAction, ...]:
        current = now or datetime.now(UTC)
        return tuple(
            item
            for item in snapshot.pending_actions
            if item.requested_by_user_id == requested_by_user_id
            and item.target_character_card_id == target_character_card_id
            and item.deployment_id == deployment_id
            and item.state not in {"completed", "cancelled", "expired"}
            and item.expires_at > current
        )


__all__ = [
    "ConversationActScores",
    "ConversationPendingAction",
    "ConversationTopicMemoryService",
    "ConversationTopicSnapshot",
    "PendingActionState",
    "TopicContinuityDecision",
    "TopicStatus",
]
