"""Internal authenticated endpoints used by platform connector workers."""

from __future__ import annotations

import hmac
from typing import Annotated, cast

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from pydantic import SecretStr

from echo_masque.api.connector_schemas import (
    DiscordConnectorDeploymentView,
    DiscordConnectorHeartbeat,
    DiscordConnectorReplyView,
    DiscordIdentityMode,
    DiscordInboundMessage,
    DiscordParticipationMode,
    DiscordWebhookRegistration,
    DiscordWebhookRegistrationView,
    DiscordWebhookStatus,
    DiscordWebhookStatusReport,
)
from echo_masque.config import Settings
from echo_masque.connector_runtime import ConnectorRuntimeError, DiscordConnectorRuntime
from echo_masque.credentials import CredentialVault
from echo_masque.persistence import (
    DeploymentRepository,
    DiscordIdentityRepository,
    Repository,
)

router = APIRouter(prefix="/api/connectors/discord", tags=["connectors"])
_WEBHOOK_SCOPE = "discord_webhook"


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


def identity_repository(request: Request) -> DiscordIdentityRepository:
    return cast(DiscordIdentityRepository, request.app.state.discord_identity_repository)


def character_repository(request: Request) -> Repository:
    return cast(Repository, request.app.state.repository)


def credential_store(request: Request) -> CredentialVault:
    return cast(CredentialVault, request.app.state.credential_store)


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
    identities = identity_repository(request)
    vault = credential_store(request)
    for record in records:
        card = repo.get_character_card(record.character_card_id, record.owner_id)
        if card is None:
            continue
        identity = identities.get_identity(record.id, record.owner_id)
        identity_mode = cast(
            DiscordIdentityMode,
            identity.mode if identity is not None else "webhook",
        )
        identity_name = (
            identity.display_name if identity is not None else card.display_name
        )
        identity_avatar = identity.avatar_url if identity is not None else ""
        webhook_status = cast(
            DiscordWebhookStatus,
            identity.webhook_status if identity is not None else "pending",
        )
        binding = identities.get_binding(
            owner_id=record.owner_id,
            connection_id=record.connection_id,
            channel_id=record.channel_id,
        )
        webhook_token: str | None = None
        if binding is not None and binding.status == "active":
            encrypted = vault.get_scope(
                owner_id=record.owner_id,
                scope_kind=_WEBHOOK_SCOPE,
                scope_id=binding.id,
            )
            if encrypted is not None:
                webhook_token = encrypted.get_secret_value()
                if identity_mode == "webhook":
                    webhook_status = "active"
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
                identity_mode=identity_mode,
                identity_display_name=identity_name,
                identity_avatar_url=identity_avatar,
                webhook_status=webhook_status,
                webhook_id=binding.webhook_id if binding is not None else None,
                webhook_token=webhook_token,
            )
        )
    return views


@router.put("/webhooks", response_model=DiscordWebhookRegistrationView)
def register_webhook(
    payload: DiscordWebhookRegistration,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> DiscordWebhookRegistrationView:
    _authorize_connector(request, authorization)
    identities = identity_repository(request)
    deployment = identities.deployment_for_connector(
        deployment_id=payload.deployment_id,
        connection_id=payload.connection_id,
        channel_id=payload.channel_id,
    )
    if deployment is None:
        raise HTTPException(status_code=404, detail="Discord deployment not found.")
    binding = identities.upsert_binding(
        owner_id=deployment.owner_id,
        connection_id=payload.connection_id,
        workspace_id=payload.workspace_id,
        channel_id=payload.channel_id,
        webhook_id=payload.webhook_id,
    )
    credential_store(request).set_scope(
        owner_id=deployment.owner_id,
        scope_kind=_WEBHOOK_SCOPE,
        scope_id=binding.id,
        value=SecretStr(payload.webhook_token),
        actor_user_id=deployment.owner_id,
        resource_type="discord_webhook",
    )
    identities.set_identity_status(
        deployment_id=payload.deployment_id,
        status="active",
    )
    return DiscordWebhookRegistrationView(
        binding_id=binding.id,
        webhook_id=binding.webhook_id,
        webhook_token=payload.webhook_token,
    )


@router.post("/webhooks/status", status_code=status.HTTP_204_NO_CONTENT)
def report_webhook_status(
    payload: DiscordWebhookStatusReport,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    _authorize_connector(request, authorization)
    identity_repository(request).set_identity_status(
        deployment_id=payload.deployment_id,
        status=payload.status,
        last_error=payload.last_error,
    )


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
