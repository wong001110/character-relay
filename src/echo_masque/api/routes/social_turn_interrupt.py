"""Connector endpoint for superseding stale durable Social Turn work."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from echo_masque.api.routes.connectors import _authorize_connector, durable_runtime_repository
from echo_masque.api.social_turn_schemas import DiscordSocialTurnCursor
from echo_masque.persistence.runtime_durability_models import (
    RuntimeOperationRecord,
    RuntimeStepRecord,
)

router = APIRouter()


class DiscordSocialTurnCancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str = Field(min_length=1, max_length=64)
    connection_id: str = Field(min_length=1, max_length=64)
    guild_id: str = Field(default="", max_length=200)
    channel_id: str = Field(default="", max_length=200)
    thread_id: str = Field(default="", max_length=200)
    superseding_message_id: str = Field(min_length=1, max_length=200)
    reason: str = Field(default="new_human_input", max_length=120)


class DiscordSocialTurnCancelView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canceled: bool
    status: str
    reason: str


@router.post(
    "/social-turns/operations/cancel",
    response_model=DiscordSocialTurnCancelView,
)
def cancel_social_turn_operation(
    payload: DiscordSocialTurnCancelRequest,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> DiscordSocialTurnCancelView:
    """Complete stale pending Social Turn work after a newer human turn supersedes it."""

    _authorize_connector(request, authorization)
    repository = durable_runtime_repository(request)
    now = datetime.now(UTC)
    with repository.database.session() as session:
        record = session.scalar(
            select(RuntimeOperationRecord)
            .where(RuntimeOperationRecord.operation_id == payload.operation_id)
            .with_for_update()
        )
        if record is None:
            return DiscordSocialTurnCancelView(
                canceled=False,
                status="missing",
                reason="operation_not_found",
            )
        identity = (
            record.connection_id,
            record.guild_id,
            record.channel_id,
            record.thread_id,
        )
        supplied = (
            payload.connection_id,
            payload.guild_id,
            payload.channel_id,
            payload.thread_id,
        )
        if identity != supplied:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Social Turn operation scope does not match the superseding Discord turn.",
            )
        if record.status == "completed":
            return DiscordSocialTurnCancelView(
                canceled=False,
                status="completed",
                reason="already_completed",
            )
        if record.status in {"awaiting_delivery", "uncertain"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Social Turn operation cannot be superseded across an unresolved delivery.",
            )

        cursor = DiscordSocialTurnCursor.model_validate_json(record.cursor_json)
        # A new room message changes optional scheduling, not ownership of another human's work.
        if cursor.pending_turns and cursor.pending_turns[0].origin == "selected":
            return DiscordSocialTurnCancelView(
                canceled=False, status=record.status, reason="direct_request_preserved"
            )
        running = session.scalar(
            select(RuntimeStepRecord.step_id).where(
                RuntimeStepRecord.operation_id == record.operation_id,
                RuntimeStepRecord.status.in_(["generating", "refreshing", "delivery_claimed"]),
            )
        )
        if running is not None:
            raise HTTPException(status_code=409, detail="running_work_requires_draft_preflight")
        cursor.pending_turns = [p for p in cursor.pending_turns if p.origin == "selected"]
        repository._advance_operation(
            session, record, cursor_json=cursor.model_dump_json(), now=now
        )
        record.last_error = "optional_continuation_yielded_to_human"
        session.commit()
        resulting_status = record.status

    return DiscordSocialTurnCancelView(
        canceled=True,
        status=resulting_status,
        reason="optional_continuation_yielded_to_human",
    )


__all__ = ["router"]
