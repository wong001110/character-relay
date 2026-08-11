import asyncio
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from echo_masque.generated_media_delivery import GeneratedMediaDeliveryService
from echo_masque.image_creation_runtime import ImageCreationRuntimeService
from echo_masque.persistence import (
    ConversationMediaReferenceRepository,
    Database,
    GeneratedMediaArtifactRepository,
)

_PNG = b"\x89PNG\r\n\x1a\n" + b"generated-image"
_ATTACHMENT_URL = "https://cdn.discordapp.com/attachments/channel/generated.png"


class FakeDeploymentRepository:
    def get_deployment(self, deployment_id: str, owner_id: str) -> SimpleNamespace:
        assert deployment_id == "deployment-1"
        assert owner_id == "owner-1"
        return SimpleNamespace(
            id="deployment-1",
            owner_id="owner-1",
            character_card_id="card-ann",
            connection_id="connection-1",
            platform="discord",
            workspace_id="guild-1",
            status="active",
        )


class FakeIdentityRepository:
    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.registered: list[dict[str, Any]] = []

    def get_identity(self, deployment_id: str, owner_id: str) -> SimpleNamespace:
        assert deployment_id == "deployment-1"
        assert owner_id == "owner-1"
        return SimpleNamespace(
            mode=self.mode,
            display_name="Ann",
            avatar_url="https://example.invalid/ann.png",
        )

    def get_binding(self, **_: object) -> SimpleNamespace:
        return SimpleNamespace(id="binding-1", status="active", webhook_id="webhook-1")

    def register_message_routes(self, **kwargs: Any) -> list[object]:
        self.registered.append(kwargs)
        return []


class FakeCredentialStore:
    def get_scope(self, **_: object) -> SecretStr:
        return SecretStr("webhook-token")


def repositories() -> tuple[
    Database,
    GeneratedMediaArtifactRepository,
    ConversationMediaReferenceRepository,
    str,
]:
    database = Database("sqlite://")
    database.initialize()
    artifacts = GeneratedMediaArtifactRepository(database)
    conversation = ConversationMediaReferenceRepository(database)
    artifact = artifacts.create(
        owner_id="owner-1",
        deployment_id="deployment-1",
        character_card_id="card-ann",
        media_key="sha256:generated",
        mime_type="image/png",
        filename="character-generated-1.png",
        provider="fake",
        model="fake-image",
        content=_PNG,
    )
    return database, artifacts, conversation, artifact.id


def test_webhook_delivery_registers_route_and_reusable_reference() -> None:
    _, artifacts, conversation, artifact_id = repositories()
    identities = FakeIdentityRepository("webhook")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/v10/webhooks/webhook-1/webhook-token"
        assert request.url.params["wait"] == "true"
        assert request.url.params["thread_id"] == "thread-1"
        assert request.headers["content-type"].startswith("multipart/form-data")
        assert b"character-generated-1.png" in request.content
        assert _PNG in request.content
        return httpx.Response(
            200,
            json={
                "id": "generated-message-1",
                "attachments": [{"url": _ATTACHMENT_URL}],
            },
        )

    service = GeneratedMediaDeliveryService(
        artifacts,
        FakeDeploymentRepository(),  # type: ignore[arg-type]
        identities,  # type: ignore[arg-type]
        FakeCredentialStore(),  # type: ignore[arg-type]
        http_transport=httpx.MockTransport(handler),
        conversation_media_repository=conversation,
    )
    result = asyncio.run(
        service.deliver(
            owner_id="owner-1",
            deployment_id="deployment-1",
            channel_id="channel-1",
            thread_id="thread-1",
            artifact_id=artifact_id,
        )
    )

    assert result.message_id == "generated-message-1"
    assert result.attachment_url == _ATTACHMENT_URL
    assert identities.registered[0]["webhook_id"] == "webhook-1"
    assert identities.registered[0]["message_ids"] == ["generated-message-1"]

    records = conversation.for_message(
        deployment_id="deployment-1",
        character_card_id="card-ann",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="thread-1",
        message_id="generated-message-1",
    )
    assert len(records) == 1
    assert records[0].source_uri == _ATTACHMENT_URL
    assert records[0].context_json == ""

    image_runtime = ImageCreationRuntimeService(
        credential_resolver=object(),  # type: ignore[arg-type]
        conversation_media_repository=conversation,
        artifact_repository=artifacts,
    )
    references = image_runtime._references(
        deployment_id="deployment-1",
        character_card_id="card-ann",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="thread-1",
        message_id="new-message",
        reply_to_message_id="generated-message-1",
        reference_mode="reply",
    )
    assert len(references) == 1
    assert references[0].uri == _ATTACHMENT_URL


def test_bot_delivery_uses_character_bot_identity_and_thread_destination() -> None:
    _, artifacts, conversation, artifact_id = repositories()
    identities = FakeIdentityRepository("bot")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/v10/channels/thread-1/messages"
        assert request.headers["authorization"] == "Bot bot-token"
        assert _PNG in request.content
        return httpx.Response(
            200,
            json={
                "id": "generated-bot-message",
                "attachments": [{"url": _ATTACHMENT_URL}],
            },
        )

    service = GeneratedMediaDeliveryService(
        artifacts,
        FakeDeploymentRepository(),  # type: ignore[arg-type]
        identities,  # type: ignore[arg-type]
        FakeCredentialStore(),  # type: ignore[arg-type]
        discord_bot_token=SecretStr("bot-token"),
        http_transport=httpx.MockTransport(handler),
        conversation_media_repository=conversation,
    )
    result = asyncio.run(
        service.deliver(
            owner_id="owner-1",
            deployment_id="deployment-1",
            channel_id="channel-1",
            thread_id="thread-1",
            artifact_id=artifact_id,
        )
    )

    assert result.message_id == "generated-bot-message"
    assert identities.registered[0]["webhook_id"] == ""
    assert identities.registered[0]["message_ids"] == ["generated-bot-message"]


def test_failed_delivery_does_not_register_route_or_reference() -> None:
    _, artifacts, conversation, artifact_id = repositories()
    identities = FakeIdentityRepository("webhook")

    service = GeneratedMediaDeliveryService(
        artifacts,
        FakeDeploymentRepository(),  # type: ignore[arg-type]
        identities,  # type: ignore[arg-type]
        FakeCredentialStore(),  # type: ignore[arg-type]
        http_transport=httpx.MockTransport(
            lambda _: httpx.Response(500, json={"message": "failed"})
        ),
        conversation_media_repository=conversation,
    )

    with pytest.raises(RuntimeError, match="HTTP 500"):
        asyncio.run(
            service.deliver(
                owner_id="owner-1",
                deployment_id="deployment-1",
                channel_id="channel-1",
                thread_id="",
                artifact_id=artifact_id,
            )
        )

    assert identities.registered == []
    assert conversation.recent(
        deployment_id="deployment-1",
        character_card_id="card-ann",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="",
    ) == []
