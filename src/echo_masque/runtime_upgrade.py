"""Post-factory composition for Semantic Runtime V2 connector extensions."""

from fastapi import FastAPI

from echo_masque.conversation_media import ConversationMediaReferenceService
from echo_masque.media_continuation_runtime import MediaContinuationRuntime
from echo_masque.orchestration import CharacterTurnGraphRunner, SocialTurnGraphRunner


def upgrade_semantic_runtime(app: FastAPI) -> None:
    """Replace only the Connector Runtime while preserving existing repositories and Tool authority."""

    state = app.state
    conversation_media = ConversationMediaReferenceService(state.conversation_media_repository)
    runtime = MediaContinuationRuntime(
        state.repository,
        state.deployment_repository,
        state.credential_store,
        context_orchestrator=state.context_orchestrator,
        deployment_tool_repository=state.deployment_tool_repository,
        tool_registry=state.tool_registry,
        live_media_service=state.live_media_service,
        conversation_media_service=conversation_media,
    )
    state.discord_connector_runtime = runtime

    settings = state.settings
    character_runner = (
        CharacterTurnGraphRunner(runtime, trace_sink=state.durable_runtime_repository)
        if settings.langgraph_allows("character_turn")
        else None
    )
    social_runner = (
        SocialTurnGraphRunner(character_runner, trace_sink=state.durable_runtime_repository)
        if character_runner is not None and settings.langgraph_allows("social_turn")
        else None
    )
    state.character_turn_graph_runner = character_runner
    state.social_turn_graph_runner = social_runner


__all__ = ["upgrade_semantic_runtime"]
