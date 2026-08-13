from echo_masque.api import create_app
from echo_masque.config import Settings
from echo_masque.media_continuation_runtime import MediaContinuationRuntime
from echo_masque.runtime_upgrade import upgrade_semantic_runtime


def test_runtime_v2_reuses_existing_tool_authority() -> None:
    app = create_app(
        Settings(
            environment="test",
            database_url="sqlite://",
            public_demo_enabled=False,
            browser_tools_enabled=False,
            semantic_embedding_enabled=False,
            semantic_participation_enabled=False,
        )
    )
    tool_registry = app.state.tool_registry
    deployment_tools = app.state.deployment_tool_repository
    credential_store = app.state.credential_store

    upgrade_semantic_runtime(app)

    assert isinstance(app.state.discord_connector_runtime, MediaContinuationRuntime)
    assert app.state.discord_connector_runtime.tool_registry is tool_registry
    assert app.state.discord_connector_runtime.deployment_tool_repository is deployment_tools
    assert app.state.discord_connector_runtime.credential_store is credential_store
