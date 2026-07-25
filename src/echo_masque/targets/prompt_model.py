"""Prompt-and-model target adapter."""

from pydantic import BaseModel, ConfigDict, Field

from echo_masque.domain import (
    TargetCapabilities,
    TargetResponse,
    TargetSummary,
    TargetType,
)
from echo_masque.providers import ChatMessage, ChatProvider


class PromptModelConfig(BaseModel):
    """Secret-free model target configuration."""

    model_config = ConfigDict(frozen=True)
    name: str = Field(min_length=1, max_length=120)
    provider: str = Field(default="custom", min_length=1, max_length=80)
    model: str = Field(min_length=1)
    system_prompt: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    api_key_env: str = Field(
        default="ECHO_MASQUE_MODEL_API_KEY",
        min_length=1,
        max_length=160,
    )
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


class PromptModelTarget:
    def __init__(self, *, config: PromptModelConfig, provider: ChatProvider) -> None:
        self.config = config
        self.provider = provider
        self._summary = TargetSummary(
            name=config.name,
            target_type=TargetType.PROMPT_MODEL,
            capabilities=TargetCapabilities(supports_reset=True, supports_trace=True),
        )
        self._history: list[ChatMessage] = []

    @property
    def summary(self) -> TargetSummary:
        return self._summary

    @property
    def history(self) -> tuple[ChatMessage, ...]:
        return tuple(self._history)

    async def reset(self) -> None:
        self._history = [ChatMessage(role="system", content=self.config.system_prompt)]

    async def send(self, message: str) -> TargetResponse:
        if not self._history:
            await self.reset()
        self._history.append(ChatMessage(role="user", content=message))
        completion = await self.provider.complete(
            messages=tuple(self._history),
            model=self.config.model,
            temperature=self.config.temperature,
        )
        self._history.append(ChatMessage(role="assistant", content=completion.text))
        return TargetResponse(
            text=completion.text,
            latency_ms=completion.latency_ms,
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens,
            trace={
                "provider": self.config.provider,
                "model": completion.model,
                "finish_reason": completion.finish_reason,
                "history_messages": len(self._history),
            },
        )
