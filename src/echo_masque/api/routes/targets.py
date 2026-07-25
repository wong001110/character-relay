"""Target CRUD endpoints."""

from fastapi import APIRouter, HTTPException, Request, status

from echo_masque.api.schemas import TargetCreate, TargetView
from echo_masque.persistence import Repository

router = APIRouter(prefix="/api/targets", tags=["targets"])


def repository(request: Request) -> Repository:
    return request.app.state.repository


@router.get("", response_model=list[TargetView])
def list_targets(request: Request) -> list[TargetView]:
    return [TargetView.from_record(item) for item in repository(request).list_targets()]


@router.post("", response_model=TargetView, status_code=status.HTTP_201_CREATED)
def create_target(payload: TargetCreate, request: Request) -> TargetView:
    record = repository(request).create_target(
        name=payload.name,
        target_kind=payload.target_kind,
        config=payload.config,
    )
    return TargetView.from_record(record)


@router.get("/{target_id}", response_model=TargetView)
def get_target(target_id: str, request: Request) -> TargetView:
    record = repository(request).get_target(target_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Target not found.")
    return TargetView.from_record(record)


@router.delete("/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_target(target_id: str, request: Request) -> None:
    if not repository(request).delete_target(target_id):
        raise HTTPException(status_code=409, detail="Target cannot be deleted.")
