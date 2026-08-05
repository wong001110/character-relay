"""Internal authenticated endpoints used by platform connector workers."""

from __future__ import annotations

import hmac
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from pydantic import SecretStr

from echo_masque.api.connector_schemas import (
    DiscordConnectorDeploymentView,
    DiscordConnectorEventBatch,
    DiscordConnectorHeartbeat,
    DiscordConnectorReplyView,
    DiscordIdentityMode,
    DiscordInboundMessage,
    DiscordInteractionClaimRequest,
    DiscordInteractionClaimView,
    DiscordInteractionRunComplete,
    DiscordInteractionSessionConnectorView,
    DiscordMessageRouteLookup,
    DiscordMessageRouteRegistration,
    DiscordMessageRouteView,
    DiscordParticipationMode,
    DiscordServerCatalogSync,
    DiscordStickerContent,
    DiscordStickerObservation,
    DiscordWebhookRegistration,
    DiscordWebhookRegistrationView,
    DiscordWebhookStatus,
    DiscordWebhookStatusReport,
)
from echo_masque.api.expression_schemas import (
    ExpressionCandidate,
    ExpressionContent,
    ExpressionNodeReport,
    ExpressionResolveRequest,
    ExpressionRetrievalView,
    ExpressionRetrieveRequest,
)
from echo_masque.config import Settings
from echo_masque.connector_runtime import ConnectorRuntimeError, DiscordConnectorRuntime
from echo_masque.credentials import CredentialVault
from echo_masque.persistence import (
    DeploymentRepository,
    DiscordIdentityRepository,
    ExpressionRepository,
    InteractionRepository,
    Repository,
)
from echo_masque.persistence.deployment_repository import decode_ids
from echo_masque.persistence.expression_models import DiscordExpressionSemanticRecord
from echo_masque.persistence.expression_repository import expression_key

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


def interaction_repository(request: Request) -> InteractionRepository:
    return cast(InteractionRepository, request.app.state.interaction_repository)


