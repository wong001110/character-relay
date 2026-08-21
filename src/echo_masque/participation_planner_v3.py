"""Unified Participation Planner v3 with Segment targeting and media epistemic grounding."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from echo_masque.api.smart_participation_v3_schemas import (
    SmartParticipationMediaDescriptor,
    SmartParticipationResolveCandidate,
    SmartParticipationResolveCandidateView,
    SmartParticipationResolveRequest,
)
from echo_masque.context_resolver_v3 import ContextBundleV3
from echo_masque.persistence.conversation_structure_repository import ConversationSegmentView
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.semantic_participation import (
    CharacterParticipationSemanticService,
    SemanticEmbeddingUnavailable,
)

GroundingLevel = Literal["context_only", "preview_grounded", "content_grounded"]

_CONTENT_STATES = {"analyzed", "complete", "content_grounded", "ready", "resolved", "understood"}
_PREVIEW_STATES = {
    "metadata",
    "partial",
    "preview",
    "preview_only",
    "preview_grounded",
    "thumbnail",
}


@dataclass(frozen=True, slots=True)
class MediaGroundingDecision:
    level: GroundingLevel
    can_reply: bool
    reason: str
    guidance: str
    grounded_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ParticipationPlanItemV3:
    deployment_id: str
    segment_id: str
    conversation_thread_id: str
    score: float
    reason: str
    guidance: str
    grounding: GroundingLevel


@dataclass(frozen=True, slots=True)
class ParticipationPlanV3:
    speakers: tuple[ParticipationPlanItemV3, ...]
    candidates: tuple[str, ...]
    grounding: MediaGroundingDecision
    reason: str


@dataclass(frozen=True, slots=True)
class _SegmentTarget:
    segment_id: str
    conversation_thread_id: str
    guidance: str


class MediaEpistemicContract:
    """Prevent planner-only media knowledge from becoming Character perception."""

    @staticmethod
    def _state(descriptor: SmartParticipationMediaDescriptor) -> str:
        return descriptor.state.strip().casefold()

    def resolve(self, payload: SmartParticipationResolveRequest) -> MediaGroundingDecision:
        descriptors = tuple(payload.media_descriptors)
        if not descriptors:
            if payload.media_dependency == "required":
                return MediaGroundingDecision(
                    "context_only",
                    False,
                    "required_media_missing",
                    "The current turn requires media understanding, but no grounded "
                    "media content is available. Do not pretend to have seen or "
                    "inspected it.",
                    (),
                )
            return MediaGroundingDecision(
                "context_only",
                True,
                "no_media_dependency",
                "Use only conversation context; do not imply unseen media perception.",
                (),
            )
        content = tuple(item for item in descriptors if self._state(item) in _CONTENT_STATES)
        if content:
            return MediaGroundingDecision(
                "content_grounded",
                True,
                "media_content_available",
                "Media content has been explicitly perceived by the media-understanding "
                "path. You may discuss only details present in the supplied grounded "
                "media context.",
                tuple(dict.fromkeys(item.ref for item in content if item.ref)),
            )
        preview = tuple(item for item in descriptors if self._state(item) in _PREVIEW_STATES)
        if preview:
            required = payload.media_dependency == "required"
            return MediaGroundingDecision(
                "preview_grounded",
                not required,
                "required_media_preview_insufficient" if required else "media_preview_only",
                "Only preview/metadata grounding is available. Mention only supplied "
                "metadata; do not infer unseen visual/audio content or extrapolate "
                "from prior related knowledge.",
                tuple(dict.fromkeys(item.ref for item in preview if item.ref)),
            )
        if payload.media_dependency == "required":
            return MediaGroundingDecision(
                "context_only",
                False,
                "required_media_not_grounded",
                "Required media content is not grounded. Prefer silence or a "
                "clarification request.",
                (),
            )
        return MediaGroundingDecision(
            "context_only",
            True,
            "media_descriptor_unusable",
            "Do not infer media contents from hidden planner metadata.",
            (),
        )


class ParticipationPlannerV3:
    """Own final speaker admission, primary Segment selection, and reply grounding."""

    def __init__(
        self,
        semantic: CharacterParticipationSemanticService,
        *,
        media_contract: MediaEpistemicContract | None = None,
    ) -> None:
        self.semantic = semantic
        self.media_contract = media_contract or MediaEpistemicContract()

    @staticmethod
    def _bounded_signal(requested: SmartParticipationResolveCandidate, key: str) -> float:
        return max(0.0, min(1.0, float(requested.signals.get(key, 0.0))))

    @classmethod
    def _score(
        cls,
        candidate: SmartParticipationResolveCandidateView,
        requested: SmartParticipationResolveCandidate,
    ) -> float:
        score = float(candidate.final_evidence_score)
        score += cls._bounded_signal(requested, "relationship")
        score += cls._bounded_signal(requested, "behavior") * 0.5
        score += cls._bounded_signal(requested, "conversation_ownership") * 0.5
        score -= cls._bounded_signal(requested, "participation_fatigue")
        return max(0.0, score)

    @staticmethod
    def _direct_pressure(signals: dict[str, float]) -> float:
        return max(
            float(signals.get("name_match", 0.0)),
            float(signals.get("recent_turn_match", 0.0)),
            float(signals.get("lightweight_follow_up", 0.0)),
            float(signals.get("trigger_phrase", 0.0)),
        )

    def _select_segment(
        self,
        *,
        deployment: CharacterDeploymentRecord,
        segments: tuple[ConversationSegmentView, ...],
        latest_message_id: str,
        deterministic_signals: dict[str, float],
    ) -> _SegmentTarget | None:
        if not segments:
            return None
        direct_pressure = self._direct_pressure(deterministic_signals)
        direct_segments = (
            tuple(
                segment
                for segment in segments
                if latest_message_id and latest_message_id in segment.message_ids
            )
            if direct_pressure > 0
            else ()
        )
        candidates = direct_segments or segments
        scores: list[tuple[float, ConversationSegmentView]] = []
        for segment in candidates:
            score = 0.05 if segment.kind in {"reaction", "side_comment"} else 0.20
            if direct_segments:
                score += min(0.55, direct_pressure / 10.0)
            if segment.summary.strip() and self.semantic.enabled:
                try:
                    _, _, semantic_scores = self.semantic.score(
                        message=segment.summary,
                        deployments=[
                            (deployment.id, deployment.owner_id, deployment.character_card_id)
                        ],
                    )
                    if semantic_scores and semantic_scores[0].profile_ready:
                        score += max(0.0, semantic_scores[0].relevance)
                except (SemanticEmbeddingUnavailable, KeyError, ValueError, RuntimeError):
                    pass
            if segment.thread_evidence:
                score += 0.05
            scores.append((score, segment))
        scores.sort(key=lambda item: item[0], reverse=True)
        value, selected = scores[0]
        if value < 0.12:
            return None
        summary = " ".join(selected.summary.split())[:150]
        return _SegmentTarget(
            segment_id=selected.id,
            conversation_thread_id=selected.thread_id,
            guidance=(
                f"Focus this turn on the selected conversation segment: {summary}. "
                "Do not summarize or answer unrelated simultaneous discussions in the Burst."
            )[:300],
        )

    def plan(
        self,
        *,
        payload: SmartParticipationResolveRequest,
        deployments: tuple[CharacterDeploymentRecord, ...],
        candidate_views: tuple[SmartParticipationResolveCandidateView, ...],
        segments: tuple[ConversationSegmentView, ...],
        context_by_deployment: dict[str, ContextBundleV3],
    ) -> ParticipationPlanV3:
        grounding = self.media_contract.resolve(payload)
        if not grounding.can_reply:
            return ParticipationPlanV3(
                speakers=(),
                candidates=tuple(item.deployment_id for item in candidate_views),
                grounding=grounding,
                reason=grounding.reason,
            )
        requested = {item.deployment_id: item for item in payload.candidates}
        deployments_by_id = {item.id: item for item in deployments}
        scored = [
            (self._score(item, requested[item.deployment_id]), item)
            for item in candidate_views
            if item.eligible
            and item.deployment_id in deployments_by_id
            and item.deployment_id in requested
        ]
        scored.sort(key=lambda item: (-item[0], item[1].deployment_id))
        selected: list[ParticipationPlanItemV3] = []
        for score, candidate in scored[: payload.max_participants]:
            deployment = deployments_by_id[candidate.deployment_id]
            requested_item = requested[candidate.deployment_id]
            if score < max(0.0, float(candidate.minimum_score)):
                continue
            chosen = self._select_segment(
                deployment=deployment,
                segments=segments,
                latest_message_id=payload.message_id,
                deterministic_signals=dict(requested_item.signals),
            )
            if chosen is None:
                continue
            guidance_parts = [chosen.guidance]
            context = context_by_deployment.get(candidate.deployment_id)
            if context is not None and context.social_context:
                guidance_parts.append(" ".join(context.social_context)[:600])
            if grounding.guidance:
                guidance_parts.append(grounding.guidance)
            selected.append(
                ParticipationPlanItemV3(
                    deployment_id=candidate.deployment_id,
                    segment_id=chosen.segment_id,
                    conversation_thread_id=chosen.conversation_thread_id,
                    score=round(score, 6),
                    reason="v3_evidence_score",
                    guidance=" ".join(guidance_parts)[:1400],
                    grounding=grounding.level,
                )
            )
        return ParticipationPlanV3(
            speakers=tuple(selected),
            candidates=tuple(item.deployment_id for _, item in scored),
            grounding=grounding,
            reason="v3_participation_plan" if selected else "no_candidate_met_threshold",
        )


__all__ = [
    "GroundingLevel",
    "MediaEpistemicContract",
    "MediaGroundingDecision",
    "ParticipationPlanItemV3",
    "ParticipationPlanV3",
    "ParticipationPlannerV3",
]
