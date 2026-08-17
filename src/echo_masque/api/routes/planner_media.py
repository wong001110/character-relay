"""Internal Discord connector endpoint for planner-only media descriptors."""

from __future__ import annotations

import hmac
from typing import Annotated, cast

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from echo_masque.api.connector_schemas import (
    DiscordAttachmentContent,
    DiscordEmbedContent,
    DiscordInboundMessage,
)
from echo_masque.config import Settings
from echo_masque.planner_media import PlannerMediaDescriptorService, PlannerMediaResult

router = APIRouter()


class PlannerMediaResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection_id: str = Field(min_length=1, max_length=64)
    message_id: str = Field(min_length=1, max_length=200)
    guild_id: str = Field(default="", max_length=200)
    channel_id: str = Field(min_length=1, max_length=200)
    thread_id: str = Field(default="", max_length=200)
    text: str = Field(default="", max_length=10000)
    attachments: list[DiscordAttachmentContent] = Field(default_factory=list, max_length=10)
    embeds: list[DiscordEmbedContent] = Field(default_factory=list, max_length=10)
    burst_media_message_ids: list[str] = Field(default_factory=list, max_length=3)

    def runtime_payload(self) -> DiscordInboundMessage:
        return DiscordInboundMessage(
            connection_id=self.connection_id,
            deployment_id="planner-media",
            message_id=self.message_id,
            guild_id=self.guild_id,
            channel_id=self.channel_id,
            thread_id=self.thread_id,
            author_id="planner-media",
            author_display_name="Planner",
            text=self.text,
            attachments=self.attachments,
            embeds=self.embeds,
            burst_media_message_ids=self.burst_media_message_ids,
        )


def _authorize_connector(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    settings = cast(Settings, request.app.state.settings)
    configured = settings.connector_shared_secret
    if configured is None or not configured.get_secret_value():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Connector API is disabled until a shared secret is configured.",
        )
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.casefold() != "bearer" or not hmac.compare_digest(
        token,
        configured.get_secret_value(),
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid connector credential.",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/media/describe", response_model=PlannerMediaResult)
async def describe_media_for_planner(
    payload: PlannerMediaResolveRequest,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> PlannerMediaResult:
    """Resolve objective routing evidence without granting it to a Character prompt."""

    _authorize_connector(request, authorization)
    service = cast(PlannerMediaDescriptorService, request.app.state.planner_media_service)
    return await service.resolve(payload.runtime_payload())


__all__ = ["router"]
