"""Internal authenticated endpoints used by platform connector workers."""

from __future__ import annotations

import hmac
from typing import Annotated, cast

from fastapi import APIRouter, Header, HTTPException, Query, Request, status

from echo_masque.api.connector_schemas import (
    DiscordConnectorDeploymentView,
    DiscordConnectorHeartbeat,
    DiscordConnectorReplyView,
    DiscordInboundMessage,
    DiscordParticipationMode,
)
from echo_masque.config import Settings
from echo_masque.connector_runtime import ConnectorRuntimeError, DiscordConnectorRuntime
from echo_masque.persistence import DeploymentRepository, Repository

router = APIRouter(prefix="/api/connectors/discord", tags=["connectors"])


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


def deployment_repository(request: Request) -> DeploymentRepository:
    return cast(DeploymentRepository, request.app.state.deployment_repository)


def character_repository(request: Request) -> Repository:
    return cast(Repository, request.app.state.repository)


def connector_runtime(request: Request) -> DiscordConnectorRuntime:
    return cast(DiscordConnectorRuntime, request.app.state.discord_connector_runtime)


@router.get("/deployments", response_model=list[DiscordConnectorDeploymentView])
def list_connector_deployments(
    request: Request,
    connection_id: str = Query(min_length=1, max_length=64),
    authorization: Annotated[str | None, Header()] = None,
) -> list[DiscordConnectorDeploymentView]:
    _authorize_connector(request, authorization)
    records = deployment_repository(request).list_connector_deployments(
        platform="discord",
        connection_id=connection_id,
    )
    views: list[DiscordConnectorDeploymentView] = []
    repo = character_repository(request)
    for record in records:
        card = repo.get_character_card(record.character_card_id, record.owner_id)
        if card is None:
            continue
        views.append(
            DiscordConnectorDeploymentView(
                deployment_id=record.id,
                connection_id=record.connection_id,
                character_card_id=record.character_card_id,
                character_display_name=card.display_name,
                workspace_id=record.workspace_id,
                workspace_name=record.workspace_name,
                channel_id=record.channel_id,
                channel_name=record.channel_name,
                thread_id=record.thread_id,
                thread_name=record.thread_name,
                participation_mode=cast(
                    DiscordParticipationMode,
                    record.participation_mode,
                ),
                version_label=record.version_label,
                status="active",
            )
        )
    return views


@router.post("/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
def connector_heartbeat(
    payload: DiscordConnectorHeartbeat,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    _authorize_connector(request, authorization)
    updated = deployment_repository(request).heartbeat_connection(
        connection_id=payload.connection_id,
        platform="discord",
        external_account_id=payload.bot_user_id,
        display_name=payload.bot_display_name,
        status=payload.status,
        last_error=payload.last_error,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Discord connection not found.")


@router.post("/messages", response_model=DiscordConnectorReplyView)
async def process_discord_message(
    payload: DiscordInboundMessage,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> DiscordConnectorReplyView:
    _authorize_connector(request, authorization)
    try:
        return await connector_runtime(request).respond(payload)
    except ConnectorRuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Character provider failed: {exc}",
        ) from exc
