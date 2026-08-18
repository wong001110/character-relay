"""Owner-scoped controls and observability for Deployment Character Discovery."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query, Request

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.api.deployment_discovery_schemas import (
    DeploymentActivitySessionDetailView,
    DeploymentActivitySessionItemView,
    DeploymentActivitySessionListView,
    DeploymentActivitySessionView,
    DeploymentDiscoveryBrowseShadowRequest,
    DeploymentDiscoveryDecisionListView,
    DeploymentDiscoveryDecisionView,
    DeploymentDiscoveryExposureListView,
    DeploymentDiscoveryExposureView,
    DeploymentDiscoveryProfileUpdate,
    DeploymentDiscoveryProfileView,
    DeploymentDiscoveryShareListView,
    DeploymentDiscoveryShareView,
    DeploymentDiscoveryShadowPreviewView,
    DiscoveryItemView,
    DiscoverySeedView,
    RankedDiscoveryCandidateView,
)
from echo_masque.deployment_discovery_service import (
    DeploymentDiscoveryPreviewService,
    DeploymentDiscoveryUnavailable,
)
from echo_masque.discovery_contracts import DiscoveryMode
from echo_masque.discovery_runtime import CompleteDeploymentDiscoveryActivityService
from echo_masque.discovery_share import DiscoveryShareCoordinator
from echo_masque.persistence.deployment_activity_repository import DeploymentActivityRepository
from echo_masque.persistence.deployment_activity_repository import (
    DeploymentActivitySessionView as ActivityDomainView,
)
from echo_masque.persistence.discovery_models import DiscoveryItemRecord
from echo_masque.persistence.discovery_repository import DiscoveryRepository
from echo_masque.persistence.discovery_share_models import DeploymentDiscoveryShareRecord
from echo_masque.persistence.discovery_share_repository import DiscoveryShareRepository

router = APIRouter(tags=["deployments"])


def repository(request: Request) -> DiscoveryRepository:
    return DiscoveryRepository(request.app.state.database)


def activity_repository(request: Request) -> DeploymentActivityRepository:
    return DeploymentActivityRepository(request.app.state.database)


def share_repository(request: Request) -> DiscoveryShareRepository:
    return DiscoveryShareRepository(request.app.state.database)


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


def _profile_view(
    request: Request,
    *,
    deployment_id: str,
    owner_id: str,
) -> DeploymentDiscoveryProfileView | None:
    profile = repository(request).get_profile(owner_id=owner_id, deployment_id=deployment_id)
    policy = share_repository(request).get_policy(
        owner_id=owner_id,
        deployment_id=deployment_id,
    )
    if profile is None or policy is None:
        return None
    settings = request.app.state.settings
    return DeploymentDiscoveryProfileView(
        deployment_id=deployment_id,
        mode=profile.mode.value,
        youtube_enabled=profile.youtube_enabled,
        bilibili_enabled=profile.bilibili_enabled,
        bilibili_experimental_available=(
            settings.bilibili_discovery_experimental_enabled
        ),
        auto_share_enabled=policy.auto_share_enabled,
        auto_global_enabled=settings.discovery_auto_share_global_enabled,
        daily_share_budget=policy.daily_share_budget,
        share_cooldown_minutes=policy.share_cooldown_minutes,
    )


def _activity(value: ActivityDomainView) -> DeploymentActivitySessionView:
    return DeploymentActivitySessionView(
        id=value.id,
        deployment_id=value.deployment_id,
        activity_type=value.activity_type,
        platform=value.platform,
        status=value.status,
        source=value.source,
        local_date=value.local_date,
        schedule_timezone=value.schedule_timezone,
        scheduled_start_at=value.scheduled_start_at,
        latest_start_at=value.latest_start_at,
        planned_duration_minutes=value.planned_duration_minutes,
        started_at=value.started_at,
        expected_end_at=value.expected_end_at,
        ended_at=value.ended_at,
        candidate_budget=value.candidate_budget,
        open_budget=value.open_budget,
        watch_budget=value.watch_budget,
        share_intent_budget=value.share_intent_budget,
        exploration_percent=value.exploration_percent,
        candidate_count=value.candidate_count,
        notice_count=value.notice_count,
        open_count=value.open_count,
        watch_count=value.watch_count,
        engage_count=value.engage_count,
        reason=value.reason,
        error=value.error,
    )


def _activity_detail(
    request: Request,
    *,
    owner_id: str,
    activity: ActivityDomainView,
) -> DeploymentActivitySessionDetailView:
    repo = activity_repository(request)
    items: list[DeploymentActivitySessionItemView] = []
    with request.app.state.database.session() as session:
        for row in repo.list_items(owner_id=owner_id, session_id=activity.id):
            content = session.get(DiscoveryItemRecord, row.discovery_item_id)
            if content is None:
                continue
            items.append(
                DeploymentActivitySessionItemView(
                    rank_position=row.rank_position,
                    attention_level=row.attention_level,
                    score=row.score,
                    reason=row.reason,
                    item=_item(content),
                )
            )
    return DeploymentActivitySessionDetailView(session=_activity(activity), items=items)


def _share_view(
    request: Request,
    record: DeploymentDiscoveryShareRecord,
) -> DeploymentDiscoveryShareView | None:
    with request.app.state.database.session() as session:
        item = session.get(DiscoveryItemRecord, record.discovery_item_id)
        if item is None:
            return None
    return DeploymentDiscoveryShareView(
        id=record.id,
        deployment_id=record.deployment_id,
        item=_item(item),
        mode=record.mode,
        status=record.status,
        motivation=record.motivation,
        confidence=record.confidence,
        topic_id=record.topic_id,
        relationship_subject_key=record.relationship_subject_key,
        channel_id=record.channel_id,
        thread_id=record.thread_id,
        draft_text=record.draft_text,
        attempt_count=record.attempt_count,
        last_error=record.last_error,
        approved_at=record.approved_at,
        rejected_at=record.rejected_at,
        queued_at=record.queued_at,
        delivered_at=record.delivered_at,
        discord_message_id=record.discord_message_id,
        created_at=record.created_at,
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
    value = _profile_view(request, deployment_id=deployment_id, owner_id=user.id)
    if value is None:
        raise HTTPException(status_code=404, detail="Deployment not found.")
    return value


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
    settings = request.app.state.settings
    if payload.bilibili_enabled and not settings.bilibili_discovery_experimental_enabled:
        raise HTTPException(
            status_code=409,
            detail="Bilibili Discovery is experimental and globally disabled.",
        )
    current = repository(request).set_profile(
        owner_id=user.id,
        deployment_id=deployment_id,
        mode=DiscoveryMode(payload.mode),
        youtube_enabled=payload.youtube_enabled,
        bilibili_enabled=payload.bilibili_enabled,
    )
    if current is None:
        raise HTTPException(status_code=404, detail="Deployment not found.")
    share_repository(request).set_policy(
        owner_id=user.id,
        deployment_id=deployment_id,
        auto_share_enabled=payload.auto_share_enabled,
        daily_share_budget=payload.daily_share_budget,
        share_cooldown_minutes=payload.share_cooldown_minutes,
    )
    value = _profile_view(request, deployment_id=deployment_id, owner_id=user.id)
    assert value is not None
    return value


@router.post(
    "/deployments/{deployment_id}/discovery/shadow-preview",
    response_model=DeploymentDiscoveryShadowPreviewView,
)
async def run_discovery_shadow_preview(
    deployment_id: str,
    request: Request,
    user: CurrentUserDependency,
    region: str = Query(default="", max_length=16),
    language: str = Query(default="", max_length=32),
    source: str = Query(default="", max_length=32),
    limit: int = Query(default=10, ge=1, le=30),
) -> DeploymentDiscoveryShadowPreviewView:
    settings = request.app.state.runtime_service.settings
    service = DeploymentDiscoveryPreviewService(request.app.state.database, settings)
    try:
        preview = await service.run(
            owner_id=user.id,
            deployment_id=deployment_id,
            region=region,
            language=language,
            limit=limit,
            sources=((source.casefold().strip(),) if source.strip() else ()),
        )
    except DeploymentDiscoveryUnavailable as exc:
        detail = str(exc)
        status = 404 if detail == "Deployment not found." else 409
        if "api_key_missing" in detail:
            status = 503
        raise HTTPException(status_code=status, detail=detail) from exc

    candidates: list[RankedDiscoveryCandidateView] = []
    with request.app.state.database.session() as session:
        for ranked in preview.ranked:
            record = session.get(DiscoveryItemRecord, ranked.discovery_item_id)
            if record is None:
                continue
            candidates.append(
                RankedDiscoveryCandidateView(
                    item=_item(record),
                    semantic_relevance=ranked.semantic_relevance,
                    sparse_relevance=ranked.sparse_relevance,
                    freshness=ranked.freshness,
                    novelty=ranked.novelty,
                    exploration=ranked.exploration,
                    final_score=ranked.final_score,
                    reason=ranked.reason,
                )
            )
    return DeploymentDiscoveryShadowPreviewView(
        deployment_id=deployment_id,
        queries=list(preview.seeds.queries),
        seeds=[
            DiscoverySeedView(
                text=seed.text,
                weight=seed.weight,
                source=seed.source,
                evidence_ref=seed.evidence_ref,
            )
            for seed in preview.seeds.seeds
        ],
        candidates=candidates,
        sources=list(preview.sources),
        source_errors=list(preview.source_errors),
        side_effects=False,
    )


@router.post(
    "/deployments/{deployment_id}/discovery/browse-shadow",
    response_model=DeploymentActivitySessionDetailView,
)
async def run_browsing_session(
    deployment_id: str,
    payload: DeploymentDiscoveryBrowseShadowRequest,
    request: Request,
    user: CurrentUserDependency,
) -> DeploymentActivitySessionDetailView:
    service = request.app.state.deployment_activity_scheduler.service
    try:
        if isinstance(service, CompleteDeploymentDiscoveryActivityService):
            activity = await service.run_manual_discovery(
                owner_id=user.id,
                deployment_id=deployment_id,
                platform=payload.platform or "",
                duration_minutes=payload.duration_minutes,
                candidate_budget=payload.candidate_budget,
                open_budget=payload.open_budget,
            )
        else:
            if payload.platform not in {None, "youtube"}:
                raise ValueError("This runtime currently supports YouTube only.")
            activity = await service.run_manual(
                owner_id=user.id,
                deployment_id=deployment_id,
                duration_minutes=payload.duration_minutes,
                candidate_budget=payload.candidate_budget,
                open_budget=payload.open_budget,
            )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Deployment not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _activity_detail(request, owner_id=user.id, activity=activity)


@router.get(
    "/deployments/{deployment_id}/discovery/sessions",
    response_model=DeploymentActivitySessionListView,
)
def list_browsing_sessions(
    deployment_id: str,
    request: Request,
    user: CurrentUserDependency,
    limit: int = Query(default=50, ge=1, le=200),
) -> DeploymentActivitySessionListView:
    profile = repository(request).get_profile(owner_id=user.id, deployment_id=deployment_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Deployment not found.")
    rows = activity_repository(request).list_for_deployment(
        owner_id=user.id,
        deployment_id=deployment_id,
        limit=limit,
    )
    return DeploymentActivitySessionListView(items=[_activity(row) for row in rows])


@router.get(
    "/deployments/{deployment_id}/discovery/sessions/{session_id}",
    response_model=DeploymentActivitySessionDetailView,
)
def get_browsing_session(
    deployment_id: str,
    session_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> DeploymentActivitySessionDetailView:
    activity = activity_repository(request).get(owner_id=user.id, session_id=session_id)
    if activity is None or activity.deployment_id != deployment_id:
        raise HTTPException(status_code=404, detail="Browsing session not found.")
    return _activity_detail(request, owner_id=user.id, activity=activity)


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
    if repo.get_profile(owner_id=user.id, deployment_id=deployment_id) is None:
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
    if repo.get_profile(owner_id=user.id, deployment_id=deployment_id) is None:
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


@router.get(
    "/deployments/{deployment_id}/discovery/shares",
    response_model=DeploymentDiscoveryShareListView,
)
def list_discovery_shares(
    deployment_id: str,
    request: Request,
    user: CurrentUserDependency,
    limit: int = Query(default=100, ge=1, le=500),
) -> DeploymentDiscoveryShareListView:
    if repository(request).get_profile(owner_id=user.id, deployment_id=deployment_id) is None:
        raise HTTPException(status_code=404, detail="Deployment not found.")
    values = []
    for row in share_repository(request).list_for_deployment(
        owner_id=user.id,
        deployment_id=deployment_id,
        limit=limit,
    ):
        view = _share_view(request, row)
        if view is not None:
            values.append(view)
    return DeploymentDiscoveryShareListView(items=values)


@router.post(
    "/deployments/{deployment_id}/discovery/shares/{share_id}/approve",
    response_model=DeploymentDiscoveryShareView,
)
def approve_discovery_share(
    deployment_id: str,
    share_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> DeploymentDiscoveryShareView:
    coordinator = DiscoveryShareCoordinator(
        request.app.state.database,
        request.app.state.settings,
    )
    try:
        record = coordinator.approve(owner_id=user.id, share_id=share_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if record is None or record.deployment_id != deployment_id:
        raise HTTPException(status_code=404, detail="Discovery share proposal not found.")
    view = _share_view(request, record)
    if view is None:
        raise HTTPException(status_code=404, detail="Discovery item not found.")
    return view


@router.post(
    "/deployments/{deployment_id}/discovery/shares/{share_id}/reject",
    response_model=DeploymentDiscoveryShareView,
)
def reject_discovery_share(
    deployment_id: str,
    share_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> DeploymentDiscoveryShareView:
    coordinator = DiscoveryShareCoordinator(
        request.app.state.database,
        request.app.state.settings,
    )
    record = coordinator.reject(owner_id=user.id, share_id=share_id)
    if record is None or record.deployment_id != deployment_id:
        raise HTTPException(status_code=404, detail="Discovery share proposal not found.")
    view = _share_view(request, record)
    if view is None:
        raise HTTPException(status_code=404, detail="Discovery item not found.")
    return view


__all__ = ["router"]
