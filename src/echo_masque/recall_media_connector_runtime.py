"""Media-aware Discord runtime with v3 Character recall and bounded Social Context."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

import httpx
from pydantic import SecretStr

from echo_masque.api.connector_schemas import DiscordConnectorReplyView, DiscordInboundMessage
from echo_masque.character_recall import CharacterRecallBundle, CharacterRecallService
from echo_masque.connector_runtime import PreparedCharacterTurn, ResolvedCharacterTurn
from echo_masque.media_connector_runtime import MediaAwareDiscordConnectorRuntime
from echo_masque.persistence.belief_repository import BeliefRepository
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.deployment_presence_notice_repository import (
    DeploymentPresenceNoticeRepository,
)
from echo_masque.persistence.deployment_presence_repository import DeploymentPresenceRepository
from echo_masque.persistence.discord_identity_repository import DiscordIdentityRepository
from echo_masque.social_intelligence_v3 import SocialIntelligenceV3Service, SocialTargetType

_DISCORD_API = "https://discord.com/api/v10"
_NAME_SPLIT = re.compile(r"\s*(?:·|•|・|/|\|)\s*|\s+(?:-|\u2014|\u2013)\s+")
_ADDRESS_BOUNDARY = r"[\s:,、.。?!\-\u2014\u2013&/+和与與跟及]"


class RecallAwareMediaDiscordConnectorRuntime(MediaAwareDiscordConnectorRuntime):
    """Inject high-confidence v3 recall/social context and enforce Deployment Presence."""

    def __init__(
        self,
        *args: Any,
        character_recall_service: CharacterRecallService | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        database = self.deployment_repository.database
        self.character_recall = character_recall_service or CharacterRecallService(
            BeliefRepository(database)
        )
        self.deployment_presence = DeploymentPresenceRepository(database)
        self.deployment_presence_notices = DeploymentPresenceNoticeRepository(database)
        self.social_intelligence = SocialIntelligenceV3Service(database)
        self.discord_identities = DiscordIdentityRepository(database)
        delivery = getattr(self.tool_registry, "generated_media_delivery", None)
        token = getattr(delivery, "discord_bot_token", None)
        self.discord_bot_token = token if isinstance(token, SecretStr) else None

    @staticmethod
    def _name_aliases(display_name: str, extra_aliases: list[str]) -> tuple[str, ...]:
        values: set[str] = set()
        for raw in (display_name, *extra_aliases):
            full = unicodedata.normalize("NFKC", raw).strip()
            if not full:
                continue
            values.add(full)
            values.update(part.strip() for part in _NAME_SPLIT.split(full) if part.strip())
        return tuple(sorted(values, key=len, reverse=True))

    @staticmethod
    def _starts_with_alias(content: str, aliases: tuple[str, ...]) -> bool:
        normalized = unicodedata.normalize("NFKC", content).strip()
        for alias in aliases:
            escaped = re.escape(unicodedata.normalize("NFKC", alias))
            if re.match(
                rf"^{escaped}(?=$|{_ADDRESS_BOUNDARY})",
                normalized,
                flags=re.IGNORECASE,
            ):
                return True
        return False

    def _fetch_source_content(self, payload: DiscordInboundMessage) -> str:
        if self.discord_bot_token is None or not payload.message_id:
            return ""
        channel_id = payload.thread_id or payload.channel_id
        if not channel_id:
            return ""
        try:
            response = httpx.get(
                f"{_DISCORD_API}/channels/{channel_id}/messages/{payload.message_id}",
                headers={
                    "Authorization": f"Bot {self.discord_bot_token.get_secret_value()}",
                    "User-Agent": "CharacterRelay/0.2 PresenceRuntime",
                },
                timeout=3.0,
                follow_redirects=False,
            )
            if response.is_error:
                return ""
            value = response.json()
        except (httpx.HTTPError, ValueError):
            return ""
        content = value.get("content") if isinstance(value, dict) else None
        return content if isinstance(content, str) else ""

    def _explicitly_addressed_while_sleeping(
        self,
        *,
        payload: DiscordInboundMessage,
        deployment: CharacterDeploymentRecord,
        display_name: str,
    ) -> bool:
        if payload.author_is_bot:
            return False
        if payload.mentioned_bot or payload.replied_to_bot:
            return True
        aliases = self._name_aliases(
            display_name,
            self.discord_identities.get_address_aliases(
                deployment.id,
                deployment.owner_id,
            ),
        )
        if self._starts_with_alias(payload.text, aliases):
            return True
        source_content = self._fetch_source_content(payload)
        return bool(source_content and self._starts_with_alias(source_content, aliases))

    def resolve_character_turn(
        self,
        payload: DiscordInboundMessage,
    ) -> tuple[ResolvedCharacterTurn | None, DiscordConnectorReplyView | None]:
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
            if self._explicitly_addressed_while_sleeping(
                payload=payload,
                deployment=deployment,
                display_name=display_name,
            ):
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
    def _inject_prompt_guidance(prompt: str, guidance: tuple[str, ...]) -> str:
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

    @staticmethod
    def _inject_recall_guidance(prompt: str, guidance: tuple[str, ...]) -> str:
        """Backward-compatible prompt helper retained for existing non-memory callers."""

        return RecallAwareMediaDiscordConnectorRuntime._inject_prompt_guidance(
            prompt,
            guidance,
        )

    def _social_target(
        self,
        *,
        resolved: ResolvedCharacterTurn,
    ) -> tuple[SocialTargetType, str]:
        payload = resolved.payload
        if payload.author_is_bot and payload.message_id:
            route = self.discord_identities.resolve_message_route(
                connection_id=payload.connection_id,
                message_id=payload.message_id,
            )
            if route is not None and route.deployment_id != resolved.deployment.id:
                return "deployment", route.deployment_id
        if payload.author_id:
            return "actor", payload.author_id
        return "actor", ""

    def prepare_character_turn(
        self,
        resolved: ResolvedCharacterTurn,
    ) -> PreparedCharacterTurn:
        prepared = super().prepare_character_turn(resolved)
        payload = resolved.payload
        deployment = resolved.deployment
        bundle: CharacterRecallBundle = self.character_recall.high_confidence_recall(
            owner_id=deployment.owner_id,
            character_card_id=resolved.card.id,
            connection_id=deployment.connection_id,
            guild_id=payload.guild_id,
            subject_user_id=payload.author_id,
            query=payload.text,
            deployment_id=deployment.id,
            exclude_source_message_id=payload.message_id,
            limit=4,
        )
        recall_guidance = bundle.prompt_guidance(max_chars=900)
        if recall_guidance:
            prepared.prompt = self._inject_prompt_guidance(prepared.prompt, recall_guidance)

        target_type, target_key = self._social_target(resolved=resolved)
        if target_key:
            social_guidance = self.social_intelligence.prompt_context(
                owner_id=deployment.owner_id,
                source_deployment_id=deployment.id,
                target_type=target_type,
                target_key=target_key,
                max_chars=480,
            )
            if social_guidance:
                prepared.prompt = self._inject_prompt_guidance(
                    prepared.prompt,
                    social_guidance,
                )
        return prepared


__all__ = ["RecallAwareMediaDiscordConnectorRuntime"]
