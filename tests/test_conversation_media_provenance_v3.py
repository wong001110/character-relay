from __future__ import annotations

import asyncio
from types import SimpleNamespace

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.api.smart_participation_v3_schemas import SmartParticipationMediaDescriptor
from echo_masque.character_turn_context_v3 import CharacterTurnContextV3Service
from echo_masque.live_media import DiscordAttachment
from echo_masque.planner_media import PlannerMediaDescriptorService


def _inbound(*, descriptors: list[SmartParticipationMediaDescriptor]) -> DiscordInboundMessage:
    return DiscordInboundMessage(
        connection_id="connection-1",
        deployment_id="deployment-1",
        message_id="message-1",
        guild_id="guild-1",
        channel_id="channel-1",
        author_id="actor-1",
        author_display_name="Member",
        text="",
        media_descriptors=descriptors,
    )


def test_direct_turn_structure_payload_keeps_planner_descriptors_as_provenance() -> None:
    descriptor = SmartParticipationMediaDescriptor(
        ref="message:message-0:attachment:2",
        kind="image",
        state="resolved",
        source_key="discord-attachment:two",
        summary="Planner-only analysis that must not become Character perception.",
    )
    resolved = SimpleNamespace(
        payload=_inbound(descriptors=[descriptor]),
        deployment=SimpleNamespace(id="deployment-1"),
    )

    structure_payload = CharacterTurnContextV3Service._structure_payload(resolved)

    assert structure_payload.media_descriptors == [descriptor]
    assert structure_payload.media_descriptors[0].summary == descriptor.summary


class _AttachmentOnlyMedia:
    media_repository = object()

    def __init__(self) -> None:
        self.by_message_id = {
            "message-1": [
                DiscordAttachment(
                    attachment_id="current-1",
                    url="https://cdn.discord.test/current-1.png",
                    filename="current-1.png",
                    content_type="image/png",
                    size_bytes=None,
                ),
                DiscordAttachment(
                    attachment_id="current-2",
                    url="https://cdn.discord.test/current-2.png",
                    filename="current-2.png",
                    content_type="image/png",
                    size_bytes=None,
                ),
                DiscordAttachment(
                    attachment_id="current-3",
                    url="https://cdn.discord.test/current-3.png",
                    filename="current-3.png",
                    content_type="image/png",
                    size_bytes=None,
                ),
            ],
            "burst-message": [
                DiscordAttachment(
                    attachment_id="burst-1",
                    url="https://cdn.discord.test/burst-1.png",
                    filename="burst-1.png",
                    content_type="image/png",
                    size_bytes=None,
                ),
                DiscordAttachment(
                    attachment_id="burst-2",
                    url="https://cdn.discord.test/burst-2.png",
                    filename="burst-2.png",
                    content_type="image/png",
                    size_bytes=None,
                ),
            ],
        }

    async def _discord_attachments(self, payload: DiscordInboundMessage) -> list[DiscordAttachment]:
        return self.by_message_id.get(payload.message_id, [])

    @staticmethod
    def _extract_urls(_: str) -> list[str]:
        return []

    @staticmethod
    def _media_type(content_type: str, _: str) -> str:
        return "image" if content_type.startswith("image/") else "file"


def test_planner_keeps_each_current_and_burst_attachment_with_message_scoped_refs() -> None:
    service = PlannerMediaDescriptorService.__new__(PlannerMediaDescriptorService)
    service.media = _AttachmentOnlyMedia()
    service.utility_provider = None
    service._utility = None
    payload = _inbound(descriptors=[]).model_copy(
        update={"burst_media_message_ids": ["burst-message"]}
    )

    result = asyncio.run(service.resolve(payload))

    assert [item.ref for item in result.descriptors] == [
        "message:message-1:attachment:1",
        "message:message-1:attachment:2",
        "message:message-1:attachment:3",
        "message:burst-message:attachment:1",
        "message:burst-message:attachment:2",
    ]
    assert {item.source_key for item in result.descriptors} == {
        "discord-attachment:current-1",
        "discord-attachment:current-2",
        "discord-attachment:current-3",
        "discord-attachment:burst-1",
        "discord-attachment:burst-2",
    }
