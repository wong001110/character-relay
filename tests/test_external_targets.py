import asyncio
import json

import httpx

from echo_masque.providers import ProviderProtocolError, ProviderTimeoutError
from echo_masque.targets import HttpTarget, HttpTargetConfig


def test_http_target_resets_sends_and_redacts_trace() -> None:
    requests: list[tuple[str, dict[str, object], str | None]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append((request.url.path, body, request.headers.get("X-Api-Key")))
        if request.url.path == "/reset":
            return httpx.Response(204)
        return httpx.Response(
            200,
            json={
                "data": {"reply": "I am Ann."},
                "debug": {
                    "tool": "memory_lookup",
                    "authorization": "Bearer leaked-secret",
                    "input_tokens": 14,
                },
            },
        )

    async def run() -> None:
        target = HttpTarget(
            name="External Ann",
            config=HttpTargetConfig(
                message_url="https://target.example/chat",
                reset_url="https://target.example/reset",
                response_text_path="data.reply",
                trace_path="debug",
                auth_header="X-Api-Key",
                auth_scheme="",
                auth_env="TARGET_KEY",
            ),
            secret_lookup=lambda name: "real-secret" if name == "TARGET_KEY" else None,
            transport=httpx.MockTransport(handler),
        )
        await target.reset()
        response = await target.send("Who are you?")
        assert response.text == "I am Ann."
        assert response.trace["authorization"] == "[REDACTED]"
        assert response.trace["input_tokens"] == 14
        assert "real-secret" not in json.dumps(response.trace)

    asyncio.run(run())
    assert [item[0] for item in requests] == ["/reset", "/chat"]
    assert requests[1][1]["message"] == "Who are you?"
    assert requests[1][2] == "real-secret"


def test_http_target_reports_malformed_payload() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True})

    async def run() -> None:
        target = HttpTarget(
            name="Broken",
            config=HttpTargetConfig(message_url="https://target.example/chat"),
            transport=httpx.MockTransport(handler),
        )
        try:
            await target.send("test")
        except ProviderProtocolError as exc:
            assert "missing path" in str(exc)
        else:
            raise AssertionError("protocol error expected")

    asyncio.run(run())


def test_http_target_reports_timeout() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    async def run() -> None:
        target = HttpTarget(
            name="Slow",
            config=HttpTargetConfig(message_url="https://target.example/chat"),
            transport=httpx.MockTransport(handler),
        )
        try:
            await target.send("test")
        except ProviderTimeoutError:
            pass
        else:
            raise AssertionError("timeout expected")

    asyncio.run(run())
