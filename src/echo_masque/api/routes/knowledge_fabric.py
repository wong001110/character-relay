"""Phase 2 administration APIs for the separate Knowledge Fabric authority."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, HTTPException, Request, status

from echo_masque.api.dependencies import (
    CurrentUserDependency,
    SuperAdminUserDependency,
    is_super_admin,
)
from echo_masque.api.knowledge_fabric_schemas import (
    KnowledgeAccessGrantView,
    KnowledgeCorpusCreate,
    KnowledgeCorpusView,
    KnowledgeExternalSourceScheduleUpdate,
    KnowledgeExternalSourceScheduleView,
    KnowledgeGrantUpdate,
    KnowledgeOverlayPolicyUpdate,
    KnowledgeOverlayPolicyView,
    KnowledgeServerAdministratorView,
    KnowledgeServerScopeCreate,
    KnowledgeServerScopeView,
    KnowledgeSourceCreate,
    KnowledgeSourceView,
    encode_profile,
)
from echo_masque.knowledge_fabric_policy import (
    may_access_server_scope,
    may_manage_global_library,
)
from echo_masque.persistence import AuthRepository
from echo_masque.persistence.knowledge_fabric_external_schedule_repository import (
    KnowledgeFabricExternalScheduleRepository,
)
from echo_masque.persistence.knowledge_fabric_models import (
    KnowledgeCorpusRecord,
    KnowledgeServerScopeRecord,
)
from echo_masque.persistence.knowledge_fabric_repository import (
    OWNER_SERVER,
    OWNER_SYSTEM,
    VISIBILITY_GLOBAL,
    KnowledgeFabricRepository,
)
from echo_masque.public_demo import is_public_demo_email

router = APIRouter(prefix="/api/knowledge-fabric", tags=["knowledge-fabric"])


def _fabric(request: Request) -> KnowledgeFabricRepository:
    return cast(KnowledgeFabricRepository, request.app.state.knowledge_fabric_repository)


def _auth(request: Request) -> AuthRepository:
    return cast(AuthRepository, request.app.state.auth_repository)


def _external_schedules(request: Request) -> KnowledgeFabricExternalScheduleRepository:
    return cast(
        KnowledgeFabricExternalScheduleRepository,
        request.app.state.knowledge_fabric_external_schedule_repository,
    )


def _is_public_demo(request: Request, email: str) -> bool:
    return bool(request.app.state.settings.public_demo_enabled and is_public_demo_email(email))


def _can_manage_global(request: Request, user: CurrentUserDependency) -> bool:
    return may_manage_global_library(
        is_super_admin=is_super_admin(user, request.app.state.settings),
        is_public_demo=_is_public_demo(request, user.email),
    )


def _require_global_manager(request: Request, user: CurrentUserDependency) -> None:
    if not _can_manage_global(request, user):
        raise HTTPException(
            status_code=403,
            detail="Knowledge Fabric administration is unavailable.",
        )


def _scope_for_actor(
    request: Request,
    *,
    scope_id: str,
    user: CurrentUserDependency,
) -> KnowledgeServerScopeRecord:
    scope = _fabric(request).get_server_scope(scope_id)
    if scope is None:
        raise HTTPException(status_code=404, detail="Knowledge Server scope not found.")
    if not may_access_server_scope(
        is_super_admin=is_super_admin(user, request.app.state.settings),
        is_explicit_administrator=_fabric(request).is_server_administrator(
            server_scope_id=scope.id,
            user_id=user.id,
        ),
        is_public_demo=_is_public_demo(request, user.email),
    ):
        raise HTTPException(status_code=404, detail="Knowledge Server scope not found.")
    return scope


def _global_corpus_or_404(request: Request, corpus_id: str) -> KnowledgeCorpusRecord:
    corpus = _fabric(request).get_corpus(corpus_id)
    if (
        corpus is None
        or corpus.owner_type != OWNER_SYSTEM
        or corpus.visibility != VISIBILITY_GLOBAL
        or corpus.status != "active"
    ):
        raise HTTPException(status_code=404, detail="Knowledge Corpus not found.")
    return corpus


def _server_local_corpus_or_404(
    request: Request,
    *,
    scope_id: str,
    corpus_id: str,
) -> KnowledgeCorpusRecord:
    corpus = _fabric(request).get_corpus(corpus_id)
    if corpus is None or corpus.owner_type != OWNER_SERVER or corpus.owner_id != scope_id:
        raise HTTPException(status_code=404, detail="Knowledge Corpus not found.")
    return corpus


def _audit(
    request: Request,
    *,
    actor_user_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    metadata: dict[str, object],
) -> None:
    _auth(request).audit(
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata=metadata,
    )


@router.get("/server-scopes", response_model=list[KnowledgeServerScopeView])
def list_server_scopes(
    request: Request,
    user: CurrentUserDependency,
) -> list[KnowledgeServerScopeView]:
    if _is_public_demo(request, user.email):
        return []
    repository = _fabric(request)
    if is_super_admin(user, request.app.state.settings):
        records = repository.list_server_scopes()
    else:
        records = repository.list_server_scopes_for_administrator(user.id)
    return [KnowledgeServerScopeView.from_record(record) for record in records]


@router.post(
    "/admin/server-scopes",
    response_model=KnowledgeServerScopeView,
    status_code=status.HTTP_201_CREATED,
)
def bootstrap_server_scope(
    payload: KnowledgeServerScopeCreate,
    request: Request,
    user: SuperAdminUserDependency,
) -> KnowledgeServerScopeView:
    _require_global_manager(request, user)
    record = _fabric(request).ensure_server_scope(**payload.model_dump())
    _audit(
        request,
        actor_user_id=user.id,
        action="knowledge_fabric.server_scope_bootstrapped",
        resource_type="knowledge_server_scope",
        resource_id=record.id,
        metadata={
            "platform": record.platform,
            "connection_id": record.connection_id,
            "workspace_id": record.workspace_id,
        },
    )
    return KnowledgeServerScopeView.from_record(record)


@router.get(
    "/admin/server-scopes/{scope_id}/administrators",
    response_model=list[KnowledgeServerAdministratorView],
)
def list_server_administrators(
    scope_id: str,
    request: Request,
    user: SuperAdminUserDependency,
) -> list[KnowledgeServerAdministratorView]:
    _require_global_manager(request, user)
    if _fabric(request).get_server_scope(scope_id) is None:
        raise HTTPException(status_code=404, detail="Knowledge Server scope not found.")
    return [
        KnowledgeServerAdministratorView(user_id=record.user_id, created_at=record.created_at)
        for record in _fabric(request).list_server_administrators(scope_id)
    ]


@router.put(
    "/admin/server-scopes/{scope_id}/administrators/{user_id}",
    response_model=KnowledgeServerAdministratorView,
)
def add_server_administrator(
    scope_id: str,
    user_id: str,
    request: Request,
    user: SuperAdminUserDependency,
) -> KnowledgeServerAdministratorView:
    _require_global_manager(request, user)
    if _fabric(request).get_server_scope(scope_id) is None:
        raise HTTPException(status_code=404, detail="Knowledge Server scope not found.")
    target = _auth(request).get_user(user_id)
    if target is None or not target.is_active:
        raise HTTPException(status_code=404, detail="Active account not found.")
    record = _fabric(request).add_server_administrator(server_scope_id=scope_id, user_id=user_id)
    _audit(
        request,
        actor_user_id=user.id,
        action="knowledge_fabric.server_administrator_added",
        resource_type="knowledge_server_scope",
        resource_id=scope_id,
        metadata={"member_user_id": user_id},
    )
    return KnowledgeServerAdministratorView(user_id=record.user_id, created_at=record.created_at)


@router.delete(
    "/admin/server-scopes/{scope_id}/administrators/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_server_administrator(
    scope_id: str,
    user_id: str,
    request: Request,
    user: SuperAdminUserDependency,
) -> None:
    _require_global_manager(request, user)
    if _fabric(request).get_server_scope(scope_id) is None:
        raise HTTPException(status_code=404, detail="Knowledge Server scope not found.")
    if not _fabric(request).remove_server_administrator(server_scope_id=scope_id, user_id=user_id):
        raise HTTPException(status_code=404, detail="Knowledge Server administrator not found.")
    _audit(
        request,
        actor_user_id=user.id,
        action="knowledge_fabric.server_administrator_removed",
        resource_type="knowledge_server_scope",
        resource_id=scope_id,
        metadata={"member_user_id": user_id},
    )


@router.post(
    "/admin/corpora",
    response_model=KnowledgeCorpusView,
    status_code=status.HTTP_201_CREATED,
)
def create_system_global_corpus(
    payload: KnowledgeCorpusCreate,
    request: Request,
    user: SuperAdminUserDependency,
) -> KnowledgeCorpusView:
    _require_global_manager(request, user)
    record = _fabric(request).create_system_global_corpus(
        **payload.model_dump(),
        status="active",
    )
    _audit(
        request,
        actor_user_id=user.id,
        action="knowledge_fabric.system_global_corpus_created",
        resource_type="knowledge_corpus",
        resource_id=record.id,
        metadata={"owner_type": record.owner_type, "visibility": record.visibility},
    )
    return KnowledgeCorpusView.from_record(record)


@router.get("/admin/corpora", response_model=list[KnowledgeCorpusView])
def list_system_global_corpora(
    request: Request,
    user: SuperAdminUserDependency,
) -> list[KnowledgeCorpusView]:
    _require_global_manager(request, user)
    return [
        KnowledgeCorpusView.from_record(record)
        for record in _fabric(request).list_system_global_corpora()
    ]


@router.post(
    "/server-scopes/{scope_id}/corpora",
    response_model=KnowledgeCorpusView,
    status_code=status.HTTP_201_CREATED,
)
def create_server_local_corpus(
    scope_id: str,
    payload: KnowledgeCorpusCreate,
    request: Request,
    user: CurrentUserDependency,
) -> KnowledgeCorpusView:
    scope = _scope_for_actor(request, scope_id=scope_id, user=user)
    record = _fabric(request).create_server_local_corpus(
        server_scope_id=scope.id,
        **payload.model_dump(),
        status="active",
    )
    _audit(
        request,
        actor_user_id=user.id,
        action="knowledge_fabric.server_local_corpus_created",
        resource_type="knowledge_corpus",
        resource_id=record.id,
        metadata={"server_scope_id": scope.id},
    )
    return KnowledgeCorpusView.from_record(record)


@router.get(
    "/server-scopes/{scope_id}/corpora",
    response_model=list[KnowledgeCorpusView],
)
def list_effective_corpora(
    scope_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> list[KnowledgeCorpusView]:
    scope = _scope_for_actor(request, scope_id=scope_id, user=user)
    return [
        KnowledgeCorpusView.from_record(item.corpus, overlay_mode=item.overlay_mode)
        for item in _fabric(request).list_effective_corpora(scope.id)
    ]


@router.get(
    "/server-scopes/{scope_id}/available-global-corpora",
    response_model=list[KnowledgeCorpusView],
)
def list_available_system_global_corpora(
    scope_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> list[KnowledgeCorpusView]:
    _scope_for_actor(request, scope_id=scope_id, user=user)
    return [
        KnowledgeCorpusView.from_record(record)
        for record in _fabric(request).list_available_system_global_corpora()
    ]


@router.put(
    "/server-scopes/{scope_id}/global-corpora/{corpus_id}/grant",
    response_model=KnowledgeAccessGrantView,
)
def set_server_global_grant(
    scope_id: str,
    corpus_id: str,
    payload: KnowledgeGrantUpdate,
    request: Request,
    user: CurrentUserDependency,
) -> KnowledgeAccessGrantView:
    scope = _scope_for_actor(request, scope_id=scope_id, user=user)
    _global_corpus_or_404(request, corpus_id)
    record = _fabric(request).set_server_global_grant(
        server_scope_id=scope.id,
        corpus_id=corpus_id,
        enabled=payload.enabled,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Knowledge Corpus not found.")
    _audit(
        request,
        actor_user_id=user.id,
        action="knowledge_fabric.server_global_grant_updated",
        resource_type="knowledge_access_grant",
        resource_id=record.id,
        metadata={
            "server_scope_id": scope.id,
            "corpus_id": corpus_id,
            "enabled": payload.enabled,
        },
    )
    return KnowledgeAccessGrantView.from_record(record)


@router.put(
    "/server-scopes/{scope_id}/global-corpora/{corpus_id}/overlay",
    response_model=KnowledgeOverlayPolicyView,
)
def set_server_overlay_policy(
    scope_id: str,
    corpus_id: str,
    payload: KnowledgeOverlayPolicyUpdate,
    request: Request,
    user: CurrentUserDependency,
) -> KnowledgeOverlayPolicyView:
    scope = _scope_for_actor(request, scope_id=scope_id, user=user)
    _global_corpus_or_404(request, corpus_id)
    try:
        record = _fabric(request).set_overlay_policy(
            server_scope_id=scope.id,
            corpus_id=corpus_id,
            mode=payload.mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _audit(
        request,
        actor_user_id=user.id,
        action="knowledge_fabric.server_overlay_updated",
        resource_type="knowledge_overlay_policy",
        resource_id=record.id,
        metadata={"server_scope_id": scope.id, "corpus_id": corpus_id, "mode": record.mode},
    )
    return KnowledgeOverlayPolicyView.from_record(record)


@router.post(
    "/admin/corpora/{corpus_id}/sources",
    response_model=KnowledgeSourceView,
    status_code=status.HTTP_201_CREATED,
)
def create_global_source(
    corpus_id: str,
    payload: KnowledgeSourceCreate,
    request: Request,
    user: SuperAdminUserDependency,
) -> KnowledgeSourceView:
    _require_global_manager(request, user)
    _global_corpus_or_404(request, corpus_id)
    record = _fabric(request).create_source(
        corpus_id=corpus_id,
        source_type=payload.source_type,
        locator=payload.locator,
        access_profile_json="{}",
        parser_profile_json=encode_profile(payload.parser_profile),
        sync_policy_json=encode_profile(payload.sync_policy),
        freshness_policy_json=encode_profile(payload.freshness_policy),
        authority_profile=payload.authority_profile,
    )
    _audit(
        request,
        actor_user_id=user.id,
        action="knowledge_fabric.global_source_registered",
        resource_type="knowledge_source",
        resource_id=record.id,
        metadata={"corpus_id": corpus_id, "source_type": record.source_type},
    )
    return KnowledgeSourceView.from_record(record)


@router.get(
    "/admin/corpora/{corpus_id}/sources",
    response_model=list[KnowledgeSourceView],
)
def list_global_sources(
    corpus_id: str,
    request: Request,
    user: SuperAdminUserDependency,
) -> list[KnowledgeSourceView]:
    _require_global_manager(request, user)
    _global_corpus_or_404(request, corpus_id)
    return [
        KnowledgeSourceView.from_record(record)
        for record in _fabric(request).list_sources(corpus_id)
    ]


@router.put(
    "/admin/sources/{source_id}/external-sync-schedule",
    response_model=KnowledgeExternalSourceScheduleView,
)
def configure_external_source_schedule(
    source_id: str,
    payload: KnowledgeExternalSourceScheduleUpdate,
    request: Request,
    user: SuperAdminUserDependency,
) -> KnowledgeExternalSourceScheduleView:
    _require_global_manager(request, user)
    try:
        record = _external_schedules(request).configure(
            source_id=source_id,
            enabled=payload.enabled,
            interval_seconds=payload.interval_seconds,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Knowledge Source not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _audit(
        request,
        actor_user_id=user.id,
        action="knowledge_fabric.external_sync_schedule_updated",
        resource_type="knowledge_source",
        resource_id=source_id,
        metadata={"enabled": record.enabled, "interval_seconds": record.interval_seconds},
    )
    return KnowledgeExternalSourceScheduleView.from_record(record)


@router.post(
    "/server-scopes/{scope_id}/corpora/{corpus_id}/sources",
    response_model=KnowledgeSourceView,
    status_code=status.HTTP_201_CREATED,
)
def create_server_local_source(
    scope_id: str,
    corpus_id: str,
    payload: KnowledgeSourceCreate,
    request: Request,
    user: CurrentUserDependency,
) -> KnowledgeSourceView:
    scope = _scope_for_actor(request, scope_id=scope_id, user=user)
    _server_local_corpus_or_404(request, scope_id=scope.id, corpus_id=corpus_id)
    record = _fabric(request).create_source(
        corpus_id=corpus_id,
        source_type=payload.source_type,
        locator=payload.locator,
        access_profile_json="{}",
        parser_profile_json=encode_profile(payload.parser_profile),
        sync_policy_json=encode_profile(payload.sync_policy),
        freshness_policy_json=encode_profile(payload.freshness_policy),
        authority_profile=payload.authority_profile,
    )
    _audit(
        request,
        actor_user_id=user.id,
        action="knowledge_fabric.server_local_source_registered",
        resource_type="knowledge_source",
        resource_id=record.id,
        metadata={
            "server_scope_id": scope.id,
            "corpus_id": corpus_id,
            "source_type": record.source_type,
        },
    )
    return KnowledgeSourceView.from_record(record)


@router.get(
    "/server-scopes/{scope_id}/corpora/{corpus_id}/sources",
    response_model=list[KnowledgeSourceView],
)
def list_server_local_sources(
    scope_id: str,
    corpus_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> list[KnowledgeSourceView]:
    scope = _scope_for_actor(request, scope_id=scope_id, user=user)
    _server_local_corpus_or_404(request, scope_id=scope.id, corpus_id=corpus_id)
    return [
        KnowledgeSourceView.from_record(record)
        for record in _fabric(request).list_sources(corpus_id)
    ]


__all__ = ["router"]
