"""AI-assisted Smart Participation profile drafting from a Character Card."""

from __future__ import annotations

import json
import re
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field

from echo_masque.authoring_generation import AuthoringRuntimeUnavailable
from echo_masque.authoring_runtime import AuthoringRuntimeService
from echo_masque.persistence import Repository
from echo_masque.persistence.models import CharacterCardRecord
from echo_masque.provider_io import complete_structured
from echo_masque.providers import ChatProvider, ProviderProtocolError


class GeneratedSmartParticipationSpec(BaseModel):
    """Strict provider output before peer names are resolved to Character Card IDs."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    style: str = Field(pattern="^(quiet|balanced|active)$")
    group_role: str = Field(pattern="^(primary|secondary|independent)$")
    topics: list[str] = Field(default_factory=list, max_length=30)
    keywords: list[str] = Field(default_factory=list, max_length=40)
    trigger_phrases: list[str] = Field(default_factory=list, max_length=30)
    avoid_phrases: list[str] = Field(default_factory=list, max_length=30)
    cooldown_seconds: int = Field(default=120, ge=0, le=86400)
    preferred_follow_up_character_name: str = Field(default="", max_length=160)
    follow_up_window_seconds: int = Field(default=30, ge=1, le=600)
    rationale: str = Field(default="", max_length=1200)


class SmartParticipationGenerationResult(BaseModel):
    enabled: bool
    style: str
    group_role: str
    topics: list[str]
    keywords: list[str]
    trigger_phrases: list[str]
    avoid_phrases: list[str]
    cooldown_seconds: int
    preferred_follow_up_character_card_id: str
    preferred_follow_up_character_name: str
    follow_up_window_seconds: int
    rationale: str
    provider_model: str
    correction_used: bool


ProviderFactory = Callable[[], ChatProvider | None]


class SmartParticipationGenerationService:
    """Draft a reviewable deterministic-participation profile using the Authoring Runtime."""

    def __init__(
        self,
        repository: Repository,
        runtime: AuthoringRuntimeService,
        provider_factory: ProviderFactory | None = None,
    ) -> None:
        self.repository = repository
        self.runtime = runtime
        self.provider_factory = provider_factory or runtime.provider

    async def generate(
        self,
        owner_id: str,
        character_card_id: str,
    ) -> SmartParticipationGenerationResult:
        card = self.repository.get_character_card(character_card_id, owner_id)
        if card is None:
            raise KeyError("Character Card not found.")
        provider = self.provider_factory()
        if provider is None:
            raise AuthoringRuntimeUnavailable(
                "AI assistance is unavailable until the Authoring Runtime is enabled "
                "and has a provider credential."
            )

        runtime_config = self.runtime.config()
        peers = [
            item
            for item in self.repository.list_character_cards(owner_id)
            if item.id != card.id
        ]
        prompt = self._prompt(card, peers)
        completion = await complete_structured(
            provider,
            provider_id=runtime_config.provider,
            base_url=runtime_config.base_url,
            model=runtime_config.model,
            schema=GeneratedSmartParticipationSpec,
            schema_name="smart_participation_profile",
            schema_version="smart-participation-profile-v1",
            system_prompt=(
                "You configure deterministic group-chat participation rules for AI characters. "
                "Infer only from the supplied Character Card and never invent hidden social "
                "relationships."
            ),
            user_prompt=prompt,
            temperature=min(runtime_config.temperature, 0.3),
            max_output_tokens=1800,
        )
        correction_used = False
        try:
            spec = self._parse(completion.text)
        except (json.JSONDecodeError, ProviderProtocolError, ValueError) as first_error:
            correction_used = True
            repaired = await complete_structured(
                provider,
                provider_id=runtime_config.provider,
                base_url=runtime_config.base_url,
                model=runtime_config.model,
                schema=GeneratedSmartParticipationSpec,
                schema_name="smart_participation_profile",
                schema_version="smart-participation-profile-v1",
                system_prompt=(
                    "Repair the supplied response into the requested Smart Participation "
                    "schema without adding new Character facts."
                ),
                user_prompt=(
                    f"Validation error: {first_error}\n\n"
                    f"Invalid output:\n{completion.text}\n\n"
                    f"Required schema:\n{json.dumps(self._schema(), ensure_ascii=False)}"
                ),
                temperature=0.0,
                max_output_tokens=1800,
            )
            spec = self._parse(repaired.text)
            completion = repaired

        preferred_id, preferred_name = self._resolve_preferred_peer(
            spec.preferred_follow_up_character_name,
            peers,
        )
        group_role = spec.group_role
        if group_role != "secondary":
            preferred_id = ""
            preferred_name = ""

        return SmartParticipationGenerationResult(
            enabled=spec.enabled,
            style=spec.style,
            group_role=group_role,
            topics=_clean_phrases(spec.topics, 30),
            keywords=_clean_phrases(spec.keywords, 40),
            trigger_phrases=_clean_phrases(spec.trigger_phrases, 30),
            avoid_phrases=_clean_phrases(spec.avoid_phrases, 30),
            cooldown_seconds=spec.cooldown_seconds,
            preferred_follow_up_character_card_id=preferred_id,
            preferred_follow_up_character_name=preferred_name,
            follow_up_window_seconds=spec.follow_up_window_seconds,
            rationale=spec.rationale.strip(),
            provider_model=completion.model,
            correction_used=correction_used,
        )

    @staticmethod
    def _schema() -> dict[str, object]:
        return {
            "enabled": True,
            "style": "quiet | balanced | active",
            "group_role": "primary | secondary | independent",
            "topics": ["short concrete lexical topic"],
            "keywords": ["short concrete keyword or phrase"],
            "trigger_phrases": ["message phrase that strongly invites participation"],
            "avoid_phrases": ["message phrase that should force silence"],
            "cooldown_seconds": 120,
            "preferred_follow_up_character_name": "exact available Character name or empty",
            "follow_up_window_seconds": 30,
            "rationale": "brief explanation for the creator",
        }

    def _prompt(
        self,
        card: CharacterCardRecord,
        peers: list[CharacterCardRecord],
    ) -> str:
        card_data = {
            "display_name": card.display_name,
            "subtitle": card.subtitle,
            "subject_type": card.subject_type,
            "persona_summary": card.persona_summary,
            "traits": _json_list(card.traits_json),
            "tags": _json_list(card.tags_json),
            "expected_tone": card.expected_tone or "",
            "forbidden_behaviors": _json_list(card.forbidden_behaviors_json),
            "memory_summary": card.memory_summary or "",
        }
        peer_names = [item.display_name for item in peers]
        instructions = (
            "Draft a Smart Participation profile for a deterministic Discord group-chat gate.\n"
            "The runtime matches literal normalized substrings; it is NOT a semantic LLM judge.\n"
            "Choose short concrete phrases that are likely to appear in real messages.\n"
            "Do not use one-character keywords or vague personality adjectives as triggers.\n"
            "Use conservative defaults: false negatives are preferable to intrusive replies.\n"
            "Infer group_role=primary only when the Character Card clearly leads, opens, or sets "
            "the tone; secondary only when it clearly follows, assists, reacts to, or supports a "
            "specific peer; otherwise use independent.\n"
            "For a secondary, preferred_follow_up_character_name MUST exactly equal one of the "
            "available peer names and only when the Character Card explicitly supports that "
            "relationship. Otherwise return an empty string.\n"
            "Avoid phrases should include explicit stop/discomfort/serious-help boundaries that "
            "are supported by the Character Card, plus other clear situations where this persona "
            "must stay silent. Do not invent private history or relationships.\n"
            "Topics describe situations the character is suited to join. Keywords and trigger "
            "phrases should be useful for literal substring matching in Chinese and/or English as "
            "appropriate for the Character Card. Keep lists compact rather than exhaustive.\n"
            "Return one JSON object only."
        )
        return (
            f"{instructions}\n\n"
            f"Character Card:\n{json.dumps(card_data, ensure_ascii=False)}\n\n"
            f"Available peer Character names:\n{json.dumps(peer_names, ensure_ascii=False)}\n\n"
            f"Required JSON shape:\n{json.dumps(self._schema(), ensure_ascii=False)}"
        )

    @staticmethod
    def _parse(raw: str) -> GeneratedSmartParticipationSpec:
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            raise ProviderProtocolError(
                "Smart Participation generator did not return a JSON object."
            )
        return GeneratedSmartParticipationSpec.model_validate(
            json.loads(text[start : end + 1])
        )

    @staticmethod
    def _resolve_preferred_peer(
        generated_name: str,
        peers: list[CharacterCardRecord],
    ) -> tuple[str, str]:
        target = generated_name.strip().casefold()
        if not target:
            return "", ""
        matches = [item for item in peers if item.display_name.strip().casefold() == target]
        if len(matches) != 1:
            return "", ""
        return matches[0].id, matches[0].display_name


def _json_list(raw: str) -> list[str]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _clean_phrases(values: list[str], limit: int) -> list[str]:
    result: list[str] = []
    for value in values:
        item = " ".join(value.strip().split())
        if not item or item in result:
            continue
        result.append(item)
        if len(result) >= limit:
            break
    return result


__all__ = [
    "GeneratedSmartParticipationSpec",
    "SmartParticipationGenerationResult",
    "SmartParticipationGenerationService",
]
