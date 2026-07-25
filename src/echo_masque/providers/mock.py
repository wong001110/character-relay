"""Offline provider used by tests and examples."""

from collections.abc import Callable

from echo_masque.providers.base import ChatMessage, ProviderCompletion


class MockChatProvider:
    def __init__(self, responder: Callable[[tuple[ChatMessage, ...]], str] | None = None) -> None:
        self.calls: list[tuple[ChatMessage, ...]] = []
        self._responder = responder or (lambda messages: f"Echo: {messages[-1].content}")

    async def complete(
        self,
        *,
        messages: tuple[ChatMessage, ...],
        model: str,
        temperature: float,
    ) -> ProviderCompletion:
        self.calls.append(messages)
        return ProviderCompletion(
            text=self._responder(messages),
            model=model,
            latency_ms=2,
            input_tokens=sum(len(item.content.split()) for item in messages),
            output_tokens=3,
            finish_reason="stop",
        )
