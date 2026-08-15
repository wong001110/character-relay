"""Connector-only planner media descriptor endpoint."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Header, Request

from echo_masque.api.routes.connectors import _authorize_connector
from echo_masque.media_planning import (
    MediaPlanningDescriptor,
    MediaPlanningDescriptorService,
    MediaPlanningRequest,
)

router = APIRouter()


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
    service = cast(
        MediaPlanningDescriptorService,
        request.app.state.media_planning_descriptor_service,
    )
    return await service.describe(payload)


__all__ = ["router"]
