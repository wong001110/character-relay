"""Unified Participation Planner v3 with explicit media epistemic grounding."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from echo_masque.api.smart_participation_v4_schemas import (
    SmartParticipationMediaDescriptor,
    SmartParticipationResolveCandidate,
    SmartParticipationResolveCandidateView,
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
    "preview_grounded",
    "thumbnail",
}


class CandidateViewLike(Protocol):
    deployment_id: str
    eligible: bool
    deterministic_score: float
    minimum_score: float
    semantic_points: float
    shadow_final_score: float
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
        # V4 semantic/deterministic computations are evidence inputs only. The v3 planner owns the
        # final admission decision and does not inherit V4's speaker-plan authority.
        deterministic = float(candidate.deterministic_score)
        semantic = max(0.0, float(candidate.semantic_points))
        raw = max(0.0, float(candidate.raw_e5_relevance))
        direct = max(
            float(requested.signals.get("name_match", 0.0)),
            float(requested.signals.get("recent_turn_match", 0.0)),
            float(requested.signals.get("lightweight_follow_up", 0.0)),
            float(requested.signals.get("trigger_phrase", 0.0)),
        )
        return deterministic + semantic + raw * 2.0 + min(4.0, direct)

    def plan(
        self,
        *,
        payload: SmartParticipationResolveRequest,
        deployments: tuple[CharacterDeploymentRecord, ...],
        candidate_views: tuple[SmartParticipationResolveCandidateView, ...],
        segments: tuple[ConversationSegmentView, ...],
        context_by_deployment: dict[str, ContextBundleV3] | None = None,
    ) -> ParticipationPlanV3:
        grounding = self.media_contract.resolve(payload)
        if not grounding.can_reply:
            return ParticipationPlanV3(
                speakers=(),
                candidates=tuple(
                    item.deployment_id for item in candidate_views if item.eligible
                ),
                grounding=grounding,
                reason=grounding.reason,
            )
        deployment_by_id = {item.id: item for item in deployments}
        requested_by_id = {item.deployment_id: item for item in payload.candidates}
        view_by_id = {item.deployment_id: item for item in candidate_views}
        ranked: list[tuple[float, str]] = []
        for deployment_id, view in view_by_id.items():
            requested = requested_by_id.get(deployment_id)
            deployment = deployment_by_id.get(deployment_id)
            if (
                requested is None
                or deployment is None
                or not view.eligible
                or not requested.eligible
            ):
                continue
            context = (context_by_deployment or {}).get(deployment_id)
            if context is not None and context.sufficiency == "unresolved":
                continue
            score = self._score(view, requested)
            if score < float(view.minimum_score):
                continue
            ranked.append((score, deployment_id))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        if not ranked:
            return ParticipationPlanV3(
                speakers=(),
                candidates=tuple(item[1] for item in ranked),
                grounding=grounding,
                reason="no_candidate_cleared_admission",
            )
        max_speakers = min(payload.max_participants, len(ranked))
        if len(ranked) > 1 and not payload.admission_group_invitation:
            margin = ranked[0][0] - ranked[1][0]
            if margin < payload.minimum_margin:
                max_speakers = 1
        selected = ranked[:max_speakers]
        items: list[ParticipationPlanItemV3] = []
        for score, deployment_id in selected:
            deployment = deployment_by_id[deployment_id]
            requested = requested_by_id[deployment_id]
            target = self.segment_planner.select(
                deployment=deployment,
                segments=segments,
                latest_message_id=payload.message_id,
                deterministic_signals=dict(requested.signals),
            )
            if target is None:
                continue
            context = (context_by_deployment or {}).get(deployment_id)
            context_guidance = ""
            if context is not None:
                if context.sufficiency == "external_lookup_needed":
                    context_guidance = (
                        "Relevant knowledge is missing. Do not invent it; respond from the local "
                        "conversation only or acknowledge uncertainty."
                    )
                elif context.sufficiency == "insufficient_nonblocking":
                    context_guidance = (
                        "Keep the reply lightweight; little durable context is needed."
                    )
            guidance = " ".join(
                item
                for item in (target.guidance, grounding.guidance, context_guidance)
                if item
            )[:600]
            items.append(
                ParticipationPlanItemV3(
                    deployment_id=deployment_id,
                    segment_id=target.segment_id,
                    conversation_thread_id=target.semantic_thread_id,
                    score=round(score, 6),
                    reason=target.reason,
                    guidance=guidance,
                    grounding=grounding.level,
                )
            )
        return ParticipationPlanV3(
            speakers=tuple(items),
            candidates=tuple(item[1] for item in ranked),
            grounding=grounding,
            reason="planned" if items else "no_segment_target",
        )


__all__ = [
    "GroundingLevel",
    "MediaEpistemicContract",
    "MediaGroundingDecision",
    "ParticipationPlanItemV3",
    "ParticipationPlanV3",
    "ParticipationPlannerV3",
]
