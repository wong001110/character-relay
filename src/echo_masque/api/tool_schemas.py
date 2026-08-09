"""HTTP schemas for Tool Calling catalog and deployment assignments."""

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
