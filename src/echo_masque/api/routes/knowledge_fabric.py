"""Phase 2 administration APIs for the separate Knowledge Fabric authority."""

from __future__ import annotations

from typing import cast
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request, status

from echo_masque.api.dependencies import (
    CurrentUserDependency,
    SuperAdminUserDependency,
    is_super_admin,
)
from echo_masque.api.knowledge_fabric_schemas import (
    KnowledgeAccessGrantView,
    KnowledgeCanonicalEntityCreate,
    KnowledgeCanonicalEntityView,
    KnowledgeCharacterCorpusPolicyUpdate,
    KnowledgeCharacterCorpusPolicyView,
    KnowledgeCorpusCreate,
    KnowledgeCorpusView,
    KnowledgeDerivedWorkSummaryView,
    KnowledgeExternalSourceScheduleUpdate,
    KnowledgeExternalSourceScheduleView,
    KnowledgeFabricResetRequest,
    KnowledgeFabricResetResult,
    KnowledgeGrantUpdate,
    KnowledgeImageAssetCandidateView,
    KnowledgeOverlayPolicyUpdate,
    KnowledgeOverlayPolicyView,
    KnowledgeQueryInspectorRequest,
    KnowledgeQueryInspectorResultView,
    KnowledgeRenderedCollectionAnalysisView,
    KnowledgeRenderedCollectionProfileUpdate,
    KnowledgeServerAdministratorView,
    KnowledgeServerGlobalCorpusAccessView,
    KnowledgeServerScopeCreate,
    KnowledgeServerScopeView,
    KnowledgeSourceCreate,
    KnowledgeSourceOperationalView,
    KnowledgeSourceView,
    KnowledgeVisualReferenceCreate,
    KnowledgeVisualReferenceView,
    encode_profile,
)
from echo_masque.knowledge_fabric_external_policy import (
    WEBSITE_COLLECTION_PUBLIC_HTTPS_SOURCE_TYPE,
)
from echo_masque.knowledge_fabric_policy import (
    may_access_server_scope,
    may_manage_global_library,
)
from echo_masque.knowledge_fabric_query import KnowledgeQueryEngine, KnowledgeQueryRequest
from echo_masque.knowledge_fabric_rendered_collection import (
    KnowledgeFabricRenderedCollectionAnalyzer,
    RenderedCollectionRejected,
    configured_rendered_collection_profile,
    rendered_collection_profile,
)
from echo_masque.persistence import AuthRepository
from echo_masque.persistence.knowledge_fabric_content_repository import (
    KnowledgeFabricContentRepository,
)
from echo_masque.persistence.knowledge_fabric_external_schedule_repository import (
    KnowledgeFabricExternalScheduleRepository,
)
from echo_masque.persistence.knowledge_fabric_external_sync_repository import (
    KnowledgeFabricExternalSyncRepository,
)
from echo_masque.persistence.knowledge_fabric_external_sync_run_repository import (
    KnowledgeFabricExternalSyncRunRepository,
)
from echo_masque.persistence.knowledge_fabric_interpretation_repository import (
    KnowledgeFabricInterpretationRepository,
)
from echo_masque.persistence.knowledge_fabric_invalidation_repository import (
    KnowledgeFabricInvalidationRepository,
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
from echo_masque.persistence.knowledge_fabric_site_collection_repository import (
    KnowledgeFabricSiteCollectionRepository,
)
from echo_masque.persistence.knowledge_fabric_visual_reference_repository import (
    KnowledgeFabricVisualReferenceRepository,
)
from echo_masque.public_demo import is_public_demo_email

router = APIRouter(prefix="/api/knowledge-fabric", tags=["knowledge-fabric"])

_QUERY_INSPECTOR_LIMIT = 4


def _fabric(request: Request) -> KnowledgeFabricRepository:
    return cast(KnowledgeFabricRepository, request.app.state.knowledge_fabric_repository)


def _auth(request: Request) -> AuthRepository:
    return cast(AuthRepository, request.app.state.auth_repository)


def _external_schedules(request: Request) -> KnowledgeFabricExternalScheduleRepository:
    return cast(
        KnowledgeFabricExternalScheduleRepository,
        request.app.state.knowledge_fabric_external_schedule_repository,
    )


def _external_sync(request: Request) -> KnowledgeFabricExternalSyncRepository:
    return cast(
        KnowledgeFabricExternalSyncRepository,
        request.app.state.knowledge_fabric_external_sync_repository,
    )


def _external_sync_runs(request: Request) -> KnowledgeFabricExternalSyncRunRepository:
    return cast(
        KnowledgeFabricExternalSyncRunRepository,
        request.app.state.knowledge_fabric_external_sync_run_repository,
    )


def _site_collections(request: Request) -> KnowledgeFabricSiteCollectionRepository:
    return cast(
        KnowledgeFabricSiteCollectionRepository,
        request.app.state.knowledge_fabric_site_collection_repository,
    )


def _rendered_collections(request: Request) -> KnowledgeFabricRenderedCollectionAnalyzer:
    return cast(
        KnowledgeFabricRenderedCollectionAnalyzer,
        request.app.state.knowledge_fabric_rendered_collection_analyzer,
    )


def _content(request: Request) -> KnowledgeFabricContentRepository:
    return cast(
        KnowledgeFabricContentRepository,
        request.app.state.knowledge_fabric_content_repository,
    )


def _derived_work(request: Request) -> KnowledgeFabricInvalidationRepository:
    return cast(
        KnowledgeFabricInvalidationRepository,
        request.app.state.knowledge_fabric_invalidation_repository,
    )


def _interpretations(request: Request) -> KnowledgeFabricInterpretationRepository:
    return cast(
        KnowledgeFabricInterpretationRepository,
        request.app.state.knowledge_fabric_interpretation_repository,
    )


def _visual_references(request: Request) -> KnowledgeFabricVisualReferenceRepository:
    return cast(
        KnowledgeFabricVisualReferenceRepository,
        request.app.state.knowledge_fabric_visual_reference_repository,
    )


def _query_engine(request: Request) -> KnowledgeQueryEngine:
    return cast(KnowledgeQueryEngine, request.app.state.knowledge_query_engine)


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


@router.post("/admin/reset", response_model=KnowledgeFabricResetResult)
def reset_knowledge_fabric(
    payload: KnowledgeFabricResetRequest,
    request: Request,
    user: SuperAdminUserDependency,
) -> KnowledgeFabricResetResult:
    """Erase all Fabric data and private artifacts for a deliberate architecture reset."""

    del payload
    _require_global_manager(request, user)
    deleted = _fabric(request).reset_all()
    _audit(
        request,
        actor_user_id=user.id,
        action="knowledge_fabric.reset",
        resource_type="knowledge_fabric",
        resource_id="all",
        metadata={"pending_object_deletions": deleted["knowledge_fabric_pending_object_deletions"]},
    )
    return KnowledgeFabricResetResult(deleted=deleted)


@router.get(
    "/admin/corpora/{corpus_id}/operational-sources",
    response_model=list[KnowledgeSourceOperationalView],
)
def list_global_corpus_operational_sources(
    corpus_id: str,
    request: Request,
    user: SuperAdminUserDependency,
) -> list[KnowledgeSourceOperationalView]:
    """Expose only redacted, persisted source/schedule/sync health to Super Admins."""

    _require_global_manager(request, user)
    _global_corpus_or_404(request, corpus_id)
    sources = _fabric(request).list_sources(corpus_id)
    source_ids = tuple(source.id for source in sources)
    schedules = {
        record.source_id: record
        for record in _external_schedules(request).list_for_source_ids(source_ids)
    }
    sync_states = {
        record.source_id: record
        for record in _external_sync(request).list_states_for_source_ids(source_ids)
    }
    collection_summaries = _site_collections(request).summaries_for_source_ids(
        tuple(
            source.id
            for source in sources
            if source.source_type == WEBSITE_COLLECTION_PUBLIC_HTTPS_SOURCE_TYPE
        )
    )
    sync_run_reports = _external_sync_runs(request).list_for_source_ids(source_ids)
    derived_work = _derived_work(request).summary_for_source_ids(source_ids)
    return [
        KnowledgeSourceOperationalView.from_record(
            source,
            external_sync=sync_states.get(source.id),
            external_schedule=schedules.get(source.id),
            site_collection_summary=collection_summaries.get(source.id),
            sync_run_reports=sync_run_reports.get(source.id, []),
            derived_work=KnowledgeDerivedWorkSummaryView(
                pending=derived_work[source.id].pending,
                running=derived_work[source.id].running,
                failed=derived_work[source.id].failed,
            ),
        )
        for source in sources
    ]


@router.post(
    "/admin/sources/{source_id}/derived-work/retry",
    response_model=KnowledgeDerivedWorkSummaryView,
)
def retry_failed_source_derived_work(
    source_id: str,
    request: Request,
    user: SuperAdminUserDependency,
) -> KnowledgeDerivedWorkSummaryView:
    """Requeue terminal failures; acquisition and publication stay worker-owned."""

    _require_global_manager(request, user)
    source = _content(request).get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Knowledge Source not found.")
    _global_corpus_or_404(request, source.corpus_id)
    requeued = _derived_work(request).retry_failed_for_source(source_id)
    _audit(
        request,
        actor_user_id=user.id,
        action="knowledge_fabric.derived_work_retry_requested",
        resource_type="knowledge_source",
        resource_id=source_id,
        metadata={"requeued_count": requeued},
    )
    summary = _derived_work(request).summary_for_source_ids((source_id,))[source_id]
    return KnowledgeDerivedWorkSummaryView(
        pending=summary.pending,
        running=summary.running,
        failed=summary.failed,
    )


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


@router.post(
    "/server-scopes/{scope_id}/query-inspector",
    response_model=KnowledgeQueryInspectorResultView,
)
def inspect_scoped_query(
    scope_id: str,
    payload: KnowledgeQueryInspectorRequest,
    request: Request,
    user: CurrentUserDependency,
) -> KnowledgeQueryInspectorResultView:
    """Inspect already-authorized Fabric Evidence without creating another retrieval path."""

    scope = _scope_for_actor(request, scope_id=scope_id, user=user)
    result = _query_engine(request).query(
        KnowledgeQueryRequest(
            server_scope_id=scope.id,
            query=payload.query,
            mode=payload.mode,
            candidate_limit=_QUERY_INSPECTOR_LIMIT,
            result_limit=_QUERY_INSPECTOR_LIMIT,
            as_of=payload.as_of,
        )
    )
    _audit(
        request,
        actor_user_id=user.id,
        action="knowledge_fabric.query_inspected",
        resource_type="knowledge_server_scope",
        resource_id=scope.id,
        metadata={
            "mode": result.mode,
            "accessible_corpus_count": result.accessible_corpus_count,
            "hit_count": len(result.hits),
        },
    )
    return KnowledgeQueryInspectorResultView.from_result(result)


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


@router.get(
    "/server-scopes/{scope_id}/global-corpora/access",
    response_model=list[KnowledgeServerGlobalCorpusAccessView],
)
def list_server_global_corpus_access(
    scope_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> list[KnowledgeServerGlobalCorpusAccessView]:
    scope = _scope_for_actor(request, scope_id=scope_id, user=user)
    return [
        KnowledgeServerGlobalCorpusAccessView(
            corpus_id=item.corpus_id,
            enabled=item.enabled,
            overlay_mode=item.overlay_mode,
        )
        for item in _fabric(request).list_server_global_corpus_access(scope.id)
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


@router.get(
    "/server-scopes/{scope_id}/character-corpus-policies",
    response_model=list[KnowledgeCharacterCorpusPolicyView],
)
def list_character_corpus_policies(
    scope_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> list[KnowledgeCharacterCorpusPolicyView]:
    scope = _scope_for_actor(request, scope_id=scope_id, user=user)
    return [
        KnowledgeCharacterCorpusPolicyView.from_record(record)
        for record in _fabric(request).list_character_corpus_policies(scope.id)
    ]


@router.put(
    "/server-scopes/{scope_id}/deployments/{deployment_id}/corpora/{corpus_id}/epistemic-policy",
    response_model=KnowledgeCharacterCorpusPolicyView,
)
def set_character_corpus_policy(
    scope_id: str,
    deployment_id: str,
    corpus_id: str,
    payload: KnowledgeCharacterCorpusPolicyUpdate,
    request: Request,
    user: CurrentUserDependency,
) -> KnowledgeCharacterCorpusPolicyView:
    scope = _scope_for_actor(request, scope_id=scope_id, user=user)
    try:
        record = _fabric(request).set_character_corpus_policy(
            server_scope_id=scope.id,
            deployment_id=deployment_id,
            corpus_id=corpus_id,
            effect=payload.effect,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Character Deployment not found.")
    _audit(
        request,
        actor_user_id=user.id,
        action="knowledge_fabric.character_corpus_policy_updated",
        resource_type="knowledge_character_corpus_policy",
        resource_id=record.id,
        metadata={
            "server_scope_id": scope.id,
            "deployment_id": record.deployment_id,
            "character_card_id": record.character_card_id,
            "corpus_id": record.corpus_id,
            "effect": record.effect,
        },
    )
    return KnowledgeCharacterCorpusPolicyView.from_record(record)


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


@router.post(
    "/admin/corpora/{corpus_id}/canonical-entities",
    response_model=KnowledgeCanonicalEntityView,
    status_code=status.HTTP_201_CREATED,
)
def create_global_canonical_entity(
    corpus_id: str,
    payload: KnowledgeCanonicalEntityCreate,
    request: Request,
    user: SuperAdminUserDependency,
) -> KnowledgeCanonicalEntityView:
    """Create or return one corpus-bound identity for explicit asset approval."""

    _require_global_manager(request, user)
    _global_corpus_or_404(request, corpus_id)
    try:
        record = _interpretations(request).create_canonical_entity(
            corpus_id=corpus_id,
            entity_type=payload.entity_type,
            canonical_name=payload.canonical_name,
            aliases=payload.aliases,
            metadata=payload.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _audit(
        request,
        actor_user_id=user.id,
        action="knowledge_fabric.canonical_entity_registered",
        resource_type="knowledge_canonical_entity",
        resource_id=record.id,
        metadata={"corpus_id": corpus_id, "entity_type": record.entity_type},
    )
    return KnowledgeCanonicalEntityView.from_record(record)


@router.get(
    "/admin/corpora/{corpus_id}/canonical-entities",
    response_model=list[KnowledgeCanonicalEntityView],
)
def list_global_canonical_entities(
    corpus_id: str,
    request: Request,
    user: SuperAdminUserDependency,
) -> list[KnowledgeCanonicalEntityView]:
    _require_global_manager(request, user)
    _global_corpus_or_404(request, corpus_id)
    return [
        KnowledgeCanonicalEntityView.from_record(record)
        for record in _interpretations(request).list_canonical_entities(corpus_id)
    ]


@router.get(
    "/admin/corpora/{corpus_id}/image-assets",
    response_model=list[KnowledgeImageAssetCandidateView],
)
def list_global_image_asset_candidates(
    corpus_id: str,
    request: Request,
    user: SuperAdminUserDependency,
) -> list[KnowledgeImageAssetCandidateView]:
    """Return only provenance metadata needed to select an image for approval."""

    _require_global_manager(request, user)
    _global_corpus_or_404(request, corpus_id)
    return [
        KnowledgeImageAssetCandidateView.from_candidate(candidate)
        for candidate in _content(request).list_image_asset_candidates(corpus_id)
    ]


@router.post(
    "/admin/corpora/{corpus_id}/visual-references",
    response_model=KnowledgeVisualReferenceView,
    status_code=status.HTTP_201_CREATED,
)
def create_global_visual_reference(
    corpus_id: str,
    payload: KnowledgeVisualReferenceCreate,
    request: Request,
    user: SuperAdminUserDependency,
) -> KnowledgeVisualReferenceView:
    """Approve a corpus-local visual reference from existing private provenance."""

    _require_global_manager(request, user)
    _global_corpus_or_404(request, corpus_id)
    try:
        record = _visual_references(request).create(
            corpus_id=corpus_id,
            canonical_entity_id=payload.canonical_entity_id,
            evidence_unit_id=payload.evidence_unit_id,
            asset_id=payload.asset_id,
            descriptor=payload.descriptor,
            comparison_authorized=payload.comparison_authorized,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail="Visual reference provenance not found."
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _audit(
        request,
        actor_user_id=user.id,
        action="knowledge_fabric.visual_reference_approved",
        resource_type="knowledge_canonical_visual_reference",
        resource_id=record.id,
        metadata={"corpus_id": corpus_id},
    )
    return KnowledgeVisualReferenceView.from_record(record)


@router.get(
    "/admin/corpora/{corpus_id}/visual-references",
    response_model=list[KnowledgeVisualReferenceView],
)
def list_global_visual_references(
    corpus_id: str,
    request: Request,
    user: SuperAdminUserDependency,
) -> list[KnowledgeVisualReferenceView]:
    _require_global_manager(request, user)
    _global_corpus_or_404(request, corpus_id)
    return [
        KnowledgeVisualReferenceView.from_record(record)
        for record in _visual_references(request).list_active(corpus_id)
    ]


@router.delete(
    "/admin/corpora/{corpus_id}/visual-references/{reference_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_global_visual_reference(
    corpus_id: str,
    reference_id: str,
    request: Request,
    user: SuperAdminUserDependency,
) -> None:
    """Revoke only an active reference within the requested global corpus."""

    _require_global_manager(request, user)
    _global_corpus_or_404(request, corpus_id)
    reference = next(
        (
            record
            for record in _visual_references(request).list_active(corpus_id)
            if record.id == reference_id
        ),
        None,
    )
    if reference is None or not _visual_references(request).revoke(reference.id):
        raise HTTPException(status_code=404, detail="Knowledge visual reference not found.")
    _audit(
        request,
        actor_user_id=user.id,
        action="knowledge_fabric.visual_reference_revoked",
        resource_type="knowledge_canonical_visual_reference",
        resource_id=reference.id,
        metadata={"corpus_id": corpus_id},
    )


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
    "/admin/sources/{source_id}/rendered-collection-analysis",
    response_model=KnowledgeRenderedCollectionAnalysisView,
)
async def analyze_rendered_collection(
    source_id: str,
    request: Request,
    user: SuperAdminUserDependency,
) -> KnowledgeRenderedCollectionAnalysisView:
    """Propose public bootstrap hosts; analysis alone cannot enable browser collection."""

    _require_global_manager(request, user)
    source = _content(request).get_source(source_id)
    if source is None or source.source_type != WEBSITE_COLLECTION_PUBLIC_HTTPS_SOURCE_TYPE:
        raise HTTPException(
            status_code=404,
            detail="Knowledge Website Collection Source not found.",
        )
    _global_corpus_or_404(request, source.corpus_id)
    try:
        analysis = await _rendered_collections(request).analyze(
            source_id=source_id,
            locator=source.locator,
        )
    except RenderedCollectionRejected as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _audit(
        request,
        actor_user_id=user.id,
        action="knowledge_fabric.rendered_collection_analyzed",
        resource_type="knowledge_source",
        resource_id=source_id,
        metadata={"candidate_host_count": len(analysis.candidate_hosts)},
    )
    return KnowledgeRenderedCollectionAnalysisView(
        source_id=analysis.source_id,
        candidate_hosts=list(analysis.candidate_hosts),
    )


@router.put(
    "/admin/sources/{source_id}/rendered-collection-profile",
    response_model=KnowledgeSourceView,
)
async def configure_rendered_collection(
    source_id: str,
    payload: KnowledgeRenderedCollectionProfileUpdate,
    request: Request,
    user: SuperAdminUserDependency,
) -> KnowledgeSourceView:
    """Save a bounded browser recipe after rechecking every external host was observed."""

    _require_global_manager(request, user)
    source = _content(request).get_source(source_id)
    if source is None or source.source_type != WEBSITE_COLLECTION_PUBLIC_HTTPS_SOURCE_TYPE:
        raise HTTPException(
            status_code=404,
            detail="Knowledge Website Collection Source not found.",
        )
    _global_corpus_or_404(request, source.corpus_id)
    try:
        parser_profile_json = configured_rendered_collection_profile(
            current_profile_json=source.parser_profile_json,
            enabled=payload.enabled,
            allowed_hosts=tuple(payload.allowed_hosts),
            page_limit=payload.page_limit,
            max_depth=payload.max_depth,
        )
        profile = rendered_collection_profile(
            locator=source.locator,
            parser_profile_json=parser_profile_json,
        )
        if payload.enabled:
            analysis = await _rendered_collections(request).analyze(
                source_id=source_id,
                locator=source.locator,
            )
            root_host = (urlsplit(source.locator).hostname or "").casefold().rstrip(".")
            granted_external_hosts = profile.allowed_hosts - {root_host}
            if not granted_external_hosts.issubset(set(analysis.candidate_hosts)):
                raise RenderedCollectionRejected(
                    "Each rendered collection host must be observed in the public bootstrap page."
                )
    except RenderedCollectionRejected as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    record = _fabric(request).update_source_parser_profile(
        source_id=source_id,
        parser_profile_json=parser_profile_json,
    )
    if record is None:
        raise HTTPException(
            status_code=404,
            detail="Knowledge Website Collection Source not found.",
        )
    _audit(
        request,
        actor_user_id=user.id,
        action="knowledge_fabric.rendered_collection_profile_updated",
        resource_type="knowledge_source",
        resource_id=source_id,
        metadata={
            "enabled": profile.enabled,
            "approved_external_host_count": max(0, len(profile.allowed_hosts) - 1),
            "page_limit": profile.page_limit,
            "max_depth": profile.max_depth,
        },
    )
    return KnowledgeSourceView.from_record(record)


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
