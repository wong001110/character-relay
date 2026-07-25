"""Model-provider contracts."""

from typing import Protocol

from pydantic import BaseModel, ConfigDict


class ChatMessage(BaseModel):
    model_config = ConfigDict(frozen=True)
    role: str
    content: str


class ProviderCompletion(BaseModel):
    model_config = ConfigDict(frozen=True)
    text: str
    model: str
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str | None = None


class ChatProvider(Protocol):
    async def complete(
        self,
        *,
        messages: tuple[ChatMessage, ...],
        model: str,
        temperature: float,
    ) -> ProviderCompletion: ...
