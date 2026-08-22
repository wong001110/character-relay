"""Shared Intelligence Core v3 context assembly for every Character turn."""

from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock
from typing import TYPE_CHECKING, TypeVar

from sqlalchemy import select

from echo_masque.api.connector_schemas import DiscordContextMessage, DiscordInboundMessage
from echo_masque.api.smart_participation_v3_schemas import (
    SmartParticipationBurstMessage,
    SmartParticipationResolveCandidate,
    SmartParticipationResolveRequest,
)
from echo_masque.belief_revision_v3 import CorrectionShield
from echo_masque.character_turn_context_types import (
    CharacterContextTraceView,
    CharacterTurnContext,
)
from echo_masque.context_resolver_v3 import ContextBundleV3, ContextResolverV3, ContextTextHit
from echo_masque.conversation_runtime import ConversationRuntimeCoordinator
from echo_masque.conversation_structure_resolver import ConversationStructureResolver
from echo_masque.current_turn_belief_v3 import (
    CurrentTurnBeliefRevisionService,
    CurrentTurnClaimExtraction,
)
from echo_masque.knowledge_retrieval import KnowledgeCandidate
from echo_masque.persistence.belief_models import BeliefRevisionEventRecord, BeliefV3Record
from echo_masque.persistence.conversation_structure_models import ConversationSegmentV3Record
from echo_masque.persistence.conversation_structure_repository import (
    ConversationSegmentView,
    ConversationStructureRepository,
)
from echo_masque.persistence.knowledge_repository import KnowledgeRepository
from echo_masque.persistence.server_knowledge_v3_repository import ServerWikiV3Repository
from echo_masque.persistence.server_runtime_repository import ServerRuntimeRepository
from echo_masque.persistence.smart_participation_state_models import (
    SmartParticipationReplyDecisionRecord,
)
from echo_masque.server_time import activate_server_timezone, server_local_now
from echo_masque.smart_output import SmartOutputContext
from echo_masque.social_intelligence_v3 import SocialTargetType

if TYPE_CHECKING:
    from echo_masque.connector_runtime import ResolvedCharacterTurn

logger = logging.getLogger(__name__)
_CacheValue = TypeVar("_CacheValue")


class CharacterTurnContextV3Unavailable(RuntimeError):
    """Raised when authoritative v3 context cannot be assembled safely."""


@dataclass(frozen=True, slots=True)
class CharacterTurnContextV3Result:
    """Bounded v3 bundle plus compatibility observability/Smart Output state."""

    bundle: ContextBundleV3
    turn_context: CharacterTurnContext
    error_reason: str = ""


@dataclass(frozen=True, slots=True)
class ParticipationCorrectionV3Result:
    """Per-candidate correction shields and extraction observability."""

    shields: dict[str, CorrectionShield]
    utility_used: bool


