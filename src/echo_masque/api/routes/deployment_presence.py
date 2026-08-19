"""Owner-scoped inspection/control for Deployment Presence and daily rhythm."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.api.deployment_presence_schemas import (
    DeploymentPresenceRhythmUpdate,
    DeploymentPresenceRhythmView,
    DeploymentPresenceUpdate,
    DeploymentPresenceView,
)
from echo_masque.deployment_presence_rhythm import DeploymentPresenceRhythmService
from echo_masque.deployment_presence_rhythm import (
    DeploymentPresenceRhythmView as RhythmDomainView,
)
from echo_masque.persistence import DeploymentPresenceRepository
from echo_masque.persistence.deployment_presence_repository import (
    DeploymentPresenceView as PresenceDomainView,
)

router = APIRouter(tags=["deployments"])


def repository(request: Request) -> DeploymentPresenceRepository:
    return DeploymentPresenceRepository(request.app.state.database)


def rhythm_service(request: Request) -> DeploymentPresenceRhythmService:
    return DeploymentPresenceRhythmService(request.app.state.database)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def _view(value: PresenceDomainView) -> DeploymentPresenceView:
    started_at = _as_utc(value.started_at)
    updated_at = _as_utc(value.updated_at)
    if started_at is None or updated_at is None:
        raise RuntimeError("Presence timestamps are required.")
    return DeploymentPresenceView(
        deployment_id=value.deployment_id,
        state=value.state,
        activity_type=value.activity_type,
        source=value.source,
        reason=value.reason,
        version=value.version,
        started_at=started_at,
        expected_end_at=_as_utc(value.expected_end_at),
        updated_at=updated_at,
        persisted=value.persisted,
        available_for_character_runtime=value.available_for_character_runtime,
        discovery_allowed=value.discovery_allowed,
    )


def _rhythm_view(value: RhythmDomainView) -> DeploymentPresenceRhythmView:
    return DeploymentPresenceRhythmView(
        deployment_id=value.deployment_id,
        enabled=value.enabled,
        preferred_sleep_start_minute=value.preferred_sleep_start_minute,
        sleep_duration_min_minutes=value.sleep_duration_min_minutes,
        sleep_duration_max_minutes=value.sleep_duration_max_minutes,
        variation_minutes=value.variation_minutes,
        config_version=value.config_version,
        schedule_local_date=value.schedule_local_date,
        schedule_timezone=value.schedule_timezone,
        scheduled_sleep_at=_as_utc(value.scheduled_sleep_at),
        scheduled_wake_at=_as_utc(value.scheduled_wake_at),
        next_transition_at=_as_utc(value.next_transition_at),
        next_state=value.next_state,
        last_transition_at=_as_utc(value.last_transition_at),
        last_transition_reason=value.last_transition_reason,
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


@router.get(
    "/deployments/{deployment_id}/presence/rhythm",
    response_model=DeploymentPresenceRhythmView,
)
def get_presence_rhythm(
    deployment_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> DeploymentPresenceRhythmView:
    current = rhythm_service(request).get(owner_id=user.id, deployment_id=deployment_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Deployment not found.")
    return _rhythm_view(current)


@router.put(
    "/deployments/{deployment_id}/presence/rhythm",
    response_model=DeploymentPresenceRhythmView,
)
def update_presence_rhythm(
    deployment_id: str,
    payload: DeploymentPresenceRhythmUpdate,
    request: Request,
    user: CurrentUserDependency,
) -> DeploymentPresenceRhythmView:
    try:
        current = rhythm_service(request).configure(
            owner_id=user.id,
            deployment_id=deployment_id,
            enabled=payload.enabled,
            preferred_sleep_start_minute=payload.preferred_sleep_start_minute,
            sleep_duration_min_minutes=payload.sleep_duration_min_minutes,
            sleep_duration_max_minutes=payload.sleep_duration_max_minutes,
            variation_minutes=payload.variation_minutes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if current is None:
        raise HTTPException(status_code=404, detail="Deployment not found.")
    return _rhythm_view(current)


__all__ = ["router"]
