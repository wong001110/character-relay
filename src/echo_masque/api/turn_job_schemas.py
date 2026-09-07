"""Public status and progress contracts for durable Discord turn jobs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from echo_masque.api.connector_schemas import DiscordConnectorReplyView
from echo_masque.api.social_turn_schemas import DiscordSocialTurnStepView

TurnJobStatus = Literal[
    "queued", "running", "succeeded", "failed", "timed_out", "stopped", "cancelled"
]


class TurnProgressEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int
    nonce: str = ""
    text: str = Field(max_length=500)


class TurnJobView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    status: TurnJobStatus
    progress: list[TurnProgressEvent] = Field(default_factory=list, max_length=3)
    reply: DiscordConnectorReplyView | None = None
    social_step: DiscordSocialTurnStepView | None = None
    error_code: str | None = None


class TurnProgressClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nonce: str = Field(min_length=1, max_length=64)


class TurnProgressClaimView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event: TurnProgressEvent | None = None


class TurnJobCancelRequest(BaseModel):
    """A Connector-authenticated, exact source-event cancellation request."""

    model_config = ConfigDict(extra="forbid")
    deployment_id: str = Field(min_length=1, max_length=64)
    guild_id: str = Field(min_length=1, max_length=200)
    channel_id: str = Field(min_length=1, max_length=200)
    thread_id: str = Field(default="", max_length=200)
    category_id: str = Field(default="", max_length=200)
    source_message_id: str = Field(min_length=1, max_length=200)
    source_author_id: str = Field(min_length=1, max_length=200)
    reason: Literal["user_cancelled", "user_replaced"]


class TurnJobRecoveryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    kind: Literal["message", "social"]
    guild_id: str
    channel_id: str
    thread_id: str
    source_message_id: str
    deployment_id: str
    status: TurnJobStatus


class TurnJobRecoveryView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[TurnJobRecoveryItem] = Field(default_factory=list, max_length=100)
    next_cursor: str | None = None
