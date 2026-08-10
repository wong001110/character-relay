"""Invitation, account, role, audit, workspace-claim, and Key Group endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, cast

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from echo_masque.account_lifecycle import (
    AccountLifecycleService,
    LifecycleConflict,
)
from echo_masque.api.dependencies import (
    AdminUserDependency,
    CurrentUserDependency,
    SuperAdminUserDependency,
)
from echo_masque.auth import SYSTEM_RUNTIME_USER_ID
from echo_masque.credentials import CredentialVault, CredentialVaultUnavailable
from echo_masque.persistence import (
    AuthRepository,
    Database,
    KeyGroupRepository,
    Repository,
    WorkspaceRepository,
)
from echo_masque.persistence.key_group_models import (
    CharacterKeyGroupAssignmentRecord,
    ProviderKeyGroupRecord,
)
from echo_masque.persistence.key_group_repository import default_models
from echo_masque.persistence.models import (
    AuditEventRecord,
    InvitationRecord,
    UserRecord,
)
from echo_masque.synthetic_test_accounts import (
    SyntheticTestAccountError,
    SyntheticTestAccountService,
)
from echo_masque.workspace import WorkspaceArchive

router = APIRouter(tags=["accounts"])
_ACCOUNT_SECURITY_LIMIT = 10
KeyGroupCapability = Literal["character", "media", "image_generation"]


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


class SyntheticTestPurgeResult(BaseModel):
    deleted_count: int
    user_ids: list[str]


class ProviderKeyGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    provider: str = Field(min_length=1, max_length=80)
    base_url: str = Field(default="", max_length=500)
    api_key: SecretStr
    default_models: dict[KeyGroupCapability, str] = Field(default_factory=dict)


class ProviderKeyGroupUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    provider: str = Field(min_length=1, max_length=80)
    base_url: str = Field(default="", max_length=500)
    api_key: SecretStr | None = None
    default_models: dict[KeyGroupCapability, str] = Field(default_factory=dict)


class ProviderKeyGroupView(BaseModel):
    id: str
    name: str
    provider: str
    base_url: str
    default_models: dict[str, str]
    credential_configured: bool
    created_at: datetime
    updated_at: datetime


class KeyGroupAssignmentConfigure(BaseModel):
    key_group_id: str = Field(min_length=1, max_length=64)
    model_override: str | None = Field(default=None, max_length=200)


class KeyGroupAssignmentView(BaseModel):
    character_card_id: str
    capability: KeyGroupCapability
    key_group_id: str
    key_group_name: str
    provider: str
    base_url: str
    model_override: str | None
    effective_model: str


class KeyGroupBulkApply(BaseModel):
    character_card_ids: list[str] = Field(min_length=1, max_length=100)
    capabilities: list[KeyGroupCapability] = Field(min_length=1, max_length=3)
    model_overrides: dict[KeyGroupCapability, str] = Field(default_factory=dict)


class KeyGroupBulkApplyResult(BaseModel):
    applied: int


def lifecycle_service(request: Request) -> AccountLifecycleService:
    return cast(AccountLifecycleService, request.app.state.account_lifecycle_service)


def auth_repository(request: Request) -> AuthRepository:
    return cast(AuthRepository, request.app.state.auth_repository)


def workspace_repository(request: Request) -> WorkspaceRepository:
    return cast(WorkspaceRepository, request.app.state.workspace_repository)


def database(request: Request) -> Database:
    return cast(Database, request.app.state.database)


def character_repository(request: Request) -> Repository:
    return cast(Repository, request.app.state.repository)


def key_group_repository(request: Request) -> KeyGroupRepository:
    return KeyGroupRepository(database(request))


def credential_vault(request: Request) -> CredentialVault:
    store = request.app.state.credential_store
    if not isinstance(store, CredentialVault):
        raise HTTPException(status_code=503, detail="Encrypted Credential Vault is unavailable.")
    return store


def synthetic_test_accounts(request: Request) -> SyntheticTestAccountService:
    return SyntheticTestAccountService(database(request), lifecycle_service(request))


def _key_group_view(
    request: Request,
    user_id: str,
    record: ProviderKeyGroupRecord,
) -> ProviderKeyGroupView:
    return ProviderKeyGroupView(
        id=record.id,
        name=record.name,
        provider=record.provider,
        base_url=record.base_url,
        default_models=default_models(record),
        credential_configured=credential_vault(request).has_scope(
            owner_id=user_id,
            scope_kind=CredentialVault.key_group_scope_kind,
            scope_id=record.id,
        ),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _assignment_view(
    request: Request,
    user_id: str,
    record: CharacterKeyGroupAssignmentRecord,
) -> KeyGroupAssignmentView:
    resolved = key_group_repository(request).resolve(
        owner_id=user_id,
        character_card_id=record.character_card_id,
        capability=record.capability,
    )
    if resolved is None:
        raise HTTPException(status_code=404, detail="Key Group assignment is no longer valid.")
    return KeyGroupAssignmentView(
        character_card_id=record.character_card_id,
        capability=cast(KeyGroupCapability, record.capability),
        key_group_id=resolved.group.id,
        key_group_name=resolved.group.name,
        provider=resolved.group.provider,
        base_url=resolved.group.base_url,
        model_override=record.model_override,
        effective_model=resolved.model,
    )


def _require_owned_character(request: Request, owner_id: str, card_id: str) -> None:
    if character_repository(request).get_character_card(card_id, owner_id) is None:
        raise HTTPException(status_code=404, detail="Character Card not found.")


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
    del admin
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
    """Return only the ten newest active accounts for Account & Security."""

    del admin
    with database(request).session() as session:
        records = list(
            session.scalars(
                select(UserRecord)
                .where(
                    UserRecord.id != SYSTEM_RUNTIME_USER_ID,
                    UserRecord.is_active.is_(True),
                )
                .order_by(UserRecord.created_at.desc(), UserRecord.id.desc())
                .limit(_ACCOUNT_SECURITY_LIMIT)
            )
        )
    return [AccountAdminView.from_record(item) for item in records]


@router.delete(
    "/api/admin/synthetic-test-users",
    response_model=SyntheticTestPurgeResult,
)
def purge_legacy_synthetic_test_users(
    request: Request,
    user: SuperAdminUserDependency,
) -> SyntheticTestPurgeResult:
    deleted_ids = synthetic_test_accounts(request).purge_legacy()
    auth_repository(request).audit(
        actor_user_id=user.id,
        action="synthetic_test_accounts.purged",
        resource_type="user",
        metadata={"deleted_count": len(deleted_ids)},
    )
    return SyntheticTestPurgeResult(
        deleted_count=len(deleted_ids),
        user_ids=deleted_ids,
    )


@router.delete(
    "/api/admin/synthetic-test-users/{user_id}",
    response_model=SyntheticTestPurgeResult,
)
def hard_delete_synthetic_test_user(
    user_id: str,
    request: Request,
    user: SuperAdminUserDependency,
) -> SyntheticTestPurgeResult:
    try:
        deleted = synthetic_test_accounts(request).hard_delete(user_id)
    except SyntheticTestAccountError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LifecycleConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Synthetic test account not found.")
    auth_repository(request).audit(
        actor_user_id=user.id,
        action="synthetic_test_account.hard_deleted",
        resource_type="user",
        resource_id=user_id,
    )
    return SyntheticTestPurgeResult(deleted_count=1, user_ids=[user_id])


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
    del admin
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


@router.get("/api/account/key-groups", response_model=list[ProviderKeyGroupView])
def list_provider_key_groups(
    request: Request,
    user: CurrentUserDependency,
) -> list[ProviderKeyGroupView]:
    return [
        _key_group_view(request, user.id, item)
        for item in key_group_repository(request).list_groups(user.id)
    ]


@router.post(
    "/api/account/key-groups",
    response_model=ProviderKeyGroupView,
    status_code=status.HTTP_201_CREATED,
)
def create_provider_key_group(
    payload: ProviderKeyGroupCreate,
    request: Request,
    user: CurrentUserDependency,
) -> ProviderKeyGroupView:
    repo = key_group_repository(request)
    try:
        record = repo.create_group(
            owner_id=user.id,
            name=payload.name,
            provider=payload.provider,
            base_url=payload.base_url,
            default_models=payload.default_models,
        )
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="A Key Group with this name already exists.") from exc
    try:
        credential_vault(request).set_scope(
            owner_id=user.id,
            scope_kind=CredentialVault.key_group_scope_kind,
            scope_id=record.id,
            value=payload.api_key,
            actor_user_id=user.id,
            resource_type="provider_key_group",
        )
    except CredentialVaultUnavailable as exc:
        repo.delete_group(owner_id=user.id, group_id=record.id)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    auth_repository(request).audit(
        actor_user_id=user.id,
        action="provider_key_group.created",
        resource_type="provider_key_group",
        resource_id=record.id,
        metadata={"provider": record.provider},
    )
    return _key_group_view(request, user.id, record)


@router.put("/api/account/key-groups/{group_id}", response_model=ProviderKeyGroupView)
def update_provider_key_group(
    group_id: str,
    payload: ProviderKeyGroupUpdate,
    request: Request,
    user: CurrentUserDependency,
) -> ProviderKeyGroupView:
    repo = key_group_repository(request)
    if repo.get_group(user.id, group_id) is None:
        raise HTTPException(status_code=404, detail="Key Group not found.")
    if payload.api_key is not None:
        try:
            credential_vault(request).set_scope(
                owner_id=user.id,
                scope_kind=CredentialVault.key_group_scope_kind,
                scope_id=group_id,
                value=payload.api_key,
                actor_user_id=user.id,
                resource_type="provider_key_group",
            )
        except CredentialVaultUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        record = repo.update_group(
            owner_id=user.id,
            group_id=group_id,
            name=payload.name,
            provider=payload.provider,
            base_url=payload.base_url,
            default_models=payload.default_models,
        )
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="A Key Group with this name already exists.") from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Key Group not found.")
    auth_repository(request).audit(
        actor_user_id=user.id,
        action="provider_key_group.updated",
        resource_type="provider_key_group",
        resource_id=group_id,
        metadata={"provider": record.provider},
    )
    return _key_group_view(request, user.id, record)


@router.delete("/api/account/key-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_provider_key_group(
    group_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> None:
    repo = key_group_repository(request)
    if not repo.delete_group(owner_id=user.id, group_id=group_id):
        raise HTTPException(status_code=404, detail="Key Group not found.")
    credential_vault(request).delete_scope(
        owner_id=user.id,
        scope_kind=CredentialVault.key_group_scope_kind,
        scope_id=group_id,
        actor_user_id=user.id,
        resource_type="provider_key_group",
    )
    auth_repository(request).audit(
        actor_user_id=user.id,
        action="provider_key_group.deleted",
        resource_type="provider_key_group",
        resource_id=group_id,
    )


@router.get(
    "/api/account/key-groups/assignments/{card_id}",
    response_model=list[KeyGroupAssignmentView],
)
def list_key_group_assignments(
    card_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> list[KeyGroupAssignmentView]:
    _require_owned_character(request, user.id, card_id)
    return [
        _assignment_view(request, user.id, item)
        for item in key_group_repository(request).list_assignments(
            owner_id=user.id,
            character_card_id=card_id,
        )
    ]


@router.put(
    "/api/account/key-groups/assignments/{card_id}/{capability}",
    response_model=KeyGroupAssignmentView,
)
def configure_key_group_assignment(
    card_id: str,
    capability: KeyGroupCapability,
    payload: KeyGroupAssignmentConfigure,
    request: Request,
    user: CurrentUserDependency,
) -> KeyGroupAssignmentView:
    _require_owned_character(request, user.id, card_id)
    try:
        record = key_group_repository(request).set_assignment(
            owner_id=user.id,
            character_card_id=card_id,
            capability=capability,
            key_group_id=payload.key_group_id,
            model_override=payload.model_override,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    auth_repository(request).audit(
        actor_user_id=user.id,
        action="provider_key_group.assigned",
        resource_type="character_card",
        resource_id=card_id,
        metadata={"capability": capability, "key_group_id": payload.key_group_id},
    )
    return _assignment_view(request, user.id, record)


@router.delete(
    "/api/account/key-groups/assignments/{card_id}/{capability}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def clear_key_group_assignment(
    card_id: str,
    capability: KeyGroupCapability,
    request: Request,
    user: CurrentUserDependency,
) -> None:
    _require_owned_character(request, user.id, card_id)
    key_group_repository(request).delete_assignment(
        owner_id=user.id,
        character_card_id=card_id,
        capability=capability,
    )
    auth_repository(request).audit(
        actor_user_id=user.id,
        action="provider_key_group.unassigned",
        resource_type="character_card",
        resource_id=card_id,
        metadata={"capability": capability},
    )


@router.post(
    "/api/account/key-groups/{group_id}/apply",
    response_model=KeyGroupBulkApplyResult,
)
def bulk_apply_key_group(
    group_id: str,
    payload: KeyGroupBulkApply,
    request: Request,
    user: CurrentUserDependency,
) -> KeyGroupBulkApplyResult:
    repo = key_group_repository(request)
    if repo.get_group(user.id, group_id) is None:
        raise HTTPException(status_code=404, detail="Key Group not found.")
    card_ids = list(dict.fromkeys(payload.character_card_ids))
    capabilities = list(dict.fromkeys(payload.capabilities))
    for card_id in card_ids:
        _require_owned_character(request, user.id, card_id)
    applied = 0
    for card_id in card_ids:
        for capability in capabilities:
            repo.set_assignment(
                owner_id=user.id,
                character_card_id=card_id,
                capability=capability,
                key_group_id=group_id,
                model_override=payload.model_overrides.get(capability),
            )
            applied += 1
    auth_repository(request).audit(
        actor_user_id=user.id,
        action="provider_key_group.bulk_applied",
        resource_type="provider_key_group",
        resource_id=group_id,
        metadata={"character_count": len(card_ids), "assignment_count": applied},
    )
    return KeyGroupBulkApplyResult(applied=applied)


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
