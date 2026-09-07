"""Static, operator-owned configuration for controlled MCP providers."""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_TOOL_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_ENVIRONMENT_NAME = re.compile(r"^[A-Z_][A-Z0-9_]{0,127}$")


class McpDeploymentGrant(BaseModel):
    """An operator grant for one owner/deployment pair on one MCP provider."""

    model_config = ConfigDict(frozen=True)

    owner_id: str = Field(min_length=1, max_length=128)
    deployment_id: str = Field(min_length=1, max_length=128)
    tool_names: tuple[str, ...] = Field(min_length=1, max_length=100)

    @field_validator("owner_id", "deployment_id")
    @classmethod
    def identifiers_are_trimmed(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("MCP grant identifiers must not be blank.")
        return normalized

    @field_validator("tool_names")
    @classmethod
    def tool_names_are_explicit(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(dict.fromkeys(item.strip() for item in value))
        if not normalized or any(not _TOOL_NAME.fullmatch(item) for item in normalized):
            raise ValueError(
                "MCP grants must contain explicit valid tool names; wildcards are not allowed."
            )
        return normalized


class McpProviderConfig(BaseModel):
    """One HTTPS Streamable HTTP MCP endpoint, configured only by an operator."""

    model_config = ConfigDict(frozen=True)

    id: str
    endpoint: str
    enabled: bool = True
    bearer_token_env: str | None = None
    deployment_grants: tuple[McpDeploymentGrant, ...] = Field(default=(), max_length=500)
    catalog_ttl_seconds: int = Field(default=300, ge=60, le=3600)
    list_timeout_seconds: float = Field(default=10.0, ge=1.0, le=10.0)
    call_timeout_seconds: float = Field(default=90.0, ge=1.0, le=120.0)
    max_catalog_pages: int = Field(default=10, ge=1, le=20)
    max_catalog_tools: int = Field(default=100, ge=1, le=200)
    max_schema_chars: int = Field(default=32_768, ge=1_024, le=65_536)
    max_result_chars: int = Field(default=12_000, ge=500, le=32_000)
    max_http_response_bytes: int = Field(default=12_000_000, ge=16_384, le=16_777_216)
    max_image_bytes: int = Field(default=8_388_608, ge=16_384, le=8_388_608)

    @field_validator("id")
    @classmethod
    def provider_id_is_static_identifier(cls, value: str) -> str:
        normalized = value.strip()
        if not _IDENTIFIER.fullmatch(normalized):
            raise ValueError("MCP provider id must use lowercase letters, digits, _ or -.")
        return normalized

    @field_validator("endpoint")
    @classmethod
    def endpoint_is_exact_credential_free_https_url(cls, value: str) -> str:
        candidate = value.strip()
        try:
            parsed = urlsplit(candidate)
            port = parsed.port
        except ValueError as exc:
            raise ValueError("MCP endpoint is invalid.") from exc
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or port not in {None, 443}
        ):
            raise ValueError("MCP endpoint must be one exact credential-free HTTPS URL.")
        hostname = parsed.hostname.casefold().rstrip(".")
        if not hostname:
            raise ValueError("MCP endpoint must include a hostname.")
        host = f"[{hostname}]" if ":" in hostname else hostname
        netloc = host if port is None else f"{host}:{port}"
        path = parsed.path or "/"
        return urlunsplit(("https", netloc, path, "", ""))

    @field_validator("bearer_token_env")
    @classmethod
    def bearer_token_env_is_name_only(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not _ENVIRONMENT_NAME.fullmatch(normalized):
            raise ValueError("MCP bearer token must be configured by an environment variable name.")
        return normalized

    @model_validator(mode="after")
    def grants_are_unique(self) -> McpProviderConfig:
        keys = [(item.owner_id, item.deployment_id) for item in self.deployment_grants]
        if len(keys) != len(set(keys)):
            raise ValueError("Each MCP provider may have one grant per owner/deployment pair.")
        encoded_image_bytes = 4 * ((self.max_image_bytes + 2) // 3)
        if self.max_http_response_bytes < encoded_image_bytes + 65_536:
            raise ValueError(
                "MCP HTTP response limit must include one maximum image encoded as base64."
            )
        return self

    def granted_tool_names(self, *, owner_id: str, deployment_id: str) -> frozenset[str]:
        for grant in self.deployment_grants:
            if grant.owner_id == owner_id and grant.deployment_id == deployment_id:
                return frozenset(grant.tool_names)
        return frozenset()


__all__ = ["McpDeploymentGrant", "McpProviderConfig"]
