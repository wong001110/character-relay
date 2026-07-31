"""Owner-scoped Phase 16 authoring draft and approval endpoints."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, HTTPException, Query, Request, status

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.authoring import (
    DraftStatus,
    ScenarioDraftApproval,
    ScenarioDraftCreate,
    ScenarioDraftUpdate,
    ScenarioDraftView,
    TestPackDraftApproval,
    TestPackDraftCreate,
    TestPackDraftUpdate,
    TestPackDraftView,
)
from echo_masque.persistence import AuthRepository, AuthoringRepository
from echo_masque.persistence.authoring_repository import AuthoringConflict

router = APIRouter(prefix="/api/authoring", tags=["authoring"])


def authoring_repository(request: Request) -> AuthoringRepository:
    return cast(AuthoringRepository, request.app.state.authoring_repository)


def auth_repository(request: Request) -> AuthRepository:
    return cast(AuthRepository, request.app.state.auth_repository)


def _audit(
    request: Request,
    *,
    actor_user_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    metadata: dict[str, object] | None = None,
) -> None:
    auth_repository(request).audit(
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata=metadata,
    )


def _conflict(exc: AuthoringConflict) -> HTTPException:
    return HTTPException(status_code=409, detail=str(exc))


@router.get("/scenario-drafts", response_model=list[ScenarioDraftView])
def list_scenario_drafts(
    request: Request,
    user: CurrentUserDependency,
    draft_status: DraftStatus | None = Query(None, alias="status"),
) -> list[ScenarioDraftView]:
    return authoring_repository(request).list_scenario_drafts(
        user.id,
        status=draft_status,
    )


@router.post(
    "/scenario-drafts",
    response_model=ScenarioDraftView,
    status_code=status.HTTP_201_CREATED,
)
def create_scenario_draft(
    payload: ScenarioDraftCreate,
    request: Request,
    user: CurrentUserDependency,
) -> ScenarioDraftView:
    draft = authoring_repository(request).create_scenario_draft(user.id, payload)
    _audit(
        request,
        actor_user_id=user.id,
        action="authoring.scenario_draft_created",
        resource_type="scenario_draft",
        resource_id=draft.id,
        metadata={"source": draft.provenance.source, "revision": draft.revision},
    )
    return draft


@router.get("/scenario-drafts/{draft_id}", response_model=ScenarioDraftView)
def get_scenario_draft(
    draft_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> ScenarioDraftView:
    draft = authoring_repository(request).get_scenario_draft(draft_id, user.id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Scenario Draft not found.")
    return draft


@router.put("/scenario-drafts/{draft_id}", response_model=ScenarioDraftView)
def update_scenario_draft(
    draft_id: str,
    payload: ScenarioDraftUpdate,
    request: Request,
    user: CurrentUserDependency,
) -> ScenarioDraftView:
    try:
        draft = authoring_repository(request).update_scenario_draft(
            draft_id,
            user.id,
            payload,
        )
    except AuthoringConflict as exc:
        raise _conflict(exc) from exc
    if draft is None:
        raise HTTPException(status_code=404, detail="Scenario Draft not found.")
    _audit(
        request,
        actor_user_id=user.id,
        action="authoring.scenario_draft_revised",
        resource_type="scenario_draft",
        resource_id=draft.id,
        metadata={"revision": draft.revision},
    )
    return draft


@router.post("/scenario-drafts/{draft_id}/reject", response_model=ScenarioDraftView)
def reject_scenario_draft(
    draft_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> ScenarioDraftView:
    try:
        draft = authoring_repository(request).reject_scenario_draft(draft_id, user.id)
    except AuthoringConflict as exc:
        raise _conflict(exc) from exc
    if draft is None:
        raise HTTPException(status_code=404, detail="Scenario Draft not found.")
    _audit(
        request,
        actor_user_id=user.id,
        action="authoring.scenario_draft_rejected",
        resource_type="scenario_draft",
        resource_id=draft.id,
        metadata={"revision": draft.revision},
    )
    return draft


@router.post(
    "/scenario-drafts/{draft_id}/approve",
    response_model=ScenarioDraftApproval,
)
def approve_scenario_draft(
    draft_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> ScenarioDraftApproval:
    try:
        approved = authoring_repository(request).approve_scenario_draft(draft_id, user.id)
    except AuthoringConflict as exc:
        raise _conflict(exc) from exc
    if approved is None:
        raise HTTPException(status_code=404, detail="Scenario Draft not found.")
    draft, scenario = approved
    _audit(
        request,
        actor_user_id=user.id,
        action="authoring.scenario_draft_approved",
        resource_type="scenario_draft",
        resource_id=draft.id,
        metadata={
            "approved_scenario_id": scenario.id,
            "revision": draft.revision,
        },
    )
    return ScenarioDraftApproval(draft=draft, scenario=scenario)


@router.delete(
    "/scenario-drafts/{draft_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_scenario_draft(
    draft_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> None:
    try:
        deleted = authoring_repository(request).delete_scenario_draft(draft_id, user.id)
    except AuthoringConflict as exc:
        raise _conflict(exc) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Scenario Draft not found.")
    _audit(
        request,
        actor_user_id=user.id,
        action="authoring.scenario_draft_deleted",
        resource_type="scenario_draft",
        resource_id=draft_id,
    )


@router.get("/test-pack-drafts", response_model=list[TestPackDraftView])
def list_test_pack_drafts(
    request: Request,
    user: CurrentUserDependency,
    draft_status: DraftStatus | None = Query(None, alias="status"),
) -> list[TestPackDraftView]:
    return authoring_repository(request).list_test_pack_drafts(
        user.id,
        status=draft_status,
    )


@router.post(
    "/test-pack-drafts",
    response_model=TestPackDraftView,
    status_code=status.HTTP_201_CREATED,
)
def create_test_pack_draft(
    payload: TestPackDraftCreate,
    request: Request,
    user: CurrentUserDependency,
) -> TestPackDraftView:
    try:
        draft = authoring_repository(request).create_test_pack_draft(user.id, payload)
    except AuthoringConflict as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _audit(
        request,
        actor_user_id=user.id,
        action="authoring.test_pack_draft_created",
        resource_type="test_pack_draft",
        resource_id=draft.id,
        metadata={"source": draft.provenance.source, "revision": draft.revision},
    )
    return draft


@router.get("/test-pack-drafts/{draft_id}", response_model=TestPackDraftView)
def get_test_pack_draft(
    draft_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> TestPackDraftView:
    draft = authoring_repository(request).get_test_pack_draft(draft_id, user.id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Test Pack Draft not found.")
    return draft


@router.put("/test-pack-drafts/{draft_id}", response_model=TestPackDraftView)
def update_test_pack_draft(
    draft_id: str,
    payload: TestPackDraftUpdate,
    request: Request,
    user: CurrentUserDependency,
) -> TestPackDraftView:
    try:
        draft = authoring_repository(request).update_test_pack_draft(
            draft_id,
            user.id,
            payload,
        )
    except AuthoringConflict as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if draft is None:
        raise HTTPException(status_code=404, detail="Test Pack Draft not found.")
    _audit(
        request,
        actor_user_id=user.id,
        action="authoring.test_pack_draft_revised",
        resource_type="test_pack_draft",
        resource_id=draft.id,
        metadata={"revision": draft.revision},
    )
    return draft


@router.post("/test-pack-drafts/{draft_id}/reject", response_model=TestPackDraftView)
def reject_test_pack_draft(
    draft_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> TestPackDraftView:
    try:
        draft = authoring_repository(request).reject_test_pack_draft(draft_id, user.id)
    except AuthoringConflict as exc:
        raise _conflict(exc) from exc
    if draft is None:
        raise HTTPException(status_code=404, detail="Test Pack Draft not found.")
    _audit(
        request,
        actor_user_id=user.id,
        action="authoring.test_pack_draft_rejected",
        resource_type="test_pack_draft",
        resource_id=draft.id,
        metadata={"revision": draft.revision},
    )
    return draft


@router.post(
    "/test-pack-drafts/{draft_id}/approve",
    response_model=TestPackDraftApproval,
)
def approve_test_pack_draft(
    draft_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> TestPackDraftApproval:
    try:
        approved = authoring_repository(request).approve_test_pack_draft(draft_id, user.id)
    except AuthoringConflict as exc:
        raise _conflict(exc) from exc
    if approved is None:
        raise HTTPException(status_code=404, detail="Test Pack Draft not found.")
    draft, pack = approved
    _audit(
        request,
        actor_user_id=user.id,
        action="authoring.test_pack_draft_approved",
        resource_type="test_pack_draft",
        resource_id=draft.id,
        metadata={
            "approved_test_pack_id": pack.id,
            "revision": draft.revision,
        },
    )
    return TestPackDraftApproval(draft=draft, test_pack=pack)


@router.delete(
    "/test-pack-drafts/{draft_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_test_pack_draft(
    draft_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> None:
    try:
        deleted = authoring_repository(request).delete_test_pack_draft(draft_id, user.id)
    except AuthoringConflict as exc:
        raise _conflict(exc) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Test Pack Draft not found.")
    _audit(
        request,
        actor_user_id=user.id,
        action="authoring.test_pack_draft_deleted",
        resource_type="test_pack_draft",
        resource_id=draft_id,
    )
