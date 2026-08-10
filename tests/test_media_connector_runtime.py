import asyncio
from types import SimpleNamespace
from typing import Any, cast

from echo_masque.live_media import LiveMediaContext, LiveMediaResult
from echo_masque.media_connector_runtime import MediaAwareDiscordConnectorRuntime


class FakeLiveMediaService:
    def __init__(self) -> None:
        self.calls = 0

    async def contexts_for_turn(self, **_: object) -> LiveMediaResult:
        self.calls += 1
        return LiveMediaResult(
            status="completed",
            reason="ok",
            contexts=(
                LiveMediaContext(
                    source_key="sha256:abc",
                    kind="image",
                    label="cat.png",
                    summary="An orange cat is sitting on a laptop.",
                    visible_text="Build failed",
                    notable_details=("One paw is on the keyboard.",),
                ),
            ),
        )


def test_media_context_is_injected_once_before_smart_output_instruction() -> None:
    service = FakeLiveMediaService()
    runtime = MediaAwareDiscordConnectorRuntime(
        cast(Any, object()),
        cast(Any, object()),
        cast(Any, object()),
        live_media_service=cast(Any, service),
    )
    prepared = SimpleNamespace(
        resolved=SimpleNamespace(
            deployment=SimpleNamespace(id="deployment-1", owner_id="owner-1"),
            card=SimpleNamespace(id="card-1"),
            payload=SimpleNamespace(message_id="message-1"),
        ),
        prompt="Recent conversation:\nhello\nReturn Smart Output now.",
    )

    async def run() -> None:
        await runtime._ensure_media_context(cast(Any, prepared))
        await runtime._ensure_media_context(cast(Any, prepared))

    asyncio.run(run())

    assert service.calls == 1
    assert "Shared objective content context for this turn:" in prepared.prompt
    assert "An orange cat is sitting on a laptop." in prepared.prompt
    assert "Visible/readable text: Build failed" in prepared.prompt
    assert prepared.prompt.endswith("Return Smart Output now.")
    assert prepared.prompt.index("Shared objective content context") < prepared.prompt.index(
        "Return Smart Output now."
    )