class CharacterTurnContextV3Service:
    """Build one scope-verified v3 Character context without legacy fallbacks."""

    def __init__(
        self,
        *,
        structure: ConversationStructureRepository,
        structure_resolver: ConversationStructureResolver,
        runtime_coordinator: ConversationRuntimeCoordinator,
        context_resolver: ContextResolverV3,
        knowledge: KnowledgeRepository,
        wiki: ServerWikiV3Repository,
        corrections: CurrentTurnBeliefRevisionService,
        cache_size: int = 512,
    ) -> None:
        self.structure = structure
        self.structure_resolver = structure_resolver
        self.runtime_coordinator = runtime_coordinator
        self.context_resolver = context_resolver
        self.knowledge = knowledge
        self.wiki = wiki
        self.corrections = corrections
        self.database = structure.database
        self.server_runtime = ServerRuntimeRepository(self.database)
        self.cache_size = max(32, min(cache_size, 4096))
        self._lock = RLock()
        self._extractions: OrderedDict[str, CurrentTurnClaimExtraction] = OrderedDict()
        self._shields: OrderedDict[str, CorrectionShield] = OrderedDict()

    def _cache_get(
        self,
        values: OrderedDict[str, _CacheValue],
        key: str,
    ) -> _CacheValue | None:
        with self._lock:
            value = values.get(key)
            if value is not None:
                values.move_to_end(key)
            return value

    def _cache_put(
        self,
        values: OrderedDict[str, _CacheValue],
        key: str,
        value: _CacheValue,
    ) -> None:
        with self._lock:
            values[key] = value
            values.move_to_end(key)
            while len(values) > self.cache_size:
                values.popitem(last=False)

    @staticmethod
    def _source_message_id(payload: DiscordInboundMessage) -> str:
        return payload.message_id[:200]

    @staticmethod
    def _burst_messages(payload: DiscordInboundMessage) -> list[SmartParticipationBurstMessage]:
        values = list(payload.recent_messages[-4:])
        if not any(item.message_id == payload.message_id for item in values):
            values.append(
                DiscordContextMessage(
                    message_id=payload.message_id,
                    author_id=payload.author_id,
                    author_display_name=payload.author_display_name,
                    text=payload.text,
                    emojis=payload.emojis,
                    stickers=payload.stickers,
                    is_bot=payload.author_is_bot,
                )
            )
        return [
            SmartParticipationBurstMessage(
                message_id=item.message_id,
                author_id=item.author_id,
                author_display_name=item.author_display_name,
                text=item.text[:4000],
                created_at=item.created_at.isoformat() if item.created_at is not None else "",
                reply_to_message_id=(
                    payload.reply_to_message_id if item.message_id == payload.message_id else ""
                ),
            )
            for item in values[-5:]
        ]

    @classmethod
    def _structure_payload(
        cls,
        resolved: ResolvedCharacterTurn,
    ) -> SmartParticipationResolveRequest:
        payload = resolved.payload
        return SmartParticipationResolveRequest(
            connection_id=payload.connection_id,
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            thread_id=payload.thread_id,
            message_id=payload.message_id,
            author_id=payload.author_id,
            reply_to_message_id=payload.reply_to_message_id,
            message=payload.text[:4000],
            burst_id=payload.conversation_burst_id or f"message:{payload.message_id}",
            burst_messages=cls._burst_messages(payload),
            max_participants=1,
            candidates=[
                SmartParticipationResolveCandidate(
                    deployment_id=resolved.deployment.id,
                    eligible=True,
                )
            ],
        )

    def _decision(
        self,
        resolved: ResolvedCharacterTurn,
    ) -> SmartParticipationReplyDecisionRecord | None:
        payload = resolved.payload
        deployment = resolved.deployment
        with self.database.session() as session:
            return session.scalar(
                select(SmartParticipationReplyDecisionRecord)
                .where(
                    SmartParticipationReplyDecisionRecord.owner_id == deployment.owner_id,
                    SmartParticipationReplyDecisionRecord.connection_id == payload.connection_id,
                    SmartParticipationReplyDecisionRecord.guild_id == payload.guild_id,
                    SmartParticipationReplyDecisionRecord.channel_id == payload.channel_id,
                    SmartParticipationReplyDecisionRecord.thread_id == payload.thread_id,
                    SmartParticipationReplyDecisionRecord.source_message_id
                    == self._source_message_id(payload),
                    SmartParticipationReplyDecisionRecord.deployment_id == deployment.id,
                    SmartParticipationReplyDecisionRecord.character_card_id == resolved.card.id,
                    SmartParticipationReplyDecisionRecord.authoritative.is_(True),
                    SmartParticipationReplyDecisionRecord.resolver_version
                    == "conversation-intelligence-v3",
                )
                .order_by(SmartParticipationReplyDecisionRecord.updated_at.desc())
                .limit(1)
            )

    def _segment(
        self,
        *,
        resolved: ResolvedCharacterTurn,
        segment_id: str,
    ) -> ConversationSegmentView | None:
        if not segment_id:
            return None
        payload = resolved.payload
        deployment = resolved.deployment
        with self.database.session() as session:
            record = session.scalar(
                select(ConversationSegmentV3Record).where(
                    ConversationSegmentV3Record.id == segment_id,
                    ConversationSegmentV3Record.owner_id == deployment.owner_id,
                    ConversationSegmentV3Record.connection_id == payload.connection_id,
                    ConversationSegmentV3Record.guild_id == payload.guild_id,
                    ConversationSegmentV3Record.channel_id == payload.channel_id,
                    ConversationSegmentV3Record.discord_thread_id == payload.thread_id,
                )
            )
            if record is None:
                return None
            membership = self.structure._current_membership_record(session, record.id)
            return self.structure.segment_view(record, membership)

    def _existing_segment_for_message(
        self,
        resolved: ResolvedCharacterTurn,
    ) -> ConversationSegmentView | None:
        payload = resolved.payload
        deployment = resolved.deployment
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(ConversationSegmentV3Record)
                    .where(
                        ConversationSegmentV3Record.owner_id == deployment.owner_id,
                        ConversationSegmentV3Record.connection_id == payload.connection_id,
                        ConversationSegmentV3Record.guild_id == payload.guild_id,
                        ConversationSegmentV3Record.channel_id == payload.channel_id,
                        ConversationSegmentV3Record.discord_thread_id == payload.thread_id,
                    )
                    .order_by(ConversationSegmentV3Record.created_at.desc())
                    .limit(100)
                )
            )
            for record in records:
                membership = self.structure._current_membership_record(session, record.id)
                view = self.structure.segment_view(record, membership)
                if payload.message_id in view.message_ids:
                    return view
        return None

    def _resolve_segment(
        self,
        resolved: ResolvedCharacterTurn,
    ) -> tuple[ConversationSegmentView, str]:
        decision = self._decision(resolved)
        if decision is not None:
            persisted = self._segment(resolved=resolved, segment_id=decision.segment_id)
            if persisted is None:
                raise CharacterTurnContextV3Unavailable(
                    "Authoritative participation decision references an unavailable Segment."
                )
            return persisted, persisted.thread_id

        existing = self._existing_segment_for_message(resolved)
        if existing is not None:
            return existing, existing.thread_id

        structure_payload = self._structure_payload(resolved)
        result = self.structure_resolver.resolve(
            payload=structure_payload,
            owner_id=resolved.deployment.owner_id,
        )
        current = next(
            (item for item in result.segments if resolved.payload.message_id in item.message_ids),
            None,
        )
        if current is None:
            raise CharacterTurnContextV3Unavailable(
                "Conversation Structure did not resolve the current message."
            )
        self.runtime_coordinator.observe(
            owner_id=resolved.deployment.owner_id,
            payload=structure_payload,
            result=result,
        )
        return current, current.thread_id

    def _existing_correction_shield(
        self,
        *,
        resolved: ResolvedCharacterTurn,
    ) -> CorrectionShield | None:
        payload = resolved.payload
        return self._existing_shield_for_scope(
            owner_id=resolved.deployment.owner_id,
            character_card_id=resolved.card.id,
            connection_id=payload.connection_id,
            guild_id=payload.guild_id,
            source_message_id=payload.message_id,
        )

    def _existing_shield_for_scope(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        connection_id: str,
        guild_id: str,
        source_message_id: str,
    ) -> CorrectionShield | None:
        with self.database.session() as session:
            row = session.execute(
                select(BeliefRevisionEventRecord, BeliefV3Record)
                .join(BeliefV3Record, BeliefV3Record.id == BeliefRevisionEventRecord.belief_id)
                .where(
                    BeliefRevisionEventRecord.owner_id == owner_id,
                    BeliefRevisionEventRecord.source_message_id == source_message_id,
                    BeliefV3Record.character_card_id == character_card_id,
                    BeliefV3Record.connection_id == connection_id,
                    BeliefV3Record.guild_id == guild_id,
                )
                .order_by(BeliefRevisionEventRecord.created_at.desc())
                .limit(1)
            ).first()
            if row is None:
                return None
            event, belief = row
            if event.action == "supersede" and event.previous_belief_id:
                return CorrectionShield(
                    (event.previous_belief_id,),
                    belief.id,
                    "MEMORY REVISION NOTICE\nCurrent evidence explicitly corrects an earlier "
                    "remembered claim. Do not rely on the superseded claim in this turn.",
                )
            if event.action == "dispute":
                conflicts = list(
                    session.scalars(
                        select(BeliefV3Record).where(
                            BeliefV3Record.owner_id == owner_id,
                            BeliefV3Record.character_card_id == character_card_id,
                            BeliefV3Record.connection_id == connection_id,
                            BeliefV3Record.guild_id == guild_id,
                            BeliefV3Record.subject_ref == belief.subject_ref,
                            BeliefV3Record.predicate == belief.predicate,
                            BeliefV3Record.id != belief.id,
                            BeliefV3Record.status.in_(("active", "provisional", "disputed")),
                        )
                    )
                )
                return CorrectionShield(
                    tuple(item.id for item in conflicts),
                    belief.id,
                    "MEMORY REVISION NOTICE\nCurrent speaker disputes earlier memory. Treat the "
                    "conflict as unresolved for this turn rather than asserting the old claim.",
                )
        return CorrectionShield((), "", "")

    def corrections_for_participation(
        self,
        *,
        payload: SmartParticipationResolveRequest,
        owner_id: str,
        deployment_characters: tuple[tuple[str, str], ...],
    ) -> ParticipationCorrectionV3Result:
        """Apply the same idempotent current-turn correction path during planning."""

        source_message_id = payload.message_id or (
            payload.burst_messages[-1].message_id if payload.burst_messages else "current-turn"
        )
        extraction_key = ":".join(
            (
                owner_id,
                payload.connection_id,
                payload.guild_id,
                source_message_id,
                payload.author_id,
            )
        )
        extraction = self._cache_get(self._extractions, extraction_key)
        if extraction is None:
            extraction = self.corrections.extract_self_claim(
                speaker_ref=payload.author_id,
                text=payload.message,
            )
            self._cache_put(self._extractions, extraction_key, extraction)
        shields: dict[str, CorrectionShield] = {}
        for deployment_id, character_card_id in deployment_characters:
            key = ":".join(
                (
                    owner_id,
                    payload.connection_id,
                    payload.guild_id,
                    source_message_id,
                    character_card_id,
                )
            )
            cached = self._cache_get(self._shields, key)
            if cached is None:
                cached = self._existing_shield_for_scope(
                    owner_id=owner_id,
                    character_card_id=character_card_id,
                    connection_id=payload.connection_id,
                    guild_id=payload.guild_id,
                    source_message_id=source_message_id,
                )
            if cached is None:
                revision = self.corrections.apply_to_character(
                    extraction=extraction,
                    owner_id=owner_id,
                    character_card_id=character_card_id,
                    connection_id=payload.connection_id,
                    guild_id=payload.guild_id,
                    speaker_ref=payload.author_id,
                    source_message_id=source_message_id,
                )
                cached = revision.shield if revision is not None else CorrectionShield((), "", "")
            self._cache_put(self._shields, key, cached)
            if cached.active:
                shields[deployment_id] = cached
        return ParticipationCorrectionV3Result(
            shields=shields,
            utility_used=extraction.utility_used,
        )

    def correction_for_turn(self, resolved: ResolvedCharacterTurn) -> CorrectionShield:
        payload = resolved.payload
        cache_key = ":".join(
            (
                resolved.deployment.owner_id,
                payload.connection_id,
                payload.guild_id,
                payload.message_id,
                resolved.card.id,
            )
        )
        cached = self._cache_get(self._shields, cache_key)
        if isinstance(cached, CorrectionShield):
            return cached
        existing = self._existing_correction_shield(resolved=resolved)
        if existing is not None:
            self._cache_put(self._shields, cache_key, existing)
            return existing

        extraction_key = ":".join(
            (
                resolved.deployment.owner_id,
                payload.connection_id,
                payload.guild_id,
                payload.message_id,
                payload.author_id,
            )
        )
        extraction = self._cache_get(self._extractions, extraction_key)
        if not isinstance(extraction, CurrentTurnClaimExtraction):
            extraction = self.corrections.extract_self_claim(
                speaker_ref=payload.author_id,
                text=payload.text,
            )
            self._cache_put(self._extractions, extraction_key, extraction)
        revision = self.corrections.apply_to_character(
            extraction=extraction,
            owner_id=resolved.deployment.owner_id,
            character_card_id=resolved.card.id,
            connection_id=payload.connection_id,
            guild_id=payload.guild_id,
            speaker_ref=payload.author_id,
            source_message_id=payload.message_id,
        )
        shield = revision.shield if revision is not None else CorrectionShield((), "", "")
        self._cache_put(self._shields, cache_key, shield)
        return shield

    @staticmethod
    def _live_context(payload: DiscordInboundMessage) -> tuple[str, ...]:
        values = [
            f"{item.author_display_name}: {item.text}"
            for item in payload.recent_messages
            if item.text.strip()
        ]
        if payload.text.strip() and not any(
            item.message_id == payload.message_id for item in payload.recent_messages
        ):
            values.append(f"{payload.author_display_name}: {payload.text}")
        return tuple(values[-30:])

    def _knowledge_hits(
        self,
        resolved: ResolvedCharacterTurn,
    ) -> tuple[tuple[ContextTextHit, ...], tuple[KnowledgeCandidate, ...], int, int]:
        payload = resolved.payload
        result = self.knowledge.retrieve_for_turn(
            owner_id=resolved.deployment.owner_id,
            connection_id=payload.connection_id,
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            thread_id=payload.thread_id,
            character_card_id=resolved.card.id,
            query=payload.text,
            top_k=4,
        )
        hits = tuple(
            ContextTextHit(
                source="knowledge",
                ref=item.resource.chunk_id,
                text=f"{item.resource.document_title}: {item.resource.content}",
                score=item.score,
            )
            for item in result.candidates
        )
        return hits, result.candidates, result.eligible_base_count, result.candidate_chunk_count

    def _wiki_hits(self, resolved: ResolvedCharacterTurn) -> tuple[ContextTextHit, ...]:
        payload = resolved.payload

        def confidence(value: object) -> float:
            return (
                float(value)
                if isinstance(value, (int, float)) and not isinstance(value, bool)
                else 0.0
            )

        return tuple(
            ContextTextHit(
                source="server_wiki_v3",
                ref=str(item.get("ref", "")),
                text=f"{item.get('title', '')}: {item.get('body', '')}",
                score=confidence(item.get("confidence", 0.0)),
            )
            for item in self.wiki.lookup(
                owner_id=resolved.deployment.owner_id,
                connection_id=payload.connection_id,
                guild_id=payload.guild_id,
                query=payload.text,
                limit=6,
            )
        )

    def build(self, resolved: ResolvedCharacterTurn) -> CharacterTurnContextV3Result:
        """Build authoritative v3 context without consulting any old context path."""

        payload = resolved.payload
        deployment = resolved.deployment
        smart_output = SmartOutputContext.from_payload(
            payload,
            character_name=resolved.card.display_name,
        )
        try:
            timezone = self.server_runtime.resolve_timezone(
                owner_id=deployment.owner_id,
                connection_id=payload.connection_id,
                guild_id=payload.guild_id,
            )
            activate_server_timezone(timezone)
            local_now = server_local_now(timezone)
            temporal_context = (
                f"Default timezone: {timezone} (IANA).",
                f"Current local datetime: {local_now.isoformat(timespec='seconds')}.",
                "Interpret dates and times without an explicit timezone in this Server timezone.",
            )
            segment, conversation_thread_id = self._resolve_segment(resolved)
            shield = self.correction_for_turn(resolved)
            knowledge_hits, candidates, eligible_count, candidate_count = self._knowledge_hits(
                resolved
            )
            wiki_hits = self._wiki_hits(resolved)
            social_target_type, social_target_key = self._social_target(resolved)
            bundle = self.context_resolver.resolve(
                owner_id=deployment.owner_id,
                connection_id=payload.connection_id,
                guild_id=payload.guild_id,
                channel_id=payload.channel_id,
                discord_thread_id=payload.thread_id,
                query=payload.text,
                character_card_id=resolved.card.id,
                deployment_id=deployment.id,
                actor_id=payload.author_id,
                segment_id=segment.id,
                conversation_thread_id=conversation_thread_id,
                live_context=self._live_context(payload),
                knowledge_hits=knowledge_hits,
                wiki_hits=wiki_hits,
                correction_shield=shield,
                social_target_type=social_target_type,
                social_target_key=social_target_key,
                temporal_context=temporal_context,
            )
        except Exception as exc:
            logger.warning(
                "Character v3 context failed deployment=%s message=%s error_type=%s",
                deployment.id,
                payload.message_id,
                type(exc).__name__,
            )
            reason = (
                "context_unavailable"
                if not isinstance(exc, CharacterTurnContextV3Unavailable)
                else "conversation_structure_unavailable"
            )
            return CharacterTurnContextV3Result(
                bundle=ContextBundleV3(
                    query=" ".join(payload.text.split())[:4000],
                    thread=None,
                    segment=None,
                    working_state=None,
                    live_context=(),
                    beliefs=(),
                    episodes=(),
                    entities=(),
                    knowledge_hits=(),
                    wiki_hits=(),
                    social_context=(),
                    pending_actions=(),
                    knowledge_gaps=(),
                    correction_notice="",
                    sufficiency="unresolved",
                    reason=reason,
                ),
                turn_context=CharacterTurnContext(
                    smart_output=smart_output,
                    knowledge=(),
                    trace=CharacterContextTraceView(
                        rag_status="failed",
                        rag_reason=reason,
                        query_chars=len(payload.text),
                    ),
                ),
                error_reason=reason,
            )

        trace = CharacterContextTraceView(
            rag_status="completed" if candidates else "skipped",
            rag_reason="ok" if candidates else "no_relevant_chunks",
            query_chars=len(payload.text),
            eligible_base_count=eligible_count,
            candidate_chunk_count=candidate_count,
            selected_chunk_count=len(candidates),
            selected_knowledge_tokens=sum(
                max(1, len(item.resource.content) // 4) for item in candidates
            ),
            conversation_message_count=min(30, len(payload.recent_messages) + 1),
            conversation_chars=sum(len(item) for item in self._live_context(payload)),
            conversation_thread_id=conversation_thread_id,
        )
        return CharacterTurnContextV3Result(
            bundle=bundle,
            turn_context=CharacterTurnContext(
                smart_output=smart_output,
                knowledge=candidates,
                trace=trace,
            ),
        )

    def _social_target(
        self,
        resolved: ResolvedCharacterTurn,
    ) -> tuple[SocialTargetType, str]:
        payload = resolved.payload
        if payload.author_is_bot and payload.message_id:
            route = self.context_resolver.identities.resolve_message_route(
                connection_id=payload.connection_id,
                message_id=payload.message_id,
            )
            if route is not None and route.deployment_id != resolved.deployment.id:
                return "deployment", route.deployment_id
        return "actor", payload.author_id


__all__ = [
    "CharacterTurnContextV3Result",
    "CharacterTurnContextV3Service",
    "CharacterTurnContextV3Unavailable",
    "ParticipationCorrectionV3Result",
]
