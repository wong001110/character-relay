"""HTTP schemas for Tool Calling catalog and deployment assignments."""

from typing import Literal

from pydantic import BaseModel, Field

from echo_masque.tool_runtime import ToolCatalogItem


class DeploymentToolProfileUpdate(BaseModel):
    enabled_tools: list[str] = Field(default_factory=list, max_length=50)


class DeploymentToolProfileView(BaseModel):
    deployment_id: str
    enabled_tools: list[str]


class ToolCatalogView(BaseModel):
    items: list[ToolCatalogItem]


class ServerRuntimeTimezoneUpdate(BaseModel):
    timezone: str = Field(min_length=1, max_length=120)


class ServerRuntimeTimezoneView(BaseModel):
    profile_id: str
    timezone: str


class ToolRuntimeTestDeploymentView(BaseModel):
    deployment_id: str
    owner_id: str
    character_card_id: str
    character_name: str
    platform: str
    connection_id: str
    guild_id: str
    channel_id: str
    channel_name: str
    thread_id: str
    thread_name: str
    timezone: str
    enabled_tools: list[str]


class ToolRuntimeTestExecute(BaseModel):
    deployment_id: str = Field(min_length=1, max_length=64)
    tool_id: str = Field(min_length=1, max_length=120)
    arguments: dict[str, object] = Field(default_factory=dict, max_length=100)
    guild_id: str = Field(default="", max_length=200)
    channel_id: str = Field(default="", max_length=200)
    thread_id: str = Field(default="", max_length=200)
    message_id: str = Field(default="", max_length=200)
    initiator_user_id: str = Field(default="", max_length=200)
    trigger_text: str = Field(default="Super Admin Tool Calling test", max_length=1000)
    confirm_side_effect: bool = False


class ToolRuntimeTestResult(BaseModel):
    deployment_id: str
    tool_id: str
    provider_function_name: str
    side_effect: bool
    status: Literal["completed", "failed", "rejected"]
    duration_ms: int
    error: str
    timezone: str
    result: object | None = None
    raw_content: str
