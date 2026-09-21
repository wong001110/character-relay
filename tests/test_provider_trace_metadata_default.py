"""Metadata defaults must not persist raw group-chat or provider error prose."""

import json

import pytest

from echo_masque.persistence import Database
from echo_masque.persistence.provider_trace_repository import ProviderTraceRepository
from echo_masque.provider_trace_classification import provider_trace_category
from echo_masque.providers import trace as trace_module
from echo_masque.providers.base import ChatMessage
from echo_masque.providers.trace import ProviderTrace, configure_provider_trace_sink


@pytest.mark.parametrize("configured", [None, "metadata", "invalid-mode", ""])
def test_default_and_invalid_modes_exclude_prose_but_keep_usage(
    monkeypatch: pytest.MonkeyPatch, configured: str | None,
) -> None:
    if configured is None:
        monkeypatch.delenv("CHARACTER_RELAY_PROVIDER_TRACE_MODE", raising=False)
    else:
        monkeypatch.setenv("CHARACTER_RELAY_PROVIDER_TRACE_MODE", configured)
    events: list[dict[str, object]] = []
    configure_provider_trace_sink(events.append)
    try:
        trace = ProviderTrace.start(
            endpoint="https://provider.example.test/v1/chat/completions", model="test-model",
            temperature=0.1, messages=(ChatMessage(role="user", content="PRIVATE_MEMBER_TEXT"),),
        )
        trace.retry(attempt=1, reason="network_error")
        trace.error(reason="provider_http_error", status_code=500,
                    response_body="PRIVATE_BODY", detail="PRIVATE_ERROR_DETAIL")
        trace.response(status_code=200, response_model="test-model", text="PRIVATE_REPLY",
                       input_tokens=None, output_tokens=7, finish_reason="stop")
    finally:
        configure_provider_trace_sink(None)
    assert len(events) == 4
    assert all(item["trace_mode"] == "metadata" for item in events)
    assert "PRIVATE_" not in json.dumps(events)
    assert events[0]["message_count"] == 1
    assert events[1]["attempt"] == 1
    assert events[2]["status_code"] == 500
    assert events[3]["input_tokens"] is None
    assert events[3]["output_tokens"] == 7


def test_metadata_preserves_tool_failure_and_category_without_tool_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHARACTER_RELAY_PROVIDER_TRACE_MODE", "metadata")
    database = Database("sqlite://")
    database.initialize()
    repository = ProviderTraceRepository(database)
    events: list[dict[str, object]] = []
    configure_provider_trace_sink(events.append)
    try:
        trace = ProviderTrace.start(
            endpoint="https://provider.example.test/v1/chat/completions", model="test-model",
            temperature=0.1,
            messages=(
                ChatMessage(role="tool", content='{"ok":false,"error":"PRIVATE_TOOL_ERROR"}'),
                ChatMessage(role="tool", content='{"ok":true,"value":"PRIVATE_TOOL_VALUE"}'),
            ),
        )
        trace.response(status_code=200, response_model="test-model", text="PRIVATE_REPLY",
                       input_tokens=15, output_tokens=5, finish_reason="stop")
    finally:
        configure_provider_trace_sink(None)
    assert events[0]["failed_tool_result_count"] == 1
    assert provider_trace_category(json.dumps(events[0]), json.dumps(events[1])) == "tool_calling"
    assert "PRIVATE_" not in json.dumps(events)
    for event in events:
        repository.record_event(event)
    record = repository.get_trace(trace.trace_id)
    assert record is not None
    assert record.trace_mode == "metadata"
    assert record.status == "error"
    assert record.input_tokens == 15


def test_metadata_preserves_character_category_without_prompt_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHARACTER_RELAY_PROVIDER_TRACE_MODE", "metadata")
    events: list[dict[str, object]] = []
    configure_provider_trace_sink(events.append)
    try:
        ProviderTrace.start(
            endpoint="https://provider.example.test/v1/chat/completions", model="test-model",
            temperature=0.1, messages=(ChatMessage(
                role="user",
                content="real Discord group conversation through Character Relay PRIVATE_TEXT",
            ),),
        )
    finally:
        configure_provider_trace_sink(None)
    assert provider_trace_category(json.dumps(events[0]), "{}") == "character_turn"
    assert "PRIVATE_TEXT" not in json.dumps(events)


def test_off_mode_still_emits_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHARACTER_RELAY_PROVIDER_TRACE_MODE", "off")
    events: list[dict[str, object]] = []
    configure_provider_trace_sink(events.append)
    try:
        trace = ProviderTrace.start(endpoint="https://provider.example.test", model="model",
                                    temperature=0, messages=())
        trace.error(reason="failed", detail="private")
    finally:
        configure_provider_trace_sink(None)
    assert events == []


def test_metadata_response_can_promote_a_model_or_character_call_to_tool_calling() -> None:
    for category in ("model_call", "character_turn"):
        request = json.dumps({"category": category, "message_roles": ["user"]})
        response = json.dumps({"tool_call_names": ["memory_search"]})
        assert provider_trace_category(request, response) == "tool_calling"
    request = json.dumps({"category": "media_understanding", "message_roles": ["user"]})
    response = json.dumps({"tool_call_names": ["memory_search"]})
    assert provider_trace_category(request, response) == "media_understanding"


def test_diagnostic_classification_failure_does_not_abort_provider_tracing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_classification(*_: str) -> str:
        raise RuntimeError("PRIVATE_DIAGNOSTIC_FAILURE")

    monkeypatch.setattr(trace_module, "provider_trace_category", fail_classification)
    monkeypatch.setenv("CHARACTER_RELAY_PROVIDER_TRACE_MODE", "metadata")
    events: list[dict[str, object]] = []
    configure_provider_trace_sink(events.append)
    try:
        trace = ProviderTrace.start(
            endpoint="https://provider.example.test", model="model", temperature=0,
            messages=(ChatMessage(role="tool", content='{"ok":false,"error":"PRIVATE_TOOL"}'),),
        )
        trace.response(status_code=200, response_model="model", text="answer",
                       input_tokens=None, output_tokens=None, finish_reason="stop")
    finally:
        configure_provider_trace_sink(None)
    assert len(events) == 2
    assert events[0]["classification_incomplete"] is True
    assert events[0]["failed_tool_result_count"] is None
    assert "latest_message" not in events[0]
    assert events[1]["event"] == "provider.response"
    assert "PRIVATE_" not in json.dumps(events)
