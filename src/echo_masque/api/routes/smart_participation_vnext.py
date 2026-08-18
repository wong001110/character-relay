"""Burst segmentation wrapper around the validated Smart Participation V4 resolver.

This route intentionally composes the existing V4 authority instead of rewriting it in one pass.
It adds non-exclusive Semantic Thread evidence while preserving the current admission decision.
"""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Header, Request

from echo_masque.api.routes.smart_participation_v4 import resolve_smart_participation_v4
from echo_masque.api.smart_participation_v4_schemas import SmartParticipationResolveRequest
from echo_masque.api.smart_participation_vnext_schemas import (
    ConversationSegmentRouteView,
    SmartParticipationResolveVNextView,
)
from echo_masque.config import Settings
from echo_masque.conversation_segmentation import ConversationSegmentationService
from echo_masque.persistence import DeploymentRepository, Repository
from echo_masque.persistence.conversation_segment_repository import ConversationSegmentRepository
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


def _owner_for_payload(payload: SmartParticipationResolveRequest, request: Request) -> str:
    records = cast(DeploymentRepository, request.app.state.deployment_repository).list_connector_deployments(
        platform="discord",
        connection_id=payload.connection_id,
    )
    requested = {item.deployment_id for item in payload.candidates}
    for record in records:
        if record.id in requested:
            return record.owner_id
    return ""


@router.post(
    "/resolve",
    response_model=SmartParticipationResolveVNextView,
)
def resolve_smart_participation_vnext(
    payload: SmartParticipationResolveRequest,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> SmartParticipationResolveVNextView:
    """Preserve V4 admission authority and add one reusable Burst segmentation projection."""

    base = resolve_smart_participation_v4(payload, request, authorization)
    owner_id = _owner_for_payload(payload, request)
    if not owner_id:
        return SmartParticipationResolveVNextView.model_validate(
            {
                **base.model_dump(),
                "resolver_version": "conversation-intelligence-vnext",
                "segmentation_used": False,
                "segmentation_source": "no_owner",
                "conversation_segments": [],
            }
        )
    try:
        result = _service(request).resolve(payload=payload, owner_id=owner_id)
    except Exception:
        # Segmentation is a migration layer. Existing V4 admission must continue even if the
        # new projection fails; owner observability/tests can inspect the missing evidence.
        return SmartParticipationResolveVNextView.model_validate(
            {
                **base.model_dump(),
                "resolver_version": "conversation-intelligence-vnext",
                "segmentation_used": False,
                "segmentation_source": "segmentation_failed",
                "conversation_segments": [],
            }
        )

    segments = [
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
    return SmartParticipationResolveVNextView.model_validate(
        {
            **base.model_dump(),
            "resolver_version": "conversation-intelligence-vnext",
            "segmentation_used": bool(segments),
            "segmentation_source": result.source,
            "conversation_segments": [item.model_dump() for item in segments],
            "utility_used": bool(base.utility_used or result.utility_used),
        }
    )


__all__ = ["router"]
