"""FastAPI application factory."""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from echo_masque.api.routes import (
    accounts_router,
    admin_router,
    auth_router,
    authoring_archive_router,
    authoring_router,
    characters_router,
    comparisons_router,
    health_router,
    matrices_router,
    reports_router,
    targets_router,
    transcripts_router,
    trials_router,
    workspace_router,
)
from echo_masque.audit_middleware import SensitiveAuditMiddleware
from echo_masque.auth import AuthService
from echo_masque.authoring_archive import AuthoringArchiveService
from echo_masque.authoring_lifecycle import AuthoringAwareAccountLifecycleService
from echo_masque.config import Settings, get_settings
from echo_masque.credentials import CredentialVault
from echo_masque.persistence import (
    AuthoringRepository,
    AuthRepository,
    Database,
    MatrixRepository,
    Repository,
    TargetAccessRepository,
    WorkspaceRepository,
    inspect_storage,
)
from echo_masque.security_controls import QuotaService
from echo_masque.services import MatrixService, RuntimeService, TrialService

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    storage_status = inspect_storage(resolved)
    database = Database(resolved.database_url)
    database.initialize()
    storage_status = storage_status.with_instance_id(database.ensure_storage_instance_id())
    logger.info(
        "Storage ready: kind=%s path=%s mount=%s instance=%s",
        storage_status.database_kind,
        storage_status.database_path,
        storage_status.mount_ready,
        storage_status.storage_instance_id,
    )

    auth_repository = AuthRepository(database)
    auth_service = AuthService(auth_repository, resolved)
    auth_service.ensure_development_user()
    auth_service.ensure_system_runtime_user()
    auth_service.ensure_bootstrap_admin()

    repository = Repository(database)
    workspace_repository = WorkspaceRepository(database)
    authoring_repository = AuthoringRepository(database, workspace_repository)
    authoring_archive_service = AuthoringArchiveService(database, authoring_repository)
    matrix_repository = MatrixRepository(database)
    target_access_repository = TargetAccessRepository(database)
    quota_service = QuotaService(database, resolved)
    account_lifecycle_service = AuthoringAwareAccountLifecycleService(
        database,
        auth_repository,
        authoring_archive_service,
    )
    recovered_matrices = matrix_repository.recover_interrupted()
    if recovered_matrices:
        logger.warning(
            "Recovered %s interrupted Experiment Matrices as paused.",
            recovered_matrices,
        )
    repository.seed_demo_targets()
    repository.remove_demo_character_cards()
    credential_store = CredentialVault(auth_repository, resolved)
    runtime_service = RuntimeService(repository, resolved, credential_store)
    trial_service = TrialService(
        repository,
        credential_store,
        runtime_service,
        workspace_repository=workspace_repository,
    )
    matrix_service = MatrixService(
        repository,
        workspace_repository,
        matrix_repository,
        trial_service,
    )

    app = FastAPI(
        title=resolved.app_name,
        version=resolved.app_version,
        debug=resolved.debug,
        description=(
            "Behavior validation and stress testing for conversational characters and agents."
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SensitiveAuditMiddleware, repository=auth_repository)
    app.state.settings = resolved
    app.state.storage_status = storage_status
    app.state.database = database
    app.state.auth_repository = auth_repository
    app.state.auth_service = auth_service
    app.state.repository = repository
    app.state.workspace_repository = workspace_repository
    app.state.authoring_repository = authoring_repository
    app.state.authoring_archive_service = authoring_archive_service
    app.state.matrix_repository = matrix_repository
    app.state.target_access_repository = target_access_repository
    app.state.quota_service = quota_service
    app.state.account_lifecycle_service = account_lifecycle_service
    app.state.credential_store = credential_store
    app.state.runtime_service = runtime_service
    app.state.trial_service = trial_service
    app.state.matrix_service = matrix_service
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(accounts_router)
    app.include_router(admin_router)
    app.include_router(authoring_router)
    app.include_router(authoring_archive_router)
    app.include_router(characters_router)
    app.include_router(targets_router)
    app.include_router(trials_router)
    app.include_router(transcripts_router)
    app.include_router(comparisons_router)
    app.include_router(reports_router)
    app.include_router(workspace_router)
    app.include_router(matrices_router)

    web_dist = Path("web/dist")
    if web_dist.exists():
        app.mount("/", StaticFiles(directory=web_dist, html=True), name="web")
    else:
        @app.get("/", include_in_schema=False)
        def root() -> JSONResponse:
            return JSONResponse(
                {"name": resolved.app_name, "ui": "Run `cd web && npm install && npm run dev`."}
            )
    return app


__all__ = ["create_app"]