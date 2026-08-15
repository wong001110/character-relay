"""Connector-only planner media descriptor endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, Request

from echo_masque.api.routes.connectors import _authorize_connector
from echo_masque.media_planning import (
    MediaPlanningDescriptor,
    MediaPlanningDescriptorService,
    MediaPlanningRequest,
)

router = APIRouter()


def _service(request: Request) -> MediaPlanningDescriptorService:
    current = getattr(request.app.state, "media_planning_descriptor_service", None)
    if isinstance(current, MediaPlanningDescriptorService):
        return current
    service = MediaPlanningDescriptorService()
    request.app.state.media_planning_descriptor_service = service
    return service


@router.post(
    "/media/planning-descriptor",
    response_model=MediaPlanningDescriptor,
)
async def media_planning_descriptor(
    payload: MediaPlanningRequest,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> MediaPlanningDescriptor:
    """Return objective routing evidence without granting Character perception."""

    _authorize_connector(request, authorization)
    return await _service(request).describe(payload)


__all__ = ["router"]
