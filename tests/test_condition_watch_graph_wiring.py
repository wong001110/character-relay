from pathlib import Path

from echo_masque.api import create_app
from echo_masque.config import Settings
from echo_masque.orchestration import ConditionWatchGraphRunner


def settings(path: Path, *, langgraph_enabled: bool) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        browser_tools_enabled=False,
        semantic_participation_enabled=False,
        legacy_local_user_enabled=False,
        langgraph_enabled=langgraph_enabled,
    )


def test_condition_watch_graph_runner_is_disabled_by_default(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "graph-disabled.db", langgraph_enabled=False))

    assert app.state.condition_watch_graph_runner is None
    assert app.state.condition_watch_service.processor is None


def test_condition_watch_graph_runner_is_wired_when_feature_is_enabled(
    tmp_path: Path,
) -> None:
    app = create_app(settings(tmp_path / "graph-enabled.db", langgraph_enabled=True))

    runner = app.state.condition_watch_graph_runner
    assert isinstance(runner, ConditionWatchGraphRunner)
    assert app.state.condition_watch_service.processor is runner
