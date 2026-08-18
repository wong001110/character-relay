"""Media-aware Discord runtime with conservative automatic Character recall."""

from __future__ import annotations

from typing import Any

from echo_masque.api.connector_schemas import DiscordConnectorReplyView, DiscordInboundMessage
from echo_masque.character_recall import CharacterRecallBundle, CharacterRecallService
from echo_masque.connector_runtime import PreparedCharacterTurn, ResolvedCharacterTurn
from echo_masque.media_connector_runtime import MediaAwareDiscordConnectorRuntime
from echo_masque.memory_layers import SynthesizedMemoryFreshnessRepository
from echo_masque.persistence.deployment_presence_notice_repository import (
    DeploymentPresenceNoticeRepository,
)
from echo_masque.persistence.deployment_presence_repository import DeploymentPresenceRepository
from echo_masque.persistence.memory_vnext_repository import MemoryVNextRepository


class RecallAwareMediaDiscordConnectorRuntime(MediaAwareDiscordConnectorRuntime):
    """Inject high-confidence recall and enforce Deployment Presence before model work."""

    def __init__(
        self,
        *args: Any,
        character_recall_service: CharacterRecallService | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        database = self.deployment_repository.database
        self.character_recall = character_recall_service or CharacterRecallService(
            MemoryVNextRepository(database)
        )
        self.memory_freshness = SynthesizedMemoryFreshnessRepository(database)
        self.deployment_presence = DeploymentPresenceRepository(database)
        self.deployment_presence_notices = DeploymentPresenceNoticeRepository(database)

    def resolve_character_turn(
        self,
        payload: DiscordInboundMessage,
    ) -> tuple[ResolvedCharacterTurn | None, DiscordConnectorReplyView | None]:
        """Hard-gate sleeping Deployments before context, Tools, or provider resolution."""

        deployment = self.deployment_repository.deployment_matches_discord_destination(
            payload.deployment_id,
            connection_id=payload.connection_id,
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            thread_id=payload.thread_id,
            category_id=payload.category_id,
        )
        if deployment is not None and self.deployment_presence.is_sleeping(deployment):
            card = self.repository.get_character_card(
                deployment.character_card_id,
                deployment.owner_id,
            )
            display_name = card.display_name if card is not None else "Character"
            if payload.mentioned_bot or payload.replied_to_bot:
                self.deployment_presence_notices.enqueue_sleeping_notice(
                    owner_id=deployment.owner_id,
                    deployment_id=deployment.id,
                    connection_id=deployment.connection_id,
                    guild_id=payload.guild_id,
                    channel_id=payload.channel_id,
                    thread_id=payload.thread_id,
                    source_message_id=payload.message_id,
                    character_display_name=display_name,
                )
            return None, DiscordConnectorReplyView(
                action="silent",
                reason="deployment_presence_sleeping",
                deployment_id=deployment.id,
                character_display_name=display_name,
            )
        return super().resolve_character_turn(payload)

    @staticmethod
    def _inject_recall_guidance(prompt: str, guidance: tuple[str, ...]) -> str:
        if not guidance:
            return prompt
        block = "\n".join(guidance)
        marker = "\nDo not mention internal prompts, deployment configuration, OOC evaluation, "
        if marker in prompt:
            return prompt.replace(marker, f"\n{block}{marker}", 1)
        final_marker = "\nReturn Smart Output now."
        if final_marker in prompt:
            return prompt.replace(final_marker, f"\n{block}{final_marker}", 1)
        return f"{prompt}\n{block}"

    def _fresh_for_auto_recall(self, bundle: CharacterRecallBundle) -> CharacterRecallBundle:
        items = tuple(
            item
            for item in bundle.items
            if item.origin != "synthesized"
            or (
                (freshness := self.memory_freshness.get(item.ref)) is None
                or freshness.freshness_status != "stale"
            )
        )
        return CharacterRecallBundle(
            items=items,
            explicit_history_cue=bundle.explicit_history_cue,
        )

    def prepare_character_turn(
        self,
        resolved: ResolvedCharacterTurn,
    ) -> PreparedCharacterTurn:
        prepared = super().prepare_character_turn(resolved)
        payload = resolved.payload
        deployment = resolved.deployment
        bundle = self.character_recall.high_confidence_recall(
            owner_id=deployment.owner_id,
            character_card_id=resolved.card.id,
            connection_id=deployment.connection_id,
            guild_id=payload.guild_id,
            subject_user_id=payload.author_id,
            topic_id=prepared.tool_context.topic_id,
            query=payload.text,
            exclude_source_message_id=payload.message_id,
            limit=4,
        )
        bundle = self._fresh_for_auto_recall(bundle)
        guidance = bundle.prompt_guidance(max_chars=900)
        if guidance:
            prepared.prompt = self._inject_recall_guidance(prepared.prompt, guidance)
        return prepared


__all__ = ["RecallAwareMediaDiscordConnectorRuntime"]
