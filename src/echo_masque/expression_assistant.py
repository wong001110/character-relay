"""AI-assisted drafting for Discord Emoji and Sticker semantics."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from echo_masque.authoring_runtime import AuthoringRuntimeService
from echo_masque.provider_io import complete_structured
from echo_masque.providers import ChatProvider, ProviderProtocolError

ExpressionResourceType = Literal["emoji", "sticker"]
ExpressionLanguage = Literal["en", "zh-CN"]


class ExpressionSuggestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_type: ExpressionResourceType
    resource_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=1000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    animated: bool = False
    asset_url: str = Field(default="", max_length=2000)
    usage_context: str = Field(min_length=3, max_length=3000)
    language: ExpressionLanguage = "en"

    @model_validator(mode="after")
    def normalize(self) -> ExpressionSuggestionRequest:
        self.tags = _clean(self.tags)
        self.usage_context = self.usage_context.strip()
        return self


class ExpressionSuggestionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    semantic_intent: str = Field(min_length=1, max_length=80)
    semantic_emotion: str = Field(min_length=1, max_length=80)
    semantic_description: str = Field(min_length=1, max_length=2000)
    aliases: list[str] = Field(default_factory=list, max_length=30)
    situations: list[str] = Field(default_factory=list, max_length=30)
    avoid_when: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def normalize(self) -> ExpressionSuggestionDraft:
        self.aliases = _clean(self.aliases)
        self.situations = _clean(self.situations)
        self.avoid_when = _clean(self.avoid_when)
        return self


class ExpressionSuggestionResult(ExpressionSuggestionDraft):
    provider_model: str
    correction_used: bool = False


class ExpressionAssistantUnavailable(RuntimeError):
    """Raised when the shared Authoring Runtime cannot serve suggestions."""


class ExpressionAssistantService:
    def __init__(
        self,
        runtime: AuthoringRuntimeService,
        provider_factory: Callable[[], ChatProvider | None] | None = None,
    ) -> None:
        self.runtime = runtime
        self.provider_factory = provider_factory or runtime.provider

    async def suggest(
        self,
        request: ExpressionSuggestionRequest,
    ) -> ExpressionSuggestionResult:
        runtime_config = self.runtime.config()
        provider = self.provider_factory()
        if not runtime_config.enabled or provider is None:
            raise ExpressionAssistantUnavailable(
                "AI assistance is unavailable because the Authoring Runtime is disabled "
                "or its encrypted credential is missing."
            )

        completion = await complete_structured(
            provider,
            provider_id=runtime_config.provider,
            base_url=runtime_config.base_url,
            model=runtime_config.model,
            schema=ExpressionSuggestionDraft,
            schema_name="expression_suggestion",
            schema_version="expression-suggestion-v1",
            system_prompt=(
                "You define custom Discord Emoji and Sticker semantics for an AI character "
                "runtime. Treat the user's usage context as a proposal, not verified truth. "
                "Produce concise, reusable definitions and avoid invented lore."
            ),
            user_prompt=self._prompt(request),
            temperature=min(runtime_config.temperature, 0.45),
            max_output_tokens=1600,
        )
        correction_used = False
        try:
            draft = self._parse(completion.text)
        except (json.JSONDecodeError, ProviderProtocolError, ValueError) as first_error:
            correction_used = True
            correction = await complete_structured(
                provider,
                provider_id=runtime_config.provider,
                base_url=runtime_config.base_url,
                model=runtime_config.model,
                schema=ExpressionSuggestionDraft,
                schema_name="expression_suggestion",
                schema_version="expression-suggestion-v1",
                system_prompt=(
                    "Repair the supplied output into the requested expression schema. "
                    "Do not invent visual details or new lore."
                ),
                user_prompt=(
                    f"Validation error: {first_error}\n\n"
                    f"Invalid output:\n{completion.text}"
                ),
                temperature=0.0,
                max_output_tokens=1600,
            )
            draft = self._parse(correction.text)
            completion = correction

        return ExpressionSuggestionResult(
            **draft.model_dump(),
            provider_model=completion.model,
            correction_used=correction_used,
        )

    @staticmethod
    def _prompt(request: ExpressionSuggestionRequest) -> str:
        language_rule = (
            "Write every generated value in Simplified Chinese."
            if request.language == "zh-CN"
            else "Write every generated value in English."
        )
        schema = {
            "semantic_intent": "short intent label",
            "semantic_emotion": "short emotion label",
            "semantic_description": "clear meaning supplied to AI characters",
            "aliases": ["search alias"],
            "situations": ["use when situation"],
            "avoid_when": ["avoid when situation"],
        }
        metadata = {
            "resource_type": request.resource_type,
            "resource_id": request.resource_id,
            "name": request.name,
            "description": request.description,
            "tags": request.tags,
            "animated": request.animated,
            "asset_url": request.asset_url,
        }
        return (
            f"{language_rule}\n"
            "The asset URL is reference metadata only; do not claim visual details you "
            "cannot verify. Base the draft on the resource name, Discord metadata, and "
            "the user's described usage context.\n"
            "Aliases should help semantic retrieval. Situations and avoid_when should be "
            "specific enough to guide expression selection.\n"
            "Do not include markdown or code fences.\n\n"
            f"Resource metadata:\n{json.dumps(metadata, ensure_ascii=False)}\n\n"
            f"User-described usage context:\n{request.usage_context}\n\n"
            f"Required JSON shape:\n{json.dumps(schema, ensure_ascii=False)}"
        )

    @staticmethod
    def _parse(raw: str) -> ExpressionSuggestionDraft:
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            raise ProviderProtocolError("Expression assistant did not return a JSON object.")
        return ExpressionSuggestionDraft.model_validate(json.loads(text[start : end + 1]))


def _clean(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        item = value.strip()
        if item and item not in result:
            result.append(item)
    return result
