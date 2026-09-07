"""Connector-facing submission and polling for asynchronous Discord turns."""

from __future__ import annotations

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Header, HTTPException, Query, Request, status

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.api.routes.connectors import (
    _authorize_connector,
    _validated_character_turn_deployment,
)
from echo_masque.api.social_turn_schemas import DiscordSocialTurnStepRequest
from echo_masque.api.turn_job_schemas import (
    TurnJobRecoveryItem,
    TurnJobRecoveryView,
    TurnJobStatus,
    TurnJobView,
    TurnProgressClaimRequest,
    TurnProgressClaimView,
    TurnProgressEvent,
)
from echo_masque.persistence.turn_job_models import TurnJobRecord
from echo_masque.persistence.turn_job_repository import TurnJobRepository
from echo_masque.turn_jobs import TurnJobManager

router = APIRouter(tags=["connectors"])


def _repository(request: Request) -> TurnJobRepository:
    return cast(TurnJobRepository, request.app.state.turn_job_repository)


def _manager(request: Request) -> TurnJobManager:
    return cast(TurnJobManager, request.app.state.turn_job_manager)


def _scoped_job(request: Request, job_id: str, connection_id: str) -> TurnJobRecord | None:
    record = _repository(request).get(job_id, connection_id=connection_id)
    if record is None:
        return None
    deployment = request.app.state.deployment_repository.deployment_matches_discord_destination(
        record.deployment_id,
        connection_id=record.connection_id,
        guild_id=record.guild_id,
        channel_id=record.channel_id,
        thread_id=record.thread_id,
        category_id=record.category_id,
    )
    if deployment is None or deployment.owner_id != record.owner_id:
        return None
    return record


def _view(repository: TurnJobRepository, record: TurnJobRecord) -> TurnJobView:
    from echo_masque.api.connector_schemas import DiscordConnectorReplyView
    from echo_masque.api.social_turn_schemas import DiscordSocialTurnStepView

    return TurnJobView(
        job_id=record.job_id,
        status=cast(TurnJobStatus, record.status),
        error_code=record.error_code or None,
        progress=[
            TurnProgressEvent(id=item.id, nonce=item.claim_nonce, text=item.text)
            for item in repository.list_progress(record.job_id)
        ],
        reply=DiscordConnectorReplyView.model_validate_json(record.reply_json)
        if record.reply_json
        else None,
        social_step=DiscordSocialTurnStepView.model_validate_json(record.social_step_json)
        if record.social_step_json
        else None,
    )


def _submit(
    *,
    request: Request,
    authorization: str | None,
    kind: str,
    payload: DiscordInboundMessage,
    request_json: str,
) -> TurnJobView:
    _authorize_connector(request, authorization)
    deployment = _validated_character_turn_deployment(request, payload)
    if deployment is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Discord deployment scope is no longer active.",
        )
    destination = request.app.state.deployment_repository.deployment_matches_discord_destination(
        deployment.id,
        connection_id=payload.connection_id,
        guild_id=payload.guild_id,
        channel_id=payload.channel_id,
        thread_id=payload.thread_id,
        category_id=payload.category_id,
    )
    if destination is None or destination.owner_id != deployment.owner_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Discord destination scope is no longer active.",
        )
    manager = _manager(request)
    repository = _repository(request)
    job_id = repository.job_id(
        kind=kind,
        connection_id=payload.connection_id,
        deployment_id=deployment.id,
        message_id=payload.message_id,
    )
    existing = repository.get(job_id, connection_id=payload.connection_id)
    if existing is not None:
        if (
            existing.guild_id != payload.guild_id
            or existing.channel_id != payload.channel_id
            or existing.thread_id != payload.thread_id
            or existing.category_id != payload.category_id
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Turn job destination does not match its Discord event.",
            )
        scoped = _scoped_job(request, job_id, payload.connection_id)
        if scoped is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Discord destination scope is no longer active.",
            )
        return _view(repository, scoped)
    if not manager.can_accept():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Discord turn queue is full."
        )
    record, created = repository.submit(
        kind=kind,
        owner_id=deployment.owner_id,
        connection_id=payload.connection_id,
        deployment_id=deployment.id,
        guild_id=payload.guild_id,
        channel_id=payload.channel_id,
        message_id=payload.message_id,
        request_json=request_json,
        deadline_seconds=manager.deadline_seconds,
        thread_id=payload.thread_id,
        category_id=payload.category_id,
    )
    if created and not manager.submit(record.job_id):
        repository.fail(record.job_id, status="stopped", error_code="queue_unavailable")
    return _view(repository, record)


