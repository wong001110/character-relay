"""Unified bounded Context Resolver for Intelligence Core v3."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from echo_masque.belief_revision_v3 import BeliefRevisionService, CorrectionShield
from echo_masque.expression_retrieval import semantic_tokens
from echo_masque.persistence.belief_repository import BeliefRepository, BeliefV3View
from echo_masque.persistence.conversation_runtime_repository import (
    ConversationEpisodeV3View,
    ConversationRuntimeRepository,
    PendingActionV3View,
    ThreadWorkingStateView,
)
from echo_masque.persistence.conversation_structure_repository import (
    ConversationSegmentView,
    ConversationStructureRepository,
    ConversationThreadView,
)
from echo_masque.persistence.discord_identity_repository import DiscordIdentityRepository
from echo_masque.persistence.entity_evidence_repository import (
    EntityEvidenceRepository,
    EntityV3View,
    KnowledgeGapView,
)
from echo_masque.social_intelligence_v3 import SocialIntelligenceV3Service, SocialTargetType

SufficiencyState = Literal[
    "sufficient",
    "insufficient_nonblocking",
    "external_lookup_needed",
    "unresolved",
]


@dataclass(frozen=True, slots=True)
class ContextTextHit:
    source: str
    ref: str
    text: str
    score: float = 1.0


@dataclass(frozen=True, slots=True)
class KnowledgePackingResult:
    """Final Knowledge Fabric admission after prompt-budget packing."""

    selected_refs: tuple[str, ...] = ()
    omitted: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class ContextBudget:
    live_chars: int = 2400
    belief_chars: int = 2200
    episode_chars: int = 1800
    entity_chars: int = 1600
    knowledge_chars: int = 2600
    social_chars: int = 900
    action_chars: int = 800


@dataclass(frozen=True, slots=True)
class ContextBundleV3:
    query: str
    thread: ConversationThreadView | None
    segment: ConversationSegmentView | None
    working_state: ThreadWorkingStateView | None
    live_context: tuple[str, ...]
    beliefs: tuple[BeliefV3View, ...]
    episodes: tuple[ConversationEpisodeV3View, ...]
    entities: tuple[EntityV3View, ...]
    knowledge_hits: tuple[ContextTextHit, ...]
    social_context: tuple[str, ...]
    pending_actions: tuple[PendingActionV3View, ...]
    knowledge_gaps: tuple[KnowledgeGapView, ...]
    correction_notice: str
    sufficiency: SufficiencyState
    reason: str
    temporal_context: tuple[str, ...] = ()
    knowledge_packing: KnowledgePackingResult = KnowledgePackingResult()

    def prompt_sections(self) -> tuple[str, ...]:
        sections: list[str] = []
        if self.correction_notice:
            sections.append(self.correction_notice)
        if self.temporal_context:
            sections.append("SERVER TIME\n" + "\n".join(self.temporal_context))
        if self.thread is not None:
            sections.append(
                "CONVERSATION THREAD\n"
                f"{self.thread.canonical_label}\n"
                f"Anchor: {self.thread.anchor_summary}\n"
                f"Current: {self.thread.working_summary}"
            )
        if self.working_state is not None:
            values: list[str] = []
            if self.working_state.current_object_ref:
                values.append(f"Current object: {self.working_state.current_object_ref}")
            if self.working_state.open_questions:
                values.append("Open questions: " + "; ".join(self.working_state.open_questions[:4]))
            if self.working_state.waiting_states:
                values.append("Waiting: " + "; ".join(self.working_state.waiting_states[:4]))
            if values:
                sections.append("THREAD WORKING STATE\n" + "\n".join(values))
        if self.live_context:
            sections.append("LIVE CONTEXT\n" + "\n".join(self.live_context))
        if self.beliefs:
            lines: list[str] = []
            for belief in self.beliefs:
                label = {
                    "active": "KNOWN",
                    "provisional": "TENTATIVE",
                    "disputed": "DISPUTED",
                }.get(belief.status, belief.status.upper())
                lines.append(
                    f"[{label}] {belief.subject_ref or belief.subject_entity_id} "
                    f"{belief.predicate}: {belief.value_text}"
                )
            sections.append("BELIEFS\n" + "\n".join(lines))
        if self.episodes:
            sections.append(
                "RELEVANT EPISODES\n"
                + "\n".join(f"- {item.summary}" for item in self.episodes if item.summary)
            )
        if self.entities:
            lines = [
                f"- {item.canonical_name} ({item.entity_type}, {item.status})"
                for item in self.entities
            ]
            sections.append("ENTITIES\n" + "\n".join(lines))
        if self.knowledge_hits:
            sections.append(
                "KNOWLEDGE EVIDENCE\n"
                + "\n".join(
                    f"- [{item.source}] {item.text}" for item in self.knowledge_hits
                )
            )
        if self.social_context:
            sections.append("SOCIAL CONTEXT\n" + "\n".join(self.social_context))
        if self.pending_actions:
            sections.append(
                "PENDING ACTIONS\n"
                + "\n".join(
                    f"- {item.tool_id}: {item.intent_summary} ({item.state})"
                    for item in self.pending_actions
                )
            )
        if self.knowledge_gaps:
            sections.append(
                "KNOWN KNOWLEDGE GAPS\n"
                + "\n".join(
                    f"- entity={item.entity_id}: {', '.join(item.missing_fields)}"
                    for item in self.knowledge_gaps
                )
                + "\nDo not invent missing facts."
            )
        return tuple(sections)


class ContextResolverV3:
    """Select runtime context across conversation, knowledge, and social state."""

    def __init__(
        self,
        *,
        structure: ConversationStructureRepository,
        runtime: ConversationRuntimeRepository,
        entities: EntityEvidenceRepository,
        beliefs: BeliefRepository,
        social: SocialIntelligenceV3Service,
        identities: DiscordIdentityRepository | None = None,
        budget: ContextBudget | None = None,
    ) -> None:
        self.structure = structure
        self.runtime = runtime
        self.entities = entities
        self.beliefs = beliefs
        self.social = social
        self.identities = identities or DiscordIdentityRepository(runtime.database)
        self.budget = budget or ContextBudget()

    def _episode_was_perceived(
        self,
        *,
        connection_id: str,
        deployment_id: str,
        episode: ConversationEpisodeV3View,
    ) -> bool:
        if not deployment_id:
            return False
        return any(
            (
                route := self.identities.resolve_message_route(
                    connection_id=connection_id,
                    message_id=message_id,
                )
            )
            is not None
            and route.deployment_id == deployment_id
            for message_id in episode.source_message_ids
        )

    @staticmethod
    def _bounded_lines(values: tuple[str, ...], limit: int) -> tuple[str, ...]:
        result: list[str] = []
        remaining = max(0, limit)
        for item in values:
            compact = " ".join(item.split())
            if not compact or remaining <= 0:
                continue
            compact = compact[:remaining]
            result.append(compact)
            remaining -= len(compact)
        return tuple(result)

    @staticmethod
    def _bounded_hits(
        values: tuple[ContextTextHit, ...], limit: int
    ) -> tuple[ContextTextHit, ...]:
        result: list[ContextTextHit] = []
        remaining = max(0, limit)
        for item in sorted(values, key=lambda value: value.score, reverse=True):
            compact = " ".join(item.text.split())
            if not compact or remaining <= 0:
                continue
            # Knowledge evidence has a closing trust boundary. Omitting an oversized hit is
            # fail-closed; truncating it could remove that boundary while leaving its data.
            if len(compact) > remaining:
                continue
            result.append(ContextTextHit(item.source, item.ref, compact, item.score))
            remaining -= len(compact)
        return tuple(result)

    @staticmethod
    def _pack_knowledge_fabric_hit(
        item: ContextTextHit,
        remaining: int,
    ) -> tuple[ContextTextHit | None, str]:
        """Keep a complete Fabric trust envelope while trimming only untrusted JSON text."""

        begin = "BEGIN UNTRUSTED EVIDENCE JSON\n"
        end = "\nEND UNTRUSTED EVIDENCE JSON"
        begin_index = item.text.find(begin)
        end_index = item.text.rfind(end)
        if begin_index < 0 or end_index < begin_index + len(begin):
            return None, "invalid_trust_envelope"
        prefix = item.text[: begin_index + len(begin)]
        raw_json = item.text[begin_index + len(begin) : end_index]
        try:
            payload = json.loads(raw_json)
        except (TypeError, ValueError):
            return None, "invalid_trust_envelope"
        required = {
            "authority",
            "evidence_unit_id",
            "freshness",
            "source_version_id",
            "text",
            "title",
        }
        if not isinstance(payload, dict) or not required.issubset(payload) or not isinstance(
            payload["text"], str
        ):
            return None, "invalid_trust_envelope"

        def render(text: str, *, truncated: bool) -> str:
            bounded_payload = dict(payload)
            bounded_payload["text"] = text
            if truncated:
                bounded_payload["truncated"] = True
            return prefix + json.dumps(
                bounded_payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ) + end

        compact = render(payload["text"], truncated=False)
        if len(compact) <= remaining:
            return ContextTextHit(item.source, item.ref, compact, item.score), ""
        if len(render("", truncated=True)) > remaining:
            return None, "trust_envelope_exceeds_budget"
        lower, upper = 0, len(payload["text"])
        while lower < upper:
            middle = (lower + upper + 1) // 2
            if len(render(payload["text"][:middle], truncated=True)) <= remaining:
                lower = middle
            else:
                upper = middle - 1
        return (
            ContextTextHit(
                item.source,
                item.ref,
                render(payload["text"][:lower], truncated=True),
                item.score,
            ),
            "truncated_to_budget",
        )

    @classmethod
    def _bounded_knowledge(
        cls,
        values: tuple[ContextTextHit, ...],
        limit: int,
    ) -> tuple[tuple[ContextTextHit, ...], KnowledgePackingResult]:
        selected: list[ContextTextHit] = []
        omitted: list[tuple[str, str]] = []
        # ``prompt_sections`` adds this heading plus one source label per hit.  Account for
        # those trusted wrapper characters here so the evidence budget is a true section cap.
        remaining = max(0, limit - len("KNOWLEDGE EVIDENCE\n"))
        for item in sorted(values, key=lambda value: value.score, reverse=True):
            if not item.text or remaining <= 0:
                omitted.append((item.ref, "budget_exhausted"))
                continue
            wrapper = len(f"- [{item.source}] ") + (1 if selected else 0)
            if wrapper > remaining:
                omitted.append((item.ref, "budget_exhausted"))
                continue
            available = remaining - wrapper
            if item.source == "knowledge_fabric":
                packed, reason = cls._pack_knowledge_fabric_hit(item, available)
                if packed is None:
                    omitted.append((item.ref, reason))
                    continue
                selected.append(packed)
                remaining -= wrapper + len(packed.text)
                if reason:
                    omitted.append((item.ref, reason))
                continue
            compact = " ".join(item.text.split())
            if not compact or len(compact) > available:
                omitted.append((item.ref, "budget_exhausted"))
                continue
            selected.append(ContextTextHit(item.source, item.ref, compact, item.score))
            remaining -= wrapper + len(compact)
        return (
            tuple(selected),
            KnowledgePackingResult(
                selected_refs=tuple(item.ref for item in selected),
                omitted=tuple(omitted),
            ),
        )

    def resolve(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        discord_thread_id: str,
        query: str,
        character_card_id: str = "",
        deployment_id: str = "",
        actor_id: str = "",
        segment_id: str = "",
        conversation_thread_id: str = "",
        live_context: tuple[str, ...] = (),
        knowledge_hits: tuple[ContextTextHit, ...] = (),
        correction_shield: CorrectionShield | None = None,
        social_target_type: SocialTargetType = "actor",
        social_target_key: str = "",
        temporal_context: tuple[str, ...] = (),
    ) -> ContextBundleV3:
        segment: ConversationSegmentView | None = None
        if segment_id:
            recent_segments = self.structure.recent_segments(
                owner_id=owner_id,
                connection_id=connection_id,
                guild_id=guild_id,
                limit=100,
            )
            segment = next((item for item in recent_segments if item.id == segment_id), None)
        thread_id = conversation_thread_id
        if not thread_id and segment is not None:
            membership = self.structure.current_membership(
                owner_id=owner_id,
                segment_id=segment.id,
            )
            if membership is not None:
                thread_id = membership.thread_id
        thread = None
        if thread_id:
            thread = next(
                (
                    item
                    for item in self.structure.recent_threads_for_server(
                        owner_id=owner_id,
                        connection_id=connection_id,
                        guild_id=guild_id,
                        limit=100,
                    )
                    if item.id == thread_id
                ),
                None,
            )
        working = (
            self.runtime.working_state(owner_id=owner_id, thread_id=thread_id)
            if thread_id
            else None
        )
        subject_refs = (actor_id,) if actor_id else ()
        query_compact = " ".join(query.split())[:4000]
        recalled = self.beliefs.search_relevant(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            character_card_id=character_card_id,
            subject_refs=subject_refs,
            query_terms=tuple(semantic_tokens(query_compact)),
            limit=60,
        )
        shield = correction_shield or CorrectionShield((), "", "")
        recalled = BeliefRevisionService.apply_shield(recalled, shield)
        belief_values: list[BeliefV3View] = []
        belief_remaining = self.budget.belief_chars
        for belief in recalled:
            cost = len(belief.value_text) + len(belief.predicate) + len(belief.subject_ref) + 16
            if cost > belief_remaining and belief_values:
                continue
            belief_values.append(belief)
            belief_remaining -= min(cost, belief_remaining)
            if belief_remaining <= 0:
                break
        episodes = self.runtime.search_episodes(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            query_terms=tuple(semantic_tokens(query_compact)),
            limit=240,
        )
        episode_values: list[ConversationEpisodeV3View] = []
        episode_remaining = self.budget.episode_chars
        for episode in episodes:
            if not self._episode_was_perceived(
                connection_id=connection_id,
                deployment_id=deployment_id,
                episode=episode,
            ):
                continue
            if thread_id and episode.conversation_thread_id not in {"", thread_id}:
                continue
            cost = len(episode.summary)
            if cost > episode_remaining and episode_values:
                continue
            episode_values.append(episode)
            episode_remaining -= min(cost, episode_remaining)
            if episode_remaining <= 0:
                break
        entities = self.entities.recent_entities(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            limit=30,
        )
        active_ids = set(thread.active_entity_ids if thread is not None else ())
        if working is not None:
            active_ids.update(working.active_entity_ids)
        if active_ids:
            entities = tuple(item for item in entities if item.id in active_ids) or entities[:8]
        else:
            entities = entities[:8]
        gaps = self.entities.unresolved_gaps(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            minimum_importance=0.55,
            limit=16,
        )
        if active_ids:
            gaps = tuple(item for item in gaps if item.entity_id in active_ids)
        pending = self.runtime.active_pending_actions(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            requested_by_user_id=actor_id,
            deployment_id=deployment_id,
            conversation_thread_id=thread_id,
            limit=8,
        )
        social_context: tuple[str, ...] = ()
        target_key = social_target_key or actor_id
        if deployment_id and target_key:
            social_context = self.social.prompt_context(
                owner_id=owner_id,
                source_deployment_id=deployment_id,
                target_type=social_target_type,
                target_key=target_key,
                max_chars=self.budget.social_chars,
            )

        bounded_live = self._bounded_lines(live_context, self.budget.live_chars)
        bounded_knowledge, knowledge_packing = self._bounded_knowledge(
            knowledge_hits,
            self.budget.knowledge_chars,
        )
        unresolved_segment = bool(
            segment is not None
            and segment.membership_relation == "unresolved"
            and not segment.thread_id
        )
        blocking_gap = bool(
            gaps
            and any(item.importance >= 0.75 for item in gaps)
            and ("?" in query_compact or "\uff1f" in query_compact)
        )
        if unresolved_segment:
            sufficiency: SufficiencyState = "unresolved"
            reason = "conversation_membership_unresolved"
        elif blocking_gap and not bounded_knowledge:
            sufficiency = "external_lookup_needed"
            reason = "high_importance_entity_knowledge_gap"
        elif not any(
            (
                bounded_live,
                belief_values,
                episode_values,
                entities,
                bounded_knowledge,
                social_context,
                pending,
            )
        ):
            sufficiency = "insufficient_nonblocking"
            reason = "no_relevant_context"
        else:
            sufficiency = "sufficient"
            reason = "bounded_context_ready"

        return ContextBundleV3(
            query=query_compact,
            thread=thread,
            segment=segment,
            working_state=working,
            live_context=bounded_live,
            beliefs=tuple(belief_values),
            episodes=tuple(episode_values),
            entities=entities,
            knowledge_hits=bounded_knowledge,
            social_context=social_context,
            pending_actions=pending,
            knowledge_gaps=gaps,
            correction_notice=shield.notice,
            sufficiency=sufficiency,
            reason=reason,
            temporal_context=self._bounded_lines(temporal_context, 480),
            knowledge_packing=knowledge_packing,
        )


__all__ = [
    "ContextBudget",
    "ContextBundleV3",
    "ContextResolverV3",
    "ContextTextHit",
    "KnowledgePackingResult",
    "SufficiencyState",
]
