"""Existing-session Web Room client and a separate trusted Discord transport surface."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.responses import StreamingResponse

from echo_masque.api.dependencies import AuthContextDependency, CurrentUserDependency
from echo_masque.api.routes.connectors import _authorize_connector
from echo_masque.persistence.web_room_repository import WebRoomRepository
from echo_masque.web_rooms import (
    MembershipInput,
    ProfileInput,
    ProfileUpdate,
    ProfileView,
    WebDeliveryView,
    WebExpressionView,
    WebReactionInput,
    WebRoomDelivery,
    WebRoomError,
    WebRoomInput,
    WebRoomView,
    WebSend,
    room_scope,
)


def real_session(context: AuthContextDependency) -> None:
    if context.session_id is None:
        raise HTTPException(status_code=401, detail="Authenticated session required.")


router = APIRouter(prefix="/api/web-chat", tags=["Web rooms"], dependencies=[Depends(real_session)])
connector_router = APIRouter(prefix="/api/connectors/discord/web-chat", tags=["Web room transport"])


def _repo(request: Request) -> WebRoomRepository:
    return cast(WebRoomRepository, request.app.state.web_room_repository)


@router.get("/profiles", response_model=list[ProfileView])
def profiles(request: Request, user: CurrentUserDependency) -> list[ProfileView]:
    return _repo(request).profiles(user.id)


@router.post("/profiles", response_model=ProfileView, status_code=201)
def create_profile(
    payload: ProfileInput, request: Request, user: CurrentUserDependency
) -> ProfileView:
    return _repo(request).save_profile(user.id, payload)


@router.patch("/profiles/{profile_id}", response_model=ProfileView)
def update_profile(
    profile_id: str, payload: ProfileUpdate, request: Request, user: CurrentUserDependency
) -> ProfileView:
    return _repo(request).save_profile(
        user.id,
        ProfileInput.model_validate(payload.model_dump(exclude={"expected_version"})),
        profile_id,
        payload.expected_version,
    )


@router.get("/rooms/{room_id}/expressions", response_model=list[WebExpressionView])
def expressions(
    room_id: str, request: Request, user: CurrentUserDependency
) -> list[WebExpressionView]:
    return _repo(request).expressions(room_id, user.id)


@router.get("/rooms", response_model=list[WebRoomView])
def rooms(request: Request, user: CurrentUserDependency) -> list[WebRoomView]:
    return _repo(request).list_rooms(user.id)


@router.post("/rooms", status_code=201)
def publish_room(
    payload: WebRoomInput, request: Request, user: CurrentUserDependency
) -> dict[str, str]:
    return {"id": _repo(request).publish(user.id, payload)}


class RoomEnabled(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


@router.patch("/rooms/{room_id}", status_code=204)
def configure_room(
    room_id: str, payload: RoomEnabled, request: Request, user: CurrentUserDependency
) -> None:
    _repo(request).configure(room_id, user.id, payload.enabled)


@router.get("/rooms/{room_id}/members")
def members(room_id: str, request: Request, user: CurrentUserDependency) -> list[dict[str, object]]:
    return _repo(request).members(room_id, user.id)


@router.put("/rooms/{room_id}/members", status_code=204)
def grant_member(
    room_id: str, payload: MembershipInput, request: Request, user: CurrentUserDependency
) -> None:
    _repo(request).member(room_id, user.id, payload.user_id, payload.can_post)


@router.delete("/rooms/{room_id}/members/{user_id}", status_code=204)
def revoke_member(
    room_id: str, user_id: str, request: Request, user: CurrentUserDependency
) -> None:
    _repo(request).member(room_id, user.id, user_id, None)


def _message_summary(message: object) -> str:
    text = str(getattr(message, "text", "") or "").strip().replace("\n", " ")
    if text:
        return text[:180] + ("…" if len(text) > 180 else "")
    if getattr(message, "stickers", ()):
        return "[Sticker]"
    if getattr(message, "attachments", ()):
        return "[Attachment]"
    if getattr(message, "custom_emojis", ()):
        return "[Emoji]"
    return "[No text content]"


def _snapshot(repo: WebRoomRepository, room_id: str, user_id: str) -> dict[str, object]:
    room = repo.require(room_id, user_id, fresh=True)
    sources = sorted(
        repo.sources.recent(room_scope(room), limit=64),
        key=lambda item: (
            item.message.created_at.isoformat() if item.message.created_at else "",
            item.message.message_id,
        ),
    )
    by_id = {item.message.message_id: item for item in sources}
    web_reactions = repo.reactions(room_id, user_id, list(by_id))
    messages: list[dict[str, object]] = []
    for item in sources:
        message = item.message
        reply_id = message.reply_to_message_id or message.response_to_message_id
        reply_source = by_id.get(reply_id) if reply_id else None
        if reply_id and reply_source is None:
            reply_source = repo.sources.get(room_scope(room), reply_id)
        reply_preview: dict[str, object] | None = None
        if reply_id:
            available = bool(
                reply_source
                and not reply_source.message.deleted
                and reply_source.message.content_available
            )
            reply_preview = {
                "message_id": reply_id,
                "available": available,
                "in_snapshot": reply_id in by_id,
                "display_name": (
                    reply_source.message.author_display_name if available and reply_source else ""
                ),
                "summary": (
                    _message_summary(reply_source.message) if available and reply_source else ""
                ),
            }

        reactions: dict[str, dict[str, Any]] = {}
        for source_reaction in message.reactions:
            reactions[source_reaction.key] = {
                "key": source_reaction.key,
                "resource_id": source_reaction.resource_id,
                "name": source_reaction.name,
                "animated": source_reaction.animated,
                "asset_url": source_reaction.asset_url,
                "discord_count": source_reaction.count,
                "web_count": 0,
                "mine": False,
                "mine_profile_ids": [],
            }
        for web_reaction in web_reactions.get(message.message_id, []):
            key = str(web_reaction["key"])
            current = reactions.setdefault(
                key,
                {
                    "key": key,
                    "resource_id": web_reaction["resource_id"],
                    "name": web_reaction["name"],
                    "animated": web_reaction["animated"],
                    "asset_url": web_reaction["asset_url"],
                    "discord_count": 0,
                    "web_count": 0,
                    "mine": False,
                    "mine_profile_ids": [],
                },
            )
            current["web_count"] = int(web_reaction["web_count"])
            current["mine"] = bool(web_reaction["mine"])
            current["mine_profile_ids"] = web_reaction.get("mine_profile_ids", [])
        for reaction_view in reactions.values():
            reaction_view["count"] = int(reaction_view["discord_count"]) + int(
                reaction_view["web_count"]
            )

        messages.append(
            {
                "id": message.message_id,
                "author_id": message.author_id,
                "display_name": message.author_display_name,
                "avatar_url": message.author_avatar_url,
                "actor_type": "web_participant"
                if message.author_external_id
                else "character"
                if message.author_deployment_id
                else "bot"
                if message.author_is_bot
                else "discord_user",
                "text": message.text,
                "deleted": message.deleted,
                "content_available": message.content_available,
                "created_at": message.created_at.isoformat() if message.created_at else None,
                "edited_at": message.edited_at.isoformat() if message.edited_at else None,
                "reply_to_message_id": reply_id,
                "reply_preview": reply_preview,
                "attachments": [entry.model_dump(mode="json") for entry in message.attachments],
                "custom_emojis": [entry.model_dump(mode="json") for entry in message.custom_emojis],
                "stickers": [entry.model_dump(mode="json") for entry in message.stickers],
                "mentions": [entry.model_dump(mode="json") for entry in message.mentions],
                "embeds": [entry.model_dump(mode="json") for entry in message.embeds],
                "poll": message.poll.model_dump(mode="json") if message.poll is not None else None,
                "reactions": list(reactions.values()),
                "pinned": message.pinned,
            }
        )
    return {
        "room_id": room.id,
        "history_limit": 64,
        "messages": messages,
        "outbox": [item.model_dump(mode="json") for item in repo.outbox(room_id, user_id)],
    }


@router.get("/rooms/{room_id}/messages")
async def messages(
    room_id: str, request: Request, user: CurrentUserDependency
) -> dict[str, object]:
    return await asyncio.to_thread(_snapshot, _repo(request), room_id, user.id)


@router.put("/rooms/{room_id}/messages/{message_id}/reactions", status_code=204)
def add_reaction(
    room_id: str,
    message_id: str,
    payload: WebReactionInput,
    request: Request,
    user: CurrentUserDependency,
) -> None:
    _repo(request).set_reaction(user.id, room_id, message_id, payload, enabled=True)


@router.delete("/rooms/{room_id}/messages/{message_id}/reactions", status_code=204)
def remove_reaction(
    room_id: str,
    message_id: str,
    payload: WebReactionInput,
    request: Request,
    user: CurrentUserDependency,
) -> None:
    _repo(request).set_reaction(user.id, room_id, message_id, payload, enabled=False)


@router.post("/rooms/{room_id}/messages", response_model=WebDeliveryView, status_code=202)
def send_message(
    room_id: str, payload: WebSend, request: Request, user: CurrentUserDependency
) -> WebDeliveryView:
    return _repo(request).enqueue(user.id, room_id, payload)


@router.get("/rooms/{room_id}/events")
async def events(
    room_id: str, request: Request, context: AuthContextDependency
) -> StreamingResponse:
    repo = _repo(request)
    await asyncio.to_thread(repo.require, room_id, context.user.id, fresh=True)
    leases: dict[str, tuple[str, float]] = request.app.state.web_room_streams
    user_id = context.user.id
    now = time.monotonic()
    for lease_id, (_, deadline) in tuple(leases.items()):
        if deadline <= now:
            leases.pop(lease_id, None)
    if sum(owner == user_id for owner, _ in leases.values()) >= 3 or len(leases) >= 128:
        raise HTTPException(status_code=429, detail="stream_capacity")
    # Per-worker leases expire even if a response generator never starts.
    from uuid import uuid4

    lease_id = uuid4().hex
    leases[lease_id] = (user_id, now + 70)
    bearer = request.headers.get("authorization", "").partition(" ")[2]
    token = bearer or request.cookies.get(request.app.state.settings.auth_cookie_name, "")

    async def stream() -> AsyncIterator[str]:
        previous = ""
        started = time.monotonic()
        try:
            while time.monotonic() - started < 60 and not await request.is_disconnected():
                resolved = await asyncio.to_thread(request.app.state.auth_service.resolve, token)
                if resolved is None or resolved.user.id != user_id:
                    yield 'event: revoked\ndata: {"reason":"session_revoked"}\n\n'
                    break
                try:
                    snapshot = await asyncio.to_thread(_snapshot, repo, room_id, user_id)
                except WebRoomError as exc:
                    yield "event: revoked\ndata: " + json.dumps({"reason": str(exc)}) + "\n\n"
                    break
                data = json.dumps(snapshot, ensure_ascii=False)
                digest = hashlib.sha256(data.encode()).hexdigest()
                if digest != previous:
                    # Client replaces its bounded view; the ID is neither
                    # authorization nor a raw transcript.
                    yield f"id: {digest}\nevent: snapshot\ndata: {data}\n\n"
                    previous = digest
                else:
                    yield ": keepalive\n\n"
                await asyncio.sleep(1)
        finally:
            leases.pop(lease_id, None)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        },
    )


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connection_id: str = Field(min_length=1, max_length=64)
    claim_nonce: str = Field(min_length=16, max_length=64)


class WebhookRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connection_id: str = Field(min_length=1, max_length=64)
    webhook_id: str = Field(min_length=1, max_length=200)


class DeliveryAck(Claim):
    status: Literal["delivered", "failed", "uncertain", "cancelled"]
    message_id: str = Field(default="", max_length=200)
    created_at: datetime | None = None
    webhook_id: str = Field(default="", max_length=200)
    reason: str = Field(default="", max_length=80)

    @field_validator("created_at")
    @classmethod
    def zoned(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("Receipt timestamp requires a timezone.")
        return value


class DispatchAck(Claim):
    outcome: Literal["processed", "failed"] = "processed"


@connector_router.get("/rooms")
def transport_rooms(
    connection_id: str, request: Request, authorization: Annotated[str | None, Header()] = None
) -> list[dict[str, str]]:
    _authorize_connector(request, authorization)
    return [
        {
            "id": room.id,
            "name": room.name,
            "guild_id": room.guild_id,
            "channel_id": room.channel_id,
            "thread_id": room.thread_id,
            "webhook_id": room.webhook_id,
        }
        for room in _repo(request).connector_rooms(connection_id)
    ]


@connector_router.put("/rooms/{room_id}/webhook", status_code=204)
def register_webhook(
    room_id: str,
    payload: WebhookRegistration,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    _authorize_connector(request, authorization)
    _repo(request).register_webhook(payload.connection_id, room_id, payload.webhook_id)


@connector_router.post("/rooms/{room_id}/claim")
def claim(
    room_id: str,
    payload: Claim,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> WebRoomDelivery | None:
    _authorize_connector(request, authorization)
    return _repo(request).claim(payload.connection_id, room_id, payload.claim_nonce)


@connector_router.post("/outbox/{message_id}/preflight")
def preflight(
    message_id: str,
    payload: Claim,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, bool]:
    _authorize_connector(request, authorization)
    return {
        "allowed": _repo(request).preflight(payload.connection_id, message_id, payload.claim_nonce)
    }


@connector_router.post("/outbox/{message_id}/ack", response_model=WebDeliveryView)
def acknowledge(
    message_id: str,
    payload: DeliveryAck,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> WebDeliveryView:
    _authorize_connector(request, authorization)
    return _repo(request).acknowledge(
        payload.connection_id,
        message_id,
        payload.claim_nonce,
        status=payload.status,
        message_id=payload.message_id,
        created_at=payload.created_at,
        webhook_id=payload.webhook_id,
        reason=payload.reason,
    )


@connector_router.get("/source/{message_id}")
def source_delivery(
    message_id: str,
    connection_id: str,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> WebRoomDelivery | None:
    _authorize_connector(request, authorization)
    return _repo(request).source_delivery(connection_id, message_id)


@connector_router.get("/dispatch")
def pending_dispatch(
    connection_id: str, request: Request, authorization: Annotated[str | None, Header()] = None
) -> list[WebRoomDelivery]:
    _authorize_connector(request, authorization)
    return _repo(request).pending_dispatch(connection_id)


@connector_router.post("/outbox/{message_id}/dispatched", status_code=204)
def finish_dispatch(
    message_id: str,
    payload: DispatchAck,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    _authorize_connector(request, authorization)
    _repo(request).finish_dispatch(
        payload.connection_id, message_id, payload.claim_nonce, payload.outcome
    )
