"""HTTP schemas for deployment message identities."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

from echo_masque.persistence.discord_identity_models import (
    DeploymentMessageIdentityRecord,
)


class DeploymentMessageIdentityUpdate(BaseModel):
    mode: Literal["bot", "webhook"] = "webhook"
    display_name: str = Field(min_length=1, max_length=80)
    avatar_url: HttpUrl | None = None


class DeploymentMessageIdentityView(BaseModel):
    deployment_id: str
    mode: Literal["bot", "webhook"]
    display_name: str
    avatar_url: str
    webhook_status: Literal[
        "pending",
        "active",
        "error",
        "not_required",
    ]
    last_error: str
    updated_at: datetime

    @classmethod
    def from_record(
        cls,
        record: DeploymentMessageIdentityRecord,
    ) -> "DeploymentMessageIdentityView":
        return cls(
            deployment_id=record.deployment_id,
            mode=record.mode,  # type: ignore[arg-type]
            display_name=record.display_name,
            avatar_url=record.avatar_url,
            webhook_status=record.webhook_status,  # type: ignore[arg-type]
            last_error=record.last_error,
            updated_at=record.updated_at,
        )
