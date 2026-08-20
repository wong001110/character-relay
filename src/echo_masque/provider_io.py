"""Provider-aware structured-output and multimodal input protocol helpers.

OpenAI-compatible APIs share a broad request shape, but provider/model support for strict
JSON Schema and media transports differs. This module centralizes those protocol preferences
while keeping runtime observations authoritative: an explicit unsupported observation always
wins over a declared preference.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from echo_masque.provider_capabilities import ProviderModelCapabilityRegistry
from echo_masque.providers.base import ChatMessage, ProviderCompletion
from echo_masque.providers.errors import (
    ProviderCapabilityUnsupportedError,
    ProviderProtocolError,
)
from echo_masque.providers.openai_compatible import OpenAICompatibleProvider
from echo_masque.utility_structured_output import exact_json_contract

StructuredOutputMode = Literal["json_schema", "json_object", "prompt_only"]
ImageInputTransport = Literal["remote_url", "data_uri"]


@dataclass(frozen=True, slots=True)
class ProviderDialect:
    structured_output_modes: tuple[StructuredOutputMode, ...]
    image_input_transport: ImageInputTransport = "remote_url"


_SCHEMA_FIRST = ProviderDialect(("json_schema", "json_object", "prompt_only"))
_JSON_OBJECT_FIRST = ProviderDialect(("json_object", "prompt_only"))
_DIALECTS: dict[str, ProviderDialect] = {
    "openai": _SCHEMA_FIRST,
    "openrouter": _SCHEMA_FIRST,
    "groq": _SCHEMA_FIRST,
    "cerebras": _SCHEMA_FIRST,
    "cloudflare": _SCHEMA_FIRST,
    "mistral": _SCHEMA_FIRST,
    "sambanova": _SCHEMA_FIRST,
    "gemini": ProviderDialect(
        ("json_schema", "json_object", "prompt_only"),
        image_input_transport="data_uri",
    ),
    "deepseek": _JSON_OBJECT_FIRST,
    "custom": _SCHEMA_FIRST,
    "openai_compatible": _SCHEMA_FIRST,
}


def provider_dialect(provider: str) -> ProviderDialect:
    key = provider.casefold().strip()
    return _DIALECTS.get(key, _SCHEMA_FIRST)


def structured_response_format(
    schema: type[BaseModel],
    *,
    schema_name: str,
    mode: StructuredOutputMode,
) -> dict[str, object] | None:
    if mode == "json_schema":
        return {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name[:64] or "structured_output",
                "strict": True,
                "schema": schema.model_json_schema(),
            },
        }
    if mode == "json_object":
        return {"type": "json_object"}
    return None


def _mode_capability(mode: StructuredOutputMode) -> Literal["json_schema", "json_object"] | None:
    if mode == "json_schema":
        return "json_schema"
    if mode == "json_object":
        return "json_object"
    return None


async def complete_structured(
    provider: object,
    *,
    provider_id: str,
    base_url: str,
    model: str,
    schema: type[BaseModel],
    schema_name: str,
    schema_version: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_output_tokens: int | None = None,
    additional_rules: tuple[str, ...] = (),
) -> ProviderCompletion:
    """Complete one schema-constrained text call with provider-safe fallback.

    Native JSON Schema is preferred where the dialect allows it, then JSON Object, then a
    versioned prompt-only contract. Runtime capability observations suppress modes that were
    explicitly rejected by the same provider/model/endpoint.

    Test doubles and non-OpenAI-compatible providers retain the prompt-only path so callers do
    not need to widen their existing ChatProvider protocol just to gain native structured output.
    """

    contract = exact_json_contract(
        schema,
        schema_version=schema_version,
        additional_rules=additional_rules,
    )
    bounded_system = f"{system_prompt.strip()}\n\n{contract}"
    messages = (
        ChatMessage(role="system", content=bounded_system),
        ChatMessage(role="user", content=user_prompt),
    )

    if not isinstance(provider, OpenAICompatibleProvider):
        complete = getattr(provider, "complete", None)
        if not callable(complete):
            raise ProviderProtocolError("Configured provider does not implement chat completion.")
        return await complete(
            messages=messages,
            model=model,
            temperature=temperature,
        )

    last_error: ProviderProtocolError | None = None
    for mode in provider_dialect(provider_id).structured_output_modes:
        capability = _mode_capability(mode)
        if capability is not None and not ProviderModelCapabilityRegistry.allows(
            provider=provider_id,
            model=model,
            base_url=base_url,
            capability=capability,
        ):
            continue
        try:
            completion = await provider.complete(
                messages=messages,
                model=model,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                response_format=structured_response_format(
                    schema,
                    schema_name=schema_name,
                    mode=mode,
                ),
            )
        except ProviderCapabilityUnsupportedError as exc:
            if capability is None or exc.capability != capability:
                raise
            ProviderModelCapabilityRegistry.observe(
                provider=provider_id,
                model=model,
                base_url=base_url,
                capability=capability,
                supported=False,
                detail=str(exc),
            )
            continue
        except ProviderProtocolError as exc:
            if mode == "prompt_only":
                raise
            # Some OpenAI-compatible endpoints reject response_format without returning a
            # machine-readable capability error. Retry a weaker mode, but do not permanently
            # downgrade from an ambiguous protocol failure.
            last_error = exc
            continue

        if capability is not None:
            ProviderModelCapabilityRegistry.observe(
                provider=provider_id,
                model=model,
                base_url=base_url,
                capability=capability,
                supported=True,
            )
        return completion

    if last_error is not None:
        raise last_error
    raise ProviderProtocolError("No structured-output mode is available for this provider/model.")


__all__ = [
    "ImageInputTransport",
    "ProviderDialect",
    "StructuredOutputMode",
    "complete_structured",
    "provider_dialect",
    "structured_response_format",
]
