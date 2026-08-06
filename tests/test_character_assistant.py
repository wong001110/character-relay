import asyncio
from types import SimpleNamespace

from echo_masque.character_assistant import (
    CharacterAssistantService,
    CharacterSuggestionRequest,
)
from echo_masque.providers import ProviderCompletion


class FakeProvider:
    async def complete(self, *, messages, model: str, temperature: float):
        assert messages[-1].role == "user"
        assert "product producer" in messages[-1].content
        return ProviderCompletion(
            text=(
                '{"display_name":"Zhi","subtitle":"AI product producer",'
                '"subject_type":"companion",'
                '"persona_summary":"A practical builder who turns vague ideas into plans.",'
                '"traits":["curious","structured"],'
                '"tags":["product","builder"],'
                '"expected_tone":"Clear, calm, and practical.",'
                '"forbidden_behaviors":["Invent completed work"],'
                '"memory_summary":"Remember agreed goals and constraints.",'
                '"system_prompt":"You are Zhi, a practical AI product producer."}'
            ),
            model=model,
            latency_ms=12,
        )


class FakeRuntime:
    def __init__(self) -> None:
        self.fake_provider = FakeProvider()

    def config(self):
        return SimpleNamespace(enabled=True, model="test-model", temperature=0.4)

    def provider(self):
        return self.fake_provider


def test_character_assistant_returns_reviewable_structured_draft() -> None:
    service = CharacterAssistantService(FakeRuntime())  # type: ignore[arg-type]
    result = asyncio.run(
        service.suggest(
            CharacterSuggestionRequest(
                concept="An AI product producer who turns vague ideas into products.",
                relationship_context="A practical collaborator for the user.",
                subject_type_hint="companion",
                language="en",
            )
        )
    )

    assert result.display_name == "Zhi"
    assert result.subject_type == "companion"
    assert result.traits == ["curious", "structured"]
    assert result.forbidden_behaviors == ["Invent completed work"]
    assert result.provider_model == "test-model"
    assert result.correction_used is False
