"""Reusable evaluation templates and secret-free Share Bundle endpoints."""

from typing import cast

from fastapi import APIRouter, HTTPException, Request, status

from echo_masque.api.dependencies import (
    CurrentUserDependency,
    quota_http_exception,
    quota_service,
)
from echo_masque.persistence import AuthRepository
from echo_masque.security_controls import QuotaExceeded
from echo_masque.template_sharing import (
    EvaluationShareBundle,
    EvaluationTemplateService,
    EvaluationTemplateView,
    ShareBundleExportRequest,
    ShareBundleImportRequest,
    ShareBundleImportResult,
    TemplateInstantiateRequest,
    TemplateInstantiationResult,
)

router = APIRouter(prefix="/api", tags=["templates-sharing"])


def template_service(request: Request) -> EvaluationTemplateService:
    return cast(
        EvaluationTemplateService,
        request.app.state.evaluation_template_service,
    )


def auth_repository(request: Request) -> AuthRepository:
    return cast(AuthRepository, request.app.state.auth_repository)


@router.get("/templates", response_model=list[EvaluationTemplateView])
def list_templates(
    request: Request,
    user: CurrentUserDependency,
) -> list[EvaluationTemplateView]:
    return template_service(request).list_templates()


@router.post(
    "/templates/{template_id}/instantiate",
    response_model=TemplateInstantiationResult,
    status_code=status.HTTP_201_CREATED,
)
def instantiate_template(
    template_id: str,
    payload: TemplateInstantiateRequest,
    request: Request,
    user: CurrentUserDependency,
) -> TemplateInstantiationResult:
    try:
        quota_service(request).consume_template_instantiation(user.id)
        result = template_service(request).instantiate(user.id, template_id, payload)
    except QuotaExceeded as exc:
        raise quota_http_exception(exc) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    auth_repository(request).audit(
        actor_user_id=user.id,
        action="template.instantiated",
        resource_type="evaluation_template",
        resource_id=template_id,
        metadata={
            "scenario_draft_count": len(result.scenario_drafts),
            "test_pack_draft_id": result.test_pack_draft.id,
        },
    )
    return result


@router.post("/share-bundles/export", response_model=EvaluationShareBundle)
def export_share_bundle(
    payload: ShareBundleExportRequest,
    request: Request,
    user: CurrentUserDependency,
) -> EvaluationShareBundle:
    try:
        quota_service(request).enforce_share_bundle(
            len(payload.scenario_ids) + len(payload.test_pack_ids)
        )
        bundle = template_service(request).export_bundle(user.id, payload)
        quota_service(request).enforce_share_bundle(
            len(bundle.scenarios) + len(bundle.test_packs)
        )
    except QuotaExceeded as exc:
        raise quota_http_exception(exc) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    auth_repository(request).audit(
        actor_user_id=user.id,
        action="share_bundle.exported",
        resource_type="share_bundle",
        resource_id=bundle.title,
        metadata={
            "scenario_count": len(bundle.scenarios),
            "test_pack_count": len(bundle.test_packs),
        },
    )
    return bundle


@router.post(
    "/share-bundles/import",
    response_model=ShareBundleImportResult,
    status_code=status.HTTP_201_CREATED,
)
def import_share_bundle(
    payload: ShareBundleImportRequest,
    request: Request,
    user: CurrentUserDependency,
) -> ShareBundleImportResult:
    try:
        quota_service(request).enforce_share_bundle(
            len(payload.bundle.scenarios) + len(payload.bundle.test_packs)
        )
        quota_service(request).consume_template_instantiation(user.id)
        result = template_service(request).import_bundle(user.id, payload.bundle)
    except QuotaExceeded as exc:
        raise quota_http_exception(exc) from exc
    auth_repository(request).audit(
        actor_user_id=user.id,
        action="share_bundle.imported_as_drafts",
        resource_type="share_bundle",
        resource_id=payload.bundle.title,
        metadata={
            "scenario_draft_count": len(result.scenario_drafts),
            "test_pack_draft_count": len(result.test_pack_drafts),
        },
    )
    return result
