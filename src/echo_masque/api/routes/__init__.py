"""HTTP route exports."""

from echo_masque.api.routes.admin import router as admin_router
from echo_masque.api.routes.auth import router as auth_router
from echo_masque.api.routes.characters import router as characters_router
from echo_masque.api.routes.comparisons import router as comparisons_router
from echo_masque.api.routes.health import router as health_router
from echo_masque.api.routes.matrices import router as matrices_router
from echo_masque.api.routes.reports import router as reports_router
from echo_masque.api.routes.targets import router as targets_router
from echo_masque.api.routes.transcripts import router as transcripts_router
from echo_masque.api.routes.trials import router as trials_router
from echo_masque.api.routes.workspace import router as workspace_router

__all__ = [
    "admin_router",
    "auth_router",
    "characters_router",
    "comparisons_router",
    "health_router",
    "matrices_router",
    "reports_router",
    "targets_router",
    "transcripts_router",
    "trials_router",
    "workspace_router",
]
