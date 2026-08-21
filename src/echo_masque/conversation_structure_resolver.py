"""Authoritative Conversation Structure resolver for Intelligence Core v3.

A Discord Burst is only a temporal collection window. This resolver projects raw messages into
Segments and revisable ConversationThread memberships. Structural evidence owns positive
continuity; semantic similarity only retrieves/ranks candidates and can reject implausible ones.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from echo_masque.api.smart_participation_v3_schemas import (
    SmartParticipationBurstMessage,
    SmartParticipationResolveRequest,
)
from echo_masque.config import Settings
from echo_masque.expression_retrieval import semantic_tokens
from echo_masque.persistence.conversation_structure_repository import (
    ConversationSegmentView,
    ConversationStructureRepository,
    ConversationThreadView,
)
from echo_masque.semantic_participation import (
    FastEmbedSemanticEncoder,
    SemanticEmbeddingUnavailable,
    SemanticEncoder,
)
from echo_masque.utility_gateway_contracts import UtilityGatewayUnavailable
from echo_masque.utility_gateway_router import UtilityGatewayRouter

SegmentKind = Literal["discussion", "reaction", "side_comment", "media_context"]
ThreadAction = Literal["attach", "create", "context_only", "unresolved"]

_REACTION = re.compile(
    r"^(?:哈+|哈哈哈*|笑死|确实|確實|真的|真的假的|对|對|嗯+|哦+|lol+|lmao+|"
    r"true|same|yes|yep|nah|wow|草+|艹+|6+|\uff1f\uff1f+|\?+|\uff01+|!+)$",
    re.IGNORECASE,
)
_IMMEDIATE_CONTINUITY = timedelta(minutes=2)
_PURE_REACTIONS = {
    "哈",
    "哈哈",
    "哈哈哈",
    "笑死",
    "确实",
    "確實",
    "真的",
    "对",
    "對",
    "嗯",
    "哦",
    "lol",
    "lmao",
    "true",
    "same",
    "yes",
    "yep",
    "nah",
    "wow",
    "草",
    "6",
    "?",
    "!",
}


class ConversationJudgeSegment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    message_ids: tuple[str, ...] = Field(min_length=1, max_length=20)
    kind: SegmentKind = "discussion"
    summary: str = Field(default="", max_length=800)
    thread_action: ThreadAction
    thread_id: str = Field(default="", max_length=64)
    thread_evidence: bool = True
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    reason: str = Field(default="", max_length=240)


class ConversationJudgeResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    segments: tuple[ConversationJudgeSegment, ...] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def no_duplicate_message_ids(self) -> ConversationJudgeResult:
        values = [message_id for segment in self.segments for message_id in segment.message_ids]
        if len(values) != len(set(values)):
            raise ValueError("conversation structure cannot assign one message twice")
        return self


@dataclass(frozen=True, slots=True)
class ConversationSegmentationResult:
    """Compatibility name for the v3 Segment projection consumed by runtime coordination."""

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


class ConversationStructureResolver:
    """Resolve one temporal Burst into Segments and revisable ConversationThread memberships."""

    def __init__(
        self,
        repository: ConversationStructureRepository,
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
    def _messages(
        payload: SmartParticipationResolveRequest,
    ) -> tuple[SmartParticipationBurstMessage, ...]:
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

    def _thread_score(self, text: str, thread: ConversationThreadView) -> float:
        target = "\n".join(
            item
            for item in (
                thread.canonical_label,
                thread.anchor_summary,
                thread.working_summary,
            )
            if item
        )
        score = self._sparse(text, target)
        if self.encoder is None:
            return score
        try:
            return max(
                0.0,
                self._cosine(
                    self.encoder.embed_query(text),
                    self.encoder.embed_passage(target),
                ),
            )
        except (SemanticEmbeddingUnavailable, ValueError, RuntimeError):
            return score

    def _rank_threads(
        self,
        text: str,
        threads: tuple[ConversationThreadView, ...],
    ) -> tuple[tuple[ConversationThreadView, float], ...]:
        scored = [(thread, self._thread_score(text, thread)) for thread in threads]
        scored.sort(key=lambda item: item[1], reverse=True)
        return tuple(scored)

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
        order = {item.message_id: index for index, item in enumerate(messages)}
        values = list(grouped.values())
        values.sort(key=lambda items: min(order[item.message_id] for item in items))
        return tuple(tuple(items) for items in values)

    def _reply_thread_hint(
        self,
        *,
        cluster: tuple[SmartParticipationBurstMessage, ...],
        owner_id: str,
        payload: SmartParticipationResolveRequest,
    ) -> ConversationThreadView | None:
        current_ids = {item.message_id for item in cluster}
        found: list[ConversationThreadView] = []
        for item in cluster:
            target = item.reply_to_message_id
            if not target or target in current_ids:
                continue
            thread = self.repository.thread_for_message(
                owner_id=owner_id,
                connection_id=payload.connection_id,
                guild_id=payload.guild_id,
                channel_id=payload.channel_id,
                discord_thread_id=payload.thread_id,
                message_id=target,
            )
            if thread is not None and all(existing.id != thread.id for existing in found):
                found.append(thread)
        return found[0] if len(found) == 1 else None

    @staticmethod
    def _participant_ids(
        cluster: tuple[SmartParticipationBurstMessage, ...],
    ) -> frozenset[str]:
        return frozenset(item.author_id for item in cluster if item.author_id)

    @staticmethod
    def _recent_enough(thread: ConversationThreadView, *, now: datetime) -> bool:
        observed = thread.last_active_at
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=UTC)
        return now - observed.astimezone(UTC) <= _IMMEDIATE_CONTINUITY

    @classmethod
    def _pure_reply_reaction(
        cls,
        cluster: tuple[SmartParticipationBurstMessage, ...],
    ) -> bool:
        texts = [cls._content(item).casefold() for item in cluster if cls._content(item)]
        return bool(texts) and all(text in _PURE_REACTIONS for text in texts)

    def _structural_candidates(
        self,
        *,
        cluster: tuple[SmartParticipationBurstMessage, ...],
        threads: tuple[ConversationThreadView, ...],
        now: datetime,
    ) -> tuple[ConversationThreadView, ...]:
        participants = self._participant_ids(cluster)
        if not participants:
            return ()
        return tuple(
            thread
            for thread in threads
            if self._recent_enough(thread, now=now)
            and bool(participants.intersection(thread.participant_ids))
        )

    def _fallback(
        self,
        *,
        messages: tuple[SmartParticipationBurstMessage, ...],
        threads: tuple[ConversationThreadView, ...],
        owner_id: str,
        payload: SmartParticipationResolveRequest,
    ) -> ConversationJudgeResult:
        now = datetime.now(UTC)
        results: list[ConversationJudgeSegment] = []
        for cluster in self._hard_clusters(messages):
            summary = self._summary(cluster)
            context_only = self._context_only(cluster)
            reply_thread = self._reply_thread_hint(
                cluster=cluster,
                owner_id=owner_id,
                payload=payload,
            )
            if reply_thread is not None:
                pure_reaction = self._pure_reply_reaction(cluster)
                results.append(
                    ConversationJudgeSegment(
                        message_ids=tuple(item.message_id for item in cluster),
                        kind="reaction" if pure_reaction else "discussion",
                        summary=summary,
                        thread_action="context_only" if pure_reaction else "attach",
                        thread_id=reply_thread.id,
                        thread_evidence=not pure_reaction,
                        confidence=0.99,
                        reason="explicit_reply_to_prior_thread",
                    )
                )
                continue

            ranked = self._rank_threads(summary, threads) if summary else ()
            score_by_id = {thread.id: score for thread, score in ranked}
            structural = self._structural_candidates(
                cluster=cluster,
                threads=threads,
                now=now,
            )
            structural_ranked = sorted(
                ((thread, score_by_id.get(thread.id, 0.0)) for thread in structural),
                key=lambda item: item[1],
                reverse=True,
            )
            best_any_score = ranked[0][1] if ranked else 0.0

            action: ThreadAction
            thread_id = ""
            evidence = False
            confidence = 0.0
            reason = ""

            if not threads:
                action = "context_only" if context_only else "create"
                evidence = not context_only
                confidence = 0.82 if not context_only else 0.72
                reason = "no_prior_thread"
            elif structural_ranked:
                best_thread, best_score = structural_ranked[0]
                second_score = structural_ranked[1][1] if len(structural_ranked) > 1 else 0.0
                margin = best_score - second_score
                if (
                    context_only
                    and best_score >= 0.25
                    and (len(structural_ranked) == 1 or margin >= 0.10)
                ):
                    action = "context_only"
                    thread_id = best_thread.id
                    confidence = min(0.94, max(0.72, 0.62 + best_score * 0.25))
                    reason = "immediate_participant_context"
                elif (
                    not context_only
                    and best_score >= 0.35
                    and (len(structural_ranked) == 1 or margin >= 0.12)
                ):
                    action = "attach"
                    thread_id = best_thread.id
                    evidence = True
                    confidence = min(0.95, max(0.74, 0.66 + best_score * 0.25))
                    reason = "immediate_participant_continuity"
                elif not context_only and best_score <= 0.15:
                    action = "create"
                    evidence = True
                    confidence = 0.72
                    reason = "structural_candidate_rejected"
                else:
                    action = "unresolved"
                    confidence = max(0.40, min(0.68, best_score))
                    reason = "ambiguous_structural_candidates"
            elif context_only:
                action = "context_only"
                confidence = 0.64
                reason = "context_without_structural_anchor"
            elif best_any_score <= 0.30:
                action = "create"
                evidence = True
                confidence = 0.72
                reason = "no_plausible_thread_candidate"
            else:
                action = "unresolved"
                confidence = max(0.40, min(0.68, best_any_score))
                reason = "semantic_candidate_without_structural_authority"

            results.append(
                ConversationJudgeSegment(
                    message_ids=tuple(item.message_id for item in cluster),
                    kind="reaction" if context_only else "discussion",
                    summary=summary,
                    thread_action=action,
                    thread_id=thread_id,
                    thread_evidence=evidence,
                    confidence=round(confidence, 6),
                    reason=reason,
                )
            )
        return ConversationJudgeResult(segments=tuple(results))

    @classmethod
    def _needs_utility(
        cls,
        messages: tuple[SmartParticipationBurstMessage, ...],
        fallback: ConversationJudgeResult,
    ) -> bool:
        if any(item.thread_action == "unresolved" for item in fallback.segments):
            return True
        clusters = cls._hard_clusters(messages)
        # A single message is explicitly eligible when deterministic structure is ambiguous above.
        return len(messages) > 1 and len(clusters) == len(messages)

    def _utility_available(self) -> bool:
        if self.gateway is None:
            return False
        config = self.gateway.runtime.config().utility_gateway
        return bool(
            config.enabled
            and any(
                member.enabled and "semantic_judge" in member.capabilities
                for member in config.members
            )
        )

    def _utility_decision(
        self,
        *,
        messages: tuple[SmartParticipationBurstMessage, ...],
        threads: tuple[ConversationThreadView, ...],
        owner_id: str,
        payload: SmartParticipationResolveRequest,
    ) -> ConversationJudgeResult | None:
        if not self._utility_available() or self.gateway is None:
            return None
        message_payload: list[dict[str, object]] = []
        for item in messages:
            reply_hint = ""
            if item.reply_to_message_id:
                prior = self.repository.thread_for_message(
                    owner_id=owner_id,
                    connection_id=payload.connection_id,
                    guild_id=payload.guild_id,
                    channel_id=payload.channel_id,
                    discord_thread_id=payload.thread_id,
                    message_id=item.reply_to_message_id,
                )
                reply_hint = prior.id if prior is not None else ""
            message_payload.append(
                {
                    "message_id": item.message_id,
                    "author": item.author_display_name or item.author_id,
                    "text": self._content(item),
                    "reply_to_message_id": item.reply_to_message_id,
                    "reply_thread_hint": reply_hint,
                }
            )
        thread_payload = [
            {
                "thread_id": item.id,
                "canonical_label": item.canonical_label,
                "anchor_summary": item.anchor_summary[:1200],
                "working_summary": item.working_summary[:1200],
                "status": item.status,
            }
            for item in threads[:8]
        ]
        system = (
            "You are Character Relay's Conversation Structure judge. A Burst is only a time "
            "window and may contain several interleaved discussions. Preserve explicit reply "
            "chains. A supplied reply_thread_hint is structural authority unless the message is "
            "explicitly clarifying that the reply was about another target. Use attach only with "
            "one supplied thread_id; create for a genuinely new discussion; context_only for a "
            "reaction that should not broaden thread identity; unresolved when evidence is too "
            "weak. Do not force a thread assignment. Every message_id must appear exactly once."
        )
        user = "\n".join(
            (
                "Current Burst:",
                json.dumps(message_payload, ensure_ascii=False),
                "Candidate Conversation Threads:",
                json.dumps(thread_payload, ensure_ascii=False),
                "Required schema:",
                json.dumps(ConversationJudgeResult.model_json_schema(), ensure_ascii=False),
            )
        )
        try:
            value, _ = self.gateway.invoke(
                "semantic_judge",
                ConversationJudgeResult,
                system_prompt=system,
                user_prompt=user,
                max_output_tokens=900,
                temperature=0.0,
            )
        except UtilityGatewayUnavailable:
            return None
        if not self._valid_utility_result(
            value,
            messages=messages,
            threads=threads,
            owner_id=owner_id,
            payload=payload,
        ):
            return None
        return value

    def _valid_utility_result(
        self,
        value: ConversationJudgeResult,
        *,
        messages: tuple[SmartParticipationBurstMessage, ...],
        threads: tuple[ConversationThreadView, ...],
        owner_id: str,
        payload: SmartParticipationResolveRequest,
    ) -> bool:
        expected = {item.message_id for item in messages}
        observed = {message_id for segment in value.segments for message_id in segment.message_ids}
        if expected != observed:
            return False
        allowed_threads = {item.id for item in threads}
        segment_index: dict[str, int] = {}
        for index, segment in enumerate(value.segments):
            for message_id in segment.message_ids:
                segment_index[message_id] = index
            if segment.thread_action == "attach" and segment.thread_id not in allowed_threads:
                return False
            if segment.thread_action in {"create", "unresolved"} and segment.thread_id:
                return False
        for item in messages:
            target = item.reply_to_message_id
            if not target:
                continue
            if target in expected and segment_index.get(target) != segment_index.get(
                item.message_id
            ):
                return False
            if target in expected:
                continue
            prior = self.repository.thread_for_message(
                owner_id=owner_id,
                connection_id=payload.connection_id,
                guild_id=payload.guild_id,
                channel_id=payload.channel_id,
                discord_thread_id=payload.thread_id,
                message_id=target,
            )
            if prior is None:
                continue
            segment = value.segments[segment_index[item.message_id]]
            if segment.thread_action not in {"attach", "context_only"}:
                return False
            if segment.thread_id != prior.id:
                return False
        return True

    def _record_explicit_relations(
        self,
        *,
        messages: tuple[SmartParticipationBurstMessage, ...],
        owner_id: str,
        payload: SmartParticipationResolveRequest,
        now: datetime,
    ) -> None:
        for item in messages:
            if not item.reply_to_message_id:
                continue
            self.repository.record_relation(
                owner_id=owner_id,
                connection_id=payload.connection_id,
                guild_id=payload.guild_id,
                channel_id=payload.channel_id,
                discord_thread_id=payload.thread_id,
                source_message_id=item.message_id,
                relation_class="interaction",
                relation_type="REPLY_TO",
                target_ref_type="message",
                target_ref=item.reply_to_message_id,
                confidence=1.0,
                source="discord_explicit",
                evidence_refs=(item.message_id, item.reply_to_message_id),
                status="resolved",
                now=now,
            )

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
        fallback = self._fallback(
            messages=messages,
            threads=threads,
            owner_id=owner_id,
            payload=payload,
        )
        judged: ConversationJudgeResult | None = None
        if self._needs_utility(messages, fallback):
            judged = self._utility_decision(
                messages=messages,
                threads=threads,
                owner_id=owner_id,
                payload=payload,
            )
        decision = judged or fallback
        source = "utility" if judged is not None else "deterministic"
        self._record_explicit_relations(
            messages=messages,
            owner_id=owner_id,
            payload=payload,
            now=current,
        )
        message_by_id = {item.message_id: item for item in messages}
        rows: list[dict[str, object]] = []
        decisions: list[ConversationJudgeSegment] = []
        known_threads = {item.id: item for item in threads}
        for index, segment in enumerate(decision.segments, start=1):
            cluster = tuple(
                message_by_id[item] for item in segment.message_ids if item in message_by_id
            )
            participants = tuple(
                dict.fromkeys(item.author_id for item in cluster if item.author_id)
            )
            summary = " ".join(segment.summary.split())[:800] or self._summary(cluster)
            thread_id = segment.thread_id
            action: ThreadAction = segment.thread_action
            if action == "attach" and thread_id not in known_threads:
                action = "unresolved"
                thread_id = ""
            if action == "create" and segment.thread_evidence:
                created = self.repository.create_thread(
                    owner_id=owner_id,
                    connection_id=payload.connection_id,
                    guild_id=payload.guild_id,
                    channel_id=payload.channel_id,
                    discord_thread_id=payload.thread_id,
                    canonical_label=summary[:240] or "Conversation thread",
                    anchor_summary=summary,
                    working_summary=summary,
                    now=current,
                )
                thread_id = created.id
                known_threads[created.id] = created
            decisions.append(
                segment.model_copy(
                    update={
                        "summary": summary,
                        "thread_action": action,
                        "thread_id": thread_id,
                    }
                )
            )
            rows.append(
                {
                    "segment_key": f"{index}:{'-'.join(segment.message_ids)}"[:120],
                    "message_ids": segment.message_ids,
                    "participant_ids": participants,
                    "kind": segment.kind,
                    "summary": summary,
                    "confidence": segment.confidence,
                    "source": source,
                }
            )
        recorded = self.repository.record_segments(
            owner_id=owner_id,
            burst_id=burst_id,
            connection_id=payload.connection_id,
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            discord_thread_id=payload.thread_id,
            segments=tuple(rows),
            now=current,
        )
        final: list[ConversationSegmentView] = []
        for item, segment in zip(recorded, decisions, strict=True):
            relation = "unresolved"
            if segment.thread_action in {"attach", "create"}:
                relation = "belongs_to"
            elif segment.thread_action == "context_only" and segment.thread_id:
                relation = "reaction_to" if segment.kind == "reaction" else "context_of"
            membership = self.repository.assign_membership(
                owner_id=owner_id,
                segment_id=item.id,
                thread_id=segment.thread_id,
                relation=relation,
                confidence=segment.confidence,
                source=source,
                reason=segment.reason or segment.thread_action,
                now=current,
            )
            if membership.thread_id and membership.relation == "belongs_to":
                updated = self.repository.update_thread_working_state(
                    owner_id=owner_id,
                    thread_id=membership.thread_id,
                    working_summary=item.summary,
                    participant_ids=item.participant_ids,
                    now=current,
                )
                if updated is not None:
                    known_threads[updated.id] = updated
            elif membership.thread_id:
                self.repository.touch_thread(
                    owner_id=owner_id,
                    thread_id=membership.thread_id,
                    now=current,
                )
            final_membership = self.repository.current_membership(
                owner_id=owner_id,
                segment_id=item.id,
            )
            if final_membership is None:
                final.append(item)
            else:
                final.append(
                    ConversationSegmentView(
                        id=item.id,
                        burst_id=item.burst_id,
                        message_ids=item.message_ids,
                        participant_ids=item.participant_ids,
                        kind=item.kind,
                        summary=item.summary,
                        thread_id=final_membership.thread_id,
                        membership_relation=final_membership.relation,
                        membership_confidence=final_membership.confidence,
                        confidence=item.confidence,
                        source=item.source,
                        created_at=item.created_at,
                    )
                )
        return ConversationSegmentationResult(
            burst_id=burst_id,
            segments=tuple(final),
            source=source,
            utility_used=judged is not None,
        )


__all__ = [
    "ConversationJudgeResult",
    "ConversationJudgeSegment",
    "ConversationSegmentationResult",
    "ConversationStructureResolver",
    "SegmentKind",
    "ThreadAction",
]
