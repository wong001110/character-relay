"""HTTP route exports."""

from echo_masque.api.routes.accounts import router as accounts_router
from echo_masque.api.routes.admin import router as admin_router
from echo_masque.api.routes.auth import router as auth_router
from echo_masque.api.routes.authoring import router as authoring_router
from echo_masque.api.routes.authoring_archive import router as authoring_archive_router
from echo_masque.api.routes.authoring_generation import router as authoring_generation_router
from echo_masque.api.routes.calibration import router as calibration_router
from echo_masque.api.routes.character_portraits import router as character_portraits_router
from echo_masque.api.routes.character_relationships import (
    character_router as character_relationships_router,
)
from echo_masque.api.routes.character_relationships import (
    deployment_router as deployment_relationships_router,
)
from echo_masque.api.routes.characters import router as characters_router
from echo_masque.api.routes.comparisons import router as comparisons_router
from echo_masque.api.routes.connectors import router as connectors_router
from echo_masque.api.routes.conversation_burst_observability import (
    router as conversation_burst_observability_router,
)
from echo_masque.api.routes.coverage import router as coverage_router
from echo_masque.api.routes.deployment_conversation_structure import (
    router as deployment_conversation_structure_router,
)
from echo_masque.api.routes.deployment_discovery import router as deployment_discovery_router
from echo_masque.api.routes.deployment_presence import router as deployment_presence_router
from echo_masque.api.routes.deployments import router as deployments_router
from echo_masque.api.routes.discord_identities import router as discord_identities_router
from echo_masque.api.routes.evaluations import router as evaluations_router
from echo_masque.api.routes.generated_media import router as generated_media_router
from echo_masque.api.routes.health import router as health_router
from echo_masque.api.routes.intelligence_product_completion import (
    router as intelligence_product_completion_router,
)
from echo_masque.api.routes.interactions import router as interactions_router
from echo_masque.api.routes.key_group_scout import router as key_group_scout_router
from echo_masque.api.routes.knowledge_fabric import router as knowledge_fabric_router
from echo_masque.api.routes.matrices import router as matrices_router
from echo_masque.api.routes.planner_media import router as planner_media_router
from echo_masque.api.routes.prompt_inspector import router as prompt_inspector_router
from echo_masque.api.routes.provider_traces import router as provider_traces_router
from echo_masque.api.routes.reports import router as reports_router
from echo_masque.api.routes.runtime_traces import router as runtime_traces_router
from echo_masque.api.routes.scheduled_reminders import router as scheduled_reminders_router
from echo_masque.api.routes.server_access import router as server_access_router
from echo_masque.api.routes.smart_participation import router as smart_participation_router
from echo_masque.api.routes.smart_participation_vnext import router as smart_participation_vnext_router
from echo_masque.api.routes.social_turn_interrupt import router as social_turn_interrupt_router
from echo_masque.api.routes.targets import router as targets_router
from echo_masque.api.routes.templates import router as templates_router
from echo_masque.api.routes.tools import router as tools_router
from echo_masque.api.routes.transcripts import router as transcripts_router
from echo_masque.api.routes.trials import router as trials_router
from echo_masque.api.routes.workspace import router as workspace_router

characters_router.include_router(character_portraits_router)
characters_router.include_router(character_relationships_router)
accounts_router.include_router(key_group_scout_router)
accounts_router.include_router(server_access_router)
connectors_router.include_router(generated_media_router)
connectors_router.include_router(planner_media_router)
connectors_router.include_router(social_turn_interrupt_router)
deployments_router.include_router(deployment_presence_router)
deployments_router.include_router(deployment_discovery_router)
deployments_router.include_router(deployment_relationships_router)
deployments_router.include_router(deployment_conversation_structure_router)
deployments_router.include_router(intelligence_product_completion_router)
smart_participation_router.include_router(smart_participation_vnext_router)

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
    "connectors_router",
    "conversation_burst_observability_router",
    "coverage_router",
    "deployments_router",
    "discord_identities_router",
    "evaluations_router",
    "health_router",
    "interactions_router",
    "knowledge_fabric_router",
    "matrices_router",
    "prompt_inspector_router",
    "provider_traces_router",
    "reports_router",
    "runtime_traces_router",
    "scheduled_reminders_router",
    "smart_participation_router",
    "targets_router",
    "templates_router",
    "tools_router",
    "transcripts_router",
    "trials_router",
    "workspace_router",
]
