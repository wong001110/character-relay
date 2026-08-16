"""FastAPI application factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
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
    authoring_generation_router,
    authoring_router,
    calibration_router,
    characters_router,
    comparisons_router,
    connectors_router,
    conversation_burst_observability_router,
    conversation_intelligence_router,
    coverage_router,
    deployments_router,
    discord_identities_router,
    evaluations_router,
    health_router,
    interactions_router,
    knowledge_router,
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
from echo_masque.audit_middleware import SensitiveAuditMiddleware
from echo_masque.auth import AuthService
from echo_masque.authoring_archive import AuthoringArchiveService
from echo_masque.authoring_generation import AuthoringGenerationService
from echo_masque.authoring_runtime import AuthoringRuntimeService
from echo_masque.browser_runtime import BrowserCapabilityManager, BrowserRuntimeSettings
from echo_masque.condition_watch_runtime import (
    ConditionWatchEvaluatorRuntime,
    ConditionWatchReminderNotifier,
)
from echo_masque.condition_watch_service import ConditionWatchService
from echo_masque.config import Settings, get_settings
from echo_masque.context_layer import ContextOrchestrator
from echo_masque.conversation_consolidation import ConversationConsolidationService
from echo_masque.conversation_media import ConversationMediaReferenceService
from echo_masque.coverage_analytics import CoverageAnalyticsService
from echo_masque.credentials import CredentialVault
from echo_masque.discord_inventory import DiscordInventoryService
from echo_masque.evaluation_lifecycle import EvaluationAwareAccountLifecycleService
from echo_masque.image_creation_runtime import ImageCreationRuntimeService
from echo_masque.internal_context import InternalContextService
from echo_masque.judge_evaluation import JudgeEvaluationService
from echo_masque.live_media_enhanced import EnhancedLiveMediaContextService
from echo_masque.live_media_scoped import KeyGroupScopedLiveMediaContextService
from echo_masque.media_connector_runtime import MediaAwareDiscordConnectorRuntime
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
    KnowledgeRepository,
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
from echo_masque.persistence.conversation_episode_repository import ConversationEpisodeRepository
from echo_masque.persistence.conversation_topic_repository import ConversationTopicRepository
from echo_masque.persistence.memory_vnext_repository import MemoryVNextRepository
from echo_masque.persistence.server_knowledge_repository import (
    ConsolidationCheckpointRepository,
    ConversationAuthorityGraphRepository,
    ServerWikiRepository,
)
from echo_masque.persistence.server_runtime_repository import ServerRuntimeRepository
from echo_masque.planner_media import PlannerMediaDescriptorService
from echo_masque.prompt_inspector import CharacterPromptInspector
from echo_masque.provider_credentials import KeyGroupProviderCredentialResolver
from echo_masque.providers.trace import configure_provider_trace_sink
from echo_masque.public_demo import PublicDemoService
from echo_masque.public_demo_middleware import PublicDemoReadOnlyMiddleware
from echo_masque.public_demo_quota import PublicDemoQuotaService
from echo_masque.scheduled_reminder_service import ScheduledReminderDeliveryService
from echo_masque.semantic_participation import CharacterParticipationSemanticService
from echo_masque.services import MatrixService, RuntimeService, TrialService
from echo_masque.smart_participation_generation import SmartParticipationGenerationService
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
    memory_vnext_repository = MemoryVNextRepository(database)
    reset_legacy_memory = memory_vnext_repository.reset_legacy_dirty_data_once()
    if reset_legacy_memory:
        logger.info(
            "Reset %s legacy derived Memory record(s) for Memory vNext.",
            reset_legacy_memory,
        )
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
    knowledge_repository = KnowledgeRepository(database)
    server_wiki_repository = ServerWikiRepository(database)
    conversation_authority_graph_repository = ConversationAuthorityGraphRepository(
        database
    )
    consolidation_checkpoint_repository = ConsolidationCheckpointRepository(database)
    context_orchestrator = ContextOrchestrator(knowledge_repository)
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
        memory_repository=memory_vnext_repository,
        topic_repository=ConversationTopicRepository(database),
        episode_repository=ConversationEpisodeRepository(database),
        settings=resolved,
        wiki_lookup_backend=server_wiki_repository.lookup,
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
    scheduled_reminder_delivery = ScheduledReminderDeliveryService(
        scheduled_reminder_repository,
        deployment_repository,
        discord_identity_repository,
        credential_store,
        discord_bot_token=resolved.discord_tool_bot_token,
        poll_seconds=resolved.scheduler_poll_seconds,
        retry_seconds=resolved.scheduler_retry_seconds,
        max_attempts=resolved.scheduler_max_attempts,
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
    discord_connector_runtime = MediaAwareDiscordConnectorRuntime(
        repository,
        deployment_repository,
        credential_store,
        context_orchestrator=context_orchestrator,
        deployment_tool_repository=deployment_tool_repository,
        tool_registry=tool_registry,
        live_media_service=live_media_service,
        conversation_media_service=conversation_media_service,
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
        knowledge_repository,
        deployment_tool_repository,
        scheduled_reminder_repository,
        condition_watch_repository,
        memory_vnext_repository=memory_vnext_repository,
        server_wiki_repository=server_wiki_repository,
        conversation_authority_graph_repository=conversation_authority_graph_repository,
        consolidation_checkpoint_repository=consolidation_checkpoint_repository,
    )
    recovered_matrices = matrix_repository.recover_interrupted()
    if recovered_matrices:
        logger.warning(
            "Recovered %s interrupted Experiment Matrices as paused.",
            recovered_matrices,
        )
    repository.seed_demo_targets()
    repository.remove_demo_character_cards()
    runtime_service = RuntimeService(repository, resolved, credential_store)
    planner_utility_gateway = UtilityGatewayRouter(
        runtime_service,
        caller=ExistingProviderUtilityCaller(),
    )
    conversation_consolidation_service = ConversationConsolidationService(
        topic_repository=ConversationTopicRepository(database),
        episode_repository=ConversationEpisodeRepository(database),
        memory_repository=memory_vnext_repository,
        wiki_repository=server_wiki_repository,
        graph_repository=conversation_authority_graph_repository,
        checkpoint_repository=consolidation_checkpoint_repository,
        gateway=planner_utility_gateway,
    )
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
        await conversation_consolidation_service.start()
        try:
            yield
        finally:
            await conversation_consolidation_service.stop()
            await condition_watch_service.stop()
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
    app.state.deployment_tool_repository = deployment_tool_repository
    app.state.tool_registry = tool_registry
    app.state.browser_runtime = browser_runtime
    app.state.scheduled_reminder_repository = scheduled_reminder_repository
    app.state.scheduled_reminder_delivery = scheduled_reminder_delivery
    app.state.condition_watch_repository = condition_watch_repository
    app.state.condition_watch_graph_runner = condition_watch_graph_runner
    app.state.condition_watch_service = condition_watch_service
    app.state.discord_identity_repository = discord_identity_repository
    app.state.interaction_repository = interaction_repository
    app.state.expression_repository = expression_repository
    app.state.smart_participation_repository = smart_participation_repository
    app.state.semantic_participation_service = semantic_participation_service
    app.state.knowledge_repository = knowledge_repository
    app.state.context_orchestrator = context_orchestrator
    app.state.provider_trace_repository = provider_trace_repository
    app.state.durable_runtime_repository = durable_runtime_repository
    app.state.key_group_repository = key_group_repository
    app.state.media_analysis_repository = media_analysis_repository
    app.state.conversation_media_repository = conversation_media_repository
    app.state.generated_media_repository = generated_media_repository
    app.state.image_creation_service = image_creation_service
    app.state.live_media_service = live_media_service
    app.state.memory_vnext_repository = memory_vnext_repository
    app.state.server_wiki_repository = server_wiki_repository
    app.state.conversation_authority_graph_repository = (
        conversation_authority_graph_repository
    )
    app.state.consolidation_checkpoint_repository = consolidation_checkpoint_repository
    app.state.conversation_consolidation_service = conversation_consolidation_service
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
    app.include_router(conversation_intelligence_router)
    app.include_router(knowledge_router)
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
        app.mount("/", StaticFiles(directory=web_dist, html=True), name="web")
    else:

        @app.get("/", include_in_schema=False)
        def root() -> JSONResponse:
            return JSONResponse(
                {"name": resolved.app_name, "ui": "Run `cd web && npm install && npm run dev`."}
            )

    return app


__all__ = ["create_app"]
