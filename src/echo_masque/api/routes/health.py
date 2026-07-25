"""Service health endpoints."""

from fastapi import APIRouter, Request

from echo_masque.config import Settings
from echo_masque.domain import HealthResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    """Report process health without touching external providers."""

    settings: Settings = request.app.state.settings
    return HealthResponse(
        name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )
