"""Owner-scoped controls and observability for Deployment Character Discovery."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query, Request

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.api.deployment_discovery_schemas import (
    DeploymentDiscoveryDecisionListView,
    DeploymentDiscoveryDecisionView,
    DeploymentDiscoveryExposureListView,
    DeploymentDiscoveryExposureView,
    DeploymentDiscoveryProfileUpdate,
    DeploymentDiscoveryProfileView,
    DiscoveryItemView,
)
from echo_masque.discovery_contracts import DiscoveryMode
from echo_masque.persistence.discovery_models import DiscoveryItemRecord
from echo_masque.persistence.discovery_repository import DiscoveryRepository

router = APIRouter(tags=["deployments"])


def repository(request: Request) -> DiscoveryRepository:
    return DiscoveryRepository(request.app.state.database)


def _item(record: DiscoveryItemRecord) -> DiscoveryItemView:
    return DiscoveryItemView(
        id=record.id,
        source=record.source,
        canonical_key=record.canonical_key,
        content_kind=record.content_kind,
        title=record.title,
        creator=record.creator,
        url=record.url,
        thumbnail_url=record.thumbnail_url,
        published_at=record.published_at,
    )


def _json_object(raw: str) -> dict[str, object]:
    try:
        decoded = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


@router.get(
    "/deployments/{deployment_id}/discovery/profile",
    response_model=DeploymentDiscoveryProfileView,
)
def get_discovery_profile(
    deployment_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> DeploymentDiscoveryProfileView:
    current = repository(request).get_profile(owner_id=user.id, deployment_id=deployment_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Deployment not found.")
    return DeploymentDiscoveryProfileView(
        deployment_id=current.deployment_id,
        mode=current.mode.value,
        youtube_enabled=current.youtube_enabled,
        bilibili_enabled=current.bilibili_enabled,
    )


@router.put(
    "/deployments/{deployment_id}/discovery/profile",
    response_model=DeploymentDiscoveryProfileView,
)
def update_discovery_profile(
    deployment_id: str,
    payload: DeploymentDiscoveryProfileUpdate,
    request: Request,
    user: CurrentUserDependency,
) -> DeploymentDiscoveryProfileView:
    current = repository(request).set_profile(
        owner_id=user.id,
        deployment_id=deployment_id,
        mode=DiscoveryMode(payload.mode),
        youtube_enabled=payload.youtube_enabled,
        bilibili_enabled=payload.bilibili_enabled,
    )
    if current is None:
        raise HTTPException(status_code=404, detail="Deployment not found.")
    return DeploymentDiscoveryProfileView(
        deployment_id=current.deployment_id,
        mode=current.mode.value,
        youtube_enabled=current.youtube_enabled,
        bilibili_enabled=current.bilibili_enabled,
    )


@router.get(
    "/deployments/{deployment_id}/discovery/exposures",
    response_model=DeploymentDiscoveryExposureListView,
)
def list_discovery_exposures(
    deployment_id: str,
    request: Request,
    user: CurrentUserDependency,
    limit: int = Query(default=100, ge=1, le=500),
) -> DeploymentDiscoveryExposureListView:
    repo = repository(request)
    profile = repo.get_profile(owner_id=user.id, deployment_id=deployment_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Deployment not found.")
    rows = repo.list_exposures(owner_id=user.id, deployment_id=deployment_id, limit=limit)
    items: list[DeploymentDiscoveryExposureView] = []
    with request.app.state.database.session() as session:
        for row in rows:
            content = session.get(DiscoveryItemRecord, row.discovery_item_id)
            if content is None:
                continue
            items.append(
                DeploymentDiscoveryExposureView(
                    id=row.id,
                    deployment_id=row.deployment_id,
                    item=_item(content),
                    attention_level=row.attention_level,
                    interest_score=row.interest_score,
                    subjective_reason=row.subjective_reason,
                    exposure_count=row.exposure_count,
                    first_exposed_at=row.first_exposed_at,
                    last_exposed_at=row.last_exposed_at,
                )
            )
    return DeploymentDiscoveryExposureListView(items=items)


@router.get(
    "/deployments/{deployment_id}/discovery/decisions",
    response_model=DeploymentDiscoveryDecisionListView,
)
def list_discovery_decisions(
    deployment_id: str,
    request: Request,
    user: CurrentUserDependency,
    limit: int = Query(default=100, ge=1, le=500),
) -> DeploymentDiscoveryDecisionListView:
    repo = repository(request)
    profile = repo.get_profile(owner_id=user.id, deployment_id=deployment_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Deployment not found.")
    rows = repo.list_decisions(owner_id=user.id, deployment_id=deployment_id, limit=limit)
    items: list[DeploymentDiscoveryDecisionView] = []
    with request.app.state.database.session() as session:
        for row in rows:
            content = session.get(DiscoveryItemRecord, row.discovery_item_id)
            if content is None:
                continue
            items.append(
                DeploymentDiscoveryDecisionView(
                    id=row.id,
                    deployment_id=row.deployment_id,
                    item=_item(content),
                    mode=row.mode,
                    decision=row.decision,
                    motivation=row.motivation,
                    confidence=row.confidence,
                    scores=_json_object(row.scores_json),
                    evidence=_json_object(row.evidence_json),
                    created_at=row.created_at,
                )
            )
    return DeploymentDiscoveryDecisionListView(items=items)


__all__ = ["router"]
