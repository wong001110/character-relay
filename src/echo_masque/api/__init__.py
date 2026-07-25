"""FastAPI application factory."""

from fastapi import FastAPI

from echo_masque.api.routes import health_router
from echo_masque.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an isolated FastAPI application instance."""

    resolved_settings = settings or get_settings()
    app = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        debug=resolved_settings.debug,
        description=(
            "Behavior validation and stress testing for conversational characters and agents."
        ),
    )
    app.state.settings = resolved_settings
    app.include_router(health_router)
    return app


__all__ = ["create_app"]
