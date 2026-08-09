from pathlib import Path

from echo_masque.api import create_app
from echo_masque.config import Settings
from echo_masque.orchestration import ConditionWatchGraphRunner


def settings(
    path: Path,
    *,
    langgraph_enabled: bool,
    condition_watch_enabled: bool,
) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        browser_tools_enabled=False,
        semantic_participation_enabled=False,
        legacy_local_user_enabled=False,
        langgraph_enabled=langgraph_enabled,
        langgraph_condition_watch_enabled=condition_watch_enabled,
    )


def test_condition_watch_graph_runner_is_disabled_by_default(tmp_path: Path) -> None:
    app = create_app(
        settings(
            tmp_path / "graph-disabled.db",
            langgraph_enabled=False,
            condition_watch_enabled=False,
        )
    )

    assert app.state.condition_watch_graph_runner is None
    assert app.state.condition_watch_service.processor is None


def test_condition_watch_switch_cannot_bypass_master_kill_switch(tmp_path: Path) -> None:
    app = create_app(
        settings(
            tmp_path / "master-disabled.db",
            langgraph_enabled=False,
            condition_watch_enabled=True,
        )
    )

    assert app.state.condition_watch_graph_runner is None
    assert app.state.condition_watch_service.processor is None


def test_master_switch_does_not_enable_condition_watch_by_itself(tmp_path: Path) -> None:
    app = create_app(
        settings(
            tmp_path / "workflow-disabled.db",
            langgraph_enabled=True,
            condition_watch_enabled=False,
        )
    )

    assert app.state.condition_watch_graph_runner is None
    assert app.state.condition_watch_service.processor is None


def test_condition_watch_graph_runner_requires_both_rollout_switches(tmp_path: Path) -> None:
    app = create_app(
        settings(
            tmp_path / "graph-enabled.db",
            langgraph_enabled=True,
            condition_watch_enabled=True,
        )
    )

    runner = app.state.condition_watch_graph_runner
    assert isinstance(runner, ConditionWatchGraphRunner)
    assert app.state.condition_watch_service.processor is runner
