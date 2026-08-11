import json

from echo_masque.provider_trace_classification import (
    provider_trace_category,
    provider_trace_media_attention,
)


def request_json() -> str:
    return json.dumps(
        {
            "event": "provider.request",
            "trace_id": "trace-attention",
            "message_roles": ["system", "user"],
            "latest_message": {
                "role": "user",
                "content": "[MEDIA_ATTENTION]\nprivate decision prompt",
            },
        }
    )


def test_media_attention_trace_extracts_watch_skip_and_declared_stance() -> None:
    response = json.dumps(
        {
            "event": "provider.response",
            "trace_id": "trace-attention",
            "response_text": json.dumps(
                {
                    "action": "skip",
                    "reason": "I do not actually want to inspect this image.",
                    "response_stance": "bluff",
                    "stance_reason": "I would rather save face than admit I skipped it.",
                }
            ),
        }
    )

    assert provider_trace_category(request_json(), response) == "media_attention"
    assert provider_trace_media_attention(request_json(), response) == {
        "action": "skip",
        "reason": "I do not actually want to inspect this image.",
        "response_stance": "bluff",
        "stance_reason": "I would rather save face than admit I skipped it.",
    }


def test_media_attention_trace_accepts_json_surrounded_by_model_prose() -> None:
    response = json.dumps(
        {
            "event": "provider.response",
            "trace_id": "trace-attention",
            "response_text": (
                "Decision: "
                '{"action":"watch","reason":"curious",'
                '"response_stance":"tease","stance_reason":"playful"}'
            ),
        }
    )

    assert provider_trace_media_attention(request_json(), response) == {
        "action": "watch",
        "reason": "curious",
        "response_stance": "tease",
        "stance_reason": "playful",
    }


def test_metadata_only_attention_trace_does_not_invent_a_stance() -> None:
    response = json.dumps(
        {
            "event": "provider.response",
            "trace_id": "trace-attention",
            "trace_mode": "metadata",
        }
    )

    assert provider_trace_category(request_json(), response) == "media_attention"
    assert provider_trace_media_attention(request_json(), response) == {}
