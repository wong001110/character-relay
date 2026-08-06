"""Reviewable AI drafting for Character Cards and prompt-model profiles."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from echo_masque.authoring_runtime import AuthoringRuntimeService
from echo_masque.providers import ChatMessage, ChatProvider, ProviderProtocolError

CharacterLanguage = Literal["en", "zh-CN"]
CharacterSubjectType = Literal["companion", "npc", "assistant", "custom"]


class CharacterSuggestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concept: str = Field(min_length=10, max_length=6000)
    name_hint: str = Field(default="", max_length=120)
    relationship_context: str = Field(default="", max_length=2000)
    writing_constraints: str = Field(default="", max_length=3000)
    subject_type_hint: CharacterSubjectType = "custom"
    language: CharacterLanguage = "en"

    @model_validator(mode="after")
    def normalize(self) -> CharacterSuggestionRequest:
        self.concept = self.concept.strip()
        self.name_hint = self.name_hint.strip()
        self.relationship_context = self.relationship_context.strip()
        self.writing_constraints = self.writing_constraints.strip()
        return self


class CharacterSuggestionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=120)
    subtitle: str = Field(default="", max_length=180)
    subject_type: CharacterSubjectType = "custom"
    persona_summary: str = Field(min_length=1, max_length=2000)
    traits: list[str] = Field(default_factory=list, max_length=12)
    tags: list[str] = Field(default_factory=list, max_length=12)
    expected_tone: str = Field(min_length=1, max_length=500)
    forbidden_behaviors: list[str] = Field(default_factory=list, max_length=20)
    memory_summary: str = Field(default="", max_length=2000)
    system_prompt: str = Field(min_length=1, max_length=20000)

    @model_validator(mode="after")
    def normalize(self) -> CharacterSuggestionDraft:
        self.traits = _clean(self.traits, 12)
        self.tags = _clean(self.tags, 12)
        self.forbidden_behaviors = _clean(self.forbidden_behaviors, 20)
        return self


class CharacterSuggestionResult(CharacterSuggestionDraft):
    provider_model: str
    correction_used: bool = False


class CharacterAssistantUnavailable(RuntimeError):
    """Raised when the shared Authoring Runtime cannot generate a draft."""


class CharacterAssistantService:
    def __init__(
        self,
        runtime: AuthoringRuntimeService,
        provider_factory: Callable[[], ChatProvider | None] | None = None,
    ) -> None:
        self.runtime = runtime
        self.provider_factory = provider_factory or runtime.provider

    async def suggest(
        self,
        request: CharacterSuggestionRequest,
    ) -> CharacterSuggestionResult:
        runtime_config = self.runtime.config()
        provider = self.provider_factory()
        if not runtime_config.enabled or provider is None:
            raise CharacterAssistantUnavailable(
                "AI assistance is unavailable because the Authoring Runtime is disabled "
                "or its encrypted credential is missing."
            )

        completion = await provider.complete(
            messages=(
                ChatMessage(
                    role="system",
                    content=(
                        "You draft production-ready AI Character Cards. Return one strict "
                        "JSON object only. Keep the character internally consistent, avoid "
                        "inventing requirements the user did not imply, and make every field "
                        "reviewable before saving."
                    ),
                ),
                ChatMessage(role="user", content=self._prompt(request)),
            ),
            model=runtime_config.model,
            temperature=min(runtime_config.temperature, 0.55),
        )
        correction_used = False
        try:
            draft = self._parse(completion.text)
        except (json.JSONDecodeError, ProviderProtocolError, ValueError) as first_error:
            correction_used = True
            correction = await provider.complete(
                messages=(
                    ChatMessage(
                        role="system",
                        content=(
                            "Repair the supplied output into one strict JSON object matching "
                            "the requested Character Card schema. Return JSON only."
                        ),
                    ),
                    ChatMessage(
                        role="user",
                        content=(
                            f"Validation error: {first_error}\n\n"
                            f"Invalid output:\n{completion.text}"
                        ),
                    ),
                ),
                model=runtime_config.model,
                temperature=0.0,
            )
            draft = self._parse(correction.text)
            completion = correction

        return CharacterSuggestionResult(
            **draft.model_dump(),
            provider_model=completion.model,
            correction_used=correction_used,
        )

    @staticmethod
    def _prompt(request: CharacterSuggestionRequest) -> str:
        language_rule = (
            "Write all generated prose and labels in Simplified Chinese."
            if request.language == "zh-CN"
            else "Write all generated prose and labels in English."
        )
        schema = {
            "display_name": "public character name",
            "subtitle": "one-line role or relationship positioning",
            "subject_type": "companion | npc | assistant | custom",
            "persona_summary": (
                "2-5 concise paragraphs covering background, motives, values, and tension"
            ),
            "traits": ["stable observable trait"],
            "tags": ["short retrieval tag"],
            "expected_tone": (
                "voice, pacing, vocabulary, emotional intensity, and audience changes"
            ),
            "forbidden_behaviors": [
                "concrete behavior that would break the character"
            ],
            "memory_summary": (
                "durable facts, relationships, promises, and non-overwritable anchors"
            ),
            "system_prompt": (
                "complete runtime instruction with identity, worldview, voice, "
                "boundaries, and priorities"
            ),
        }
        context = {
            "concept": request.concept,
            "name_hint": request.name_hint,
            "relationship_context": request.relationship_context,
            "writing_constraints": request.writing_constraints,
            "subject_type_hint": request.subject_type_hint,
        }
        return (
            f"{language_rule}\n"
            "Create a coherent draft rather than independent field fragments. Traits and "
            "boundaries must be observable. The system_prompt must agree with every other "
            "field and must not include API keys, hidden platform instructions, or claims of "
            "capabilities not provided by the user. Do not include markdown or code fences.\n\n"
            f"User brief:\n{json.dumps(context, ensure_ascii=False)}\n\n"
            f"Required JSON shape:\n{json.dumps(schema, ensure_ascii=False)}"
        )

    @staticmethod
    def _parse(raw: str) -> CharacterSuggestionDraft:
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            raise ProviderProtocolError("Character assistant did not return a JSON object.")
        return CharacterSuggestionDraft.model_validate(json.loads(text[start : end + 1]))


def _clean(values: list[str], limit: int) -> list[str]:
    result: list[str] = []
    for value in values:
        item = value.strip()
        if item and item not in result:
            result.append(item)
        if len(result) >= limit:
            break
    return result
