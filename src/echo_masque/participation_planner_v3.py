"""Unified Participation Planner v3 with explicit media epistemic grounding."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from echo_masque.api.smart_participation_v3_schemas import (
    SmartParticipationMediaDescriptor,
    SmartParticipationResolveCandidate,
    SmartParticipationResolveRequest,
)
from echo_masque.context_resolver_v3 import ContextBundleV3
from echo_masque.conversation_reply_planner import CharacterSegmentReplyPlanner
from echo_masque.persistence.conversation_structure_repository import (
    ConversationSegmentView,
)
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord

GroundingLevel = Literal["context_only", "preview_grounded", "content_grounded"]

_CONTENT_STATES = {
    "analyzed",
    "complete",
    "content_grounded",
    "ready",
    "resolved",
    "understood",
}
_PREVIEW_STATES = {
    "metadata",
    "partial",
    "preview",
    "preview_only",
    "preview_grounded",
    "thumbnail",
}


class CandidateViewLike(Protocol):
    deployment_id: str
    eligible: bool
    deterministic_score: float
    minimum_score: float
    semantic_points: float
    final_evidence_score: float
    raw_e5_relevance: float


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
                    (
                        "The current turn requires media understanding, but no grounded media "
                        "content is available. Do not pretend to have seen or inspected it."
                    ),
                    (),
                )
            return MediaGroundingDecision(
                "context_only",
                True,
                "no_media_dependency",
                "Use only conversation context; do not imply unseen media perception.",
                (),
            )
        content = tuple(
            item for item in descriptors if self._state(item) in _CONTENT_STATES
        )
        if content:
            refs = tuple(dict.fromkeys(item.ref for item in content if item.ref))
            return MediaGroundingDecision(
                "content_grounded",
                True,
                "media_content_available",
                (
                    "Media content has been explicitly perceived by the media-understanding path. "
                    "You may discuss only details present in the supplied grounded media context."
                ),
                refs,
            )
        preview = tuple(
            item for item in descriptors if self._state(item) in _PREVIEW_STATES
        )
        if preview:
            refs = tuple(dict.fromkeys(item.ref for item in preview if item.ref))
            required = payload.media_dependency == "required"
            reason = (
                "required_media_preview_insufficient"
                if required
                else "media_preview_only"
            )
            return MediaGroundingDecision(
                "preview_grounded",
                not required,
                reason,
                (
                    "Only preview/metadata grounding is available. You may mention metadata that "
                    "was supplied, but do not claim visual/audio content perception."
                ),
                refs,
            )
        if payload.media_dependency == "required":
            return MediaGroundingDecision(
                "context_only",
                False,
                "required_media_not_grounded",
                (
                    "Required media content is not grounded. Prefer silence or a clarification "
                    "request."
                ),
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
    """Choose speakers and primary Segments using runtime evidence."""

    def __init__(
        self,
        segment_planner: CharacterSegmentReplyPlanner,
        *,
        media_contract: MediaEpistemicContract | None = None,
    ) -> None:
        self.segment_planner = segment_planner
        self.media_contract = media_contract or MediaEpistemicContract()

    @staticmethod
    def _score(
        candidate: CandidateViewLike,
        requested: SmartParticipationResolveCandidate,
    ) -> float:
        deterministic = float(candidate.deterministic_score)
        semantic = max(0.0, float(candidate.semantic_points))
        evidence = max(0.0, float(candidate.final_evidence_score))
        relationship = max(0.0, requested.relationship_signal)
        behavior = max(0.0, requested.behavior_signal)
        directness = max(0.0, requested.directness_signal)
        ownership = max(0.0, requested.conversation_ownership_signal)
        fatigue = max(0.0, requested.participation_fatigue)
        return max(
            0.0,
            min(
                1.5,
                deterministic * 0.34
                + semantic * 0.24
                + evidence * 0.18
                + relationship * 0.08
                + behavior * 0.05
                + directness * 0.08
                + ownership * 0.05
                - fatigue * 0.10,
            ),
        )

    def plan(
        self,
        *,
        payload: SmartParticipationResolveRequest,
        candidates: tuple[CandidateViewLike, ...],
        deployments: dict[str, CharacterDeploymentRecord],
        segments: tuple[ConversationSegmentView, ...],
        context: ContextBundleV3 | None,
    ) -> ParticipationPlanV3:
        grounding = self.media_contract.resolve(payload)
        if not grounding.can_reply:
            return ParticipationPlanV3(
                speakers=(),
                candidates=tuple(item.deployment_id for item in candidates),
                grounding=grounding,
                reason=grounding.reason,
            )
        requested = {item.deployment_id: item for item in payload.candidates}
        scored = [
            (self._score(item, requested[item.deployment_id]), item)
            for item in candidates
            if (
                item.eligible
                and item.deployment_id in deployments
                and item.deployment_id in requested
            )
        ]
        scored.sort(key=lambda item: (-item[0], item[1].deployment_id))
        selected: list[ParticipationPlanItemV3] = []
        for score, candidate in scored[:3]:
            deployment = deployments[candidate.deployment_id]
            threshold = max(0.0, float(candidate.minimum_score))
            if score < threshold:
                continue
            chosen = self.segment_planner.choose_for_character(
                deployment=deployment,
                segments=segments,
                current_message=payload.message,
            )
            if chosen is None:
                continue
            guidance_parts: list[str] = []
            requested_item = requested[candidate.deployment_id]
            if requested_item.participation_guidance.strip():
                guidance_parts.append(requested_item.participation_guidance.strip())
            if context is not None and context.social_context:
                guidance_parts.append(context.social_context[:600])
            if grounding.guidance:
                guidance_parts.append(grounding.guidance)
            selected.append(
                ParticipationPlanItemV3(
                    deployment_id=candidate.deployment_id,
                    segment_id=chosen.segment_id,
                    conversation_thread_id=chosen.thread_id,
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
