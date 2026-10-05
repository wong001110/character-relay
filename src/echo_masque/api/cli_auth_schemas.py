"""Public P0 schemas; credentials occur only in private device/token responses."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class DeviceAuthorizationView(BaseModel):
    device_code: str = Field(repr=False, json_schema_extra={"writeOnly": True})
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


class CliTokenView(BaseModel):
    access_token: str = Field(repr=False, json_schema_extra={"writeOnly": True})
    token_type: Literal["Bearer"]
    expires_in: int
    scope: str


class CliAccountView(BaseModel):
    user_id: str
    display_name: str
    email: str


class CliBrowserContextView(BaseModel):
    csrf_token: str = Field(repr=False)
    account: CliAccountView


class CliRoomView(BaseModel):
    id: str
    name: str


class CliReviewView(BaseModel):
    client_id: str
    client_name: str
    account: CliAccountView
    rooms: list[CliRoomView]
    scopes: list[str]
    device_expires_at: str
    access_token_ttl_seconds: int


class CliGrantView(BaseModel):
    grant_id: str
    client_id: str
    client_name: str
    scopes: list[str]
    room_ids: list[str]
    approved_at: str
    expires_at: str
    revoked_at: str | None


class CliDecisionView(BaseModel):
    status: Literal["approved", "denied"]
    grant: CliGrantView | None = None


class CliGrantsView(BaseModel):
    grants: list[CliGrantView]


class CliIdentityView(CliGrantView):
    user_id: str
    display_name: str


class CliRoomsView(BaseModel):
    rooms: list[CliRoomView]


class CliSnapshotView(BaseModel):
    room_id: str
    history_limit: Literal[64]
    messages: list[dict[str, Any]] = Field(
        max_length=64,
        description="Web Room message fields, rich media and bounded reply previews; no outbox. "
        "See docs/developer/cli-readonly.md. Not a replay cursor or complete history.",
    )
