import asyncio
import json

import httpx
from pydantic import SecretStr

from echo_masque.media_runtime import MediaAsset
from echo_masque.providers.openai_multimodal import OpenAICompatibleMultimodalProvider
from echo_masque.providers.trace import configure_provider_trace_sink


def test_keyframe_video_trace_marks_local_delivery_without_frame_or_cdn_data() -> None:
    events: list[dict[str, object]] = []

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "Sampled video frames.",
                                    "visible_text": "",
                                    "people": [],
                                    "objects": [],
                                    "notable_details": [],
                                    "topics": ["video"],
                                    "tone": "neutral",
                                }
                            )
                        }
                    }
                ]
            },
        )

    provider = OpenAICompatibleMultimodalProvider(
        provider_id="openrouter",
        api_key=SecretStr("secret-key"),
        model="xiaomi/mimo-v2.5",
        base_url="https://openrouter.ai/api/v1",
        transport=httpx.MockTransport(handler),
    )
    configure_provider_trace_sink(events.append)
    try:
        asyncio.run(
            provider.analyze(
                MediaAsset(
                    media_key="url:bilibili:platform-keyframes-v1",
                    media_type="video",
                    filename="BV1test_keyframes",
                    source_uri="https://www.bilibili.com/video/BV1test?from=share",
                    keyframe_uris=(
                        "data:image/jpeg;base64,SECRET_FRAME_A",
                        "data:image/jpeg;base64,SECRET_FRAME_B",
                    ),
                    keyframe_timestamps_seconds=(4.0, 20.0),
                )
            )
        )
    finally:
        configure_provider_trace_sink(None)

    request = events[0]
    latest = request["latest_message"]
    assert isinstance(latest, dict)
    content = latest["content"]
    assert isinstance(content, str)
    assert '"input_part_type": "video_keyframes"' in content
    assert '"delivery_mode": "local_keyframes"' in content
    assert '"keyframe_count": 2' in content
    assert '"source_query_redacted": true' in content
    assert "SECRET_FRAME" not in content
    assert "from=share" not in content
    assert "upos" not in content
