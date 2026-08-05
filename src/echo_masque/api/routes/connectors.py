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
    DiscordMessageRouteLookup,
    DiscordMessageRouteRegistration,
    DiscordMessageRouteView,
    DiscordParticipationMode,
    DiscordServerCatalogSync,
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
from echo_masque.persistence.deployment_repository import decode_ids

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
    deployments = deployment_repository(request)
    records = deployments.list_connector_deployments(
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
        scope = deployments.get_deployment_scope(record.id)
        profile = (
            deployments.get_server_profile_for_deployment(record.id) if scope is not None else None
        )
        if scope is not None and profile is None:
            continue
        identity = identities.get_identity(record.id, record.owner_id)
        identity_mode = cast(
            DiscordIdentityMode,
            identity.mode if identity is not None else "webhook",
        )
        identity_name = identity.display_name if identity is not None else card.display_name
        identity_avatar = identity.avatar_url if identity is not None else ""
        webhook_status = cast(
            DiscordWebhookStatus,
            identity.webhook_status if identity is not None else "pending",
        )
        binding = None
        if scope is None:
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
        excluded_channels = (
            decode_ids(profile.excluded_channel_ids_json)
            + decode_ids(scope.excluded_channel_ids_json)
            if scope is not None and profile is not None
            else []
        )
        excluded_categories = (
            decode_ids(profile.excluded_category_ids_json)
            + decode_ids(scope.excluded_category_ids_json)
            if scope is not None and profile is not None
            else []
        )
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
                server_profile_id=scope.server_profile_id if scope is not None else "",
                channel_scope_mode="all_except" if scope is not None else "exact",
                excluded_channel_ids=list(dict.fromkeys(excluded_channels)),
                excluded_category_ids=list(dict.fromkeys(excluded_categories)),
                participation_mode=cast(
                    DiscordParticipationMode,
                    record.participation_mode,
                ),
                version_label=record.version_label,
                status="active",
                identity_mode=identity_mode,
                identity_display_name=identity_name,
                identity_avatar_url=identity_avatar,
                address_aliases=identities.get_address_aliases(record.id, record.owner_id),
                webhook_status=webhook_status,
                webhook_id=binding.webhook_id if binding is not None else None,
                webhook_token=webhook_token,
            )
        )
    return views


@router.put("/server-catalog", status_code=status.HTTP_204_NO_CONTENT)
def sync_server_catalog(
    payload: DiscordServerCatalogSync,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    _authorize_connector(request, authorization)
    try:
        deployment_repository(request).sync_discord_server_catalog(
            connection_id=payload.connection_id,
            servers=[
                (
                    server.guild_id,
                    server.guild_name,
                    [channel.model_dump() for channel in server.channels],
                )
                for server in payload.servers
            ],
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Discord connection not found.") from exc


@router.put("/webhooks", response_model=DiscordWebhookRegistrationView)
def register_webhook(
    payload: DiscordWebhookRegistration,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> DiscordWebhookRegistrationView:
    _authorize_connector(request, authorization)
    deployments = deployment_repository(request)
    deployment = deployments.deployment_matches_discord_destination(
        payload.deployment_id,
        connection_id=payload.connection_id,
        guild_id=payload.workspace_id,
        channel_id=payload.channel_id,
        thread_id=payload.thread_id,
        category_id=payload.category_id,
    )
    if deployment is None:
        raise HTTPException(status_code=404, detail="Discord deployment not found.")

    identities = identity_repository(request)
    identity = identities.get_identity(deployment.id, deployment.owner_id)
    if identity is None:
        card = character_repository(request).get_character_card(
            deployment.character_card_id,
            deployment.owner_id,
        )
        identities.upsert_identity(
            deployment_id=deployment.id,
            owner_id=deployment.owner_id,
            mode="webhook",
            display_name=card.display_name if card is not None else "Character",
            avatar_url="",
        )

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


@router.put("/message-routes", status_code=status.HTTP_204_NO_CONTENT)
def register_message_routes(
    payload: DiscordMessageRouteRegistration,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    _authorize_connector(request, authorization)
    if any(not item.strip() or len(item) > 200 for item in payload.message_ids):
        raise HTTPException(status_code=422, detail="Invalid Discord message ID.")
    try:
        identity_repository(request).register_message_routes(
            connection_id=payload.connection_id,
            deployment_id=payload.deployment_id,
            workspace_id=payload.guild_id,
            channel_id=payload.channel_id,
            thread_id=payload.thread_id,
            webhook_id=payload.webhook_id,
            message_ids=payload.message_ids,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Discord deployment not found.") from exc


@router.get("/message-routes", response_model=DiscordMessageRouteLookup)
def resolve_message_route(
    request: Request,
    connection_id: str = Query(min_length=1, max_length=64),
    message_id: str = Query(min_length=1, max_length=200),
    authorization: Annotated[str | None, Header()] = None,
) -> DiscordMessageRouteLookup:
    _authorize_connector(request, authorization)
    record = identity_repository(request).resolve_message_route(
        connection_id=connection_id,
        message_id=message_id,
    )
    if record is None:
        return DiscordMessageRouteLookup()
    return DiscordMessageRouteLookup(
        route=DiscordMessageRouteView(
            message_id=record.message_id,
            deployment_id=record.deployment_id,
            character_card_id=record.character_card_id,
            channel_id=record.channel_id,
            thread_id=record.thread_id,
        )
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
