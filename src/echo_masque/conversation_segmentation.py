"""Burst-level conversation segmentation and concurrent Semantic Thread assignment."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from echo_masque.api.smart_participation_v4_schemas import (
    SmartParticipationBurstMessage,
    SmartParticipationResolveRequest,
)
from echo_masque.config import Settings
from echo_masque.expression_retrieval import semantic_tokens
from echo_masque.persistence.conversation_segment_repository import (
    ConversationSegmentRepository,
    ConversationSegmentView,
    SemanticThreadView,
)
from echo_masque.semantic_participation import (
    FastEmbedSemanticEncoder,
    SemanticEmbeddingUnavailable,
    SemanticEncoder,
)
from echo_masque.utility_gateway_contracts import UtilityGatewayUnavailable
from echo_masque.utility_gateway_router import UtilityGatewayRouter

SegmentKind = Literal["discussion", "reaction", "side_comment", "media_context"]
ThreadAction = Literal["attach", "create", "context_only"]
_REACTION = re.compile(
    r"^(?:哈+|哈哈哈*|笑死|确实|確實|真的|真的假的|对|對|嗯+|哦+|lol+|lmao+|true|same|yes|yep|nah|wow|草+|艹+|6+|？？+|\?+|！+|!+)$",
    re.IGNORECASE,
)


class ConversationJudgeSegment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    message_ids: tuple[str, ...] = Field(min_length=1, max_length=20)
    kind: SegmentKind = "discussion"
    summary: str = Field(default="", max_length=800)
    thread_action: ThreadAction
    thread_id: str = Field(default="", max_length=64)
    thread_evidence: bool = True
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)


class ConversationJudgeResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    segments: tuple[ConversationJudgeSegment, ...] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def no_duplicate_message_ids(self) -> ConversationJudgeResult:
        values = [message_id for segment in self.segments for message_id in segment.message_ids]
        if len(values) != len(set(values)):
            raise ValueError("conversation segmentation cannot assign one message twice")
        return self


@dataclass(frozen=True, slots=True)
class ConversationSegmentationResult:
    burst_id: str
    segments: tuple[ConversationSegmentView, ...]
    source: str
    utility_used: bool

    @property
    def analysis_text(self) -> str:
        values = [item.summary.strip() for item in self.segments if item.summary.strip()]
        return "\n".join(values)[:4000]


class _UnionFind:
    def __init__(self, values: tuple[str, ...]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        if left not in self.parent or right not in self.parent:
            return
        a = self.find(left)
        b = self.find(right)
        if a != b:
            self.parent[b] = a


class ConversationSegmentationService:
    """Interpret one temporal Burst without assuming one exclusive active Topic."""

    def __init__(
        self,
        repository: ConversationSegmentRepository,
        settings: Settings,
        gateway: UtilityGatewayRouter | None = None,
        *,
        encoder: SemanticEncoder | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.gateway = gateway
        self.encoder = encoder
        if self.encoder is None and settings.semantic_embedding_runtime_enabled:
            self.encoder = FastEmbedSemanticEncoder(
                model_name=settings.semantic_embedding_model,
                model_file=settings.semantic_embedding_model_file,
                cache_dir=settings.semantic_embedding_cache_dir,
                dimension=settings.semantic_embedding_dimension,
            )

    @staticmethod
    def _messages(payload: SmartParticipationResolveRequest) -> tuple[SmartParticipationBurstMessage, ...]:
        if payload.burst_messages:
            return tuple(payload.burst_messages)
        if not payload.message_id and not payload.message:
            return ()
        return (
            SmartParticipationBurstMessage(
                message_id=payload.message_id or "message",
                author_id=payload.author_id or "unknown",
                text=payload.message,
                reply_to_message_id=payload.reply_to_message_id,
            ),
        )

    @staticmethod
    def _content(message: SmartParticipationBurstMessage) -> str:
        return " ".join(message.text.split())[:4000]

    @classmethod
    def _context_only(cls, messages: tuple[SmartParticipationBurstMessage, ...]) -> bool:
        nonempty = [cls._content(item) for item in messages if cls._content(item)]
        if not nonempty:
            return True
        if len(nonempty) == 1 and (_REACTION.match(nonempty[0]) or len(nonempty[0]) <= 4):
            return True
        tokens = [token for text in nonempty for token in semantic_tokens(text)]
        return len(tokens) <= 2 and max(len(text) for text in nonempty) <= 12

    @staticmethod
    def _summary(messages: tuple[SmartParticipationBurstMessage, ...]) -> str:
        lines: list[str] = []
        for item in messages:
            text = " ".join(item.text.split())[:500]
            if not text:
                continue
            author = " ".join(item.author_display_name.split())[:80]
            lines.append(f"{author}: {text}" if author else text)
        return " | ".join(lines)[:800]

    @staticmethod
    def _keywords(text: str) -> tuple[str, ...]:
        values: list[str] = []
        for token in semantic_tokens(text):
            clean = token.strip()[:120]
            if len(clean) >= 2 and clean not in values:
                values.append(clean)
        return tuple(values[:16])

    @staticmethod
    def _sparse(left: str, right: str) -> float:
        a = set(semantic_tokens(left))
        b = set(semantic_tokens(right))
        if not a or not b:
            return 0.0
        return len(a & b) / max(1, len(a | b))

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        if not left or len(left) != len(right):
            return 0.0
        dot = sum(a * b for a, b in zip(left, right, strict=True))
        left_norm = math.sqrt(sum(item * item for item in left))
        right_norm = math.sqrt(sum(item * item for item in right))
        if not left_norm or not right_norm:
            return 0.0
        return dot / (left_norm * right_norm)

    def _thread_score(self, text: str, thread: SemanticThreadView) -> float:
        target = "\n".join(item for item in (thread.label, thread.summary, " ".join(thread.keywords)) if item)
        score = self._sparse(text, target)
        if self.encoder is None:
            return score
        try:
            return max(0.0, self._cosine(self.encoder.embed_query(text), self.encoder.embed_passage(target)))
        except (SemanticEmbeddingUnavailable, ValueError, RuntimeError):
            return score

    def _best_thread(
        self,
        text: str,
        threads: tuple[SemanticThreadView, ...],
    ) -> tuple[SemanticThreadView | None, float]:
        scored = [(self._thread_score(text, thread), thread) for thread in threads]
        scored.sort(key=lambda item: item[0], reverse=True)
        return (scored[0][1], scored[0][0]) if scored else (None, 0.0)

    @staticmethod
    def _hard_clusters(
        messages: tuple[SmartParticipationBurstMessage, ...],
    ) -> tuple[tuple[SmartParticipationBurstMessage, ...], ...]:
        ids = tuple(item.message_id for item in messages)
        graph = _UnionFind(ids)
        for item in messages:
            if item.reply_to_message_id in graph.parent:
                graph.union(item.message_id, item.reply_to_message_id)
        grouped: dict[str, list[SmartParticipationBurstMessage]] = {}
        for item in messages:
            grouped.setdefault(graph.find(item.message_id), []).append(item)
        # Preserve original temporal order across clusters.
        order = {item.message_id: index for index, item in enumerate(messages)}
        values = list(grouped.values())
        values.sort(key=lambda items: min(order[item.message_id] for item in items))
        return tuple(tuple(items) for items in values)

    def _fallback(
        self,
        messages: tuple[SmartParticipationBurstMessage, ...],
        threads: tuple[SemanticThreadView, ...],
    ) -> ConversationJudgeResult:
        results: list[ConversationJudgeSegment] = []
        for cluster in self._hard_clusters(messages):
            summary = self._summary(cluster)
            context_only = self._context_only(cluster)
            best, similarity = self._best_thread(summary, threads) if summary else (None, 0.0)
            if context_only:
                action: ThreadAction = "context_only"
                thread_id = best.id if best is not None and similarity >= 0.48 else ""
                evidence = False
            elif best is not None and similarity >= 0.62:
                action = "attach"
                thread_id = best.id
                evidence = True
            else:
                action = "create"
                thread_id = ""
                evidence = True
            results.append(
                ConversationJudgeSegment(
                    message_ids=tuple(item.message_id for item in cluster),
                    kind="reaction" if context_only else "discussion",
                    summary=summary,
                    thread_action=action,
                    thread_id=thread_id,
                    thread_evidence=evidence,
                    confidence=round(max(0.55, min(max(similarity, 0.55), 0.92)), 6),
                )
            )
        return ConversationJudgeResult(segments=tuple(results))

    def _utility_decision(
        self,
        *,
        messages: tuple[SmartParticipationBurstMessage, ...],
        threads: tuple[SemanticThreadView, ...],
    ) -> ConversationJudgeResult | None:
        if self.gateway is None or len(messages) <= 1:
            return None
        config = self.gateway.runtime.config().utility_gateway
        if not config.enabled or not any(
            member.enabled and "topic_intelligence" in member.capabilities
            for member in config.members
        ):
            return None
        message_payload = [
            {
                "message_id": item.message_id,
                "author": item.author_display_name or item.author_id,
                "text": self._content(item),
                "reply_to_message_id": item.reply_to_message_id,
            }
            for item in messages
        ]
        thread_payload = [
            {
                "thread_id": item.id,
                "label": item.label,
                "summary": item.summary[-1200:],
                "status": item.status,
            }
            for item in threads[:6]
        ]
        system = (
            "You are Character Relay's Burst conversation-structure judge. A Burst is only a "
            "time window and may contain several interleaved discussions. Group messages into "
            "conversation segments using explicit reply links as strong evidence. A short reaction "
            "may belong to a thread while thread_evidence=false. Use thread_action=attach only with "
            "one supplied thread_id; create for a genuinely new discussion; context_only for banter "
            "or reactions that should not broaden semantic identity. Every message_id must appear "
            "exactly once. Return one strict JSON object matching the requested schema and no prose."
        )
        user = "\n".join(
            (
                "Current Burst:",
                json.dumps(message_payload, ensure_ascii=False),
                "Candidate Semantic Threads:",
                json.dumps(thread_payload, ensure_ascii=False),
                "Required schema:",
                json.dumps(ConversationJudgeResult.model_json_schema(), ensure_ascii=False),
            )
        )
        try:
            value, _ = self.gateway.invoke(
                "topic_intelligence",
                ConversationJudgeResult,
                system_prompt=system,
                user_prompt=user,
                max_output_tokens=700,
                temperature=0.0,
            )
        except UtilityGatewayUnavailable:
            return None
        expected = {item.message_id for item in messages}
        observed = {message_id for segment in value.segments for message_id in segment.message_ids}
        if expected != observed:
            return None
        allowed_threads = {item.id for item in threads}
        for segment in value.segments:
            if segment.thread_action == "attach" and segment.thread_id not in allowed_threads:
                return None
            if segment.thread_action != "attach" and segment.thread_id and segment.thread_id not in allowed_threads:
                return None
        return value

    def resolve(
        self,
        *,
        payload: SmartParticipationResolveRequest,
        owner_id: str,
        now: datetime | None = None,
    ) -> ConversationSegmentationResult:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        messages = self._messages(payload)
        burst_id = payload.burst_id or f"message:{payload.message_id or 'unknown'}"
        if not messages:
            return ConversationSegmentationResult(burst_id, (), "empty", False)
        threads = self.repository.recent_threads(
            owner_id=owner_id,
            connection_id=payload.connection_id,
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            discord_thread_id=payload.thread_id,
            limit=12,
            now=current,
        )
        judged = self._utility_decision(messages=messages, threads=threads)
        source = "utility" if judged is not None else "deterministic"
        decision = judged or self._fallback(messages, threads)
        message_by_id = {item.message_id: item for item in messages}
        persisted: list[dict[str, object]] = []
        known_threads = {item.id: item for item in threads}
        for index, segment in enumerate(decision.segments, start=1):
            cluster = tuple(message_by_id[item] for item in segment.message_ids if item in message_by_id)
            participants = tuple(dict.fromkeys(item.author_id for item in cluster if item.author_id))
            summary = " ".join(segment.summary.split())[:800] or self._summary(cluster)
            thread_id = segment.thread_id
            action: ThreadAction = segment.thread_action
            if action == "attach" and thread_id not in known_threads:
                action = "create" if segment.thread_evidence else "context_only"
                thread_id = ""
            if action == "create" and segment.thread_evidence:
                created = self.repository.create_thread(
                    owner_id=owner_id,
                    connection_id=payload.connection_id,
                    guild_id=payload.guild_id,
                    channel_id=payload.channel_id,
                    discord_thread_id=payload.thread_id,
                    label=summary[:240] or "Conversation thread",
                    summary=summary,
                    keywords=self._keywords(summary),
                    now=current,
                )
                thread_id = created.id
                known_threads[created.id] = created
            elif thread_id:
                if segment.thread_evidence:
                    updated = self.repository.update_thread_evidence(
                        owner_id=owner_id,
                        thread_id=thread_id,
                        summary=summary,
                        keywords=self._keywords(summary),
                        now=current,
                    )
                    if updated is not None:
                        known_threads[thread_id] = updated
                else:
                    self.repository.touch_thread(owner_id=owner_id, thread_id=thread_id, now=current)
            persisted.append(
                {
                    "segment_key": f"{index}:{'-'.join(segment.message_ids)}"[:120],
                    "message_ids": segment.message_ids,
                    "participant_ids": participants,
                    "kind": segment.kind,
                    "summary": summary,
                    "semantic_thread_id": thread_id,
                    "thread_action": action,
                    "thread_evidence": segment.thread_evidence,
                    "confidence": segment.confidence,
                    "source": source,
                }
            )
        records = self.repository.record_segments(
            owner_id=owner_id,
            burst_id=burst_id,
            connection_id=payload.connection_id,
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            discord_thread_id=payload.thread_id,
            segments=tuple(persisted),
            now=current,
        )
        return ConversationSegmentationResult(
            burst_id=burst_id,
            segments=records,
            source=source,
            utility_used=judged is not None,
        )


__all__ = [
    "ConversationJudgeResult",
    "ConversationJudgeSegment",
    "ConversationSegmentationResult",
    "ConversationSegmentationService",
]
