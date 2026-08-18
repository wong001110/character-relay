"""Owner-scoped manual inspection/control for Deployment Presence."""

from fastapi import APIRouter, HTTPException, Request

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.api.deployment_presence_schemas import (
    DeploymentPresenceUpdate,
    DeploymentPresenceView,
)
from echo_masque.persistence import DeploymentPresenceRepository
from echo_masque.persistence.deployment_presence_repository import (
    DeploymentPresenceView as PresenceDomainView,
)

router = APIRouter(tags=["deployments"])


def repository(request: Request) -> DeploymentPresenceRepository:
    return DeploymentPresenceRepository(request.app.state.database)


def _view(value: PresenceDomainView) -> DeploymentPresenceView:
    return DeploymentPresenceView(
        deployment_id=value.deployment_id,
        state=value.state,
        activity_type=value.activity_type,
        source=value.source,
        reason=value.reason,
        version=value.version,
        started_at=value.started_at,
        expected_end_at=value.expected_end_at,
        updated_at=value.updated_at,
        persisted=value.persisted,
        available_for_character_runtime=value.available_for_character_runtime,
        discovery_allowed=value.discovery_allowed,
    )


@router.get("/deployments/{deployment_id}/presence", response_model=DeploymentPresenceView)
def get_presence(
    deployment_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> DeploymentPresenceView:
    current = repository(request).get(owner_id=user.id, deployment_id=deployment_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Deployment not found.")
    return _view(current)


@router.put("/deployments/{deployment_id}/presence", response_model=DeploymentPresenceView)
def update_presence(
    deployment_id: str,
    payload: DeploymentPresenceUpdate,
    request: Request,
    user: CurrentUserDependency,
) -> DeploymentPresenceView:
    try:
        current = repository(request).set_state(
            owner_id=user.id,
            deployment_id=deployment_id,
            state=payload.state,
            activity_type=payload.activity_type,
            source="manual",
            reason=payload.reason,
            expected_end_at=payload.expected_end_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if current is None:
        raise HTTPException(status_code=404, detail="Deployment not found.")
    return _view(current)


__all__ = ["router"]
