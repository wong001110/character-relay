import asyncio
import base64

from pydantic import SecretStr

from echo_masque.image_creation_runtime import ImageCreationRuntimeService, ImageGenerateToolInput
from echo_masque.image_generation import (
    GeneratedImage,
    ImageGenerationRequest,
    ImageGenerationResult,
)
from echo_masque.live_media import LiveMediaContext
from echo_masque.persistence import Database
from echo_masque.persistence.conversation_media_repository import (
    ConversationMediaReferenceRepository,
)
from echo_masque.persistence.generated_media_repository import GeneratedMediaArtifactRepository
from echo_masque.provider_credentials import ResolvedProviderCredential

_PNG = b"\x89PNG\r\n\x1a\n" + b"generated-image"


class FakeCredentialResolver:
    def __init__(self, available: bool = True) -> None:
        self.available = available

    def resolve(self, **_: object) -> ResolvedProviderCredential | None:
        if not self.available:
            return None
        return ResolvedProviderCredential(
            key_group_id="kg-image",
            provider="custom",
            base_url="https://images.example.test/v1",
            model="image-model",
            api_key=SecretStr("secret"),
        )


class FakeImageProvider:
    provider_id = "fake-image"
    model = "fake-model"

    def __init__(self) -> None:
        self.requests: list[ImageGenerationRequest] = []

    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        self.requests.append(request)
        return ImageGenerationResult(
            images=(
                GeneratedImage(
                    b64_json=base64.b64encode(_PNG).decode("ascii"),
                    media_type="image/png",
                ),
            ),
            provider=self.provider_id,
            model=self.model,
        )


def build_service(*, credential_available: bool = True):
    database = Database("sqlite://")
    database.initialize()
    conversation = ConversationMediaReferenceRepository(database)
    artifacts = GeneratedMediaArtifactRepository(database)
    provider = FakeImageProvider()
    service = ImageCreationRuntimeService(
        credential_resolver=FakeCredentialResolver(credential_available),  # type: ignore[arg-type]
        conversation_media_repository=conversation,
        artifact_repository=artifacts,
        provider_factory=lambda _: provider,
    )
    return service, conversation, artifacts, provider


def generate(service: ImageCreationRuntimeService, payload: ImageGenerateToolInput):
    return asyncio.run(
        service.generate(
            owner_id="owner-1",
            deployment_id="dep-1",
            character_card_id="card-ann",
            guild_id="guild-1",
            channel_id="channel-1",
            thread_id="",
            message_id="message-current",
            reply_to_message_id="message-source",
            payload=payload,
        )
    )


def test_generated_base64_image_becomes_short_lived_artifact() -> None:
    service, _, artifacts, provider = build_service()

    artifact_ids = generate(
        service,
        ImageGenerateToolInput(prompt="Draw a chibi cat holding an umbrella."),
    )

    assert len(artifact_ids) == 1
    artifact = artifacts.get(artifact_ids[0], owner_id="owner-1")
    assert artifact is not None
    assert artifact.content == _PNG
    assert artifact.mime_type == "image/png"
    assert artifact.media_key.startswith("sha256:")
    assert provider.requests[0].references == ()


def test_reply_reference_uses_only_character_perceived_image() -> None:
    service, conversation, _, provider = build_service()
    conversation.remember(
        owner_id="owner-1",
        deployment_id="dep-1",
        character_card_id="card-ann",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="",
        message_id="message-source",
        context=LiveMediaContext(
            source_key="sha256:source",
            kind="image",
            label="source.png",
            summary="A character portrait Ann actually inspected.",
        ),
        source_uri="https://cdn.discordapp.com/attachments/example/source.png",
    )

    generate(
        service,
        ImageGenerateToolInput(
            prompt="Turn the portrait into a rainy cafe scene.",
            reference_mode="reply",
        ),
    )

    request = provider.requests[0]
    assert len(request.references) == 1
    assert request.references[0].uri.endswith("source.png")
    assert request.references[0].role == "conversation_reference"


def test_reference_request_fails_when_character_never_perceived_an_image() -> None:
    service, _, _, provider = build_service()

    try:
        generate(
            service,
            ImageGenerateToolInput(
                prompt="Edit that image.",
                reference_mode="reply",
            ),
        )
    except ValueError as exc:
        assert "previously perceived image" in str(exc)
    else:
        raise AssertionError("missing perceived reference should fail")
    assert provider.requests == []


def test_image_generation_requires_character_key_group_assignment() -> None:
    service, _, _, provider = build_service(credential_available=False)

    try:
        generate(service, ImageGenerateToolInput(prompt="Draw something."))
    except ValueError as exc:
        assert "Image Generation Key Group" in str(exc)
    else:
        raise AssertionError("missing image-generation Key Group should fail")
    assert provider.requests == []
