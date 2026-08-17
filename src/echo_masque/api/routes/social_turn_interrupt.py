"""Connector endpoint for superseding stale durable Social Turn work."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from echo_masque.api.routes.connectors import _authorize_connector, durable_runtime_repository
from echo_masque.persistence.runtime_durability_models import RuntimeOperationRecord

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
        record = session.get(RuntimeOperationRecord, payload.operation_id)
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

        try:
            cursor = json.loads(record.cursor_json or "{}")
        except json.JSONDecodeError:
            cursor = {}
        if not isinstance(cursor, dict):
            cursor = {}
        cursor["pending_turns"] = []
        cursor["superseded_by_message_id"] = payload.superseding_message_id
        cursor["superseded_reason"] = payload.reason
        record.cursor_json = json.dumps(
            cursor,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        record.sources_json = "[]"
        record.status = "completed"
        record.last_error = f"superseded:{payload.reason}"[:1000]
        record.updated_at = now
        record.completed_at = now
        session.commit()

    return DiscordSocialTurnCancelView(
        canceled=True,
        status="completed",
        reason=payload.reason,
    )


__all__ = ["router"]
