import asyncio
from types import SimpleNamespace

from echo_masque.expression_assistant import (
    ExpressionAssistantService,
    ExpressionSuggestionRequest,
)
from echo_masque.providers import ProviderCompletion


class FakeProvider:
    async def complete(self, *, messages, model: str, temperature: float):
        assert messages[-1].role == "user"
        assert "playful curiosity" in messages[-1].content
        return ProviderCompletion(
            text=(
                '{"semantic_intent":"peek","semantic_emotion":"curious",'
                '"semantic_description":"Playful curiosity while waiting for more.",'
                '"aliases":["peek","watching"],'
                '"situations":["A friend hints at surprising news"],'
                '"avoid_when":["A serious apology"]}'
            ),
            model=model,
            latency_ms=12,
        )


class FakeRuntime:
    def __init__(self) -> None:
        self.fake_provider = FakeProvider()

    def config(self):
        return SimpleNamespace(enabled=True, model="test-model", temperature=0.35)

    def provider(self):
        return self.fake_provider


def test_expression_assistant_returns_reviewable_structured_draft() -> None:
    service = ExpressionAssistantService(FakeRuntime())  # type: ignore[arg-type]
    result = asyncio.run(
        service.suggest(
            ExpressionSuggestionRequest(
                resource_type="emoji",
                resource_id="123",
                name="peek",
                usage_context="playful curiosity while waiting for more",
                language="en",
            )
        )
    )

    assert result.semantic_intent == "peek"
    assert result.semantic_emotion == "curious"
    assert result.aliases == ["peek", "watching"]
    assert result.situations == ["A friend hints at surprising news"]
    assert result.avoid_when == ["A serious apology"]
    assert result.provider_model == "test-model"
    assert result.correction_used is False
