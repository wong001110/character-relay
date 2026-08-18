"""Burst segmentation + Segment Reply Planner wrapper around Smart Participation V4.

The wrapper composes the validated V4 admission authority. It adds non-exclusive Semantic Thread
evidence and chooses one primary Segment for each admitted Character without rewriting V4.
"""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Header, Request

from echo_masque.api.routes.smart_participation_v4 import resolve_smart_participation_v4
from echo_masque.api.smart_participation_v4_schemas import (
    SmartParticipationResolveRequest,
    SmartParticipationSpeakerPlanItem,
)
from echo_masque.api.smart_participation_vnext_schemas import (
    ConversationSegmentRouteView,
    ReplyTargetRouteView,
    SmartParticipationResolveVNextView,
)
from echo_masque.config import Settings
from echo_masque.conversation_reply_planner import CharacterSegmentReplyPlanner
from echo_masque.conversation_segmentation import ConversationSegmentationService
from echo_masque.persistence import DeploymentRepository, Repository
from echo_masque.persistence.conversation_segment_repository import ConversationSegmentRepository
from echo_masque.semantic_participation import CharacterParticipationSemanticService
from echo_masque.services.runtime import RuntimeService
from echo_masque.utility_gateway_live import ExistingProviderUtilityCaller
from echo_masque.utility_gateway_router import UtilityGatewayRouter

router = APIRouter()


def _service(request: Request) -> ConversationSegmentationService:
    current = getattr(request.app.state, "conversation_segmentation_vnext", None)
    if isinstance(current, ConversationSegmentationService):
        return current
    database = cast(DeploymentRepository, request.app.state.deployment_repository).database
    runtime = getattr(request.app.state, "runtime_service", None)
    if not isinstance(runtime, RuntimeService):
        runtime = RuntimeService(
            cast(Repository, request.app.state.repository),
            cast(Settings, request.app.state.settings),
        )
    service = ConversationSegmentationService(
        ConversationSegmentRepository(database),
        cast(Settings, request.app.state.settings),
        UtilityGatewayRouter(runtime, caller=ExistingProviderUtilityCaller()),
    )
    request.app.state.conversation_segmentation_vnext = service
    return service


def _reply_planner(request: Request) -> CharacterSegmentReplyPlanner:
    current = getattr(request.app.state, "character_segment_reply_planner_vnext", None)
    if isinstance(current, CharacterSegmentReplyPlanner):
        return current
    planner = CharacterSegmentReplyPlanner(
        cast(CharacterParticipationSemanticService, request.app.state.semantic_participation_service)
    )
    request.app.state.character_segment_reply_planner_vnext = planner
    return planner


def _records_for_payload(payload: SmartParticipationResolveRequest, request: Request):
    records = cast(DeploymentRepository, request.app.state.deployment_repository).list_connector_deployments(
        platform="discord",
        connection_id=payload.connection_id,
    )
    requested = {item.deployment_id for item in payload.candidates}
    return [item for item in records if item.id in requested]


def _base_result(base: object, *, source: str) -> SmartParticipationResolveVNextView:
    dumped = base.model_dump()  # type: ignore[attr-defined]
    return SmartParticipationResolveVNextView.model_validate(
        {
            **dumped,
            "resolver_version": "conversation-intelligence-vnext",
            "segmentation_used": False,
            "segmentation_source": source,
            "conversation_segments": [],
            "reply_targets": [],
        }
    )


@router.post(
    "/resolve",
    response_model=SmartParticipationResolveVNextView,
)
def resolve_smart_participation_vnext(
    payload: SmartParticipationResolveRequest,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> SmartParticipationResolveVNextView:
    """Keep V4 admission authority and layer Burst segmentation / primary Segment targeting."""

    base = resolve_smart_participation_v4(payload, request, authorization)
    records = _records_for_payload(payload, request)
    if not records:
        return _base_result(base, source="no_owner")
    owner_id = records[0].owner_id
    try:
        result = _service(request).resolve(payload=payload, owner_id=owner_id)
    except Exception:
        # Migration layer: never turn a segmentation defect into a duplicate/failed Discord turn.
        return _base_result(base, source="segmentation_failed")

    segment_views = [
        ConversationSegmentRouteView(
            id=item.id,
            message_ids=list(item.message_ids),
            participant_ids=list(item.participant_ids),
            kind=item.kind,
            summary=item.summary,
            semantic_thread_id=item.semantic_thread_id,
            thread_action=item.thread_action,
            thread_evidence=item.thread_evidence,
            confidence=item.confidence,
            source=item.source,
        )
        for item in result.segments
    ]
    record_by_id = {item.id: item for item in records}
    request_candidate_by_id = {item.deployment_id: item for item in payload.candidates}
    reply_targets: list[ReplyTargetRouteView] = []
    guidance_by_id: dict[str, str] = {}
    planner = _reply_planner(request)
    planned_ids = {
        item.deployment_id for item in base.speaker_plan
    } or {
        item.deployment_id for item in base.shadow_speaker_plan
    }
    for deployment_id in planned_ids:
        deployment = record_by_id.get(deployment_id)
        requested = request_candidate_by_id.get(deployment_id)
        if deployment is None or requested is None:
            continue
        target = planner.select(
            deployment=deployment,
            segments=result.segments,
            latest_message_id=payload.message_id,
            deterministic_signals=dict(requested.signals),
        )
        if target is None:
            continue
        reply_targets.append(
            ReplyTargetRouteView(
                deployment_id=target.deployment_id,
                segment_id=target.segment_id,
                semantic_thread_id=target.semantic_thread_id,
                score=target.score,
                reason=target.reason,
            )
        )
        guidance_by_id[deployment_id] = target.guidance

    def guided(items: list[SmartParticipationSpeakerPlanItem]) -> list[SmartParticipationSpeakerPlanItem]:
        values: list[SmartParticipationSpeakerPlanItem] = []
        for item in items:
            segment_guidance = guidance_by_id.get(item.deployment_id, "")
            combined = " ".join(
                value.strip() for value in (item.guidance, segment_guidance) if value.strip()
            )[:240]
            values.append(item.model_copy(update={"guidance": combined}))
        return values

    speaker_plan = guided(base.speaker_plan)
    shadow_plan = guided(base.shadow_speaker_plan)
    planner_shadow = guided(base.conversation_planner_shadow_plan)
    return SmartParticipationResolveVNextView.model_validate(
        {
            **base.model_dump(),
            "resolver_version": "conversation-intelligence-vnext",
            "segmentation_used": bool(segment_views),
            "segmentation_source": result.source,
            "conversation_segments": [item.model_dump() for item in segment_views],
            "reply_targets": [item.model_dump() for item in reply_targets],
            "speaker_plan": [item.model_dump() for item in speaker_plan],
            "shadow_speaker_plan": [item.model_dump() for item in shadow_plan],
            "conversation_planner_shadow_plan": [item.model_dump() for item in planner_shadow],
            "utility_used": bool(base.utility_used or result.utility_used),
        }
    )


__all__ = ["router"]
