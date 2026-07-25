"""FastAPI application factory."""

from fastapi import FastAPI

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
    app.state.settings = resolved
    app.state.database = database
    app.state.repository = repository
    app.state.trial_service = TrialService(repository)
    app.include_router(health_router)
    app.include_router(targets_router)
    app.include_router(trials_router)
    return app


__all__ = ["create_app"]
