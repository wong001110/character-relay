"""Connector contracts for Phase 4 Social Turn continuation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from echo_masque.api.connector_schemas import (
    DiscordConnectorReplyView,
    DiscordInboundMessage,
)

SocialTurnOrigin = Literal["selected", "invite", "mention"]


class DiscordSocialPendingTurn(BaseModel):
    """One privacy-safe participant cursor entry carried by the Connector."""

    model_config = ConfigDict(extra="forbid")

    deployment_id: str = Field(min_length=1, max_length=64)
    origin: SocialTurnOrigin = "selected"
    depth: int = Field(default=0, ge=0, le=12)
    source_deployment_id: str = Field(default="", max_length=64)


class DiscordSocialTurnCursor(BaseModel):
    """Stateless continuation cursor; raw Discord content stays outside this object."""

    model_config = ConfigDict(extra="forbid")

    pending_turns: list[DiscordSocialPendingTurn] = Field(default_factory=list, max_length=30)
    completed_deployment_ids: list[str] = Field(default_factory=list, max_length=30)
    continuation_budget_remaining: int = Field(default=0, ge=0, le=30)
    max_depth: int = Field(default=4, ge=1, le=12)
    step_index: int = Field(default=0, ge=0, le=60)


class DiscordSocialTurnStepRequest(BaseModel):
    """Run one participant step, then return control to the Discord transport."""

    model_config = ConfigDict(extra="forbid")

    payload: DiscordInboundMessage
    initial_deployment_ids: list[str] = Field(min_length=1, max_length=3)
    available_deployment_ids: list[str] = Field(min_length=1, max_length=30)
    continuation_budget: int = Field(default=8, ge=0, le=30)
    max_depth: int = Field(default=4, ge=1, le=12)
    cursor: DiscordSocialTurnCursor | None = None


class DiscordSocialTurnStepView(BaseModel):
    """One generated platform command plus the next orchestration cursor."""

    model_config = ConfigDict(extra="forbid")

    reply: DiscordConnectorReplyView
    cursor: DiscordSocialTurnCursor
    current_deployment_id: str
    next_turn: DiscordSocialPendingTurn | None = None
    done: bool = False
    stop_reason: str = ""
    invite_candidate_deployment_id: str = ""
    mentioned_character_deployment_ids: list[str] = Field(default_factory=list, max_length=20)


__all__ = [
    "DiscordSocialPendingTurn",
    "DiscordSocialTurnCursor",
    "DiscordSocialTurnStepRequest",
    "DiscordSocialTurnStepView",
    "SocialTurnOrigin",
]
