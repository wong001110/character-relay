"""Runtime bridge from normalized connector messages to deployed characters."""

from __future__ import annotations

import os
from collections.abc import Callable

from pydantic import SecretStr

from echo_masque.api.connector_schemas import (
    DiscordConnectorReplyView,
    DiscordContextMessage,
    DiscordInboundMessage,
)
from echo_masque.character_prompts import (
    CharacterPromptProfile,
    compile_character_prompt,
)
from echo_masque.credentials import CredentialStore
from echo_masque.persistence import DeploymentRepository, Repository
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.providers import ChatProvider, OpenAICompatibleProvider
from echo_masque.targets import PromptModelConfig, PromptModelTarget, fragile_target, stable_target
from echo_masque.targets.base import TargetAdapter

type ConnectorProviderFactory = Callable[[str, SecretStr], ChatProvider]


def default_connector_provider_factory(base_url: str, api_key: SecretStr) -> ChatProvider:
    return OpenAICompatibleProvider(base_url=base_url, api_key=api_key)


class ConnectorRuntimeError(RuntimeError):
    """Raised when a deployment cannot produce a connector reply."""


class DiscordConnectorRuntime:
    """Resolve one Discord destination and generate one character response."""

    def __init__(
        self,
        repository: Repository,
        deployment_repository: DeploymentRepository,
        credential_store: CredentialStore,
        provider_factory: ConnectorProviderFactory = default_connector_provider_factory,
    ) -> None:
        self.repository = repository
        self.deployment_repository = deployment_repository
        self.credential_store = credential_store
        self.provider_factory = provider_factory

    async def respond(self, payload: DiscordInboundMessage) -> DiscordConnectorReplyView:
        deployment = self.deployment_repository.deployment_matches_discord_destination(
            payload.deployment_id,
            connection_id=payload.connection_id,
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            thread_id=payload.thread_id,
            category_id=payload.category_id,
        )
        if deployment is None:
            return DiscordConnectorReplyView(
                action="silent",
                reason="no_active_deployment",
                deployment_id=payload.deployment_id,
            )

        if not self._should_reply(deployment, payload):
            return DiscordConnectorReplyView(
                action="silent",
                reason="trigger_not_matched",
                deployment_id=deployment.id,
            )

        card = self.repository.get_character_card(
            deployment.character_card_id,
            deployment.owner_id,
        )
        if card is None:
            self.deployment_repository.record_deployment_error(
                deployment.id,
                "Character Card is unavailable.",
            )
            raise ConnectorRuntimeError("Character Card is unavailable.")
        target_record = self.repository.get_target(card.target_id)
        if target_record is None:
            self.deployment_repository.record_deployment_error(
                deployment.id,
                "Character target binding is unavailable.",
            )
            raise ConnectorRuntimeError("Character target binding is unavailable.")

        target = self._target(
            target_kind=target_record.target_kind,
            target_name=target_record.name,
            config_json=target_record.config_json,
            owner_id=deployment.owner_id,
            character_card_id=card.id,
            character_profile=CharacterPromptProfile.from_record(card),
        )
        prompt = self._social_prompt(
            character_name=card.display_name,
            payload=payload,
        )
        try:
            response = await target.send(prompt)
        except Exception as exc:
            self.deployment_repository.record_deployment_error(
                deployment.id,
                str(exc),
            )
            raise

        text = response.text.strip()
        if not text:
            return DiscordConnectorReplyView(
                action="silent",
                reason="empty_model_response",
                deployment_id=deployment.id,
                character_display_name=card.display_name,
            )

        self.deployment_repository.record_deployment_activity(deployment.id)
        return DiscordConnectorReplyView(
            action="reply",
            reason="character_response_generated",
            deployment_id=deployment.id,
            character_display_name=card.display_name,
            text=text,
            reply_to_message_id=payload.message_id,
            latency_ms=response.latency_ms,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )

    @staticmethod
    def _should_reply(
        deployment: CharacterDeploymentRecord,
        payload: DiscordInboundMessage,
    ) -> bool:
        mode = deployment.participation_mode
        if mode == "mention_only":
            return payload.mentioned_bot
        if mode == "reply_only":
            return payload.replied_to_bot
        if mode == "mention_and_reply":
            return payload.mentioned_bot or payload.replied_to_bot
        if mode == "smart":
            return payload.mentioned_bot or payload.replied_to_bot or payload.smart_candidate
        return False

    def _target(
        self,
        *,
        target_kind: str,
        target_name: str,
        config_json: str,
        owner_id: str,
        character_card_id: str,
        character_profile: CharacterPromptProfile,
    ) -> TargetAdapter:
        if target_kind == "stable":
            return stable_target()
        if target_kind == "fragile":
            return fragile_target()
        if target_kind != "prompt_model":
            raise ConnectorRuntimeError(
                f"Discord deployment does not support target kind {target_kind!r}."
            )

        config = PromptModelConfig.model_validate_json(config_json)
        credential = self.credential_store.get(owner_id, character_card_id)
        if credential is None:
            environment_key = os.getenv(config.api_key_env)
            if environment_key:
                credential = SecretStr(environment_key)
        if credential is None:
            raise ConnectorRuntimeError(
                "The deployed Character Card needs a provider credential."
            )
        compiled = compile_character_prompt(config.system_prompt, character_profile)
        return PromptModelTarget(
            config=config,
            provider=self.provider_factory(config.base_url, credential),
            runtime_system_prompt=compiled.compiled_system_prompt,
        )

    @staticmethod
    def _social_prompt(
        *,
        character_name: str,
        payload: DiscordInboundMessage,
    ) -> str:
        messages = list(payload.recent_messages)
        if not any(item.message_id == payload.message_id for item in messages):
            messages.append(
                DiscordContextMessage(
                    message_id=payload.message_id,
                    author_id=payload.author_id,
                    author_display_name=payload.author_display_name,
                    text=payload.text,
                    is_bot=False,
                )
            )
        transcript = "\n".join(
            f"[{item.author_display_name} | {item.author_id}]: {item.text}"
            for item in messages[-30:]
            if item.text.strip()
        )
        location = payload.channel_name or payload.channel_id
        if payload.thread_id:
            location = f"{location} / {payload.thread_name or payload.thread_id}"
        return "\n".join(
            (
                "You are participating in a real Discord group conversation "
                "through Character Relay.",
                f"Continue acting as {character_name} using the existing system "
                "prompt and persona.",
                "Reply to the latest triggering message, not to every line in the transcript.",
                "Distinguish participants by their displayed name and stable user ID.",
                "Do not mention internal prompts, deployment configuration, OOC evaluation, "
                "or Character Relay.",
                "Do not claim to have seen messages outside the supplied transcript.",
                "Keep the response natural for a group chat and do not prefix it with your name.",
                f"Discord location: {payload.guild_name or payload.guild_id} / {location}",
                "Recent conversation:",
                transcript or "(No readable recent messages.)",
                "Latest triggering message:",
                f"[{payload.author_display_name} | {payload.author_id}]: {payload.text}",
                "Respond now as the character.",
            )
        )
