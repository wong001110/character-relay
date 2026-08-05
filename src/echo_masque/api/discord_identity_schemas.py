"""HTTP schemas for deployment message identities."""

from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel, Field, HttpUrl

from echo_masque.persistence.discord_identity_models import (
    DeploymentMessageIdentityRecord,
)

IdentityMode = Literal["bot", "webhook"]
WebhookStatus = Literal["pending", "active", "error", "not_required"]


class DeploymentMessageIdentityUpdate(BaseModel):
    mode: IdentityMode = "webhook"
    display_name: str = Field(min_length=1, max_length=80)
    avatar_url: HttpUrl | None = None
    address_aliases: list[str] = Field(default_factory=list, max_length=20)


class DeploymentMessageIdentityView(BaseModel):
    deployment_id: str
    mode: IdentityMode
    display_name: str
    avatar_url: str
    address_aliases: list[str] = Field(default_factory=list)
    webhook_status: WebhookStatus
    last_error: str
    updated_at: datetime

    @classmethod
    def from_record(
        cls,
        record: DeploymentMessageIdentityRecord,
        *,
        address_aliases: list[str] | None = None,
    ) -> "DeploymentMessageIdentityView":
        return cls(
            deployment_id=record.deployment_id,
            mode=cast(IdentityMode, record.mode),
            display_name=record.display_name,
            avatar_url=record.avatar_url,
            address_aliases=address_aliases or [],
            webhook_status=cast(WebhookStatus, record.webhook_status),
            last_error=record.last_error,
            updated_at=record.updated_at,
        )
