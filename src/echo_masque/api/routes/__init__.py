"""HTTP route exports."""

from echo_masque.api.routes.accounts import router as accounts_router
from echo_masque.api.routes.admin import router as admin_router
from echo_masque.api.routes.auth import router as auth_router
from echo_masque.api.routes.authoring import router as authoring_router
from echo_masque.api.routes.authoring_archive import router as authoring_archive_router
from echo_masque.api.routes.authoring_generation import (
    router as authoring_generation_router,
)
from echo_masque.api.routes.calibration import router as calibration_router
from echo_masque.api.routes.characters import router as characters_router
from echo_masque.api.routes.comparisons import router as comparisons_router
from echo_masque.api.routes.coverage import router as coverage_router
from echo_masque.api.routes.evaluations import router as evaluations_router
from echo_masque.api.routes.health import router as health_router
from echo_masque.api.routes.matrices import router as matrices_router
from echo_masque.api.routes.prompt_inspector import router as prompt_inspector_router
from echo_masque.api.routes.reports import router as reports_router
from echo_masque.api.routes.targets import router as targets_router
from echo_masque.api.routes.templates import router as templates_router
from echo_masque.api.routes.transcripts import router as transcripts_router
from echo_masque.api.routes.trials import router as trials_router
from echo_masque.api.routes.workspace import router as workspace_router

__all__ = [
    "accounts_router",
    "admin_router",
    "auth_router",
    "authoring_archive_router",
    "authoring_generation_router",
    "authoring_router",
    "calibration_router",
    "characters_router",
    "comparisons_router",
    "coverage_router",
    "evaluations_router",
    "health_router",
    "matrices_router",
    "prompt_inspector_router",
    "reports_router",
    "targets_router",
    "templates_router",
    "transcripts_router",
    "trials_router",
    "workspace_router",
]
