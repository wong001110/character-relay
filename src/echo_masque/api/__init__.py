"""FastAPI application factory."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from echo_masque.admin_runtime import RuntimeCredentialStore
from echo_masque.api.routes import (
    admin_router,
    characters_router,
    comparisons_router,
    health_router,
    reports_router,
    targets_router,
    transcripts_router,
    trials_router,
    workspace_router,
)
from echo_masque.config import Settings, get_settings
from echo_masque.credentials import CredentialStore
from echo_masque.persistence import Database, Repository, WorkspaceRepository
from echo_masque.services import RuntimeService, TrialService


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    database = Database(resolved.database_url)
    database.initialize()
    repository = Repository(database)
    workspace_repository = WorkspaceRepository(database)
    repository.seed_demo_targets()
    repository.remove_demo_character_cards()
    credential_store = CredentialStore()
    runtime_credentials = RuntimeCredentialStore()
    runtime_service = RuntimeService(repository, resolved, runtime_credentials)

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
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings = resolved
    app.state.database = database
    app.state.repository = repository
    app.state.workspace_repository = workspace_repository
    app.state.credential_store = credential_store
    app.state.runtime_credentials = runtime_credentials
    app.state.runtime_service = runtime_service
    app.state.trial_service = TrialService(
        repository,
        credential_store,
        runtime_service,
        workspace_repository=workspace_repository,
    )
    app.include_router(health_router)
    app.include_router(admin_router)
    app.include_router(characters_router)
    app.include_router(targets_router)
    app.include_router(trials_router)
    app.include_router(transcripts_router)
    app.include_router(comparisons_router)
    app.include_router(reports_router)
    app.include_router(workspace_router)

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
