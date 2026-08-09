from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from echo_masque.config import Settings
from echo_masque.orchestration import (
    OrchestrationRuntimeContext,
    RuntimeTraceEvent,
    build_foundation_graph,
)


@dataclass
class MemoryTraceSink:
    events: list[RuntimeTraceEvent] = field(default_factory=list)

    def emit(self, event: RuntimeTraceEvent) -> None:
        self.events.append(event)


def test_langgraph_feature_flags_default_disabled() -> None:
    settings = Settings(environment="test")
    assert settings.langgraph_enabled is False
    assert settings.langgraph_condition_watch_enabled is False
    assert settings.langgraph_character_turn_enabled is False
    assert settings.langgraph_social_turn_enabled is False


def test_langgraph_feature_flags_can_be_enabled(monkeypatch: Any) -> None:
    monkeypatch.setenv("CHARACTER_RELAY_LANGGRAPH_ENABLED", "true")
    monkeypatch.setenv("CHARACTER_RELAY_LANGGRAPH_CONDITION_WATCH_ENABLED", "true")
    settings = Settings(environment="test")
    assert settings.langgraph_enabled is True
    assert settings.langgraph_condition_watch_enabled is True


def test_foundation_graph_exercises_state_context_and_trace_contracts() -> None:
    sink = MemoryTraceSink()
    graph = build_foundation_graph()

    result = graph.invoke(
        {
            "trace_id": "trace-phase-1",
            "graph_run_id": "run-phase-1",
            "status": "pending",
        },
        context=OrchestrationRuntimeContext(trace_sink=sink),
    )

    assert result["graph_name"] == "foundation"
    assert result["orchestration_version"] == "langgraph-phase-1"
    assert result["status"] == "completed"
    assert [event.status for event in sink.events] == ["started", "completed"]
    assert sink.events[-1].changed_keys == (
        "graph_name",
        "orchestration_version",
        "status",
    )
    assert sink.events[-1].metadata == (("shadow_mode", "true"),)
