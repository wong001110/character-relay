"""Shared Intelligence Core v3 context assembly for every Character turn."""

from __future__ import annotations

import asyncio
import logging
import re
from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock
from typing import TYPE_CHECKING, TypeVar, cast

from sqlalchemy import select

from echo_masque.api.connector_schemas import DiscordContextMessage, DiscordInboundMessage
from echo_masque.api.smart_participation_v3_schemas import (
    SmartParticipationBurstMessage,
    SmartParticipationMediaDescriptor,
    SmartParticipationResolveCandidate,
    SmartParticipationResolveRequest,
)
from echo_masque.belief_revision_v3 import CorrectionShield
from echo_masque.character_turn_context_types import (
    CharacterContextTraceView,
    CharacterTurnContext,
)
from echo_masque.context_resolver_v3 import ContextBundleV3, ContextResolverV3
from echo_masque.conversation_runtime import ConversationRuntimeCoordinator
from echo_masque.conversation_structure_resolver import ConversationStructureResolver
from echo_masque.current_turn_belief_v3 import (
    CurrentTurnBeliefRevisionService,
    CurrentTurnClaimExtraction,
)
from echo_masque.entity_grounding_v3 import EntityGroundingService, EntityType
from echo_masque.knowledge_fabric_context import KnowledgeContextBuilder
from echo_masque.knowledge_gap_discovery_v3 import KnowledgeGapDiscoveryService
from echo_masque.persistence.belief_models import BeliefRevisionEventRecord, BeliefV3Record
from echo_masque.persistence.conversation_structure_models import ConversationSegmentV3Record
from echo_masque.persistence.conversation_structure_repository import (
    ConversationSegmentView,
    ConversationStructureRepository,
)
from echo_masque.persistence.entity_evidence_repository import (
    KnowledgeGapView,
    normalize_entity_name,
)
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
        knowledge_context: KnowledgeContextBuilder,
        corrections: CurrentTurnBeliefRevisionService,
        entity_grounding: EntityGroundingService | None = None,
        knowledge_gap_discovery: KnowledgeGapDiscoveryService | None = None,
        cache_size: int = 512,
    ) -> None:
        self.structure = structure
        self.structure_resolver = structure_resolver
        self.runtime_coordinator = runtime_coordinator
        self.context_resolver = context_resolver
        self.knowledge_context = knowledge_context
        self.corrections = corrections
        self.entity_grounding = entity_grounding
        self.knowledge_gap_discovery = knowledge_gap_discovery
        self.database = structure.database
        self.server_runtime = ServerRuntimeRepository(self.database)
        self.cache_size = max(32, min(cache_size, 4096))
        self._lock = RLock()
        self._extractions: OrderedDict[str, CurrentTurnClaimExtraction] = OrderedDict()
        self._shields: OrderedDict[str, CorrectionShield] = OrderedDict()
        self._knowledge_gap_tasks: set[asyncio.Task[None]] = set()

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

    @staticmethod
    def _attachment_provenance(
        payload: DiscordInboundMessage,
    ) -> list[SmartParticipationMediaDescriptor]:
        """Retain opaque attachment identity for direct-turn Episode provenance only.

        These descriptors contain no analysis and are never emitted as Character perception.
        They cover direct/mention turns that do not first travel through planner media routing.
        """

        values: list[SmartParticipationMediaDescriptor] = []
        for index, attachment in enumerate(payload.attachments[:6], start=1):
            content_type = attachment.content_type.casefold()
            kind = (
                "image"
                if content_type.startswith("image/")
                else "video"
                if content_type.startswith("video/")
                else "file"
            )
            values.append(
                SmartParticipationMediaDescriptor(
                    ref=f"message:{payload.message_id}:attachment:{index}",
                    kind=kind,
                    state="preview_only",
                    label=attachment.filename,
                    source_key=f"discord-attachment:{attachment.attachment_id}",
                    source_url=attachment.url or attachment.proxy_url,
                )
            )
        return values

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
            media_descriptors=(
                list(payload.media_descriptors)
                if payload.media_descriptors
                else cls._attachment_provenance(payload)
            ),
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
            burst_context = tuple(
                f"{item.author_id} [{item.message_id}]: {item.text}"
                for item in payload.burst_messages
                if item.text.strip()
            )
            extraction = self.corrections.extract_self_claim(
                speaker_ref=payload.author_id,
                text=payload.message,
                burst_context=burst_context,
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
                    evidence_message_ids=tuple(
                        item.message_id for item in payload.burst_messages
                    ),
                    burst_id=payload.burst_id,
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
            burst_context = tuple(
                f"{item.author_id} [{item.message_id}]: {item.text}"
                for item in payload.recent_messages
                if item.text.strip()
            )
            extraction = self.corrections.extract_self_claim(
                speaker_ref=payload.author_id,
                text=payload.text,
                burst_context=burst_context,
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
            evidence_message_ids=tuple(item.message_id for item in payload.recent_messages),
            burst_id=payload.conversation_burst_id,
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

    @staticmethod
    def _explicit_existing_entity_reference(text: str, name: str) -> bool:
        """Recognize only an exact reference to an already scoped Entity.

        The inbound Conversation contracts do not carry Entity extraction output.  In particular,
        this deliberately does not promote arbitrary message tokens into Entity names.  A stored
        Entity may be reused only when its canonical name or alias appears explicitly in the
        current message.
        """

        normalized_name = normalize_entity_name(name)
        if len(normalized_name) < 2:
            return False
        normalized_text = normalize_entity_name(text)
        if not normalized_text:
            return False
        if normalized_name.isascii() and normalized_name.replace(" ", "").isalnum():
            return (
                re.search(
                    rf"(?<![a-z0-9_]){re.escape(normalized_name)}(?![a-z0-9_])",
                    normalized_text,
                )
                is not None
            )
        return normalized_name in normalized_text

    @staticmethod
    def _identity_question(text: str) -> bool:
        lowered = text.casefold()
        return (
            "?" in text
            or "\uff1f" in text
            or any(
                token in lowered
                for token in (
                    "who",
                    "what",
                    "identity",
                    "\u8c01",
                    "\u4ec0\u4e48",
                    "\u4ec0\u9ebc",
                    "\u8eab\u4efd",
                )
            )
        )

    def _dispatch_knowledge_gap_search(
        self,
        *,
        resolved: ResolvedCharacterTurn,
        gap: KnowledgeGapView,
    ) -> None:
        """Schedule an eligible search without coupling Character-turn success to Discovery."""

        service = self.knowledge_gap_discovery
        if service is None:
            return
        # A previous runtime attempt owns the open Gap until Content Understanding accepts
        # evidence or the Discovery service explicitly reopens it.  Do not re-dispatch on a
        # repeated Character turn.
        if (
            getattr(gap, "resolution_state", "") != "unresolved"
            or bool(getattr(gap, "discovery_requested", False))
            or float(getattr(gap, "importance", 0.0)) < 0.65
        ):
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Synchronous callers (including narrow maintenance/test paths) have no safe task
            # lifecycle.  The Gap remains unresolved and can be handled by a later runtime turn.
            return

        async def search_safely() -> None:
            try:
                await service.search(
                    owner_id=resolved.deployment.owner_id,
                    deployment_id=resolved.deployment.id,
                    connection_id=resolved.payload.connection_id,
                    guild_id=resolved.payload.guild_id,
                    gap=gap,
                )
            except Exception:
                # Discovery is optional and must never block context construction.  Do not log
                # message text, candidate content, or credential-derived details here.
                logger.warning(
                    "Knowledge Gap Discovery dispatch failed deployment=%s gap=%s",
                    resolved.deployment.id,
                    getattr(gap, "id", ""),
                )

        task = loop.create_task(
            search_safely(),
            name="character-relay-knowledge-gap-discovery",
        )
        self._knowledge_gap_tasks.add(task)
        task.add_done_callback(self._knowledge_gap_tasks.discard)

    def _ground_existing_entity_references(
        self,
        *,
        resolved: ResolvedCharacterTurn,
        segment: ConversationSegmentView,
    ) -> None:
        """Reuse scoped Entity records and open only supported provisional-identity Gaps."""

        grounding = self.entity_grounding
        if grounding is None:
            return
        payload = resolved.payload
        owner_id = resolved.deployment.owner_id
        evidence_refs = tuple(
            value for value in (f"message:{payload.message_id}", f"segment:{segment.id}") if value
        )
        if not evidence_refs:
            return
        # `recent_entities` is already owner/connection/guild scoped.  The only missing-field
        # contract currently supported by this runtime is a provisional Entity's canonical
        # identity; ordinary canonical records do not imply unknown fields.
        for entity in grounding.repository.recent_entities(
            owner_id=owner_id,
            connection_id=payload.connection_id,
            guild_id=payload.guild_id,
            limit=30,
        ):
            names = (entity.canonical_name, *entity.aliases)
            if not any(
                self._explicit_existing_entity_reference(payload.text, name) for name in names
            ):
                continue
            provisional = entity.status == "provisional"
            result = grounding.resolve_or_provision(
                owner_id=owner_id,
                connection_id=payload.connection_id,
                guild_id=payload.guild_id,
                name=entity.canonical_name,
                entity_type=cast(EntityType, entity.entity_type),
                evidence_refs=evidence_refs,
                missing_fields=("identity",) if provisional else (),
                importance=0.75 if provisional and self._identity_question(payload.text) else 0.5,
                triggered_by_ref=f"message:{payload.message_id}",
            )
            if result.knowledge_gap is not None:
                self._dispatch_knowledge_gap_search(resolved=resolved, gap=result.knowledge_gap)

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
            self._ground_existing_entity_references(resolved=resolved, segment=segment)
            shield = self.correction_for_turn(resolved)
            knowledge_context = self.knowledge_context.build(
                platform=deployment.platform,
                connection_id=payload.connection_id,
                workspace_id=payload.guild_id,
                deployment_id=deployment.id,
                character_card_id=resolved.card.id,
                query=payload.text,
            )
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
                knowledge_hits=knowledge_context.prompt_hits(),
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

        query_result = knowledge_context.result
        trace = CharacterContextTraceView(
            rag_status="completed" if knowledge_context.hits else "skipped",
            rag_reason=(
                "knowledge_fabric_admitted"
                if knowledge_context.hits
                else "knowledge_fabric_no_admitted_evidence"
            ),
            query_chars=len(payload.text),
            eligible_base_count=(query_result.accessible_corpus_count if query_result else 0),
            candidate_chunk_count=(len(query_result.hits) if query_result else 0),
            selected_chunk_count=len(knowledge_context.hits),
            selected_knowledge_tokens=sum(
                max(1, len(item.text_content) // 4) for item in knowledge_context.hits
            ),
            conversation_message_count=min(30, len(payload.recent_messages) + 1),
            conversation_chars=sum(len(item) for item in self._live_context(payload)),
            conversation_thread_id=conversation_thread_id,
        )
        return CharacterTurnContextV3Result(
            bundle=bundle,
            turn_context=CharacterTurnContext(
                smart_output=smart_output,
                knowledge=knowledge_context.hits,
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
