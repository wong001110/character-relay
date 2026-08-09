"""Portal inspection and cancellation endpoints for scheduled reminders."""

from typing import Literal, cast

from fastapi import APIRouter, HTTPException, Query, Request

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.api.scheduled_reminder_schemas import (
    ReminderStatus,
    ScheduledReminderListView,
    ScheduledReminderPage,
    ScheduledReminderStatusCounts,
    ScheduledReminderView,
)
from echo_masque.persistence import DeploymentRepository, Repository, ScheduledReminderRepository
from echo_masque.persistence.scheduled_reminder_models import ScheduledReminderRecord
from echo_masque.persistence.scheduled_reminder_repository import ScheduledReminderPortalRow

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


def reminder_repository(request: Request) -> ScheduledReminderRepository:
    return cast(ScheduledReminderRepository, request.app.state.scheduled_reminder_repository)


def deployment_repository(request: Request) -> DeploymentRepository:
    return cast(DeploymentRepository, request.app.state.deployment_repository)


def character_repository(request: Request) -> Repository:
    return cast(Repository, request.app.state.repository)


def _view(record: ScheduledReminderRecord, request: Request) -> ScheduledReminderView:
    """Resolve a single row, used only for one-record mutation responses."""

    deployments = deployment_repository(request)
    characters = character_repository(request)
    deployment = deployments.get_deployment(record.deployment_id, record.owner_id)
    character_card_id = deployment.character_card_id if deployment is not None else ""
    character = (
        characters.get_character_card(character_card_id, record.owner_id)
        if character_card_id
        else None
    )
    channel_name = ""
    thread_name = ""
    if deployment is not None:
        channel_name = deployment.channel_name
        thread_name = deployment.thread_name
    return ScheduledReminderView(
        id=record.id,
        deployment_id=record.deployment_id,
        character_card_id=character_card_id,
        character_name=character.display_name if character is not None else "Character",
        platform=record.platform,
        channel_id=record.channel_id,
        channel_name=channel_name,
        thread_id=record.thread_id,
        thread_name=thread_name,
        reminder_text=record.reminder_text,
        scheduled_at=record.scheduled_at,
        status=cast(ReminderStatus, record.status),
        attempt_count=record.attempt_count,
        delivered_at=record.delivered_at,
        last_error=record.last_error,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _portal_view(row: ScheduledReminderPortalRow) -> ScheduledReminderView:
    record = row.record
    return ScheduledReminderView(
        id=record.id,
        deployment_id=record.deployment_id,
        character_card_id=row.character_card_id,
        character_name=row.character_name,
        platform=record.platform,
        channel_id=record.channel_id,
        channel_name=row.channel_name,
        thread_id=record.thread_id,
        thread_name=row.thread_name,
        reminder_text=record.reminder_text,
        scheduled_at=record.scheduled_at,
        status=cast(ReminderStatus, record.status),
        attempt_count=record.attempt_count,
        delivered_at=record.delivered_at,
        last_error=record.last_error,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _status_counts(values: dict[str, int]) -> ScheduledReminderStatusCounts:
    return ScheduledReminderStatusCounts(
        pending=values.get("pending", 0),
        processing=values.get("processing", 0),
        completed=values.get("completed", 0),
        failed=values.get("failed", 0),
        cancelled=values.get("cancelled", 0),
    )


@router.get("/reminders", response_model=ScheduledReminderListView)
def list_reminders(
    request: Request,
    user: CurrentUserDependency,
    deployment_id: str | None = Query(default=None, max_length=64),
    status_filter: Literal[
        "pending", "processing", "completed", "failed", "cancelled"
    ]
    | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=250),
) -> ScheduledReminderListView:
    rows, _, _ = reminder_repository(request).list_portal_page(
        owner_id=user.id,
        deployment_id=deployment_id.strip() if deployment_id else None,
        status=status_filter,
        limit=limit,
    )
    return ScheduledReminderListView(items=[_portal_view(item) for item in rows])


@router.get("/reminders/page", response_model=ScheduledReminderPage)
def paginate_reminders(
    request: Request,
    user: CurrentUserDependency,
    deployment_id: str | None = Query(default=None, max_length=64),
    status_filter: Literal[
        "pending", "processing", "completed", "failed", "cancelled"
    ]
    | None = Query(default=None, alias="status"),
    cursor: str | None = Query(default=None, max_length=1000),
    limit: int = Query(default=50, ge=1, le=100),
) -> ScheduledReminderPage:
    try:
        rows, next_cursor, counts = reminder_repository(request).list_portal_page(
            owner_id=user.id,
            deployment_id=deployment_id.strip() if deployment_id else None,
            status=status_filter,
            cursor=cursor,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ScheduledReminderPage(
        items=[_portal_view(item) for item in rows],
        next_cursor=next_cursor,
        has_more=next_cursor is not None,
        counts=_status_counts(counts),
    )


@router.delete("/reminders/{reminder_id}", response_model=ScheduledReminderView)
def cancel_reminder(
    reminder_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> ScheduledReminderView:
    repo = reminder_repository(request)
    record = repo.get(owner_id=user.id, reminder_id=reminder_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Reminder not found.")
    if record.status not in {"pending", "processing"}:
        raise HTTPException(
            status_code=409,
            detail=f"Reminder cannot be cancelled from status {record.status}.",
        )
    cancelled = repo.cancel(
        owner_id=user.id,
        deployment_id=record.deployment_id,
        reminder_id=record.id,
    )
    if cancelled is None:
        raise HTTPException(status_code=404, detail="Reminder not found.")
    return _view(cancelled, request)
