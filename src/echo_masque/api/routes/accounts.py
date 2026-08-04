"""Invitation, account, role, audit, and workspace-claim endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, cast

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from echo_masque.account_lifecycle import (
    AccountLifecycleService,
    LifecycleConflict,
)
from echo_masque.api.dependencies import AdminUserDependency, CurrentUserDependency
from echo_masque.persistence import AuthRepository, WorkspaceRepository
from echo_masque.persistence.models import (
    AuditEventRecord,
    InvitationRecord,
    UserRecord,
)
from echo_masque.workspace import WorkspaceArchive

router = APIRouter(tags=["accounts"])


class InvitationCreate(BaseModel):
    email: str | None = Field(default=None, min_length=3, max_length=320)
    role: Literal["user", "admin"] = "user"
    expires_in_days: int = Field(default=7, ge=1, le=30)


class InvitationView(BaseModel):
    id: str
    email: str | None
    role: Literal["user", "admin"]
    created_by: str | None
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    status: Literal["active", "accepted", "revoked", "expired"]

    @classmethod
    def from_record(cls, record: InvitationRecord) -> InvitationView:
        now = datetime.now(UTC)
        expires_at = _utc(record.expires_at)
        if record.accepted_at is not None:
            invitation_status = "accepted"
        elif record.revoked_at is not None:
            invitation_status = "revoked"
        elif expires_at <= now:
            invitation_status = "expired"
        else:
            invitation_status = "active"
        return cls(
            id=record.id,
            email=record.email,
            role=cast(Literal["user", "admin"], record.role),
            created_by=record.created_by,
            created_at=record.created_at,
            expires_at=record.expires_at,
            accepted_at=record.accepted_at,
            revoked_at=record.revoked_at,
            status=cast(
                Literal["active", "accepted", "revoked", "expired"],
                invitation_status,
            ),
        )


class InvitationCreated(BaseModel):
    invitation: InvitationView
    code: str


class AccountAdminView(BaseModel):
    id: str
    email: str
    display_name: str
    role: Literal["user", "admin"]
    is_active: bool
    created_at: datetime

    @classmethod
    def from_record(cls, record: UserRecord) -> AccountAdminView:
        return cls(
            id=record.id,
            email=record.email,
            display_name=record.display_name,
            role=cast(Literal["user", "admin"], record.role),
            is_active=record.is_active,
            created_at=record.created_at,
        )


class RoleUpdate(BaseModel):
    role: Literal["user", "admin"]


class AuditEventView(BaseModel):
    id: str
    actor_user_id: str | None
    action: str
    resource_type: str
    resource_id: str | None
    metadata: dict[str, object]
    created_at: datetime

    @classmethod
    def from_record(
        cls,
        record: AuditEventRecord,
        service: AccountLifecycleService,
    ) -> AuditEventView:
        return cls(
            id=record.id,
            actor_user_id=record.actor_user_id,
            action=record.action,
            resource_type=record.resource_type,
            resource_id=record.resource_id,
            metadata=service.audit_metadata(record),
            created_at=record.created_at,
        )


class AuditEventPage(BaseModel):
    items: list[AuditEventView]
    next_cursor: str | None
    has_more: bool


class LocalWorkspaceClaim(BaseModel):
    confirmation: str


class LifecycleResult(BaseModel):
    affected: dict[str, int]


class AccountDeleteRequest(BaseModel):
    email: str
    confirmation: str


def lifecycle_service(request: Request) -> AccountLifecycleService:
    return cast(AccountLifecycleService, request.app.state.account_lifecycle_service)


def auth_repository(request: Request) -> AuthRepository:
    return cast(AuthRepository, request.app.state.auth_repository)


def workspace_repository(request: Request) -> WorkspaceRepository:
    return cast(WorkspaceRepository, request.app.state.workspace_repository)


@router.post(
    "/api/admin/invitations",
    response_model=InvitationCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_invitation(
    payload: InvitationCreate,
    request: Request,
    admin: AdminUserDependency,
) -> InvitationCreated:
    record, code = lifecycle_service(request).create_invitation(
        actor_user_id=admin.id,
        email=payload.email,
        role=payload.role,
        expires_in_days=payload.expires_in_days,
    )
    return InvitationCreated(
        invitation=InvitationView.from_record(record),
        code=code,
    )


@router.get("/api/admin/invitations", response_model=list[InvitationView])
def list_invitations(
    request: Request,
    admin: AdminUserDependency,
) -> list[InvitationView]:
    return [
        InvitationView.from_record(item)
        for item in lifecycle_service(request).list_invitations()
    ]


@router.delete(
    "/api/admin/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_invitation(
    invitation_id: str,
    request: Request,
    admin: AdminUserDependency,
) -> None:
    if not lifecycle_service(request).revoke_invitation(
        invitation_id,
        actor_user_id=admin.id,
    ):
        raise HTTPException(status_code=404, detail="Active invitation not found.")


@router.get("/api/admin/users", response_model=list[AccountAdminView])
def list_users(
    request: Request,
    admin: AdminUserDependency,
) -> list[AccountAdminView]:
    return [
        AccountAdminView.from_record(item)
        for item in lifecycle_service(request).list_users()
    ]


@router.put("/api/admin/users/{user_id}/role", response_model=AccountAdminView)
def update_user_role(
    user_id: str,
    payload: RoleUpdate,
    request: Request,
    admin: AdminUserDependency,
) -> AccountAdminView:
    try:
        record = lifecycle_service(request).set_role(
            user_id,
            payload.role,
            actor_user_id=admin.id,
        )
    except LifecycleConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Active account not found.")
    return AccountAdminView.from_record(record)


@router.get("/api/admin/audit", response_model=list[AuditEventView])
def list_audit_events(
    request: Request,
    admin: AdminUserDependency,
    limit: int = 200,
) -> list[AuditEventView]:
    bounded = max(1, min(limit, 500))
    service = lifecycle_service(request)
    return [
        AuditEventView.from_record(item, service)
        for item in service.list_audit_events(limit=bounded)
    ]


@router.get("/api/admin/audit/page", response_model=AuditEventPage)
def paginate_audit_events(
    request: Request,
    admin: AdminUserDependency,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=1000),
) -> AuditEventPage:
    del admin
    service = lifecycle_service(request)
    try:
        records, next_cursor = service.list_audit_events_page(
            limit=limit,
            cursor=cursor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return AuditEventPage(
        items=[AuditEventView.from_record(item, service) for item in records],
        next_cursor=next_cursor,
        has_more=next_cursor is not None,
    )


@router.post("/api/admin/workspace/claim-local", response_model=LifecycleResult)
def claim_local_workspace(
    payload: LocalWorkspaceClaim,
    request: Request,
    admin: AdminUserDependency,
) -> LifecycleResult:
    if payload.confirmation != "CLAIM LOCAL WORKSPACE":
        raise HTTPException(status_code=422, detail="Confirmation phrase does not match.")
    try:
        affected = lifecycle_service(request).claim_local_workspace(
            actor_user_id=admin.id
        )
    except LifecycleConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return LifecycleResult(affected=affected)


@router.get("/api/account/export", response_model=WorkspaceArchive)
def export_account_workspace(
    request: Request,
    user: CurrentUserDependency,
) -> WorkspaceArchive:
    archive = workspace_repository(request).export_workspace(user.id).model_copy(
        update={"admin_runtime": None}
    )
    auth_repository(request).audit(
        actor_user_id=user.id,
        action="workspace.exported",
        resource_type="workspace",
        resource_id=user.id,
        metadata={
            "characters": len(archive.character_cards),
            "scenarios": len(archive.scenarios),
            "test_packs": len(archive.test_packs),
            "runs": len(archive.run_snapshots),
        },
    )
    return archive


@router.delete("/api/account", response_model=LifecycleResult)
def delete_account(
    payload: AccountDeleteRequest,
    request: Request,
    response: Response,
    user: CurrentUserDependency,
) -> LifecycleResult:
    if payload.confirmation != "DELETE MY ACCOUNT":
        raise HTTPException(status_code=422, detail="Confirmation phrase does not match.")
    if payload.email.casefold().strip() != user.email.casefold().strip():
        raise HTTPException(status_code=422, detail="Confirmation email does not match.")
    try:
        affected = lifecycle_service(request).delete_account(
            user.id,
            email=user.email,
        )
    except LifecycleConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    response.delete_cookie(
        key=request.app.state.settings.auth_cookie_name,
        path="/",
    )
    return LifecycleResult(affected=affected)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
