"""Owner-scoped Target CRUD endpoints."""

from typing import cast

from fastapi import APIRouter, HTTPException, Request, status

from echo_masque.api.dependencies import (
    CurrentUserDependency,
    OptionalAuthContextDependency,
)
from echo_masque.api.schemas import TargetCreate, TargetView
from echo_masque.persistence import Repository, TargetAccessRepository

router = APIRouter(prefix="/api/targets", tags=["targets"])


def repository(request: Request) -> Repository:
    return cast(Repository, request.app.state.repository)


def target_access(request: Request) -> TargetAccessRepository:
    return cast(TargetAccessRepository, request.app.state.target_access_repository)


@router.get("", response_model=list[TargetView])
def list_targets(
    request: Request,
    context: OptionalAuthContextDependency,
) -> list[TargetView]:
    owner_id = context.user.id if context is not None else None
    return [
        TargetView.from_record(item)
        for item in target_access(request).list_visible(owner_id)
    ]


@router.post("", response_model=TargetView, status_code=status.HTTP_201_CREATED)
def create_target(
    payload: TargetCreate,
    request: Request,
    user: CurrentUserDependency,
) -> TargetView:
    record = repository(request).create_target(
        name=payload.name,
        target_kind=payload.target_kind,
        config=payload.config,
    )
    target_access(request).assign(owner_id=user.id, target_id=record.id)
    return TargetView.from_record(record)


@router.get("/{target_id}", response_model=TargetView)
def get_target(
    target_id: str,
    request: Request,
    context: OptionalAuthContextDependency,
) -> TargetView:
    is_visible = target_id.startswith("demo-") or (
        context is not None
        and target_access(request).can_access(
            owner_id=context.user.id,
            target_id=target_id,
        )
    )
    record = repository(request).get_target(target_id) if is_visible else None
    if record is None:
        raise HTTPException(status_code=404, detail="Target not found.")
    return TargetView.from_record(record)


@router.delete("/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_target(
    target_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> None:
    access = target_access(request)
    if not access.can_access(owner_id=user.id, target_id=target_id):
        raise HTTPException(status_code=404, detail="Target not found.")
    access.remove(owner_id=user.id, target_id=target_id)
    if not repository(request).delete_target(target_id):
        access.assign(owner_id=user.id, target_id=target_id)
        raise HTTPException(status_code=409, detail="Target cannot be deleted.")
