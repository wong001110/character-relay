"""FastAPI application factory."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from echo_masque.api.routes import (
    accounts_router,
    admin_router,
    auth_router,
    authoring_archive_router,
    authoring_generation_router,
    authoring_router,
    calibration_router,
    characters_router,
    comparisons_router,
    connectors_router,
    conversation_burst_observability_router,
    coverage_router,
    deployments_router,
    discord_identities_router,
    evaluations_router,
    health_router,
    interactions_router,
    knowledge_fabric_router,
    matrices_router,
    prompt_inspector_router,
    provider_traces_router,
    reports_router,
    runtime_traces_router,
    scheduled_reminders_router,
    smart_participation_router,
    targets_router,
    templates_router,
    tools_router,
    transcripts_router,
    trials_router,
    workspace_router,
)
from echo_masque.api.routes.discord_debug_captures import (
    router as discord_debug_captures_router,
)
from echo_masque.audit_middleware import SensitiveAuditMiddleware
from echo_masque.auth import AuthService
from echo_masque.authoring_archive import AuthoringArchiveService
from echo_masque.authoring_generation import AuthoringGenerationService
from echo_masque.authoring_runtime import AuthoringRuntimeService
from echo_masque.browser_runtime import BrowserCapabilityManager, BrowserRuntimeSettings
from echo_masque.character_turn_context_v3 import CharacterTurnContextV3Service
from echo_masque.condition_watch_runtime import (
    ConditionWatchEvaluatorRuntime,
    ConditionWatchReminderNotifier,
)
from echo_masque.condition_watch_service import ConditionWatchService
from echo_masque.config import Settings, get_settings
from echo_masque.context_resolver_v3 import ContextResolverV3
from echo_masque.conversation_media import ConversationMediaReferenceService
from echo_masque.conversation_structure_resolver import ConversationStructureResolver
from echo_masque.coverage_analytics import CoverageAnalyticsService
from echo_masque.credentials import CredentialVault
from echo_masque.current_turn_belief_v3 import CurrentTurnBeliefRevisionService
from echo_masque.deployment_activity import DeploymentBrowsingActivityService
from echo_masque.deployment_activity_scheduler import DeploymentActivityScheduler
from echo_masque.deployment_discovery_service import DeploymentDiscoveryPreviewService
from echo_masque.discord_debug_capture import InMemoryDiscordDebugCaptureStore
from echo_masque.discord_inventory import DiscordInventoryService
from echo_masque.entity_grounding_v3 import EntityGroundingService
from echo_masque.evaluation_lifecycle import EvaluationAwareAccountLifecycleService
from echo_masque.evidence_graph_v3 import EvidenceGraphService
from echo_masque.image_creation_runtime import ImageCreationRuntimeService
from echo_masque.intelligence_v3_projection import ProjectionConversationRuntimeCoordinator
from echo_masque.internal_context import InternalContextService
from echo_masque.judge_evaluation import JudgeEvaluationService
from echo_masque.knowledge_fabric_atom_sync import KnowledgeFabricAtomSyncService
from echo_masque.knowledge_fabric_context import KnowledgeContextBuilder
from echo_masque.knowledge_fabric_epistemic_policy import PersistedCharacterEpistemicPolicy
from echo_masque.knowledge_fabric_external_policy import (
    ATOM_PUBLIC_HTTPS_SOURCE_TYPE,
    WEBSITE_COLLECTION_PUBLIC_HTTPS_SOURCE_TYPE,
    WEBSITE_PUBLIC_HTTPS_SOURCE_TYPE,
)
from echo_masque.knowledge_fabric_external_sync_report_retention import (
    KnowledgeFabricExternalSyncReportRetentionService,
)
from echo_masque.knowledge_fabric_external_sync_scheduler import (
    KnowledgeFabricExternalSyncScheduler,
)
from echo_masque.knowledge_fabric_ingestion import KnowledgeFabricIngestionService
from echo_masque.knowledge_fabric_invalidation_worker import KnowledgeFabricInvalidationWorker
from echo_masque.knowledge_fabric_pinned_fetcher import (
    AsyncioPinnedHttpsDialTransport,
    PinnedPublicHttpsFetcher,
)
from echo_masque.knowledge_fabric_query import KnowledgeQueryEngine
from echo_masque.knowledge_fabric_visual_identity import KnowledgeFabricVisualIdentityResolver
from echo_masque.knowledge_fabric_website_collection_sync import (
    KnowledgeFabricWebsiteCollectionSyncService,
)
from echo_masque.knowledge_fabric_website_sync import KnowledgeFabricWebsiteSyncService
from echo_masque.knowledge_gap_discovery_v3 import KnowledgeGapDiscoveryService
from echo_masque.knowledge_object_storage import object_storage_from_settings
from echo_masque.live_media_enhanced import EnhancedLiveMediaContextService
from echo_masque.live_media_scoped import KeyGroupScopedLiveMediaContextService
from echo_masque.media_tools import MediaToolRegistry
from echo_masque.orchestration import (
    CharacterTurnGraphRunner,
    ConditionWatchGraphRunner,
    SocialTurnGraphRunner,
)
from echo_masque.persistence import (
    AuthoringRepository,
    AuthRepository,
    CalibrationRepository,
    ConditionWatchRepository,
    ConversationMediaReferenceRepository,
    Database,
    DeploymentRepository,
    DeploymentToolRepository,
    DiscordIdentityRepository,
    DurableRuntimeRepository,
    EvaluationRepository,
    ExpressionRepository,
    GeneratedMediaArtifactRepository,
    InteractionRepository,
    KeyGroupRepository,
    KnowledgeFabricIndexRepository,
    KnowledgeFabricRepository,
    MatrixRepository,
    MediaAnalysisRepository,
    ProviderTraceRepository,
    Repository,
    ScheduledReminderRepository,
    SmartParticipationRepository,
    TargetAccessRepository,
    WorkspaceRepository,
    inspect_storage,
)
from echo_masque.persistence.belief_repository import BeliefRepository
from echo_masque.persistence.conversation_runtime_repository import ConversationRuntimeRepository
from echo_masque.persistence.conversation_structure_repository import (
    ConversationStructureRepository,
)
from echo_masque.persistence.entity_evidence_repository import EntityEvidenceRepository
from echo_masque.persistence.knowledge_fabric_content_repository import (
    KnowledgeFabricContentRepository,
)
from echo_masque.persistence.knowledge_fabric_external_schedule_repository import (
    KnowledgeFabricExternalScheduleRepository,
)
from echo_masque.persistence.knowledge_fabric_external_sync_repository import (
    KnowledgeFabricExternalSyncRepository,
)
from echo_masque.persistence.knowledge_fabric_external_sync_run_repository import (
    KnowledgeFabricExternalSyncRunRepository,
)
from echo_masque.persistence.knowledge_fabric_interpretation_repository import (
    KnowledgeFabricInterpretationRepository,
)
from echo_masque.persistence.knowledge_fabric_invalidation_repository import (
    KnowledgeFabricInvalidationRepository,
)
from echo_masque.persistence.knowledge_fabric_projection_repository import (
    KnowledgeFabricProjectionRepository,
)
from echo_masque.persistence.knowledge_fabric_site_collection_repository import (
    KnowledgeFabricSiteCollectionRepository,
)
from echo_masque.persistence.knowledge_fabric_visual_reference_repository import (
    KnowledgeFabricVisualReferenceRepository,
)
from echo_masque.persistence.server_runtime_repository import ServerRuntimeRepository
from echo_masque.planner_media import PlannerMediaDescriptorService
from echo_masque.prompt_inspector import CharacterPromptInspector
from echo_masque.provider_credentials import KeyGroupProviderCredentialResolver
from echo_masque.providers.trace import configure_provider_trace_sink
from echo_masque.public_demo import PublicDemoService
from echo_masque.public_demo_middleware import PublicDemoReadOnlyMiddleware
from echo_masque.public_demo_quota import PublicDemoQuotaService
from echo_masque.recall_media_connector_runtime import RecallAwareMediaDiscordConnectorRuntime
from echo_masque.scheduled_reminder_service import ScheduledReminderDeliveryService
from echo_masque.semantic_participation import CharacterParticipationSemanticService
from echo_masque.services import MatrixService, RuntimeService, TrialService
from echo_masque.smart_participation_generation import SmartParticipationGenerationService
from echo_masque.social_intelligence_v3 import SocialIntelligenceV3Service
from echo_masque.template_sharing import EvaluationTemplateService
from echo_masque.utility_gateway_live import ExistingProviderUtilityCaller
from echo_masque.utility_gateway_router import UtilityGatewayRouter
from echo_masque.utility_media_provider import UtilityMediaUnderstandingProvider

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    storage_status = inspect_storage(resolved)
    database = Database(resolved.database_url)
    database.initialize()
    migrated_timezones = ServerRuntimeRepository(database).migrate_legacy_utc_defaults()
    if migrated_timezones:
        logger.info(
            "Migrated %s legacy Discord Server timezone setting(s) from UTC to Asia/Kuala_Lumpur.",
            migrated_timezones,
        )
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
    bootstrap_admin = auth_service.ensure_bootstrap_admin()

    repository = Repository(database)
    deployment_repository = DeploymentRepository(database)
    discord_debug_capture_store = InMemoryDiscordDebugCaptureStore()
    deployment_tool_repository = DeploymentToolRepository(database)
    discord_identity_repository = DiscordIdentityRepository(database)
    scheduled_reminder_repository = ScheduledReminderRepository(database)
    condition_watch_repository = ConditionWatchRepository(database)
    durable_runtime_repository = DurableRuntimeRepository(database)
    browser_runtime = BrowserCapabilityManager(
        BrowserRuntimeSettings(
            enabled=resolved.browser_tools_enabled,
            page_idle_seconds=resolved.browser_page_idle_seconds,
            context_idle_seconds=resolved.browser_context_idle_seconds,
            browser_idle_seconds=resolved.browser_idle_seconds,
            browser_max_lifetime_seconds=resolved.browser_max_lifetime_seconds,
            browser_max_operations=resolved.browser_max_operations,
            max_concurrent_contexts=resolved.browser_max_concurrent_contexts,
            navigation_timeout_ms=resolved.browser_navigation_timeout_ms,
        )
    )
    interaction_repository = InteractionRepository(database)
    expression_repository = ExpressionRepository(database)
    smart_participation_repository = SmartParticipationRepository(database)
    semantic_participation_service = CharacterParticipationSemanticService(
        repository,
        smart_participation_repository,
        resolved,
    )
    knowledge_object_storage = object_storage_from_settings(resolved)
    knowledge_fabric_repository = KnowledgeFabricRepository(
        database,
        object_storage=knowledge_object_storage,
    )
    knowledge_fabric_content_repository = KnowledgeFabricContentRepository(
        database,
        object_storage=knowledge_object_storage,
    )
    knowledge_fabric_interpretation_repository = KnowledgeFabricInterpretationRepository(database)
    knowledge_fabric_index_repository = KnowledgeFabricIndexRepository(database)
    knowledge_fabric_invalidation_repository = KnowledgeFabricInvalidationRepository(database)
    knowledge_fabric_projection_repository = KnowledgeFabricProjectionRepository(database)
    knowledge_query_engine = KnowledgeQueryEngine(
        fabric_repository=knowledge_fabric_repository,
        index_repository=knowledge_fabric_index_repository,
    )
    # One fail-closed policy instance gates both automatic turn context and explicit
    # internal knowledge.search Tool output before either can return to a Character.
    character_epistemic_policy = PersistedCharacterEpistemicPolicy(knowledge_fabric_repository)
    knowledge_context_builder = KnowledgeContextBuilder(
        fabric_repository=knowledge_fabric_repository,
        query_engine=knowledge_query_engine,
        epistemic_policy=character_epistemic_policy,
    )
    knowledge_fabric_ingestion_service = KnowledgeFabricIngestionService(
        knowledge_fabric_content_repository,
        knowledge_object_storage,
        object_key_prefix=resolved.knowledge_object_storage_prefix,
    )
    external_sync_repository = KnowledgeFabricExternalSyncRepository(database)
    external_schedule_repository = KnowledgeFabricExternalScheduleRepository(database)
    external_sync_run_repository = KnowledgeFabricExternalSyncRunRepository(
        database, retention_days=resolved.knowledge_external_sync_report_retention_days
    )
    external_sync_report_retention = KnowledgeFabricExternalSyncReportRetentionService(
        external_sync_run_repository
    )
    site_collection_repository = KnowledgeFabricSiteCollectionRepository(database)

    async def resolve_public_host(hostname: str) -> tuple[str, ...]:
        loop = asyncio.get_running_loop()
        records = await loop.getaddrinfo(hostname, 443, type=0)
        return tuple(dict.fromkeys(str(record[4][0]) for record in records))

    pinned_fetcher = PinnedPublicHttpsFetcher(
        resolver=resolve_public_host,
        dial_transport=AsyncioPinnedHttpsDialTransport(timeout_seconds=15),
    )
    website_sync_service = KnowledgeFabricWebsiteSyncService(
        sync_repository=external_sync_repository,
        ingestion_service=knowledge_fabric_ingestion_service,
        fetcher=pinned_fetcher,
    )
    atom_sync_service = KnowledgeFabricAtomSyncService(
        sync_repository=external_sync_repository,
        ingestion_service=knowledge_fabric_ingestion_service,
        fetcher=pinned_fetcher,
    )
    website_collection_sync_service = KnowledgeFabricWebsiteCollectionSyncService(
        sync_repository=external_sync_repository,
        collection_repository=site_collection_repository,
        ingestion_service=knowledge_fabric_ingestion_service,
        fetcher=pinned_fetcher,
    )
    external_sync_scheduler = KnowledgeFabricExternalSyncScheduler(
        schedule_repository=external_schedule_repository,
        sync_run_repository=external_sync_run_repository,
        sync_by_source_type={
            WEBSITE_PUBLIC_HTTPS_SOURCE_TYPE: website_sync_service.sync_claim,
            ATOM_PUBLIC_HTTPS_SOURCE_TYPE: atom_sync_service.sync_claim,
            WEBSITE_COLLECTION_PUBLIC_HTTPS_SOURCE_TYPE: website_collection_sync_service.sync_claim,
        },
    )
    knowledge_fabric_invalidation_worker = KnowledgeFabricInvalidationWorker(
        invalidations=knowledge_fabric_invalidation_repository,
        indexes=knowledge_fabric_index_repository,
        projections=knowledge_fabric_projection_repository,
    )

    # Intelligence Core v3 runtime authorities.
    belief_repository = BeliefRepository(database)
    conversation_structure_repository = ConversationStructureRepository(database)
    conversation_runtime_repository = ConversationRuntimeRepository(database)

    if bootstrap_admin is not None:
        centralized = DiscordInventoryService(database).centralize(bootstrap_admin.id)
        if any(centralized.values()):
            logger.info("Centralized Discord inventory: %s", centralized)
    provider_trace_repository = ProviderTraceRepository(
        database,
        retention_days=resolved.provider_trace_retention_days,
        maximum_records=resolved.provider_trace_max_records,
    )
    configure_provider_trace_sink(provider_trace_repository.record_event)
    workspace_repository = WorkspaceRepository(database)
    authoring_repository = AuthoringRepository(database, workspace_repository)
    authoring_archive_service = AuthoringArchiveService(database, authoring_repository)
    evaluation_template_service = EvaluationTemplateService(
        workspace_repository,
        authoring_repository,
    )
    calibration_repository = CalibrationRepository(
        database,
        repository,
        workspace_repository,
    )
    evaluation_repository = EvaluationRepository(database)
    coverage_analytics_service = CoverageAnalyticsService(
        calibration_repository,
        evaluation_repository,
    )
    matrix_repository = MatrixRepository(database)
    character_prompt_inspector = CharacterPromptInspector(
        repository,
        matrix_repository,
    )
    target_access_repository = TargetAccessRepository(database)
    credential_store = CredentialVault(auth_repository, resolved)
    key_group_repository = KeyGroupRepository(database)
    media_analysis_repository = MediaAnalysisRepository(database)
    conversation_media_repository = ConversationMediaReferenceRepository(database)
    generated_media_repository = GeneratedMediaArtifactRepository(database)
    media_credential_resolver = KeyGroupProviderCredentialResolver(
        key_group_repository,
        credential_store,
    )
    conversation_media_service = ConversationMediaReferenceService(conversation_media_repository)
    image_creation_service = ImageCreationRuntimeService(
        credential_resolver=media_credential_resolver,
        conversation_media_repository=conversation_media_repository,
        artifact_repository=generated_media_repository,
    )
    internal_context_service = InternalContextService(
        belief_repository=belief_repository,
        structure_repository=conversation_structure_repository,
        runtime_repository=conversation_runtime_repository,
        settings=resolved,
        knowledge_context=knowledge_context_builder,
    )
    tool_registry = MediaToolRegistry(
        browser_runtime=browser_runtime,
        reminder_repository=scheduled_reminder_repository,
        condition_watch_repository=condition_watch_repository,
        condition_watch_enabled=True,
        discord_bot_token=resolved.discord_tool_bot_token,
        side_effect_store=durable_runtime_repository,
        image_creation_service=image_creation_service,
        internal_context_service=internal_context_service,
    )
    live_media_service = KeyGroupScopedLiveMediaContextService(
        media_repository=media_analysis_repository,
        credential_resolver=media_credential_resolver,
        discord_bot_token=resolved.discord_tool_bot_token,
    )
    deployment_activity_service = DeploymentBrowsingActivityService(database, resolved)
    deployment_activity_scheduler = DeploymentActivityScheduler(
        deployment_activity_service,
        poll_seconds=resolved.discovery_activity_poll_seconds,
    )
    scheduled_reminder_delivery = ScheduledReminderDeliveryService(
        scheduled_reminder_repository,
        deployment_repository,
        discord_identity_repository,
        credential_store,
        discord_bot_token=resolved.discord_tool_bot_token,
        poll_seconds=resolved.scheduler_poll_seconds,
        retry_seconds=resolved.scheduler_retry_seconds,
        max_attempts=resolved.scheduler_max_attempts,
        activity_scheduler=deployment_activity_scheduler,
    )
    condition_watch_evaluator = ConditionWatchEvaluatorRuntime(
        repository,
        deployment_repository,
        deployment_tool_repository,
        credential_store,
        tool_registry,
    )
    condition_watch_notifier = ConditionWatchReminderNotifier(
        scheduled_reminder_repository,
        deployment_repository,
    )
    condition_watch_graph_runner = (
        ConditionWatchGraphRunner(
            condition_watch_repository,
            evaluator=condition_watch_evaluator,
            notifier=condition_watch_notifier,
            trace_sink=durable_runtime_repository,
        )
        if resolved.langgraph_allows("condition_watch")
        else None
    )
    condition_watch_service = ConditionWatchService(
        condition_watch_repository,
        evaluator=condition_watch_evaluator,
        notifier=condition_watch_notifier,
        processor=condition_watch_graph_runner,
        poll_seconds=resolved.condition_watch_poll_seconds,
    )
    runtime_service = RuntimeService(repository, resolved, credential_store)
    planner_utility_gateway = UtilityGatewayRouter(
        runtime_service,
        caller=ExistingProviderUtilityCaller(),
    )
    conversation_structure_resolver = ConversationStructureResolver(
        conversation_structure_repository,
        resolved,
        planner_utility_gateway,
    )
    entity_evidence_repository = EntityEvidenceRepository(database)
    knowledge_gap_discovery_service = KnowledgeGapDiscoveryService(
        entities=entity_evidence_repository,
        discovery=DeploymentDiscoveryPreviewService(database, resolved),
    )
    conversation_runtime_coordinator = ProjectionConversationRuntimeCoordinator(
        conversation_structure_repository,
        conversation_runtime_repository,
        graph=EvidenceGraphService(entity_evidence_repository),
    )
    context_resolver_v3 = ContextResolverV3(
        structure=conversation_structure_repository,
        runtime=conversation_runtime_repository,
        entities=entity_evidence_repository,
        beliefs=belief_repository,
        social=SocialIntelligenceV3Service(database),
        identities=discord_identity_repository,
    )
    character_turn_context_v3_service = CharacterTurnContextV3Service(
        structure=conversation_structure_repository,
        structure_resolver=conversation_structure_resolver,
        runtime_coordinator=conversation_runtime_coordinator,
        context_resolver=context_resolver_v3,
        knowledge_context=knowledge_context_builder,
        corrections=CurrentTurnBeliefRevisionService(
            repository=belief_repository,
            gateway=planner_utility_gateway,
        ),
        entity_grounding=EntityGroundingService(entity_evidence_repository),
        knowledge_gap_discovery=knowledge_gap_discovery_service,
    )
    knowledge_fabric_visual_reference_repository = KnowledgeFabricVisualReferenceRepository(
        database
    )
    discord_connector_runtime = RecallAwareMediaDiscordConnectorRuntime(
        repository,
        deployment_repository,
        credential_store,
        context_service_v3=character_turn_context_v3_service,
        deployment_tool_repository=deployment_tool_repository,
        tool_registry=tool_registry,
        turn_director_gateway=planner_utility_gateway,
        live_media_service=live_media_service,
        conversation_media_service=conversation_media_service,
        visual_identity_resolver=KnowledgeFabricVisualIdentityResolver(
            fabric=knowledge_fabric_repository,
            references=knowledge_fabric_visual_reference_repository,
            object_storage=knowledge_object_storage,
        ),
    )
    character_turn_graph_runner = (
        CharacterTurnGraphRunner(
            discord_connector_runtime,
            trace_sink=durable_runtime_repository,
        )
        if resolved.langgraph_allows("character_turn")
        else None
    )
    social_turn_graph_runner = (
        SocialTurnGraphRunner(
            character_turn_graph_runner,
            trace_sink=durable_runtime_repository,
        )
        if (character_turn_graph_runner is not None and resolved.langgraph_allows("social_turn"))
        else None
    )
    public_demo_result = PublicDemoService(
        settings=resolved,
        auth_service=auth_service,
        auth_repository=auth_repository,
        repository=repository,
        workspace_repository=workspace_repository,
        target_access_repository=target_access_repository,
        credential_store=credential_store,
    ).synchronize()
    if public_demo_result is not None:
        logger.info(
            "Public Demo ready: user=%s characters=%s scenarios=%s packs=%s",
            public_demo_result.user_id,
            public_demo_result.character_count,
            public_demo_result.scenario_count,
            public_demo_result.test_pack_count,
        )
    quota_service = PublicDemoQuotaService(database, resolved)
    account_lifecycle_service = EvaluationAwareAccountLifecycleService(
        database,
        auth_repository,
        authoring_archive_service,
        calibration_repository,
        evaluation_repository,
        deployment_repository,
        discord_identity_repository,
        interaction_repository,
        expression_repository,
        smart_participation_repository,
        knowledge_fabric_repository,
        deployment_tool_repository,
        scheduled_reminder_repository,
        condition_watch_repository,
        conversation_media_repository,
        generated_media_repository,
    )
    recovered_matrices = matrix_repository.recover_interrupted()
    if recovered_matrices:
        logger.warning(
            "Recovered %s interrupted Experiment Matrices as paused.",
            recovered_matrices,
        )
    recovered_knowledge_ingestion_jobs = (
        knowledge_fabric_ingestion_service.recover_interrupted_jobs()
    )
    if recovered_knowledge_ingestion_jobs:
        logger.warning(
            "Requeued %s interrupted Knowledge Fabric ingestion jobs.",
            recovered_knowledge_ingestion_jobs,
        )
    repository.seed_demo_targets()
    repository.remove_demo_character_cards()
    planner_media_service = PlannerMediaDescriptorService(
        media=EnhancedLiveMediaContextService.from_service(
            live_media_service,
            browser_runtime=browser_runtime,
        ),
        utility_provider=UtilityMediaUnderstandingProvider(planner_utility_gateway),
    )
    authoring_runtime_service = AuthoringRuntimeService(
        database,
        auth_repository,
        credential_store,
        resolved,
    )
    authoring_generation_service = AuthoringGenerationService(
        repository,
        workspace_repository,
        authoring_repository,
        auth_repository,
        authoring_runtime_service,
    )
    smart_participation_generation_service = SmartParticipationGenerationService(
        repository,
        authoring_runtime_service,
    )
    judge_evaluation_service = JudgeEvaluationService(
        calibration_repository,
        evaluation_repository,
        repository,
        workspace_repository,
        runtime_service,
    )
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

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await browser_runtime.start()
        await scheduled_reminder_delivery.start()
        await condition_watch_service.start()
        await external_sync_report_retention.start()
        await external_sync_scheduler.start()
        await knowledge_fabric_invalidation_worker.start()
        try:
            yield
        finally:
            await knowledge_fabric_invalidation_worker.stop()
            await condition_watch_service.stop()
            await external_sync_scheduler.stop()
            await external_sync_report_retention.stop()
            await scheduled_reminder_delivery.stop()
            await browser_runtime.stop()

    app = FastAPI(
        title=resolved.app_name,
        version=resolved.app_version,
        debug=resolved.debug,
        description=(
            "Create, test, publish, and deploy persistent AI characters across chat platforms."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SensitiveAuditMiddleware, repository=auth_repository)
    app.add_middleware(PublicDemoReadOnlyMiddleware)
    app.state.settings = resolved
    app.state.storage_status = storage_status
    app.state.database = database
    app.state.auth_repository = auth_repository
    app.state.auth_service = auth_service
    app.state.repository = repository
    app.state.deployment_repository = deployment_repository
    app.state.discord_debug_capture_store = discord_debug_capture_store
    app.state.deployment_tool_repository = deployment_tool_repository
    app.state.tool_registry = tool_registry
    app.state.browser_runtime = browser_runtime
    app.state.scheduled_reminder_repository = scheduled_reminder_repository
    app.state.scheduled_reminder_delivery = scheduled_reminder_delivery
    app.state.deployment_activity_service = deployment_activity_service
    app.state.deployment_activity_scheduler = deployment_activity_scheduler
    app.state.condition_watch_repository = condition_watch_repository
    app.state.condition_watch_graph_runner = condition_watch_graph_runner
    app.state.condition_watch_service = condition_watch_service
    app.state.discord_identity_repository = discord_identity_repository
    app.state.interaction_repository = interaction_repository
    app.state.expression_repository = expression_repository
    app.state.smart_participation_repository = smart_participation_repository
    app.state.semantic_participation_service = semantic_participation_service
    app.state.knowledge_fabric_repository = knowledge_fabric_repository
    app.state.knowledge_fabric_index_repository = knowledge_fabric_index_repository
    app.state.knowledge_fabric_invalidation_repository = knowledge_fabric_invalidation_repository
    app.state.knowledge_fabric_projection_repository = knowledge_fabric_projection_repository
    app.state.knowledge_query_engine = knowledge_query_engine
    app.state.knowledge_object_storage = knowledge_object_storage
    app.state.knowledge_fabric_content_repository = knowledge_fabric_content_repository
    app.state.knowledge_fabric_interpretation_repository = (
        knowledge_fabric_interpretation_repository
    )
    app.state.knowledge_fabric_ingestion_service = knowledge_fabric_ingestion_service
    app.state.knowledge_fabric_external_schedule_repository = external_schedule_repository
    app.state.knowledge_fabric_external_sync_repository = external_sync_repository
    app.state.knowledge_fabric_external_sync_run_repository = external_sync_run_repository
    app.state.knowledge_fabric_external_sync_report_retention = external_sync_report_retention
    app.state.knowledge_fabric_site_collection_repository = site_collection_repository
    app.state.knowledge_fabric_external_sync_scheduler = external_sync_scheduler
    app.state.knowledge_fabric_invalidation_worker = knowledge_fabric_invalidation_worker
    app.state.knowledge_fabric_visual_reference_repository = (
        knowledge_fabric_visual_reference_repository
    )
    app.state.entity_evidence_repository = entity_evidence_repository
    app.state.knowledge_gap_discovery_service = knowledge_gap_discovery_service
    app.state.context_resolver_v3 = context_resolver_v3
    app.state.conversation_structure_resolver_v3 = conversation_structure_resolver
    app.state.conversation_runtime_coordinator_v3 = conversation_runtime_coordinator
    app.state.character_turn_context_v3_service = character_turn_context_v3_service
    app.state.utility_gateway_router_v3 = planner_utility_gateway
    app.state.provider_trace_repository = provider_trace_repository
    app.state.durable_runtime_repository = durable_runtime_repository
    app.state.key_group_repository = key_group_repository
    app.state.media_analysis_repository = media_analysis_repository
    app.state.conversation_media_repository = conversation_media_repository
    app.state.generated_media_repository = generated_media_repository
    app.state.image_creation_service = image_creation_service
    app.state.live_media_service = live_media_service
    app.state.belief_repository = belief_repository
    app.state.conversation_structure_repository = conversation_structure_repository
    app.state.conversation_runtime_repository = conversation_runtime_repository
    app.state.internal_context_service = internal_context_service
    app.state.planner_media_service = planner_media_service
    app.state.discord_connector_runtime = discord_connector_runtime
    app.state.character_turn_graph_runner = character_turn_graph_runner
    app.state.social_turn_graph_runner = social_turn_graph_runner
    app.state.workspace_repository = workspace_repository
    app.state.authoring_repository = authoring_repository
    app.state.authoring_archive_service = authoring_archive_service
    app.state.evaluation_template_service = evaluation_template_service
    app.state.authoring_runtime_service = authoring_runtime_service
    app.state.authoring_generation_service = authoring_generation_service
    app.state.smart_participation_generation_service = smart_participation_generation_service
    app.state.calibration_repository = calibration_repository
    app.state.evaluation_repository = evaluation_repository
    app.state.coverage_analytics_service = coverage_analytics_service
    app.state.judge_evaluation_service = judge_evaluation_service
    app.state.matrix_repository = matrix_repository
    app.state.character_prompt_inspector = character_prompt_inspector
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
    app.include_router(discord_debug_captures_router)
    app.include_router(conversation_burst_observability_router)
    app.include_router(provider_traces_router)
    app.include_router(runtime_traces_router)
    app.include_router(authoring_router)
    app.include_router(authoring_archive_router)
    app.include_router(authoring_generation_router)
    app.include_router(calibration_router)
    app.include_router(evaluations_router)
    app.include_router(coverage_router)
    app.include_router(templates_router)
    app.include_router(characters_router)
    app.include_router(deployments_router)
    app.include_router(tools_router)
    app.include_router(scheduled_reminders_router)
    app.include_router(discord_identities_router)
    app.include_router(interactions_router)
    app.include_router(smart_participation_router)
    app.include_router(knowledge_fabric_router)
    app.include_router(connectors_router)
    app.include_router(prompt_inspector_router)
    app.include_router(targets_router)
    app.include_router(trials_router)
    app.include_router(transcripts_router)
    app.include_router(comparisons_router)
    app.include_router(reports_router)
    app.include_router(workspace_router)
    app.include_router(matrices_router)

    web_dist = Path("web/dist")
    if web_dist.exists():

        @app.get("/characters", include_in_schema=False)
        @app.get("/characters/", include_in_schema=False)
        @app.get("/characters/new", include_in_schema=False)
        @app.get("/characters/{character_id}/prompt/inspect", include_in_schema=False)
        @app.get("/characters/{character_id}/persona", include_in_schema=False)
        @app.get("/characters/{character_id}/prompt", include_in_schema=False)
        @app.get("/characters/{character_id}/memory", include_in_schema=False)
        @app.get("/characters/{character_id}/runtime", include_in_schema=False)
        @app.get("/characters/{character_id}/deployments", include_in_schema=False)
        @app.get("/characters/{character_id}/edit", include_in_schema=False)
        @app.get("/characters/{character_id}/test", include_in_schema=False)
        @app.get("/characters/{character_id}", include_in_schema=False)
        @app.get("/deployments", include_in_schema=False)
        @app.get("/deployments/", include_in_schema=False)
        @app.get("/deployments/{server_profile_id}/characters", include_in_schema=False)
        @app.get("/deployments/{server_profile_id}/knowledge", include_in_schema=False)
        @app.get("/deployments/{server_profile_id}/interactions", include_in_schema=False)
        @app.get("/deployments/{server_profile_id}/intelligence", include_in_schema=False)
        @app.get("/deployments/{server_profile_id}/intelligence/presence", include_in_schema=False)
        @app.get("/deployments/{server_profile_id}/intelligence/social", include_in_schema=False)
        @app.get(
            "/deployments/{server_profile_id}/intelligence/participation",
            include_in_schema=False,
        )
        @app.get(
            "/deployments/{server_profile_id}/intelligence/conversation",
            include_in_schema=False,
        )
        @app.get("/deployments/{server_profile_id}/intelligence/discovery", include_in_schema=False)
        @app.get("/toolbox", include_in_schema=False)
        @app.get("/toolbox/", include_in_schema=False)
        @app.get("/settings", include_in_schema=False)
        @app.get("/settings/", include_in_schema=False)
        @app.get("/dev/ui", include_in_schema=False)
        @app.get("/dev/ui/", include_in_schema=False)
        def portal_index(
            character_id: str = "",
            server_profile_id: str = "",
        ) -> FileResponse:
            """Serve the Portal entry document for an explicitly supported client route."""

            del character_id
            del server_profile_id
            return FileResponse(web_dist / "index.html")

        app.mount("/", StaticFiles(directory=web_dist, html=True), name="web")
    else:

        @app.get("/", include_in_schema=False)
        def root() -> JSONResponse:
            return JSONResponse(
                {"name": resolved.app_name, "ui": "Run `cd web && npm install && npm run dev`."}
            )

    return app


__all__ = ["create_app"]
