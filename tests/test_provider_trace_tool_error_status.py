from echo_masque.persistence import Database
from echo_masque.persistence.provider_trace_repository import ProviderTraceRepository


def test_failed_tool_result_marks_followup_provider_trace_error() -> None:
    database = Database("sqlite:///:memory:")
    database.initialize()
    repository = ProviderTraceRepository(database)
    trace_id = "trace-tool-error"

    repository.record_event(
        {
            "event": "provider.request",
            "trace_id": trace_id,
            "endpoint": "https://api.deepseek.com/v1/chat/completions",
            "model": "deepseek-v4-flash",
            "trace_mode": "summary",
            "message_roles": ["system", "user", "assistant", "tool"],
            "prior_tool_call_names": ["scheduler_remind"],
            "tool_result_count": 1,
            "latest_message": {
                "role": "tool",
                "content": '{"ok":false,"error":"Reminder time must be in the future."}',
            },
        }
    )

    pending = repository.get_trace(trace_id)
    assert pending is not None
    assert pending.status == "error"

    repository.record_event(
        {
            "event": "provider.response",
            "trace_id": trace_id,
            "endpoint": "https://api.deepseek.com/v1/chat/completions",
            "request_model": "deepseek-v4-flash",
            "response_model": "deepseek-v4-flash",
            "status_code": 200,
            "latency_ms": 200,
            "trace_mode": "summary",
            "response_text": "That reminder time has already passed.",
        }
    )

    completed = repository.get_trace(trace_id)
    assert completed is not None
    assert completed.status == "error"
