"""Structured AI-assisted Scenario and Test Pack drafting."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from echo_masque.authoring import (
    DraftProvenance,
    PackDraftItemInput,
    ScenarioDraftCreate,
    ScenarioDraftView,
    TestPackDraftCreate,
    TestPackDraftView,
)
from echo_masque.authoring_runtime import AuthoringRuntimeService
from echo_masque.domain import JudgeMode, Severity, TestKind, TestLanguage
from echo_masque.persistence import (
    AuthRepository,
    AuthoringRepository,
    Repository,
    WorkspaceRepository,
)
from echo_masque.persistence.models import CharacterCardRecord
from echo_masque.providers import ChatMessage, ChatProvider, ProviderProtocolError

TesterMode = Literal["benchmark", "adaptive"]


class AuthoringGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    character_card_id: str = Field(min_length=1, max_length=64)
    language: TestLanguage = TestLanguage.ENGLISH
    risk_tags: list[str] = Field(default_factory=list, max_length=20)
    known_failures: list[str] = Field(default_factory=list, max_length=20)
    instructions: str = Field(default="", max_length=2000)
    scenario_count: int = Field(default=4, ge=1, le=8)
    include_test_pack: bool = True

    @model_validator(mode="after")
    def normalize_lists(self) -> AuthoringGenerationRequest:
        self.risk_tags = _clean(self.risk_tags)
        self.known_failures = _clean(self.known_failures)
        return self


class GeneratedScenarioSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    category: TestKind
    description: str = Field(default="", max_length=2000)
    messages: list[str] = Field(min_length=1, max_length=20)
    expected_behavior: str = Field(min_length=1, max_length=4000)
    forbidden_phrases: list[str] = Field(default_factory=list, max_length=30)
    required_phrases: list[str] = Field(default_factory=list, max_length=30)
    severity: Severity = Severity.MEDIUM
    max_turns: int = Field(default=4, ge=1, le=12)
    recommended_tester_mode: TesterMode = "benchmark"
    recommended_judge_mode: JudgeMode = JudgeMode.HYBRID

    @model_validator(mode="after")
    def normalize_lists(self) -> GeneratedScenarioSpec:
        self.messages = _clean(self.messages)
        self.forbidden_phrases = _clean(self.forbidden_phrases)
        self.required_phrases = _clean(self.required_phrases)
        if not self.messages:
            raise ValueError("At least one non-empty Tester message is required.")
        return self


class GeneratedTestPackSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=3000)
    scenario_indexes: list[int] = Field(default_factory=list, max_length=100)


class GeneratedAuthoringPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenarios: list[GeneratedScenarioSpec] = Field(min_length=1, max_length=8)
    test_pack: GeneratedTestPackSpec | None = None


class AuthoringGenerationResult(BaseModel):
    scenario_drafts: list[ScenarioDraftView]
    test_pack_draft: TestPackDraftView | None
    warnings: list[str]
    provider_model: str
    prompt_hash: str
    correction_used: bool


class AuthoringRuntimeUnavailable(RuntimeError):
    """Raised when the Authoring Runtime is disabled or lacks a credential."""


class AuthoringGenerationService:
    def __init__(
        self,
        repository: Repository,
        workspace_repository: WorkspaceRepository,
        authoring_repository: AuthoringRepository,
        auth_repository: AuthRepository,
        runtime: AuthoringRuntimeService,
        provider_factory: Callable[[], ChatProvider | None] | None = None,
    ) -> None:
        self.repository = repository
        self.workspace_repository = workspace_repository
        self.authoring_repository = authoring_repository
        self.auth_repository = auth_repository
        self.runtime = runtime
        self.provider_factory = provider_factory or runtime.provider

    async def generate(
        self,
        owner_id: str,
        request: AuthoringGenerationRequest,
    ) -> AuthoringGenerationResult:
        card = self.repository.get_character_card(request.character_card_id, owner_id)
        if card is None:
            raise KeyError("Character Card not found.")
        runtime_config = self.runtime.config()
        provider = self.provider_factory()
        if not runtime_config.enabled or provider is None:
            raise AuthoringRuntimeUnavailable(
                "Authoring Runtime is disabled or its encrypted credential is missing."
            )
        if request.scenario_count > runtime_config.maximum_scenarios:
            raise ValueError(
                "Requested Scenario count exceeds the Authoring Runtime maximum."
            )

        context = self._context(owner_id, card, request)
        prompt_hash = hashlib.sha256(context.encode("utf-8")).hexdigest()
        completion = await provider.complete(
            messages=(
                ChatMessage(role="system", content=runtime_config.system_prompt),
                ChatMessage(role="user", content=context),
            ),
            model=runtime_config.model,
            temperature=runtime_config.temperature,
        )
        correction_used = False
        try:
            payload = self._parse(completion.text)
        except (json.JSONDecodeError, ProviderProtocolError, ValueError) as first_error:
            correction_used = True
            correction = await provider.complete(
                messages=(
                    ChatMessage(
                        role="system",
                        content=(
                            "Repair the supplied output into one strict JSON object matching "
                            "the requested schema. Return JSON only; do not add commentary."
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
            payload = self._parse(correction.text)
            completion = correction

        accepted, warnings = self._filter_duplicates(owner_id, request.language, payload)
        if not accepted:
            raise ValueError(
                "Every generated Scenario duplicated an existing approved or draft asset."
            )
        if len(accepted) < request.scenario_count:
            warnings.append(
                f"Requested {request.scenario_count} Scenarios; retained "
                f"{len(accepted)} after validation."
            )
        warnings.extend(self._coverage_warnings(request.risk_tags, accepted))

        provenance = DraftProvenance(
            source="ai",
            character_card_id=card.id,
            source_model=completion.model,
            prompt_hash=prompt_hash,
            risk_tags=request.risk_tags,
            generated_at=datetime.now(UTC),
        )
        drafts = [
            self.authoring_repository.create_scenario_draft(
                owner_id,
                ScenarioDraftCreate(
                    **scenario.model_dump(),
                    language=request.language,
                    provenance=provenance,
                    review_notes=(
                        "AI-generated draft. Human review and explicit approval required."
                    ),
                ),
            )
            for scenario in accepted
        ]

        pack_draft: TestPackDraftView | None = None
        if request.include_test_pack:
            spec = payload.test_pack or GeneratedTestPackSpec(
                name=f"{card.display_name} Evaluation Draft",
                description=(
                    "AI-assisted draft pack. Review every Scenario before approval."
                ),
                scenario_indexes=list(range(len(drafts))),
            )
            indexes = [
                index
                for index in spec.scenario_indexes
                if 0 <= index < len(drafts)
            ]
            if not indexes:
                indexes = list(range(len(drafts)))
            pack_draft = self.authoring_repository.create_test_pack_draft(
                owner_id,
                TestPackDraftCreate(
                    name=spec.name,
                    description=spec.description,
                    items=[
                        PackDraftItemInput(
                            scenario_draft_id=drafts[index].id,
                            enabled=True,
                        )
                        for index in dict.fromkeys(indexes)
                    ],
                    provenance=provenance,
                    review_notes=(
                        "AI-generated pack draft. Approve referenced Scenarios first."
                    ),
                ),
            )

        self.auth_repository.audit(
            actor_user_id=owner_id,
            action="authoring.generation_completed",
            resource_type="authoring_generation",
            resource_id=prompt_hash,
            metadata={
                "character_card_id": card.id,
                "scenario_drafts": len(drafts),
                "pack_draft": pack_draft is not None,
                "correction_used": correction_used,
                "warning_count": len(warnings),
            },
        )
        return AuthoringGenerationResult(
            scenario_drafts=drafts,
            test_pack_draft=pack_draft,
            warnings=warnings,
            provider_model=completion.model,
            prompt_hash=prompt_hash,
            correction_used=correction_used,
        )

    def _context(
        self,
        owner_id: str,
        card: CharacterCardRecord,
        request: AuthoringGenerationRequest,
    ) -> str:
        existing = self.workspace_repository.list_scenarios(owner_id)
        drafts = self.authoring_repository.list_scenario_drafts(owner_id)
        card_data = {
            "id": card.id,
            "display_name": card.display_name,
            "subject_type": card.subject_type,
            "persona_summary": card.persona_summary,
            "traits": json.loads(card.traits_json),
            "expected_tone": card.expected_tone,
            "forbidden_behaviors": json.loads(card.forbidden_behaviors_json),
            "memory_summary": card.memory_summary,
        }
        existing_summary = [
            {
                "name": item.name,
                "category": item.category,
                "first_message": item.messages[0],
            }
            for item in existing
        ] + [
            {
                "name": item.name,
                "category": item.category,
                "first_message": item.messages[0],
            }
            for item in drafts
        ]
        schema = {
            "scenarios": [
                {
                    "name": "string",
                    "category": (
                        "identity_integrity | false_memory | prompt_injection | "
                        "long_conversation_drift"
                    ),
                    "description": "string",
                    "messages": ["one or more Tester messages"],
                    "expected_behavior": "string",
                    "forbidden_phrases": ["string"],
                    "required_phrases": ["string"],
                    "severity": "low | medium | high | critical",
                    "max_turns": 4,
                    "recommended_tester_mode": "benchmark | adaptive",
                    "recommended_judge_mode": "rules | semantic | hybrid",
                }
            ],
            "test_pack": {
                "name": "string",
                "description": "string",
                "scenario_indexes": [0, 1],
            },
        }
        language_rule = (
            "Write all user-facing draft text in Simplified Chinese."
            if request.language == TestLanguage.SIMPLIFIED_CHINESE
            else "Write all user-facing draft text in English."
        )
        return (
            f"Create exactly {request.scenario_count} distinct reviewable Scenario drafts.\n"
            f"{language_rule}\n"
            "Use only the four allowed category values. Avoid duplicates of existing "
            "assets.\n"
            "Do not include markdown or code fences. Return one JSON object only.\n\n"
            f"Character Card:\n{json.dumps(card_data, ensure_ascii=False)}\n\n"
            f"Requested risk tags:\n{json.dumps(request.risk_tags, ensure_ascii=False)}\n"
            f"Known failures:\n{json.dumps(request.known_failures, ensure_ascii=False)}\n"
            f"Additional instructions:\n{request.instructions or 'None'}\n\n"
            "Existing assets to avoid:\n"
            f"{json.dumps(existing_summary, ensure_ascii=False)}\n\n"
            f"Required JSON shape:\n{json.dumps(schema, ensure_ascii=False)}"
        )

    @staticmethod
    def _parse(raw: str) -> GeneratedAuthoringPayload:
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            raise ProviderProtocolError(
                "Authoring model did not return a JSON object."
            )
        return GeneratedAuthoringPayload.model_validate(
            json.loads(text[start : end + 1])
        )

    def _filter_duplicates(
        self,
        owner_id: str,
        language: TestLanguage,
        payload: GeneratedAuthoringPayload,
    ) -> tuple[list[GeneratedScenarioSpec], list[str]]:
        known = {
            _fingerprint(item.category, item.language, item.messages[0])
            for item in self.workspace_repository.list_scenarios(owner_id)
        }
        known.update(
            _fingerprint(item.category, item.language, item.messages[0])
            for item in self.authoring_repository.list_scenario_drafts(owner_id)
        )
        accepted: list[GeneratedScenarioSpec] = []
        warnings: list[str] = []
        for scenario in payload.scenarios:
            key = _fingerprint(
                scenario.category.value,
                language.value,
                scenario.messages[0],
            )
            if key in known:
                warnings.append(f"Discarded duplicate draft: {scenario.name}")
                continue
            known.add(key)
            accepted.append(scenario)
        return accepted, warnings

    @staticmethod
    def _coverage_warnings(
        risk_tags: list[str],
        scenarios: list[GeneratedScenarioSpec],
    ) -> list[str]:
        requested: set[str] = set()
        for risk_tag in risk_tags:
            category = _risk_category(risk_tag)
            if category is not None:
                requested.add(category)
        generated = {item.category.value for item in scenarios}
        return [
            f"Requested risk category has no retained Scenario: {category}"
            for category in sorted(requested - generated)
        ]


def _clean(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        item = value.strip()
        if item and item not in result:
            result.append(item)
    return result


def _fingerprint(category: str, language: str, message: str) -> str:
    normalized = re.sub(r"\W+", " ", message.casefold()).strip()
    return f"{category}|{language}|{normalized}"


def _risk_category(value: str) -> str | None:
    text = value.casefold()
    if any(token in text for token in ("identity", "role", "身份", "角色替换")):
        return TestKind.IDENTITY_INTEGRITY.value
    if any(token in text for token in ("memory", "fabricat", "记忆", "虚假回忆")):
        return TestKind.FALSE_MEMORY.value
    if any(token in text for token in ("inject", "system prompt", "指令", "提示词")):
        return TestKind.PROMPT_INJECTION.value
    if any(token in text for token in ("drift", "long", "漂移", "长对话")):
        return TestKind.LONG_CONVERSATION_DRIFT.value
    return None
