"""Custom scenarios, test packs, experiment history, and persistence endpoints."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import cast

from fastapi import (
    APIRouter,
    BackgroundTasks,
    HTTPException,
    Query,
    Request,
    status,
)

from echo_masque.api.dependencies import (
    AdminUserDependency,
    CurrentUserDependency,
    quota_http_exception,
    quota_service,
)
from echo_masque.config import Settings
from echo_masque.persistence import (
    Database,
    Repository,
    TargetAccessRepository,
    WorkspaceRepository,
)
from echo_masque.security_controls import QuotaExceeded, ResourceKind
from echo_masque.services import TrialService
from echo_masque.workspace import (
    ExperimentHistoryPage,
    PersistenceProbeView,
    RunSnapshotView,
    ScenarioCreate,
    ScenarioUpdate,
    ScenarioView,
    StorageDiagnostics,
    TestPackCreate,
    TestPackUpdate,
    TestPackView,
    WorkspaceArchive,
    WorkspaceImportRequest,
    WorkspaceImportResult,
)

router = APIRouter(tags=["workspace"])


def workspace_repository(request: Request) -> WorkspaceRepository:
    return cast(WorkspaceRepository, request.app.state.workspace_repository)


def repository(request: Request) -> Repository:
    return cast(Repository, request.app.state.repository)


def target_access(request: Request) -> TargetAccessRepository:
    return cast(TargetAccessRepository, request.app.state.target_access_repository)


def trial_service(request: Request) -> TrialService:
    return cast(TrialService, request.app.state.trial_service)


def _enforce_create_quota(
    request: Request,
    owner_id: str,
    kind: ResourceKind,
) -> None:
    try:
        quota_service(request).enforce_create(owner_id, kind)
    except QuotaExceeded as exc:
        raise quota_http_exception(exc) from exc


@router.get("/api/scenarios", response_model=list[ScenarioView])
def list_scenarios(
    request: Request,
    user: CurrentUserDependency,
) -> list[ScenarioView]:
    return workspace_repository(request).list_scenarios(user.id)


@router.post(
    "/api/scenarios",
    response_model=ScenarioView,
    status_code=status.HTTP_201_CREATED,
)
def create_scenario(
    payload: ScenarioCreate,
    request: Request,
    user: CurrentUserDependency,
) -> ScenarioView:
    _enforce_create_quota(request, user.id, "scenario")
    return workspace_repository(request).create_scenario(user.id, payload)


@router.get("/api/scenarios/{scenario_id}", response_model=ScenarioView)
def get_scenario(
    scenario_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> ScenarioView:
    item = workspace_repository(request).get_scenario(scenario_id, user.id)
    if item is None:
        raise HTTPException(status_code=404, detail="Scenario not found.")
    return item


@router.put("/api/scenarios/{scenario_id}", response_model=ScenarioView)
def update_scenario(
    scenario_id: str,
    payload: ScenarioUpdate,
    request: Request,
    user: CurrentUserDependency,
) -> ScenarioView:
    item = workspace_repository(request).update_scenario(
        scenario_id,
        user.id,
        payload,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Scenario not found.")
    return item


@router.post(
    "/api/scenarios/{scenario_id}/duplicate",
    response_model=ScenarioView,
)
def duplicate_scenario(
    scenario_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> ScenarioView:
    _enforce_create_quota(request, user.id, "scenario")
    item = workspace_repository(request).duplicate_scenario(scenario_id, user.id)
    if item is None:
        raise HTTPException(status_code=404, detail="Scenario not found.")
    return item


@router.delete(
    "/api/scenarios/{scenario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_scenario(
    scenario_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> None:
    if not workspace_repository(request).delete_scenario(scenario_id, user.id):
        raise HTTPException(status_code=404, detail="Scenario not found.")


@router.get("/api/test-packs", response_model=list[TestPackView])
def list_packs(
    request: Request,
    user: CurrentUserDependency,
) -> list[TestPackView]:
    return workspace_repository(request).list_packs(user.id)


@router.post(
    "/api/test-packs",
    response_model=TestPackView,
    status_code=status.HTTP_201_CREATED,
)
def create_pack(
    payload: TestPackCreate,
    request: Request,
    user: CurrentUserDependency,
) -> TestPackView:
    _enforce_create_quota(request, user.id, "pack")
    try:
        return workspace_repository(request).create_pack(user.id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/test-packs/{pack_id}", response_model=TestPackView)
def get_pack(
    pack_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> TestPackView:
    item = workspace_repository(request).get_pack(pack_id, user.id)
    if item is None:
        raise HTTPException(status_code=404, detail="Test Pack not found.")
    return item


@router.put("/api/test-packs/{pack_id}", response_model=TestPackView)
def update_pack(
    pack_id: str,
    payload: TestPackUpdate,
    request: Request,
    user: CurrentUserDependency,
) -> TestPackView:
    try:
        item = workspace_repository(request).update_pack(pack_id, user.id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Test Pack not found.")
    return item


@router.post(
    "/api/test-packs/{pack_id}/duplicate",
    response_model=TestPackView,
)
def duplicate_pack(
    pack_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> TestPackView:
    _enforce_create_quota(request, user.id, "pack")
    item = workspace_repository(request).duplicate_pack(pack_id, user.id)
    if item is None:
        raise HTTPException(status_code=404, detail="Test Pack not found.")
    return item


@router.delete(
    "/api/test-packs/{pack_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_pack(
    pack_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> None:
    if not workspace_repository(request).delete_pack(pack_id, user.id):
        raise HTTPException(status_code=404, detail="Test Pack not found.")


@router.get("/api/experiments", response_model=ExperimentHistoryPage)
def experiment_history(
    request: Request,
    user: CurrentUserDependency,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    character_card_id: str | None = None,
    test_pack_id: str | None = None,
    language: str | None = None,
    tester_mode: str | None = None,
    judge_mode: str | None = None,
    run_status: str | None = Query(None, alias="status"),
) -> ExperimentHistoryPage:
    return workspace_repository(request).history(
        user.id,
        page=page,
        page_size=page_size,
        character_card_id=character_card_id,
        test_pack_id=test_pack_id,
        language=language,
        tester_mode=tester_mode,
        judge_mode=judge_mode,
        status=run_status,
    )


@router.get(
    "/api/experiments/{run_id}/snapshot",
    response_model=RunSnapshotView,
)
def experiment_snapshot(
    run_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> RunSnapshotView:
    item = workspace_repository(request).get_run_snapshot(run_id, user.id)
    if item is None:
        raise HTTPException(status_code=404, detail="Experiment snapshot not found.")
    return item


@router.put(
    "/api/experiments/{run_id}/baseline",
    response_model=RunSnapshotView,
)
def set_experiment_baseline(
    run_id: str,
    value: bool,
    request: Request,
    user: CurrentUserDependency,
) -> RunSnapshotView:
    item = workspace_repository(request).set_baseline(run_id, user.id, value)
    if item is None:
        raise HTTPException(status_code=404, detail="Experiment snapshot not found.")
    return item


@router.post(
    "/api/experiments/{run_id}/rerun",
    status_code=status.HTTP_202_ACCEPTED,
)
def rerun_experiment(
    run_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    user: CurrentUserDependency,
) -> dict[str, str]:
    try:
        quota_service(request).enforce_run_start(user.id)
    except QuotaExceeded as exc:
        raise quota_http_exception(exc) from exc
    service = trial_service(request)
    try:
        new_run_id = service.rerun(run_id, owner_id=user.id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail="Experiment snapshot not found.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    background_tasks.add_task(service.execute, new_run_id)
    return {"run_id": new_run_id}


@router.delete(
    "/api/experiments/{run_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_experiment(
    run_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> None:
    if not workspace_repository(request).delete_run(run_id, user.id):
        raise HTTPException(status_code=404, detail="Experiment not found.")


@router.get("/api/admin/storage", response_model=StorageDiagnostics)
def storage_diagnostics(
    request: Request,
    admin: AdminUserDependency,
) -> StorageDiagnostics:
    settings = cast(Settings, request.app.state.settings)
    database = cast(Database, request.app.state.database)
    repo = workspace_repository(request)
    url = database.engine.url
    kind = url.get_backend_name()
    path: str | None = None
    writable = True
    if kind == "sqlite" and url.database not in {None, ":memory:"}:
        path = str(Path(str(url.database)).resolve())
        parent = Path(path).parent
        try:
            parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                dir=parent,
                prefix="echo-masque-write-",
                delete=True,
            ):
                pass
        except OSError:
            writable = False
    persistent_expected = settings.environment == "production" and kind == "sqlite"
    persistent_configured = not persistent_expected or (
        path is not None and path.startswith("/data/")
    )
    warning = None
    if persistent_expected and not persistent_configured:
        warning = (
            "Production SQLite is not stored under /data; "
            "data may be lost after redeploy."
        )
    counts = repo.counts(admin.id)
    return StorageDiagnostics(
        environment=settings.environment,
        database_url_redacted=f"{kind}:///{path or ':memory:'}",
        database_kind=kind,
        database_path=path,
        writable=writable,
        persistent_path_expected=persistent_expected,
        persistent_path_configured=persistent_configured,
        warning=warning,
        character_count=counts["characters"],
        scenario_count=counts["scenarios"],
        pack_count=counts["packs"],
        run_count=counts["runs"],
        last_write_at=repo.last_write_at(admin.id),
    )


@router.post(
    "/api/admin/storage/probes",
    response_model=PersistenceProbeView,
)
def create_persistence_probe(
    marker: str,
    request: Request,
    admin: AdminUserDependency,
) -> PersistenceProbeView:
    return workspace_repository(request).create_probe(admin.id, marker)


@router.get(
    "/api/admin/storage/probes/{probe_id}",
    response_model=PersistenceProbeView,
)
def get_persistence_probe(
    probe_id: str,
    request: Request,
    admin: AdminUserDependency,
) -> PersistenceProbeView:
    probe = workspace_repository(request).get_probe(probe_id, admin.id)
    if probe is None:
        raise HTTPException(status_code=404, detail="Persistence probe not found.")
    return probe


@router.delete(
    "/api/admin/storage/probes/{probe_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_persistence_probe(
    probe_id: str,
    request: Request,
    admin: AdminUserDependency,
) -> None:
    if not workspace_repository(request).delete_probe(probe_id, admin.id):
        raise HTTPException(status_code=404, detail="Persistence probe not found.")


@router.get(
    "/api/admin/workspace/export",
    response_model=WorkspaceArchive,
)
def export_workspace(
    request: Request,
    user: CurrentUserDependency,
) -> WorkspaceArchive:
    archive = workspace_repository(request).export_workspace(user.id)
    return archive.model_copy(update={"admin_runtime": None})


@router.post(
    "/api/admin/workspace/import",
    response_model=WorkspaceImportResult,
)
def import_workspace(
    payload: WorkspaceImportRequest,
    request: Request,
    user: CurrentUserDependency,
) -> WorkspaceImportResult:
    archive = payload.archive.model_copy(
        update={"owner_id": user.id, "admin_runtime": None}
    )
    try:
        quota_service(request).enforce_import(
            user.id,
            characters=len(archive.character_cards),
            scenarios=len(archive.scenarios),
            packs=len(archive.test_packs),
            runs=len(archive.runs),
        )
    except QuotaExceeded as exc:
        raise quota_http_exception(exc) from exc
    for raw in archive.targets:
        target_id = raw.get("id")
        if not isinstance(target_id, str) or not target_id:
            raise HTTPException(status_code=422, detail="Imported Target ID is invalid.")
        existing = repository(request).get_target(target_id)
        if existing is not None and not target_access(request).can_access(
            owner_id=user.id,
            target_id=target_id,
        ):
            raise HTTPException(
                status_code=409,
                detail="Workspace import conflicts with another user's Target.",
            )
    try:
        result = workspace_repository(request).import_workspace(
            user.id,
            archive,
            payload.mode,
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Workspace import failed: {exc}",
        ) from exc
    for raw in archive.targets:
        target_id = raw.get("id")
        if isinstance(target_id, str) and repository(request).get_target(target_id) is not None:
            target_access(request).assign(owner_id=user.id, target_id=target_id)
    return result
