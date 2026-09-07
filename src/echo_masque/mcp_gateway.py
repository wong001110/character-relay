"""Static MCP discover/invoke gateway for Character Relay Tool Runtime."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic
from typing import TYPE_CHECKING, Protocol

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import SchemaError  # type: ignore[import-untyped]
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from pydantic import ValidationError as PydanticValidationError

from echo_masque.mcp_client import (
    McpCallOutcomeUnknown,
    McpClient,
    McpClientError,
    McpRemoteCallResult,
    McpRemoteTool,
)
from echo_masque.mcp_config import McpProviderConfig
from echo_masque.network_safety import PublicUrlGuard
from echo_masque.tool_external import ExternalToolFailed, ExternalToolRejected, json_result
from echo_masque.turn_progress import publish_turn_progress

if TYPE_CHECKING:
    from echo_masque.tool_runtime import ToolExecutionContext


_MCP_TOOL_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_MAX_SCHEMA_DEPTH = 16
_MAX_SCHEMA_PROPERTIES = 300
_MAX_DISCOVERY_RESPONSE_BYTES = 16_384
_ACCEPTED_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
_SAFE_SCHEMA_KEYS = {
    "$schema",
    "additionalProperties",
    "const",
    "default",
    "description",
    "enum",
    "exclusiveMaximum",
    "exclusiveMinimum",
    "items",
    "maxItems",
    "maxLength",
    "maximum",
    "minItems",
    "minLength",
    "minimum",
    "properties",
    "required",
    "title",
    "type",
    "uniqueItems",
}


class McpImageDelivery(Protocol):
    async def __call__(
        self,
        context: ToolExecutionContext,
        mime_type: str,
        data_base64: str,
    ) -> dict[str, object]: ...


type McpClientFactory = Callable[[PublicUrlGuard], McpClient]
type BearerTokenResolver = Callable[[str], SecretStr | None]
type McpScopeValidator = Callable[[ToolExecutionContext, str], None]


class McpDiscoverInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    query: str = Field(min_length=1, max_length=400)
    server_id: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("query")
    @classmethod
    def normalized_query(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("MCP discovery query cannot be blank.")
        return normalized


class McpInvokeInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    server_id: str = Field(min_length=1, max_length=64)
    tool_name: str = Field(min_length=1, max_length=128)
    schema_fingerprint: str = Field(min_length=64, max_length=64)
    arguments: dict[str, object] = Field(default_factory=dict)

    @field_validator("server_id")
    @classmethod
    def server_id_is_safe(cls, value: str) -> str:
        normalized = value.strip()
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", normalized):
            raise ValueError("MCP server id is invalid.")
        return normalized

    @field_validator("tool_name")
    @classmethod
    def tool_name_is_safe(cls, value: str) -> str:
        normalized = value.strip()
        if not _MCP_TOOL_NAME.fullmatch(normalized):
            raise ValueError("MCP tool name is invalid.")
        return normalized

    @field_validator("schema_fingerprint")
    @classmethod
    def schema_fingerprint_is_sha256(cls, value: str) -> str:
        normalized = value.casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", normalized):
            raise ValueError("MCP schema fingerprint is invalid.")
        return normalized

    @model_validator(mode="after")
    def arguments_are_bounded_json_object(self) -> McpInvokeInput:
        try:
            encoded = json.dumps(self.arguments, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ValueError("MCP arguments must be JSON serializable.") from exc
        if len(encoded.encode("utf-8")) > 16_384:
            raise ValueError("MCP arguments exceed the 16 KiB limit.")
        return self


@dataclass(frozen=True)
class McpCatalogEntry:
    provider_id: str
    tool_name: str
    title: str
    description: str
    input_schema: dict[str, object]
    schema_fingerprint: str


@dataclass(frozen=True)
class _CatalogSnapshot:
    expires_at: float
    entries: tuple[McpCatalogEntry, ...]


class McpGateway:
    """Discover and invoke only operator-granted MCP tools for a deployment."""

    def __init__(
        self,
        *,
        providers: tuple[McpProviderConfig, ...],
        bearer_token_resolver: BearerTokenResolver | None = None,
        image_delivery: McpImageDelivery | None = None,
        url_guard: PublicUrlGuard | None = None,
        client_factory: McpClientFactory | None = None,
        scope_validator: McpScopeValidator | None = None,
    ) -> None:
        duplicate_ids = [item.id for item in providers]
        if len(duplicate_ids) != len(set(duplicate_ids)):
            raise ValueError("MCP provider ids must be unique.")
        self._providers = {item.id: item for item in providers}
        self._bearer_token_resolver = bearer_token_resolver or _environment_bearer_token
        self._image_delivery = image_delivery
        self._url_guard = url_guard or PublicUrlGuard()
        self._client = (client_factory or (lambda guard: McpClient(url_guard=guard)))(
            self._url_guard
        )
        self._scope_validator = scope_validator
        self._catalog_cache: dict[tuple[str, str, str], _CatalogSnapshot] = {}

    @property
    def available(self) -> bool:
        return any(item.enabled and item.deployment_grants for item in self._providers.values())

    async def discover(self, arguments: dict[str, object], context: ToolExecutionContext) -> str:
        try:
            payload = McpDiscoverInput.model_validate(arguments)
        except PydanticValidationError as exc:
            raise ExternalToolRejected(_input_error_code(exc)) from exc
        candidates: list[McpCatalogEntry] = []
        providers = self._providers_for_context(
            context,
            requested_provider_id=payload.server_id,
        )
        if providers:
            self._validate_current_scope(context, "mcp.discover")
            await self._publish_progress(context)
        for provider in providers:
            candidates.extend(
                await self._catalog_for(provider, context=context, force_refresh=False)
            )
        ranked = sorted(
            candidates,
            key=lambda item: (
                -self._relevance(item, payload.query),
                item.provider_id,
                item.tool_name,
            ),
        )
        descriptors: list[dict[str, object]] = []
        omitted_schema_count = 0
        for item in ranked:
            descriptor: dict[str, object] = {
                "server_id": item.provider_id,
                "tool_name": item.tool_name,
                "title": item.title,
                "description": item.description,
                "input_schema": item.input_schema,
                "schema_fingerprint": item.schema_fingerprint,
            }
            if len(descriptors) >= 3:
                break
            trial = [*descriptors, descriptor]
            if _discovery_response_fits(trial, omitted_schema_count):
                descriptors.append(descriptor)
            else:
                omitted_schema_count += 1
        return json_result(
            ok=True,
            query=payload.query,
            tools=descriptors,
            omitted_schema_count=omitted_schema_count,
            omitted_reason=("schema_response_budget" if omitted_schema_count else ""),
            external_data_untrusted=True,
        )

    async def invoke(self, arguments: dict[str, object], context: ToolExecutionContext) -> str:
        try:
            payload = McpInvokeInput.model_validate(arguments)
        except PydanticValidationError as exc:
            raise ExternalToolRejected(_input_error_code(exc)) from exc
        provider = self._provider_for_context(
            context,
            provider_id=payload.server_id,
            tool_name=payload.tool_name,
        )
        entries = await self._catalog_for(provider, context=context, force_refresh=True)
        entry = next((item for item in entries if item.tool_name == payload.tool_name), None)
        if entry is None:
            raise ExternalToolRejected("mcp_tool_not_currently_available")
        if entry.schema_fingerprint != payload.schema_fingerprint:
            raise ExternalToolRejected("mcp_schema_changed_refresh_discovery")
        try:
            Draft202012Validator(entry.input_schema).validate(payload.arguments)
        except (JsonSchemaValidationError, SchemaError) as exc:
            raise ExternalToolRejected("mcp_arguments_do_not_match_current_schema") from exc
        self._validate_current_scope(context, "mcp.invoke")
        await self._publish_progress(context)

        try:
            result = await self._client.call_tool(
                provider,
                self._bearer_token(provider),
                tool_name=entry.tool_name,
                arguments=payload.arguments,
            )
        except McpCallOutcomeUnknown as exc:
            raise ExternalToolFailed("mcp_call_outcome_unknown") from exc
        except McpClientError as exc:
            raise ExternalToolFailed(str(exc)) from exc
        if result.is_error:
            raise ExternalToolFailed("mcp_remote_tool_reported_error")
        return await self._normalize_result(result, provider=provider, entry=entry, context=context)

    def _providers_for_context(
        self,
        context: ToolExecutionContext,
        *,
        requested_provider_id: str | None,
    ) -> tuple[McpProviderConfig, ...]:
        if requested_provider_id is not None:
            provider = self._providers.get(requested_provider_id)
            if provider is None or not provider.enabled:
                raise ExternalToolRejected("mcp_provider_not_configured")
            return (provider,) if provider.granted_tool_names(
                owner_id=context.owner_id, deployment_id=context.deployment_id
            ) else ()
        return tuple(
            provider
            for provider in self._providers.values()
            if provider.enabled
            and provider.granted_tool_names(
                owner_id=context.owner_id,
                deployment_id=context.deployment_id,
            )
        )

    def _provider_for_context(
        self,
        context: ToolExecutionContext,
        *,
        provider_id: str,
        tool_name: str,
    ) -> McpProviderConfig:
        provider = self._providers.get(provider_id)
        if provider is None or not provider.enabled:
            raise ExternalToolRejected("mcp_provider_not_configured")
        grants = provider.granted_tool_names(
            owner_id=context.owner_id,
            deployment_id=context.deployment_id,
        )
        if tool_name not in grants:
            raise ExternalToolRejected("mcp_tool_not_granted_to_deployment")
        return provider

    async def _catalog_for(
        self,
        provider: McpProviderConfig,
        *,
        context: ToolExecutionContext,
        force_refresh: bool,
    ) -> tuple[McpCatalogEntry, ...]:
        cache_key = (provider.id, context.owner_id, context.deployment_id)
        cached = self._catalog_cache.get(cache_key)
        if not force_refresh and cached is not None and cached.expires_at > monotonic():
            return cached.entries
        grants = provider.granted_tool_names(
            owner_id=context.owner_id,
            deployment_id=context.deployment_id,
        )
        try:
            remote_tools = await self._client.list_tools(provider, self._bearer_token(provider))
        except McpClientError as exc:
            raise ExternalToolFailed(str(exc)) from exc
        entries_by_name: dict[str, McpCatalogEntry] = {}
        for raw_tool in remote_tools:
            if raw_tool.name not in grants:
                continue
            entry = self._catalog_entry(provider, raw_tool)
            if entry is None:
                continue
            if entry.tool_name in entries_by_name:
                raise ExternalToolFailed("mcp_duplicate_remote_tool_name")
            entries_by_name[entry.tool_name] = entry
        entries = tuple(entries_by_name.values())
        snapshot = _CatalogSnapshot(
            expires_at=monotonic() + provider.catalog_ttl_seconds,
            entries=entries,
        )
        self._catalog_cache[cache_key] = snapshot
        return snapshot.entries

    @staticmethod
    def _catalog_entry(
        provider: McpProviderConfig,
        tool: McpRemoteTool,
    ) -> McpCatalogEntry | None:
        if not _MCP_TOOL_NAME.fullmatch(tool.name):
            return None
        schema = tool.input_schema
        try:
            serialized = json.dumps(
                schema,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except (TypeError, ValueError):
            return None
        if len(serialized.encode("utf-8")) > provider.max_schema_chars:
            return None
        if not _safe_input_schema(schema):
            return None
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError:
            return None
        return McpCatalogEntry(
            provider_id=provider.id,
            tool_name=tool.name,
            title=(tool.title or tool.name).strip()[:240],
            description=" ".join(tool.description.split())[:1_000],
            input_schema=schema,
            schema_fingerprint=hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        )

    def _bearer_token(self, provider: McpProviderConfig) -> SecretStr | None:
        if provider.bearer_token_env is None:
            return None
        token = self._bearer_token_resolver(provider.bearer_token_env)
        if token is None:
            raise ExternalToolFailed("mcp_bearer_token_not_configured")
        return token

    async def _normalize_result(
        self,
        result: McpRemoteCallResult,
        *,
        provider: McpProviderConfig,
        entry: McpCatalogEntry,
        context: ToolExecutionContext,
    ) -> str:
        text_parts: list[str] = []
        artifacts: list[dict[str, object]] = []
        image_seen = False
        for block in result.content:
            block_type = getattr(block, "type", "")
            if block_type == "text":
                text = getattr(block, "text", "")
                if isinstance(text, str):
                    text_parts.append(text)
            elif block_type == "image" and not image_seen:
                image_seen = True
                artifact = await self._deliver_image(block, provider=provider, context=context)
                if artifact is not None:
                    artifacts.append(artifact)
        text = "\n".join(text_parts).strip()
        if len(text) > provider.max_result_chars:
            text = text[: provider.max_result_chars] + "…"
        payload: dict[str, object] = {
            "ok": True,
            "server_id": provider.id,
            "tool_name": entry.tool_name,
            "content": text or "Remote MCP tool completed.",
            "external_data_untrusted": True,
        }
        if artifacts:
            payload["artifacts"] = artifacts
        structured = _bounded_json(result.structured_content, maximum=provider.max_result_chars)
        if structured is not None:
            payload["structured_content"] = structured
        return json_result(**payload)

    async def _deliver_image(
        self,
        block: object,
        *,
        provider: McpProviderConfig,
        context: ToolExecutionContext,
    ) -> dict[str, object] | None:
        mime_type = getattr(block, "mime_type", "")
        data_base64 = getattr(block, "data", "")
        if (
            not isinstance(mime_type, str)
            or mime_type.casefold() not in _ACCEPTED_IMAGE_MIME_TYPES
            or not isinstance(data_base64, str)
        ):
            return None
        try:
            decoded = base64.b64decode(data_base64, validate=True)
        except (ValueError, TypeError):
            return None
        if len(decoded) > provider.max_image_bytes or self._image_delivery is None:
            return None
        try:
            return await self._image_delivery(context, mime_type.casefold(), data_base64)
        except Exception as exc:
            raise ExternalToolFailed("mcp_image_delivery_failed") from exc

    @staticmethod
    async def _publish_progress(context: ToolExecutionContext) -> None:
        message = getattr(context, "progress_message", "")
        if isinstance(message, str) and message:
            await publish_turn_progress(message)

    def _validate_current_scope(self, context: ToolExecutionContext, tool_id: str) -> None:
        if self._scope_validator is not None:
            self._scope_validator(context, tool_id)

    @staticmethod
    def _relevance(entry: McpCatalogEntry, query: str) -> int:
        tokens = tuple(item for item in re.split(r"\W+", query.casefold()) if item)
        haystack = " ".join((entry.tool_name, entry.title, entry.description)).casefold()
        return sum(token in haystack for token in tokens)


def _safe_input_schema(value: object, *, depth: int = 0, property_count: int = 0) -> bool:
    if depth > _MAX_SCHEMA_DEPTH:
        return False
    if isinstance(value, list):
        return all(
            _safe_input_schema(item, depth=depth + 1, property_count=property_count)
            for item in value
        )
    if not isinstance(value, dict):
        return True
    if any(not isinstance(key, str) or key not in _SAFE_SCHEMA_KEYS for key in value):
        return False
    if depth == 0 and value.get("type") != "object":
        return False
    if "type" in value and not isinstance(value["type"], str):
        return False
    if "$schema" in value and value["$schema"] not in {
        "https://json-schema.org/draft/2020-12/schema",
    }:
        return False
    enum = value.get("enum")
    if enum is not None and (
        not isinstance(enum, list)
        or len(enum) > 100
        or any(not isinstance(item, (str, int, float, bool, type(None))) for item in enum)
    ):
        return False
    if "const" in value and not isinstance(value["const"], (str, int, float, bool, type(None))):
        return False
    properties = value.get("properties")
    if properties is not None and (
        not isinstance(properties, dict)
        or any(not isinstance(key, str) or len(key) > 128 for key in properties)
    ):
        return False
    next_count = property_count + (len(properties) if isinstance(properties, dict) else 0)
    if next_count > _MAX_SCHEMA_PROPERTIES:
        return False
    if isinstance(properties, dict) and not all(
        _safe_input_schema(item, depth=depth + 1, property_count=next_count)
        for item in properties.values()
    ):
        return False
    items = value.get("items")
    if isinstance(items, dict) and not _safe_input_schema(
        items,
        depth=depth + 1,
        property_count=next_count,
    ):
        return False
    if items is not None and not isinstance(items, dict):
        return False
    additional = value.get("additionalProperties")
    if isinstance(additional, dict) and not _safe_input_schema(
        additional,
        depth=depth + 1,
        property_count=next_count,
    ):
        return False
    if additional is not None and not isinstance(additional, (bool, dict)):
        return False
    required = value.get("required")
    return required is None or (
        isinstance(required, list)
        and len(required) <= _MAX_SCHEMA_PROPERTIES
        and all(isinstance(item, str) and item in (properties or {}) for item in required)
    )


def _input_error_code(error: PydanticValidationError) -> str:
    errors = error.errors()
    kind = errors[0]["type"] if errors else "invalid"
    safe_kind = re.sub(r"[^a-z0-9_]+", "_", str(kind).casefold()).strip("_")
    return f"mcp_invalid_arguments_{safe_kind or 'invalid'}"


def _discovery_response_fits(
    descriptors: list[dict[str, object]],
    omitted_schema_count: int,
) -> bool:
    payload = {
        "ok": True,
        "query": "x" * 400,
        "tools": descriptors,
        "omitted_schema_count": max(999, omitted_schema_count),
        "omitted_reason": "schema_response_budget",
        "external_data_untrusted": True,
    }
    return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) <= (
        _MAX_DISCOVERY_RESPONSE_BYTES - 256
    )


def _environment_bearer_token(name: str) -> SecretStr | None:
    value = os.environ.get(name)
    return SecretStr(value) if value else None


def _bounded_json(value: object, *, maximum: int) -> object | None:
    if value is None:
        return None
    try:
        serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return None
    if len(serialized.encode("utf-8")) > maximum:
        return None
    return value


__all__ = [
    "BearerTokenResolver",
    "McpCatalogEntry",
    "McpDiscoverInput",
    "McpGateway",
    "McpImageDelivery",
    "McpInvokeInput",
    "McpScopeValidator",
]
