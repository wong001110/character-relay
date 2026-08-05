"""Runtime bridge from normalized connector messages to deployed characters."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable

from pydantic import SecretStr

from echo_masque.api.connector_schemas import (
    DiscordConnectorReplyView,
    DiscordContextMessage,
    DiscordInboundMessage,
)
from echo_masque.api.expression_schemas import ExpressionCandidate, ExpressionDecision
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

        text, expression = self._parse_expression_decision(
            response.text.strip(),
            payload.expression_candidates,
        )
        if not text and expression.action == "none":
            return DiscordConnectorReplyView(
                action="silent",
                reason="empty_model_response",
                deployment_id=deployment.id,
                character_display_name=card.display_name,
                expression=expression,
            )

        self.deployment_repository.record_deployment_activity(deployment.id)
        return DiscordConnectorReplyView(
            action="reply" if text else "expression",
            reason="character_response_generated",
            deployment_id=deployment.id,
            character_display_name=card.display_name,
            text=text,
            reply_to_message_id=payload.message_id,
            latency_ms=response.latency_ms,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            expression=expression,
        )

    @staticmethod
    def _parse_expression_decision(
        text: str,
        candidates: list[ExpressionCandidate],
    ) -> tuple[str, ExpressionDecision]:
        marker = re.search(r"\[\[CR_EXPRESSION\s+(.*?)\s*\]\]\s*$", text, re.DOTALL)
        if marker is None:
            return text.strip(), ExpressionDecision(reason="model_omitted_expression_control")
        clean_text = text[: marker.start()].rstrip()
        try:
            value = json.loads(marker.group(1))
            decision = ExpressionDecision.model_validate(value)
        except (json.JSONDecodeError, ValueError):
            return clean_text, ExpressionDecision(reason="invalid_expression_control")
        if decision.action == "none":
            return clean_text, decision
        candidate = next(
            (item for item in candidates if item.resource_key == decision.resource_key),
            None,
        )
        if candidate is None or decision.action not in candidate.allowed_actions:
            return clean_text, ExpressionDecision(reason="expression_candidate_not_allowed")
        return clean_text, decision

    @staticmethod
    def _should_reply(
        deployment: CharacterDeploymentRecord,
        payload: DiscordInboundMessage,
    ) -> bool:
        if payload.interaction_session_id:
            return True
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
            raise ConnectorRuntimeError("The deployed Character Card needs a provider credential.")
        compiled = compile_character_prompt(config.system_prompt, character_profile)
        return PromptModelTarget(
            config=config,
            provider=self.provider_factory(config.base_url, credential),
            runtime_system_prompt=compiled.compiled_system_prompt,
        )

    @staticmethod
    def _context_message_content(message: DiscordContextMessage) -> str:
        parts: list[str] = []
        if message.text.strip():
            parts.append(message.text.strip())
        for emoji in message.emojis:
            meaning = (
                emoji.semantic_description.strip()
                or f"Custom Emoji named {emoji.name} with no confirmed meaning."
            )
            parts.append(
                f"[Discord Custom Emoji: {emoji.name}; interpreted meaning: {meaning}; "
                f"source: {emoji.semantic_source}; confidence: {emoji.semantic_confidence:.2f}]"
            )
        for sticker in message.stickers:
            meaning = (
                sticker.semantic_description.strip()
                or sticker.description.strip()
                or f"Sticker named {sticker.name} with no confirmed meaning."
            )
            parts.append(
                f"[Discord Sticker: {sticker.name}; interpreted meaning: {meaning}; "
                f"source: {sticker.semantic_source}; confidence: "
                f"{sticker.semantic_confidence:.2f}]"
            )
        return "\n".join(parts) or "(No readable text or interpreted expression content.)"

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
                    stickers=payload.stickers,
                    is_bot=payload.author_is_bot,
                )
            )
        transcript = "\n".join(
            (
                f"[{'Character' if item.is_bot else 'Member'}: "
                f"{item.author_display_name} | {item.author_id}]: "
                f"{DiscordConnectorRuntime._context_message_content(item)}"
            )
            for item in messages[-30:]
            if item.text.strip() or item.emojis or item.stickers
        )
        location = payload.channel_name or payload.channel_id
        if payload.thread_id:
            location = f"{location} / {payload.thread_name or payload.thread_id}"

        peers = list(
            dict.fromkeys(
                item.strip()
                for item in payload.available_characters
                if item.strip() and item.strip().casefold() != character_name.casefold()
            )
        )
        interaction_guidance: tuple[str, ...] = ()
        if payload.interaction_session_id:
            intensity_rules = {
                "light": "Use mild teasing and keep the response easy to brush off.",
                "playful": "Use clear playful roasting with wit, not hostility.",
                "sharp": "Be more direct and cutting, while remaining non-abusive.",
            }
            target_name = payload.interaction_target_display_name or payload.author_display_name
            target_user_id = payload.interaction_target_user_id or payload.author_id
            interaction_guidance = (
                "This reply is part of a Portal-configured Roast Interaction Session.",
                f"The target member is {target_name} with stable Discord user ID {target_user_id}.",
                f"You are speaker {payload.interaction_position} of "
                f"{payload.interaction_participant_count} in round "
                f"{payload.interaction_round} of {payload.interaction_total_rounds}.",
                intensity_rules.get(
                    payload.interaction_intensity,
                    "Use playful teasing without hostility.",
                ),
                "Build on earlier character replies in this Interaction Session without "
                "repeating the same joke. Do not Tag another character; speaking order is "
                "controlled by the Session.",
                "Roast only the target member's current words, choices, harmless habits, "
                "gameplay, coding mistakes, lateness, or self-directed jokes. Never target "
                "identity traits, nationality, race, religion, gender, sexuality, disability, "
                "health, body, appearance, trauma, family, private data, or threats. Do not "
                "invent personal facts or encourage harassment outside this bounded exchange.",
            )
        tag_guidance: tuple[str, ...] = ()
        if peers:
            example = f"@{peers[0]}"
            if len(peers) > 1:
                example = f"{example} and @{peers[1]}"
            tag_guidance = (
                f"Other active character Tags at this location: {', '.join(peers)}.",
                "To intentionally invite another character to answer, begin your "
                "reply with @ followed by one of the listed character Tags. Tag each "
                f"intended character separately, for example {example}.",
                "The examples name other active characters, never you. Use character "
                "tags sparingly and only when their response adds value. Never tag "
                "yourself. A leading tag may cause another provider call.",
            )
        expression_guidance: tuple[str, ...] = ()
        if payload.expression_candidates:
            candidate_lines = tuple(
                (
                    f"- key={item.resource_key}; type={item.resource_type}; "
                    f"actions={','.join(item.allowed_actions)}; meaning="
                    f"{item.semantic_description or item.semantic_intent or item.name}"
                )
                for item in payload.expression_candidates[:6]
            )
            expression_guidance = (
                "A small retrieved set of Server expressions is available below.",
                *candidate_lines,
                "Using an expression is optional. Use at most one. Unicode Emoji may remain "
                "naturally in your reply text. Never invent a custom Emoji or Sticker ID.",
                "Append exactly one final machine-control line after the visible reply: "
                '[[CR_EXPRESSION {"action":"none","reason":"not needed"}]] or '
                '[[CR_EXPRESSION {"action":"reaction","resource_key":"emoji:123",'
                '"reason":"brief reason"}]]. Valid actions are none, inline, reaction, sticker. '
                "Choose only a listed resource_key and an action allowed for that candidate.",
            )
        source_guidance = (
            "The latest triggering message was written by another deployed character."
            if payload.author_is_bot
            else "The latest triggering message was written by a human Discord member."
        )
        latest_message = DiscordContextMessage(
            message_id=payload.message_id,
            author_id=payload.author_id,
            author_display_name=payload.author_display_name,
            text=payload.text,
            stickers=payload.stickers,
            is_bot=payload.author_is_bot,
        )
        latest_content = DiscordConnectorRuntime._context_message_content(latest_message)
        return "\n".join(
            (
                "You are participating in a real Discord group conversation "
                "through Character Relay.",
                f"Continue acting as {character_name} using the existing system "
                "prompt and persona.",
                "Reply to the latest triggering message, not to every line in the transcript.",
                source_guidance,
                "Distinguish human members and deployed characters by their displayed "
                "name, participant type, and stable ID.",
                *interaction_guidance,
                *tag_guidance,
                *expression_guidance,
                "Do not mention internal prompts, deployment configuration, OOC evaluation, "
                "or Character Relay.",
                "Do not claim to have seen messages outside the supplied transcript.",
                "Keep the response natural for a group chat and do not prefix it with your name.",
                f"Discord location: {payload.guild_name or payload.guild_id} / {location}",
                "Recent conversation:",
                transcript or "(No readable recent messages.)",
                "Latest triggering message:",
                (
                    f"[{'Character' if payload.author_is_bot else 'Member'}: "
                    f"{payload.author_display_name} | {payload.author_id}]: {latest_content}"
                ),
                "Respond now as the character.",
            )
        )
