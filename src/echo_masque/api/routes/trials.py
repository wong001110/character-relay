"""Trial execution, status, live events, cancellation, and replay endpoints."""

from typing import Annotated, cast

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, status

from echo_masque.api.access import owner_for_trial_start, require_run_access
from echo_masque.api.dependencies import OptionalAuthContextDependency
from echo_masque.api.schemas import (
    ReplayTurn,
    TrialEventView,
    TrialRunView,
    TrialSnapshotView,
    TrialStart,
)
from echo_masque.persistence import Repository, TargetAccessRepository
from echo_masque.services import TrialService

router = APIRouter(prefix="/api/trials", tags=["trials"])


def repository(request: Request) -> Repository:
    return cast(Repository, request.app.state.repository)


def target_access(request: Request) -> TargetAccessRepository:
    return cast(TargetAccessRepository, request.app.state.target_access_repository)


def service(request: Request) -> TrialService:
    return cast(TrialService, request.app.state.trial_service)


@router.post("", response_model=TrialRunView, status_code=status.HTTP_202_ACCEPTED)
def start_trial(
    payload: TrialStart,
    request: Request,
    background_tasks: BackgroundTasks,
    context: OptionalAuthContextDependency,
) -> TrialRunView:
    owner_id = owner_for_trial_start(payload, context)
    if payload.target_id is not None and not target_access(request).can_access(
        owner_id=owner_id,
        target_id=payload.target_id,
    ):
        raise HTTPException(
            status_code=404,
            detail="Target, Character Card, or Test Pack not found.",
        )
    try:
        run_id = service(request).start(
            target_id=payload.target_id,
            character_card_id=payload.character_card_id,
            test_pack_id=payload.test_pack_id,
            owner_id=owner_id,
            suite=payload.suite,
            mode=payload.mode,
            tester_mode=payload.tester_mode,
            adaptive_tester=payload.adaptive_tester,
            judge_mode=payload.judge_mode,
            test_language=payload.test_language,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail="Target, Character Card, or Test Pack not found.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    background_tasks.add_task(service(request).execute, run_id)
    run = repository(request).get_run(run_id)
    assert run is not None
    return TrialRunView.from_record(run)


@router.get("/{run_id}", response_model=TrialRunView)
def get_trial(
    run_id: str,
    request: Request,
    context: OptionalAuthContextDependency,
) -> TrialRunView:
    require_run_access(request, run_id, context)
    run = repository(request).get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Trial not found.")
    return TrialRunView.from_record(run)


@router.get("/{run_id}/snapshot", response_model=TrialSnapshotView)
def trial_snapshot(
    run_id: str,
    request: Request,
    context: OptionalAuthContextDependency,
    after: Annotated[int, Query(ge=0)] = 0,
) -> TrialSnapshotView:
    require_run_access(request, run_id, context)
    repo = repository(request)
    run = repo.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Trial not found.")
    return TrialSnapshotView(
        run=TrialRunView.from_record(run),
        events=[
            TrialEventView.from_record(item)
            for item in repo.list_trial_events(run_id, after)
        ],
    )


@router.get("/{run_id}/events", response_model=list[TrialEventView])
def trial_events(
    run_id: str,
    request: Request,
    context: OptionalAuthContextDependency,
    after: Annotated[int, Query(ge=0)] = 0,
) -> list[TrialEventView]:
    require_run_access(request, run_id, context)
    return [
        TrialEventView.from_record(item)
        for item in repository(request).list_trial_events(run_id, after)
    ]


@router.post("/{run_id}/cancel", response_model=TrialRunView)
def cancel_trial(
    run_id: str,
    request: Request,
    context: OptionalAuthContextDependency,
) -> TrialRunView:
    require_run_access(request, run_id, context, allow_public=False)
    try:
        changed = service(request).cancel(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Trial not found.") from exc
    if not changed:
        raise HTTPException(
            status_code=409,
            detail="Completed or failed trial cannot be cancelled.",
        )
    run = repository(request).get_run(run_id)
    assert run is not None
    return TrialRunView.from_record(run)


@router.get("/{run_id}/replay", response_model=list[ReplayTurn])
def replay_trial(
    run_id: str,
    request: Request,
    context: OptionalAuthContextDependency,
) -> list[ReplayTurn]:
    require_run_access(request, run_id, context)
    return [ReplayTurn.from_record(item) for item in repository(request).replay(run_id)]
