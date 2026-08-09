"""Portal inspection and cancellation endpoints for scheduled reminders."""

from typing import Literal, cast

from fastapi import APIRouter, HTTPException, Query, Request

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.api.scheduled_reminder_schemas import (
    ReminderStatus,
    ScheduledReminderListView,
    ScheduledReminderView,
)
from echo_masque.persistence import DeploymentRepository, Repository, ScheduledReminderRepository
from echo_masque.persistence.scheduled_reminder_models import ScheduledReminderRecord

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


def reminder_repository(request: Request) -> ScheduledReminderRepository:
    return cast(ScheduledReminderRepository, request.app.state.scheduled_reminder_repository)


def deployment_repository(request: Request) -> DeploymentRepository:
    return cast(DeploymentRepository, request.app.state.deployment_repository)


def character_repository(request: Request) -> Repository:
    return cast(Repository, request.app.state.repository)


def _view(record: ScheduledReminderRecord, request: Request) -> ScheduledReminderView:
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
    records = reminder_repository(request).list_for_owner(
        owner_id=user.id,
        deployment_id=deployment_id.strip() if deployment_id else None,
        status=status_filter,
        limit=limit,
    )
    return ScheduledReminderListView(items=[_view(item, request) for item in records])


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
