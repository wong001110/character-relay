"""Trial execution, status, live events, cancellation, and replay endpoints."""

from typing import Annotated, cast

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, status

from echo_masque.api.schemas import ReplayTurn, TrialEventView, TrialRunView, TrialStart
from echo_masque.persistence import Repository
from echo_masque.services import TrialService

router = APIRouter(prefix="/api/trials", tags=["trials"])


def repository(request: Request) -> Repository:
    return cast(Repository, request.app.state.repository)


def service(request: Request) -> TrialService:
    return cast(TrialService, request.app.state.trial_service)


@router.post("", response_model=TrialRunView, status_code=status.HTTP_202_ACCEPTED)
def start_trial(
    payload: TrialStart,
    request: Request,
    background_tasks: BackgroundTasks,
) -> TrialRunView:
    try:
        run_id = service(request).start(
            target_id=payload.target_id,
            character_card_id=payload.character_card_id,
            suite=payload.suite,
            mode=payload.mode,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Target or Character Card not found.") from exc
    background_tasks.add_task(service(request).execute, run_id)
    run = repository(request).get_run(run_id)
    assert run is not None
    return TrialRunView.from_record(run)


@router.get("/{run_id}", response_model=TrialRunView)
def get_trial(run_id: str, request: Request) -> TrialRunView:
    run = repository(request).get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Trial not found.")
    return TrialRunView.from_record(run)


@router.get("/{run_id}/events", response_model=list[TrialEventView])
def trial_events(
    run_id: str,
    request: Request,
    after: Annotated[int, Query(ge=0)] = 0,
) -> list[TrialEventView]:
    if repository(request).get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Trial not found.")
    return [
        TrialEventView.from_record(item)
        for item in repository(request).list_trial_events(run_id, after)
    ]


@router.post("/{run_id}/cancel", response_model=TrialRunView)
def cancel_trial(run_id: str, request: Request) -> TrialRunView:
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
def replay_trial(run_id: str, request: Request) -> list[ReplayTurn]:
    if repository(request).get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Trial not found.")
    return [ReplayTurn.from_record(item) for item in repository(request).replay(run_id)]
