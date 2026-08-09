from pathlib import Path

from echo_masque.api import create_app
from echo_masque.config import LangGraphMode, Settings
from echo_masque.orchestration import ConditionWatchGraphRunner


def settings(path: Path, *, langgraph_mode: LangGraphMode) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        browser_tools_enabled=False,
        semantic_participation_enabled=False,
        legacy_local_user_enabled=False,
        langgraph_mode=langgraph_mode,
    )


def test_condition_watch_graph_runner_is_disabled_in_off_mode(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "graph-disabled.db", langgraph_mode="off"))

    assert app.state.condition_watch_graph_runner is None
    assert app.state.condition_watch_service.processor is None


def test_condition_watch_mode_wires_graph_runner(tmp_path: Path) -> None:
    app = create_app(
        settings(tmp_path / "condition-watch.db", langgraph_mode="condition_watch")
    )

    runner = app.state.condition_watch_graph_runner
    assert isinstance(runner, ConditionWatchGraphRunner)
    assert app.state.condition_watch_service.processor is runner


def test_later_rollout_modes_keep_condition_watch_on(tmp_path: Path) -> None:
    for mode in ("character_turn", "social_turn"):
        app = create_app(settings(tmp_path / f"{mode}.db", langgraph_mode=mode))

        runner = app.state.condition_watch_graph_runner
        assert isinstance(runner, ConditionWatchGraphRunner)
        assert app.state.condition_watch_service.processor is runner
