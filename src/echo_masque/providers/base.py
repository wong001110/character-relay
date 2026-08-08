"""Model-provider contracts."""

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class ChatToolFunction(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    description: str = ""
    parameters: dict[str, object] = Field(default_factory=dict)


class ChatToolDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)
    type: Literal["function"] = "function"
    function: ChatToolFunction


class ChatToolFunctionCall(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    arguments: str


class ChatToolCall(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    type: Literal["function"] = "function"
    function: ChatToolFunctionCall


class ChatMessage(BaseModel):
    model_config = ConfigDict(frozen=True)
    role: str
    content: str = ""
    tool_call_id: str | None = None
    tool_calls: tuple[ChatToolCall, ...] = ()


class ProviderCompletion(BaseModel):
    model_config = ConfigDict(frozen=True)
    text: str
    model: str
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str | None = None
    tool_calls: tuple[ChatToolCall, ...] = ()


class ChatProvider(Protocol):
    async def complete(
        self,
        *,
        messages: tuple[ChatMessage, ...],
        model: str,
        temperature: float,
    ) -> ProviderCompletion: ...


class ToolCapableChatProvider(Protocol):
    async def complete_with_tools(
        self,
        *,
        messages: tuple[ChatMessage, ...],
        model: str,
        temperature: float,
        tools: tuple[ChatToolDefinition, ...],
    ) -> ProviderCompletion: ...
