"""Server-timezone-aware Tool Registry behavior."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from echo_masque.providers import ChatToolDefinition
from echo_masque.server_time import current_server_timezone, validate_timezone
from echo_masque.tool_runtime import ToolExecutionContext, ToolRegistry


class ServerAwareToolRegistry(ToolRegistry):
    """Use the current Discord Server timezone when a Tool call omits one."""

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
                    scheduled_schema = properties.get("scheduled_at")
                    if isinstance(scheduled_schema, dict):
                        scheduled_schema["description"] = (
                            "ISO-8601 date/time. A timezone offset is optional; an unqualified "
                            f"local time is interpreted in the Server timezone ({timezone})."
                        )
                    function["description"] = (
                        "Schedule a future reminder. Use delay_seconds for relative time or "
                        "scheduled_at for a local/offset ISO-8601 time. Unqualified times use "
                        f"the Server timezone ({timezone})."
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
        return await super()._execute_tool(tool_id, arguments, context)

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


__all__ = ["ServerAwareToolRegistry"]