@router.post("/messages/jobs", response_model=TurnJobView, status_code=status.HTTP_202_ACCEPTED)
async def submit_message_job(
    payload: DiscordInboundMessage,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> TurnJobView:
    payload = payload.model_copy(update={"runtime_operation_id": "", "runtime_step_id": ""})
    return _submit(
        request=request,
        authorization=authorization,
        kind="message",
        payload=payload,
        request_json=payload.model_dump_json(),
    )


@router.post("/social-turns/jobs", response_model=TurnJobView, status_code=status.HTTP_202_ACCEPTED)
async def submit_social_job(
    payload: DiscordSocialTurnStepRequest,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> TurnJobView:
    inbound = payload.payload.model_copy(update={"runtime_operation_id": "", "runtime_step_id": ""})
    payload = payload.model_copy(update={"payload": inbound})
    return _submit(
        request=request,
        authorization=authorization,
        kind="social",
        payload=payload.payload,
        request_json=payload.model_dump_json(),
    )


@router.get("/turn-jobs/{job_id}", response_model=TurnJobView)
def get_turn_job(
    job_id: str,
    request: Request,
    connection_id: str = Query(min_length=1, max_length=64),
    authorization: Annotated[str | None, Header()] = None,
) -> TurnJobView:
    _authorize_connector(request, authorization)
    record = _scoped_job(request, job_id, connection_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turn job not found.")
    return _view(_repository(request), record)


@router.get("/turn-jobs", response_model=TurnJobRecoveryView)
def list_turn_job_recovery(
    request: Request,
    connection_id: str = Query(min_length=1, max_length=64),
    after_job_id: str = Query(default="", max_length=64),
    limit: int = Query(default=50, ge=1, le=50),
    authorization: Annotated[str | None, Header()] = None,
) -> TurnJobRecoveryView:
    _authorize_connector(request, authorization)
    records = _repository(request).list_recoverable(
        connection_id=connection_id, after_job_id=after_job_id, limit=limit
    )
    items = [
        TurnJobRecoveryItem(
            job_id=record.job_id,
            kind=cast(Literal["message", "social"], record.kind),
            guild_id=record.guild_id,
            channel_id=record.channel_id,
            thread_id=record.thread_id,
            source_message_id=record.source_message_id,
            deployment_id=record.deployment_id,
            status=cast(TurnJobStatus, record.status),
        )
        for record in records
        if _scoped_job(request, record.job_id, connection_id) is not None
    ]
    return TurnJobRecoveryView(
        items=items, next_cursor=records[-1].job_id if len(records) == limit else None
    )


@router.post("/turn-jobs/{job_id}/consume", status_code=status.HTTP_204_NO_CONTENT)
def consume_terminal_notice(
    job_id: str,
    request: Request,
    connection_id: str = Query(min_length=1, max_length=64),
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    _authorize_connector(request, authorization)
    if _scoped_job(request, job_id, connection_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turn job not found.")
    if not _repository(request).acknowledge_final_notice(job_id, connection_id=connection_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Terminal notice unavailable."
        )


@router.post("/turn-jobs/{job_id}/progress/claim", response_model=TurnProgressClaimView)
def claim_turn_progress(
    job_id: str,
    payload: TurnProgressClaimRequest,
    request: Request,
    connection_id: str = Query(min_length=1, max_length=64),
    authorization: Annotated[str | None, Header()] = None,
) -> TurnProgressClaimView:
    _authorize_connector(request, authorization)
    if _scoped_job(request, job_id, connection_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turn job not found.")
    event = _repository(request).claim_progress(job_id, nonce=payload.nonce)
    return TurnProgressClaimView(
        event=TurnProgressEvent(id=event.id, nonce=event.claim_nonce, text=event.text)
        if event
        else None
    )


@router.post(
    "/turn-jobs/{job_id}/progress/{progress_id}/ack", status_code=status.HTTP_204_NO_CONTENT
)
def acknowledge_turn_progress(
    job_id: str,
    progress_id: int,
    payload: TurnProgressClaimRequest,
    request: Request,
    connection_id: str = Query(min_length=1, max_length=64),
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    _authorize_connector(request, authorization)
    if _scoped_job(request, job_id, connection_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turn job not found.")
    if not _repository(request).acknowledge_progress(job_id, progress_id, nonce=payload.nonce):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Progress acknowledgement did not match its claim.",
        )
