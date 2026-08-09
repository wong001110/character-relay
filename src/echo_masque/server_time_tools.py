"""Server-timezone-aware Tool Registry behavior."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, model_validator

from echo_masque.character_invite_runtime import (
    CharacterInviteProposal,
    current_character_invite_turn,
)
from echo_masque.persistence.condition_watch_repository import ConditionWatchRepository
from echo_masque.persistence.deployment_repository import DeploymentRepository
from echo_masque.providers import ChatToolDefinition
from echo_masque.server_time import current_server_timezone, validate_timezone
from echo_masque.tool_external import json_result
from echo_masque.tool_runtime import ToolExecutionContext, ToolRegistry, _tool


class WatchConditionInput(BaseModel):
    condition_text: str = Field(min_length=1, max_length=1200)
    notification_text: str = Field(min_length=1, max_length=1800)
    check_interval_seconds: int = Field(default=900, ge=300, le=86_400)
    expires_in_seconds: int = Field(default=86_400, ge=600, le=2_592_000)
    max_attempts: int = Field(default=96, ge=1, le=500)
    mention_user: bool = True

    @model_validator(mode="after")
    def normalize_text(self) -> WatchConditionInput:
        self.condition_text = self.condition_text.strip()
        self.notification_text = self.notification_text.strip()
        if not self.condition_text or not self.notification_text:
            raise ValueError("Condition and notification text cannot be blank.")
        return self


class CharacterInviteInput(BaseModel):
    participant_alias: str = Field(min_length=2, max_length=16, pattern=r"^p[1-9][0-9]*$")
    reason: str = Field(default="", max_length=600)

    @model_validator(mode="after")
    def normalize_reason(self) -> CharacterInviteInput:
        self.participant_alias = self.participant_alias.strip()
        self.reason = self.reason.strip()
        return self


class ServerAwareToolRegistry(ToolRegistry):
    """Use the current Discord Server timezone and expose server-aware V2 capabilities."""

    def __init__(
        self,
        *args: Any,
        condition_watch_repository: ConditionWatchRepository | None = None,
        condition_watch_enabled: bool = False,
        deployment_repository: DeploymentRepository | None = None,
        character_invite_enabled: bool | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        if condition_watch_repository is None and self.reminders is not None:
            condition_watch_repository = ConditionWatchRepository(self.reminders.database)
        self.condition_watches = condition_watch_repository
        if deployment_repository is None and condition_watch_repository is not None:
            deployment_repository = DeploymentRepository(condition_watch_repository.database)
        self.deployments = deployment_repository

        watch_available = (
            condition_watch_enabled and condition_watch_repository is not None
        )
        watch_tool = _tool(
            tool_id="watch.condition",
            display_name="Watch Condition",
            description=(
                "Persist a bounded future condition watch for this Character Deployment. "
                "Runtime checks it later and queues a real notification only after the "
                "condition triggers."
            ),
            category="watch",
            operation="coordination",
            risk="medium",
            side_effect=True,
            provider_name="watch_condition",
            provider_description=(
                "Create a bounded future condition watch after an explicit human request. "
                "The condition is not considered triggered until Runtime later evaluates "
                "and persists it."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "condition_text": {"type": "string", "maxLength": 1200},
                    "notification_text": {"type": "string", "maxLength": 1800},
                    "check_interval_seconds": {
                        "type": "integer",
                        "minimum": 300,
                        "maximum": 86400,
                        "default": 900,
                    },
                    "expires_in_seconds": {
                        "type": "integer",
                        "minimum": 600,
                        "maximum": 2592000,
                        "default": 86400,
                    },
                    "max_attempts": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 500,
                        "default": 96,
                    },
                    "mention_user": {"type": "boolean", "default": True},
                },
                "required": ["condition_text", "notification_text"],
                "additionalProperties": False,
            },
            available=watch_available,
            availability_reason=(
                ""
                if watch_available
                else "Condition Watch background Runtime is not enabled."
            ),
        )
        self._by_id[watch_tool.catalog.id] = watch_tool
        self._by_provider_name[watch_tool.catalog.provider_function_name] = watch_tool

        invite_enabled = (
            condition_watch_enabled
            if character_invite_enabled is None
            else character_invite_enabled
        )
        invite_available = invite_enabled and self.deployments is not None
        invite_tool = _tool(
            tool_id="character.invite",
            display_name="Invite Character",
            description=(
                "Propose one prompt-local Character to join the current Discord turn. "
                "Runtime validates the candidate and may decline or suppress participation."
            ),
            category="character",
            operation="coordination",
            risk="medium",
            side_effect=True,
            provider_name="character_invite",
            provider_description=(
                "Propose one listed participant alias such as p1 to join this live human-"
                "initiated turn when the relationship, capability, or context justifies it. "
                "This Tool does not guarantee that the invited Character will speak."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "participant_alias": {
                        "type": "string",
                        "pattern": "^p[1-9][0-9]*$",
                        "description": "A prompt-local Character participant alias, e.g. p1.",
                    },
                    "reason": {
                        "type": "string",
                        "maxLength": 600,
                        "description": "Brief social or capability reason for the invitation.",
                    },
                },
                "required": ["participant_alias"],
                "additionalProperties": False,
            },
            available=invite_available,
            availability_reason=(
                ""
                if invite_available
                else "Character invite Runtime validation is not enabled."
            ),
        )
        self._by_id[invite_tool.catalog.id] = invite_tool
        self._by_provider_name[invite_tool.catalog.provider_function_name] = invite_tool

    def provider_tools(
        self,
        enabled_tool_ids: tuple[str, ...],
    ) -> tuple[ChatToolDefinition, ...]:
        timezone = current_server_timezone()
        definitions = super().provider_tools(enabled_tool_ids)
        adjusted: list[ChatToolDefinition] = []
        for definition in definitions:
            payload = definition.model_dump()
            function = payload.get("function")
            if not isinstance(function, dict):
                adjusted.append(definition)
                continue
            name = function.get("name")
            parameters = function.get("parameters")
            if isinstance(parameters, dict):
                properties = parameters.get("properties")
                if isinstance(properties, dict) and name == "utility_current_time":
                    timezone_schema = properties.get("timezone")
                    if isinstance(timezone_schema, dict):
                        timezone_schema.pop("default", None)
                        timezone_schema["description"] = (
                            "Optional IANA timezone override. Omit it to use this Server's "
                            f"default timezone ({timezone})."
                        )
                    function["description"] = (
                        "Get the current date and time. If no timezone is supplied, use the "
                        f"Server default ({timezone})."
                    )
                if isinstance(properties, dict) and name == "scheduler_remind":
                    reminder_schema = properties.get("reminder_text")
                    if isinstance(reminder_schema, dict):
                        reminder_schema["description"] = (
                            "The exact future message this Character will send when the "
                            "reminder fires. "
                            "Write it now in the current Character persona and voice. "
                            "Do not write an "
                            "internal title or instruction, and do not add an @mention; "
                            "Runtime handles "
                            "the target mention separately."
                        )
                    scheduled_schema = properties.get("scheduled_at")
                    if isinstance(scheduled_schema, dict):
                        scheduled_schema["description"] = (
                            "ISO-8601 date/time. A timezone offset is optional; an unqualified "
                            f"local time is interpreted in the Server timezone ({timezone})."
                        )
                    function["description"] = (
                        "Schedule a future reminder. Write reminder_text as the exact future "
                        "Character-facing message in the current persona and voice; Runtime will "
                        "deliver it deterministically without another model call. "
                        "Use delay_seconds "
                        "for relative time or scheduled_at for a local/offset ISO-8601 time. "
                        f"Unqualified times use the Server timezone ({timezone})."
                    )
                if isinstance(properties, dict) and name == "watch_condition":
                    notification_schema = properties.get("notification_text")
                    if isinstance(notification_schema, dict):
                        notification_schema["description"] = (
                            "The exact future message this Character will send only after the "
                            "condition triggers. Write it now in the current Character "
                            "persona and "
                            "voice. Do not write an internal title or instruction, and do not add an "
                            "@mention; Runtime handles the target mention separately."
                        )
                    function["description"] = (
                        "Create a bounded future condition watch after an explicit human "
                        "request. "
                        "Write notification_text as the exact future Character-facing message in "
                        "the current persona and voice. Runtime later evaluates the condition and "
                        "delivers that stored text deterministically only after a persisted "
                        "trigger."
                    )
            adjusted.append(ChatToolDefinition.model_validate(payload))
        return tuple(adjusted)

    async def _execute_tool(
        self,
        tool_id: str,
        arguments: dict[str, object],
        context: ToolExecutionContext,
    ) -> str:
        if tool_id == "utility.current_time":
            adjusted = arguments.copy()
            timezone = adjusted.get("timezone")
            if not isinstance(timezone, str) or not timezone.strip():
                adjusted["timezone"] = current_server_timezone()
            return await super()._execute_tool(tool_id, adjusted, context)
        if tool_id == "watch.condition":
            return self._watch_condition(arguments, context)
        if tool_id == "character.invite":
            return self._character_invite(arguments, context)
        return await super()._execute_tool(tool_id, arguments, context)

    def _character_invite(
        self,
        arguments: dict[str, object],
        context: ToolExecutionContext,
    ) -> str:
        self._require_discord(context)
        if context.initiator_is_bot:
            raise ValueError(
                "Character invitations are allowed only on a human-initiated turn."
            )
        if self.deployments is None:
            raise ValueError("Character invite Runtime validation is unavailable.")
        state = current_character_invite_turn()
        if state is None or state.deployment_id != context.deployment_id:
            raise ValueError("No prompt-local Character participants are available to invite.")
        if (
            state.connection_id != context.connection_id
            or state.guild_id != context.guild_id
            or state.channel_id != context.channel_id
            or state.thread_id != context.thread_id
        ):
            raise ValueError("Character invite Runtime context does not match this turn.")

        payload = CharacterInviteInput.model_validate(arguments)
        participant = state.participant(payload.participant_alias)
        if participant is None:
            raise ValueError("Unknown prompt-local participant alias.")
        if participant.kind != "character" or not participant.ref.startswith("deployment:"):
            raise ValueError("character.invite can target only a Character participant alias.")
        candidate_id = participant.ref.removeprefix("deployment:").strip()
        if not candidate_id or candidate_id == context.deployment_id:
            raise ValueError("A Character cannot invite itself.")

        candidate = self.deployments.deployment_matches_discord_destination(
            candidate_id,
            connection_id=context.connection_id,
            guild_id=context.guild_id,
            channel_id=context.channel_id,
            thread_id=context.thread_id,
            category_id=state.category_id,
        )
        if candidate is None or candidate.owner_id != context.owner_id:
            raise ValueError("The invited Character is not active in this Runtime scope.")
        if candidate.participation_mode != "smart":
            raise ValueError(
                "The invited Character must use Smart Participation in this destination."
            )

        state.record(
            CharacterInviteProposal(
                participant_alias=payload.participant_alias,
                candidate_deployment_id=candidate.id,
                candidate_character_card_id=candidate.character_card_id,
                candidate_display_name=participant.display_name,
                reason=payload.reason,
            )
        )
        return json_result(
            ok=True,
            proposal_status="pending_runtime_validation",
            participant_alias=payload.participant_alias,
            participant_name=participant.display_name,
            reason=payload.reason,
            note=(
                "Character Relay will validate the final Smart Output and participant "
                "budget. This does not guarantee the invited Character will speak."
            ),
        )

    def _watch_condition(
        self,
        arguments: dict[str, object],
        context: ToolExecutionContext,
    ) -> str:
        self._require_discord(context)
        if context.initiator_is_bot:
            raise ValueError("Condition watches require an explicit human-initiated request.")
        if self.condition_watches is None:
            raise ValueError("Condition Watch persistence is unavailable.")
        payload = WatchConditionInput.model_validate(arguments)
        now = datetime.now(UTC)
        maximum_possible_attempts = max(
            1,
            payload.expires_in_seconds // payload.check_interval_seconds,
        )
        max_attempts = min(payload.max_attempts, maximum_possible_attempts)
        record = self.condition_watches.create(
            owner_id=context.owner_id,
            deployment_id=context.deployment_id,
            channel_id=context.channel_id,
            thread_id=context.thread_id,
            target_user_id=(
                context.initiator_user_id
                if payload.mention_user and context.initiator_user_id
                else ""
            ),
            condition_text=payload.condition_text,
            notification_text=payload.notification_text,
            check_interval_seconds=payload.check_interval_seconds,
            max_attempts=max_attempts,
            next_check_at=now + timedelta(seconds=payload.check_interval_seconds),
            expires_at=now + timedelta(seconds=payload.expires_in_seconds),
        )
        return json_result(
            ok=True,
            watch_id=record.id,
            status=record.status,
            channel_id=record.channel_id,
            thread_id=record.thread_id,
            next_check_at=record.next_check_at.isoformat(),
            expires_at=record.expires_at.isoformat(),
            check_interval_seconds=record.check_interval_seconds,
            max_attempts=record.max_attempts,
        )

    def _schedule_reminder(
        self,
        arguments: dict[str, object],
        context: ToolExecutionContext,
    ) -> str:
        timezone = validate_timezone(current_server_timezone())
        adjusted = arguments.copy()
        raw_scheduled_at = adjusted.get("scheduled_at")
        if isinstance(raw_scheduled_at, str) and raw_scheduled_at.strip():
            normalized = raw_scheduled_at.strip().replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(normalized)
            except ValueError:
                parsed = None
            if parsed is not None and parsed.tzinfo is None:
                adjusted["scheduled_at"] = parsed.replace(
                    tzinfo=ZoneInfo(timezone)
                ).isoformat()

        result = json.loads(super()._schedule_reminder(adjusted, context))
        scheduled_at = result.get("scheduled_at")
        if isinstance(scheduled_at, str):
            result["scheduled_at_utc"] = scheduled_at
            result["scheduled_at"] = self._local_iso(scheduled_at, timezone)
        result["timezone"] = timezone
        return json.dumps(result, ensure_ascii=False, separators=(",", ":"))

    def _list_reminders(
        self,
        arguments: dict[str, object],
        context: ToolExecutionContext,
    ) -> str:
        timezone = validate_timezone(current_server_timezone())
        result = json.loads(super()._list_reminders(arguments, context))
        reminders = result.get("reminders")
        if isinstance(reminders, list):
            for item in reminders:
                if not isinstance(item, dict):
                    continue
                scheduled_at = item.get("scheduled_at")
                if not isinstance(scheduled_at, str):
                    continue
                item["scheduled_at_utc"] = scheduled_at
                item["scheduled_at"] = self._local_iso(scheduled_at, timezone)
        result["timezone"] = timezone
        return json.dumps(result, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _local_iso(value: str, timezone: str) -> str:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(ZoneInfo(timezone)).isoformat(timespec="seconds")


__all__ = ["CharacterInviteInput", "ServerAwareToolRegistry", "WatchConditionInput"]
