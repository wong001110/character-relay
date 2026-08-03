"""Owner-scoped deployment message identity endpoints."""

from typing import cast

from fastapi import APIRouter, HTTPException, Request, status

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.api.discord_identity_schemas import (
    DeploymentMessageIdentityUpdate,
    DeploymentMessageIdentityView,
)
from echo_masque.persistence import DiscordIdentityRepository

router = APIRouter(prefix="/api/deployment-identities", tags=["deployments"])


def identity_repository(request: Request) -> DiscordIdentityRepository:
    return cast(DiscordIdentityRepository, request.app.state.discord_identity_repository)


@router.get("", response_model=list[DeploymentMessageIdentityView])
def list_identities(
    request: Request,
    user: CurrentUserDependency,
) -> list[DeploymentMessageIdentityView]:
    return [
        DeploymentMessageIdentityView.from_record(item)
        for item in identity_repository(request).list_identities(user.id)
    ]


@router.put(
    "/{deployment_id}",
    response_model=DeploymentMessageIdentityView,
)
def update_identity(
    deployment_id: str,
    payload: DeploymentMessageIdentityUpdate,
    request: Request,
    user: CurrentUserDependency,
) -> DeploymentMessageIdentityView:
    try:
        record = identity_repository(request).upsert_identity(
            deployment_id=deployment_id,
            owner_id=user.id,
            mode=payload.mode,
            display_name=payload.display_name,
            avatar_url=str(payload.avatar_url) if payload.avatar_url is not None else "",
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Deployment not found.") from exc
    return DeploymentMessageIdentityView.from_record(record)


@router.delete("/{deployment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_identity(
    deployment_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> None:
    identity_repository(request).delete_identity(deployment_id, user.id)