def expression_repository(request: Request) -> ExpressionRepository:
    return cast(ExpressionRepository, request.app.state.expression_repository)


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
        for server in payload.servers:
            interaction_repository(request).sync_sticker_catalog(
                connection_id=payload.connection_id,
                guild_id=server.guild_id,
                stickers=[item.model_dump() for item in server.stickers],
            )
            expression_repository(request).sync_server_resources(
                connection_id=payload.connection_id,
                guild_id=server.guild_id,
                emojis=[item.model_dump() for item in server.emojis],
                stickers=[item.model_dump() for item in server.stickers],
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
        replica_region=payload.replica_region,
        replica_id=payload.replica_id,
        gateway_ready=payload.gateway_ready,
        state_synchronized=payload.state_synchronized,
        visible_server_count=payload.visible_server_count,
        event_log_pending_count=payload.event_log_pending_count,
        event_log_last_error=payload.event_log_last_error,
        event_log_last_success_at=payload.event_log_last_success_at,
        event_log_last_recorded_at=payload.event_log_last_recorded_at,
        event_log_last_recorded_type=payload.event_log_last_recorded_type,
        event_log_sent_count=payload.event_log_sent_count,
        last_gateway_message_at=payload.last_gateway_message_at,
        last_gateway_message_id=payload.last_gateway_message_id,
        last_gateway_mentioned_bot=payload.last_gateway_mentioned_bot,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Discord connection not found.")


@router.post("/events", status_code=status.HTTP_204_NO_CONTENT)
def record_connector_events(
    payload: DiscordConnectorEventBatch,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    _authorize_connector(request, authorization)
    try:
        deployment_repository(request).record_discord_events(
            connection_id=payload.connection_id,
            events=[item.model_dump() for item in payload.events],
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Discord connection not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/stickers/resolve", response_model=DiscordStickerContent)
def resolve_discord_sticker(
    payload: DiscordStickerObservation,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> DiscordStickerContent:
    _authorize_connector(request, authorization)
    try:
        record = interaction_repository(request).resolve_sticker(**payload.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Discord connection not found.") from exc
    return DiscordStickerContent(
        sticker_id=record.sticker_id,
        name=record.name,
        description=record.description,
        tags=interaction_repository(request).sticker_tags(record),
        format_type=record.format_type,
        asset_url=record.asset_url,
        semantic_intent=record.semantic_intent,
        semantic_emotion=record.semantic_emotion,
        semantic_description=record.semantic_description,
        semantic_source=cast(
            Literal["manual", "discord_metadata", "unknown"],
            record.semantic_source,
        ),
        semantic_confidence=record.semantic_confidence,
    )





def expression_content(request: Request, record: object) -> ExpressionContent:
    item = cast("DiscordExpressionSemanticRecord", record)
    expressions = expression_repository(request)
    return ExpressionContent(
        resource_key=expression_key(item.resource_type, item.resource_id),
        resource_type=item.resource_type,  # type: ignore[arg-type]
        resource_id=item.resource_id,
        name=item.name,
        animated=item.animated,
        available=item.available,
        enabled=item.enabled,
        allowed_actions=expressions.allowed_actions(item),  # type: ignore[arg-type]
        semantic_intent=item.semantic_intent,
        semantic_emotion=item.semantic_emotion,
        semantic_description=item.semantic_description,
        semantic_source=item.semantic_source,  # type: ignore[arg-type]
        semantic_confidence=item.semantic_confidence,
        asset_url=item.asset_url,
        format_type=item.format_type,
    )


@router.post("/expressions/resolve", response_model=ExpressionContent)
def resolve_discord_expression(
    payload: ExpressionResolveRequest,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> ExpressionContent:
    _authorize_connector(request, authorization)
    try:
        record = expression_repository(request).resolve_resource(**payload.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Discord connection not found.") from exc
    return expression_content(request, record)


@router.post("/expressions/retrieve", response_model=ExpressionRetrievalView)
def retrieve_discord_expressions(
    payload: ExpressionRetrieveRequest,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> ExpressionRetrievalView:
    _authorize_connector(request, authorization)
    try:
        run, candidates = expression_repository(request).retrieve(**payload.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Expression workflow scope not found.") from exc
    return ExpressionRetrievalView(
        run_id=run.id,
        attempt=run.attempt_count,
        candidates=[ExpressionCandidate.model_validate(item) for item in candidates],
    )


@router.post(
    "/expressions/runs/{run_id}/nodes",
    status_code=status.HTTP_204_NO_CONTENT,
)
def record_expression_node(
    run_id: str,
    payload: ExpressionNodeReport,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    _authorize_connector(request, authorization)
    try:
        expression_repository(request).record_node(run_id=run_id, **payload.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Expression run not found.") from exc


@router.post("/interaction-sessions/claim", response_model=DiscordInteractionClaimView)
def claim_interaction_session(
    payload: DiscordInteractionClaimRequest,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> DiscordInteractionClaimView:
    _authorize_connector(request, authorization)
    interaction, run, claimed = interaction_repository(request).claim_session(
        **payload.model_dump()
    )
    if interaction is None or run is None:
        return DiscordInteractionClaimView()
    return DiscordInteractionClaimView(
        claimed=claimed,
        run_id=run.id,
        session=DiscordInteractionSessionConnectorView(
            id=interaction.id,
            participant_deployment_ids=interaction_repository(request).participant_ids(interaction),
            rounds_per_trigger=interaction.rounds_per_trigger,
            intensity=cast(
                Literal["light", "playful", "sharp"],
                interaction.intensity,
            ),
            target_user_id=interaction.target_user_id,
            target_display_name=interaction.target_display_name,
        ),
    )


@router.post(
    "/interaction-sessions/runs/{run_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def complete_interaction_run(
    run_id: str,
    payload: DiscordInteractionRunComplete,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    _authorize_connector(request, authorization)
    if not interaction_repository(request).complete_run(
        run_id=run_id,
        **payload.model_dump(),
    ):
        raise HTTPException(status_code=404, detail="Interaction run not found.")


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
