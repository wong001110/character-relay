"""Bounded contextual reranking for already-eligible Smart Participation candidates.

Graph and Learned State are derived evidence. This module deliberately cannot make an ineligible
candidate eligible or lift a below-threshold candidate across its minimum score. It only reorders
or demotes candidates that the deterministic + E5 layer already considered plausible.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import log1p

from echo_masque.character_learned_state import CharacterLearnedStateService
from echo_masque.persistence.conversation_graph_repository import (
    ConversationGraphRepository,
    ConversationGraphScope,
)
from echo_masque.persistence.conversation_topic_repository import ConversationTopicRepository


@dataclass(frozen=True, slots=True)
class ParticipationContextCandidate:
    deployment_id: str
    owner_id: str
    character_card_id: str
    eligible: bool
    minimum_score: float
    base_final_score: float
    deterministic_signals: dict[str, float]


@dataclass(frozen=True, slots=True)
class ParticipationContextEvidence:
    name: str
    adjustment: float
    source: str
    confidence: float


@dataclass(frozen=True, slots=True)
class ParticipationContextScore:
    deployment_id: str
    base_final_score: float
    contextual_adjustment: float
    contextual_final_score: float
    selected: bool
    evidence: tuple[ParticipationContextEvidence, ...]


@dataclass(frozen=True, slots=True)
class ParticipationContextPlanItem:
    deployment_id: str
    turn_role: str
    reason: str


@dataclass(frozen=True, slots=True)
class ParticipationContextResult:
    scores: tuple[ParticipationContextScore, ...]
    plan: tuple[ParticipationContextPlanItem, ...]
    graph_used: bool
    learned_state_used: bool


def _bounded(value: float, limit: float) -> float:
    return max(-limit, min(limit, float(value)))


class ParticipationContextReranker:
    """Combine named Graph/Learned evidence without creating another opaque detector score."""

    def __init__(
        self,
        graph: ConversationGraphRepository,
        topics: ConversationTopicRepository,
        learned: CharacterLearnedStateService,
    ) -> None:
        self.graph = graph
        self.topics = topics
        self.learned = learned

    def _candidate_evidence(
        self,
        candidate: ParticipationContextCandidate,
        *,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
        author_id: str,
        graph_enabled: bool,
        learned_enabled: bool,
    ) -> tuple[ParticipationContextEvidence, ...]:
        # Below-threshold candidates are intentionally invisible to contextual support. This is the
        # central no-boost invariant for the first active V4 rollout.
        if not candidate.eligible or candidate.base_final_score < candidate.minimum_score:
            return ()

        values: list[ParticipationContextEvidence] = []
        topic = self.topics.active_for_scope(
            owner_id=candidate.owner_id,
            platform="discord",
            connection_id=connection_id,
            guild_id=guild_id,
            channel_id=channel_id,
            thread_id=thread_id,
        )
        topic_key = f"topic:{topic.id}" if topic is not None else ""
        scope_key = ":".join((connection_id, guild_id, channel_id, thread_id))

        if graph_enabled and topic is not None:
            scope = ConversationGraphScope(
                scope_owner_id=candidate.owner_id,
                platform="discord",
                connection_id=connection_id,
                guild_id=guild_id,
                channel_id=channel_id,
                thread_id=thread_id,
            )
            character = self.graph.find_node(
                scope=scope,
                node_type="Character",
                canonical_key=f"character:{candidate.character_card_id}",
            )
            if character is not None:
                neighbors = self.graph.neighbors(
                    scope=scope,
                    node_id=character.id,
                    relations=("PARTICIPATED_IN",),
                    limit=20,
                )
                for neighbor in neighbors:
                    if (
                        neighbor.node.node_type != "Topic"
                        or neighbor.node.canonical_key != topic_key
                    ):
                        continue
                    edge = neighbor.edge
                    strength = min(1.0, log1p(max(0, edge.evidence_count)) / log1p(8))
                    confidence = max(0.0, min(1.0, edge.confidence))
                    adjustment = round(0.65 * strength * confidence, 3)
                    if adjustment:
                        values.append(
                            ParticipationContextEvidence(
                                "active_topic_participation",
                                adjustment,
                                "graph",
                                confidence,
                            )
                        )
                    break

        if learned_enabled:
            if topic_key:
                interest = self.learned.get(
                    owner_id=candidate.owner_id,
                    character_card_id=candidate.character_card_id,
                    state_type="interest",
                    subject_type="topic",
                    subject_key=topic_key,
                )
                if interest is not None:
                    adjustment = round(_bounded(interest.value * interest.confidence * 0.8, 0.8), 3)
                    if adjustment:
                        values.append(
                            ParticipationContextEvidence(
                                "dynamic_interest",
                                adjustment,
                                "learned_state",
                                interest.confidence,
                            )
                        )

                question_weight = max(
                    candidate.deterministic_signals.get("question", 0.0),
                    candidate.deterministic_signals.get("help_request", 0.0),
                )
                if question_weight > 0:
                    expertise = self.learned.get(
                        owner_id=candidate.owner_id,
                        character_card_id=candidate.character_card_id,
                        state_type="expertise",
                        subject_type="topic",
                        subject_key=topic_key,
                    )
                    if expertise is not None:
                        adjustment = round(
                            _bounded(expertise.value * expertise.confidence * 0.55, 0.55),
                            3,
                        )
                        if adjustment:
                            values.append(
                                ParticipationContextEvidence(
                                    "topic_expertise",
                                    adjustment,
                                    "learned_state",
                                    expertise.confidence,
                                )
                            )

                ownership = self.learned.get(
                    owner_id=candidate.owner_id,
                    character_card_id=candidate.character_card_id,
                    state_type="conversation_ownership",
                    subject_type="topic",
                    subject_key=topic_key,
                )
                if ownership is not None and ownership.value > 0:
                    adjustment = round(
                        _bounded(ownership.value * ownership.confidence * 0.9, 0.9),
                        3,
                    )
                    if adjustment:
                        values.append(
                            ParticipationContextEvidence(
                                "conversation_ownership",
                                adjustment,
                                "learned_state",
                                ownership.confidence,
                            )
                        )

            if author_id:
                relationship = self.learned.get(
                    owner_id=candidate.owner_id,
                    character_card_id=candidate.character_card_id,
                    state_type="relationship",
                    subject_type="actor",
                    subject_key=f"actor:{author_id}",
                )
                if relationship is not None:
                    adjustment = round(
                        _bounded(relationship.value * relationship.confidence * 0.35, 0.35),
                        3,
                    )
                    if adjustment:
                        values.append(
                            ParticipationContextEvidence(
                                "speaker_relationship",
                                adjustment,
                                "learned_state",
                                relationship.confidence,
                            )
                        )

            fatigue = self.learned.get(
                owner_id=candidate.owner_id,
                character_card_id=candidate.character_card_id,
                state_type="participation_fatigue",
                subject_type="concept",
                subject_key=f"scope:{scope_key}",
            )
            if fatigue is not None and fatigue.value > 0:
                adjustment = round(
                    -_bounded(fatigue.value * fatigue.confidence * 1.25, 1.25),
                    3,
                )
                if adjustment:
                    values.append(
                        ParticipationContextEvidence(
                            "participation_fatigue",
                            adjustment,
                            "learned_state",
                            fatigue.confidence,
                        )
                    )

        return tuple(values)

    def rerank(
        self,
        candidates: list[ParticipationContextCandidate],
        *,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
        author_id: str,
        minimum_margin: float,
        max_participants: int,
        graph_enabled: bool,
        learned_enabled: bool,
    ) -> ParticipationContextResult:
        bounded_margin = max(0.0, float(minimum_margin))
        bounded_participants = max(1, min(int(max_participants), 3))
        rows: list[
            tuple[ParticipationContextCandidate, tuple[ParticipationContextEvidence, ...], float]
        ] = []
        for candidate in candidates:
            evidence = self._candidate_evidence(
                candidate,
                connection_id=connection_id,
                guild_id=guild_id,
                channel_id=channel_id,
                thread_id=thread_id,
                author_id=author_id,
                graph_enabled=graph_enabled,
                learned_enabled=learned_enabled,
            )
            adjustment = round(sum(item.adjustment for item in evidence), 3)
            # No contextual evidence can move an implausible candidate over its minimum.
            final_score = (
                round(candidate.base_final_score + adjustment, 3)
                if candidate.eligible and candidate.base_final_score >= candidate.minimum_score
                else candidate.base_final_score
            )
            rows.append((candidate, evidence, final_score))

        rows.sort(key=lambda item: (not item[0].eligible, -item[2], item[0].deployment_id))
        plausible = [
            item
            for item in rows
            if item[0].eligible
            and item[0].base_final_score >= item[0].minimum_score
            and item[2] >= item[0].minimum_score
        ]
        selected_ids: list[str] = []
        if plausible:
            top = plausible[0]
            selected_ids.append(top[0].deployment_id)
            for item in plausible[1:]:
                if len(selected_ids) >= bounded_participants:
                    break
                if top[2] - item[2] > bounded_margin:
                    continue
                # Secondary speakers still need a Character-specific reason. Context evidence
                # counts as such a reason because it is bounded to this Character and topic.
                semantic_or_specific = bool(item[1]) or any(
                    item[0].deterministic_signals.get(name, 0.0) > 0
                    for name in ("topic_match", "keyword_match", "trigger_phrase", "semantic_match")
                )
                if not semantic_or_specific:
                    continue
                selected_ids.append(item[0].deployment_id)

        selected = set(selected_ids)
        scores = tuple(
            ParticipationContextScore(
                deployment_id=candidate.deployment_id,
                base_final_score=candidate.base_final_score,
                contextual_adjustment=round(final_score - candidate.base_final_score, 3),
                contextual_final_score=final_score,
                selected=candidate.deployment_id in selected,
                evidence=evidence,
            )
            for candidate, evidence, final_score in rows
        )
        plan = tuple(
            ParticipationContextPlanItem(
                deployment_id=deployment_id,
                turn_role="primary" if index == 0 else "complement",
                reason="context_rerank",
            )
            for index, deployment_id in enumerate(selected_ids)
        )
        return ParticipationContextResult(
            scores=scores,
            plan=plan,
            graph_used=any(
                evidence.source == "graph" for score in scores for evidence in score.evidence
            ),
            learned_state_used=any(
                evidence.source == "learned_state"
                for score in scores
                for evidence in score.evidence
            ),
        )


__all__ = [
    "ParticipationContextCandidate",
    "ParticipationContextEvidence",
    "ParticipationContextPlanItem",
    "ParticipationContextReranker",
    "ParticipationContextResult",
    "ParticipationContextScore",
]
