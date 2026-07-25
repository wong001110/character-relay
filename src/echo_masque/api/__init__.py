"""FastAPI application factory."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from echo_masque.api.routes import health_router, targets_router, trials_router
from echo_masque.config import Settings, get_settings
from echo_masque.persistence import Database, Repository
from echo_masque.services import TrialService


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    database = Database(resolved.database_url)
    database.initialize()
    repository = Repository(database)
    repository.seed_demo_targets()

    app = FastAPI(
        title=resolved.app_name,
        version=resolved.app_version,
        debug=resolved.debug,
        description="Behavior validation and stress testing for conversational characters and agents.",
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
    app.state.trial_service = TrialService(repository)
    app.include_router(health_router)
    app.include_router(targets_router)
    app.include_router(trials_router)

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
