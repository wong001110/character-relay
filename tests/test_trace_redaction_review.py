from __future__ import annotations

import json

from echo_masque.persistence import Database
from echo_masque.persistence.provider_trace_repository import ProviderTraceRepository
from echo_masque.providers.base import ChatMessage
from echo_masque.providers.trace import ProviderTrace, configure_provider_trace_sink
from echo_masque.security import redact


def test_structured_redaction_handles_embedded_json_and_credential_bearing_urls() -> None:
    synthetic_value = "synthetic-credential-value"
    payload = {
        "endpoint": (
            "https://trace-user:trace-pass@provider.example.test/v1/chat?"
            f"apiKey={synthetic_value}&region=eu"
        ),
        "request_json": json.dumps(
            {
                "metadata": {
                    "accessToken": synthetic_value,
                    "endpoint": f"https://api.example.test/data?token={synthetic_value}&page=2",
                }
            }
        ),
        "response_body": json.dumps({"error": {"secret": synthetic_value}}),
        "input_tokens": 12,
        "latest_message": {"content": "The user wrote ordinary prose."},
    }

    result = redact(payload)

    assert isinstance(result, dict)
    rendered = json.dumps(result, ensure_ascii=False)
    assert synthetic_value not in rendered
    assert "trace-user" not in rendered
    assert "trace-pass" not in rendered
    assert result["input_tokens"] == 12
    assert result["latest_message"] == {"content": "The user wrote ordinary prose."}
    assert "region=eu" in str(result["endpoint"])
    assert json.loads(str(result["request_json"]))["metadata"] == {
        "accessToken": "[REDACTED]",
        "endpoint": "https://api.example.test/data?token=%5BREDACTED%5D&page=2",
    }
    assert json.loads(str(result["response_body"])) == {"error": {"secret": "[REDACTED]"}}


def test_provider_trace_emission_redacts_preview_endpoint_and_structured_error() -> None:
    synthetic_value = "synthetic-trace-value"
    events: list[dict[str, object]] = []
    configure_provider_trace_sink(events.append)
    try:
        trace = ProviderTrace.start(
            endpoint=(
                "https://trace-user:trace-pass@provider.example.test/v1?"
                f"access_token={synthetic_value}"
            ),
            model="test-model",
            temperature=0.1,
            messages=(
                ChatMessage(
                    role="user",
                    content=f"See https://docs.example.test/guide?api_key={synthetic_value}",
                ),
            ),
        )
        trace.error(
            reason="provider_http_error",
            response_body=json.dumps({"details": {"token": synthetic_value}}),
            detail=(
                "provider endpoint https://trace-user:trace-pass@provider.example.test/"
                f"failure?secret={synthetic_value}"
            ),
        )
    finally:
        configure_provider_trace_sink(None)

    assert len(events) == 2
    rendered = json.dumps(events, ensure_ascii=False)
    assert synthetic_value not in rendered
    assert "trace-user" not in rendered
    assert "trace-pass" not in rendered
    assert json.loads(str(events[1]["response_body"])) == {
        "details": {"token": "[REDACTED]"}
    }


def test_provider_trace_repository_redacts_direct_untrusted_event_payload() -> None:
    synthetic_value = "synthetic-persistence-value"
    database = Database("sqlite://")
    database.initialize()
    repository = ProviderTraceRepository(database)

    repository.record_event(
        {
            "event": "provider.response",
            "trace_id": "trace-redaction-review",
            "endpoint": (
                "https://trace-user:trace-pass@provider.example.test/v1?"
                f"credential={synthetic_value}"
            ),
            "response_model": "test-model",
            "status_code": 200,
            "input_tokens": 33,
            "output_tokens": 7,
            "response_body": json.dumps({"nested": {"api_key": synthetic_value}}),
            "metadata_json": json.dumps({"refresh_token": synthetic_value}),
        }
    )

    record = repository.get_trace("trace-redaction-review")

    assert record is not None
    persisted = "\n".join(
        (
            record.endpoint,
            record.request_json,
            record.response_json,
            record.error_json,
            record.retries_json,
        )
    )
    assert synthetic_value not in persisted
    assert "trace-user" not in persisted
    assert "trace-pass" not in persisted
    response = json.loads(record.response_json)
    assert response["input_tokens"] == 33
    assert response["output_tokens"] == 7
    assert json.loads(response["metadata_json"]) == {"refresh_token": "[REDACTED]"}
    assert json.loads(response["response_body"]) == {"nested": {"api_key": "[REDACTED]"}}
