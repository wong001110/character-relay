"""Real media registry/artifact flow with local delayed image providers and fake delivery."""

import asyncio
import base64
import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from echo_masque.media_tools import MediaToolRegistry
from echo_masque.persistence import Database
from echo_masque.persistence.generated_media_repository import GeneratedMediaArtifactRepository
from echo_masque.providers import ChatToolCall, ChatToolFunctionCall
from echo_masque.tool_external import ExternalToolFailed
from echo_masque.tool_runtime import ToolExecutionContext
from echo_masque.turn_progress import bind_turn_progress


def scope():
    return ToolExecutionContext(
        owner_id="owner",
        deployment_id="deployment",
        character_card_id="character",
        platform="discord",
        connection_id="connection",
        guild_id="guild",
        channel_id="channel",
        category_id="category",
        thread_id="thread",
        message_id="message",
    )


def png():
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), "blue").save(buffer, format="PNG")
    return buffer.getvalue()


class Authority:
    allowed = True

    def deployment_matches_discord_destination(self, deployment_id, **destination):
        assert deployment_id == "deployment"
        assert destination == {
            "connection_id": "connection",
            "guild_id": "guild",
            "channel_id": "channel",
            "thread_id": "thread",
            "category_id": "category",
        }
        return (
            SimpleNamespace(owner_id="owner", character_card_id="character")
            if self.allowed
            else None
        )

    def get_enabled_tools(self, deployment_id, owner_id):
        assert (deployment_id, owner_id) == ("deployment", "owner")
        return ["image.generate", "mcp.invoke"]


class Delivery:
    def __init__(self):
        self.calls = []

    async def deliver(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(message_id="discord-image", attachment_url="")


def build():
    database = Database("sqlite://")
    database.initialize()
    artifacts = GeneratedMediaArtifactRepository(database)
    authority = Authority()
    delivery = Delivery()
    service = SimpleNamespace(artifact_repository=artifacts)
    registry = MediaToolRegistry(
        image_creation_service=service,
        generated_media_delivery=delivery,
        deployment_repository=authority,
        deployment_tool_repository=authority,
    )
    return registry, artifacts, authority, delivery, service


def test_slow_native_image_acknowledges_before_generation_and_uses_original_destination():
    async def run():
        registry, artifacts, _, delivery, service = build()
        started, release = asyncio.Event(), asyncio.Event()
        progress = []

        async def generate(**kwargs):
            assert kwargs["guild_id"] == "guild"
            started.set()
            await release.wait()
            record = artifacts.create(
                owner_id="owner",
                deployment_id="deployment",
                character_card_id="character",
                media_key="sha256:fixture",
                mime_type="image/png",
                filename="fixture.png",
                provider="fixture",
                model="fixture",
                content=png(),
            )
            return (record.id,)

        service.generate = generate

        async def publish(text):
            progress.append(text)
            return True

        call = ChatToolCall(
            id="image",
            function=ChatToolFunctionCall(
                name="image_generate",
                arguments=json.dumps(
                    {
                        "prompt": "blue sky",
                        "progress_message": "我來畫一下天空。",
                    }
                ),
            ),
        )
        with bind_turn_progress(publish):
            task = asyncio.create_task(
                registry.execute(
                    call,
                    enabled_tool_ids=("image.generate",),
                    context=scope(),
                )
            )
            await asyncio.wait_for(started.wait(), 2)
            assert progress == ["我來畫一下天空。"]
            assert not delivery.calls and not task.done()
            release.set()
            result = await task
        assert result.trace.status == "completed"
        payload = json.loads(result.content)
        assert payload["delivered"] is True
        assert delivery.calls == [
            {
                "owner_id": "owner",
                "deployment_id": "deployment",
                "channel_id": "channel",
                "thread_id": "thread",
                "artifact_id": payload["artifact_ids"][0],
            }
        ]

    asyncio.run(run())


def test_mcp_image_becomes_scoped_artifact_and_revoked_destination_prevents_publication():
    async def run():
        registry, artifacts, authority, delivery, _ = build()
        encoded = base64.b64encode(png()).decode()
        result = await registry._deliver_mcp_image(scope(), "image/png", encoded)
        artifact_id = result["artifact_ids"][0]
        assert artifacts.get(artifact_id, owner_id="owner").content == png()
        assert artifacts.get(artifact_id, owner_id="another-owner") is None
        assert delivery.calls[0]["thread_id"] == "thread"
        authority.allowed = False
        with pytest.raises(ExternalToolFailed, match="scope_revoked"):
            await registry._deliver_mcp_image(scope(), "image/png", encoded)
        assert len(delivery.calls) == 1

    asyncio.run(run())


def test_mcp_non_image_bytes_are_never_persisted_or_sent():
    async def run():
        registry, _, _, delivery, _ = build()
        with pytest.raises(ExternalToolFailed, match="image_invalid"):
            await registry._deliver_mcp_image(
                scope(), "image/png", base64.b64encode(b"text").decode()
            )
        assert delivery.calls == []

    asyncio.run(run())
