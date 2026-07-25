"""Core models shared by the API and future trial engine."""

from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class TargetType(StrEnum):
    """Supported target integration families."""

    PROMPT_MODEL = "prompt_model"
    HTTP_API = "http_api"
    TRANSCRIPT = "transcript"


class TrialStatus(StrEnum):
    """Lifecycle states for a trial run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TestKind(StrEnum):
    """Initial behavior dimensions planned for the MVP."""

    IDENTITY_INTEGRITY = "identity_integrity"
    FALSE_MEMORY = "false_memory"
    PROMPT_INJECTION = "prompt_injection"
    LONG_CONVERSATION_DRIFT = "long_conversation_drift"


class TargetCapabilities(BaseModel):
    """Observable features exposed by a target integration."""

    model_config = ConfigDict(frozen=True)

    supports_reset: bool = False
    supports_trace: bool = False
    supports_tools: bool = False


class TargetSummary(BaseModel):
    """Secret-free target metadata safe to display and serialize."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=120)
    target_type: TargetType
    capabilities: TargetCapabilities = Field(default_factory=TargetCapabilities)


class HealthResponse(BaseModel):
    """Health endpoint response contract."""

    name: str
    version: str
    status: str = "ok"
    environment: str
