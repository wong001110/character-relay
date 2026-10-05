"""Existing-session Web Room client and a separate trusted Discord transport surface."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import AsyncIterator
from datetime import datetime
from io import BytesIO
from typing import Annotated, Any, Literal, cast
from urllib.parse import quote, unquote

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.responses import Response, StreamingResponse

from echo_masque.agent_reading import (
    AgentReadingComplete,
    AgentReadingGap,
    AgentReadingStart,
    AgentReadingStatus,
)
from echo_masque.api.dependencies import AuthContextDependency, CurrentUserDependency
from echo_masque.api.routes.connectors import _authorize_connector
from echo_masque.persistence.agent_reading_repository import AgentReadingRepository
from echo_masque.persistence.web_room_repository import WebRoomRepository
from echo_masque.web_room_message import message_summary as _message_summary
from echo_masque.web_room_message import web_message_view
from echo_masque.web_rooms import (
    MembershipInput,
    ProfileInput,
    ProfileUpdate,
    ProfileView,
    WebAttachmentView,
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


_MAX_WEB_ATTACHMENT_BYTES = 8 * 1024 * 1024
_WEB_IMAGE_TYPES = {
    "PNG": ("image/png", ".png"),
    "JPEG": ("image/jpeg", ".jpg"),
    "WEBP": ("image/webp", ".webp"),
    "GIF": ("image/gif", ".gif"),
}
_WEB_FILE_TYPES: dict[str, tuple[str, frozenset[str]]] = {
    ".txt": ("text/plain", frozenset({"text/plain"})),
    ".md": ("text/markdown", frozenset({"text/markdown", "text/plain"})),
    ".csv": ("text/csv", frozenset({"text/csv", "text/plain", "application/vnd.ms-excel"})),
    ".log": ("text/plain", frozenset({"text/plain"})),
    ".json": ("application/json", frozenset({"application/json", "text/json", "text/plain"})),
    ".xml": ("application/xml", frozenset({"application/xml", "text/xml", "text/plain"})),
    ".yaml": (
        "application/yaml",
        frozenset({"application/yaml", "application/x-yaml", "text/yaml", "text/plain"}),
    ),
    ".yml": (
        "application/yaml",
        frozenset({"application/yaml", "application/x-yaml", "text/yaml", "text/plain"}),
    ),
    ".pdf": ("application/pdf", frozenset({"application/pdf"})),
    ".rtf": ("application/rtf", frozenset({"application/rtf", "text/rtf"})),
    ".doc": ("application/msword", frozenset({"application/msword"})),
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        frozenset({"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}),
    ),
    ".xls": ("application/vnd.ms-excel", frozenset({"application/vnd.ms-excel"})),
    ".xlsx": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        frozenset({"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}),
    ),
    ".ppt": ("application/vnd.ms-powerpoint", frozenset({"application/vnd.ms-powerpoint"})),
    ".pptx": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        frozenset({"application/vnd.openxmlformats-officedocument.presentationml.presentation"}),
    ),
    ".zip": (
        "application/zip",
        frozenset({"application/zip", "application/x-zip-compressed"}),
    ),
    ".gz": ("application/gzip", frozenset({"application/gzip", "application/x-gzip"})),
    ".tar": ("application/x-tar", frozenset({"application/x-tar"})),
    ".7z": ("application/x-7z-compressed", frozenset({"application/x-7z-compressed"})),
    ".rar": (
        "application/vnd.rar",
        frozenset({"application/vnd.rar", "application/x-rar-compressed"}),
    ),
    ".mp3": ("audio/mpeg", frozenset({"audio/mpeg", "audio/mp3"})),
    ".wav": ("audio/wav", frozenset({"audio/wav", "audio/x-wav"})),
    ".ogg": ("audio/ogg", frozenset({"audio/ogg", "application/ogg"})),
    ".opus": ("audio/ogg", frozenset({"audio/ogg", "audio/opus", "application/ogg"})),
    ".m4a": ("audio/mp4", frozenset({"audio/mp4", "audio/x-m4a"})),
    ".flac": ("audio/flac", frozenset({"audio/flac", "audio/x-flac"})),
    ".mp4": ("video/mp4", frozenset({"video/mp4"})),
    ".webm": ("video/webm", frozenset({"video/webm"})),
    ".mov": ("video/quicktime", frozenset({"video/quicktime"})),
}


def _clean_web_filename(raw_filename: str) -> str:
    filename = unquote(raw_filename).replace("\\", "/").rsplit("/", 1)[-1]
    filename = "".join(
        char for char in filename if char.isprintable() and char not in "\r\n"
    ).strip()
    return filename[:220] or "attachment"


async def _read_bounded_attachment(request: Request) -> bytes:
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > _MAX_WEB_ATTACHMENT_BYTES:
        raise HTTPException(status_code=413, detail="attachment_too_large")
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > _MAX_WEB_ATTACHMENT_BYTES:
            raise HTTPException(status_code=413, detail="attachment_too_large")
        chunks.append(chunk)
    content = b"".join(chunks)
    if not content:
        raise HTTPException(status_code=422, detail="empty_attachment")
    return content


def _validated_web_attachment(
    content: bytes,
    raw_filename: str,
    declared_mime: str,
) -> tuple[str, str]:
    filename = _clean_web_filename(raw_filename)
    try:
        with Image.open(BytesIO(content)) as image:
            image_format = (image.format or "").upper()
            image_type = _WEB_IMAGE_TYPES.get(image_format)
            if image_type is None:
                raise HTTPException(status_code=422, detail="unsupported_attachment_type")
            width, height = image.size
            if width < 1 or height < 1 or width * height > 40_000_000:
                raise ValueError("image_dimensions_invalid")
            image.verify()
    except UnidentifiedImageError:
        image_type = None
    except HTTPException:
        raise
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise HTTPException(status_code=422, detail="invalid_image") from exc

    if image_type is not None:
        mime_type, extension = image_type
        stem = filename.rsplit(".", 1)[0].strip() if "." in filename else filename
        stem = stem[:180] or "image"
        return mime_type, f"{stem}{extension}"

    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    file_type = _WEB_FILE_TYPES.get(suffix)
    if file_type is None:
        raise HTTPException(status_code=422, detail="unsupported_attachment_type")
    mime_type, accepted_mimes = file_type
    declared = declared_mime.partition(";")[0].strip().lower()
    if declared and declared != "application/octet-stream" and declared not in accepted_mimes:
        raise HTTPException(status_code=422, detail="attachment_mime_mismatch")
    return mime_type, filename


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


def _snapshot(
    repo: WebRoomRepository, room_id: str, user_id: str, *, include_outbox: bool = True
) -> dict[str, object]:
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
            raw_web_count = web_reaction.get("web_count", 0)
            current["web_count"] = raw_web_count if isinstance(raw_web_count, int) else 0
            current["mine"] = bool(web_reaction["mine"])
            current["mine_profile_ids"] = web_reaction.get("mine_profile_ids", [])
        for reaction_view in reactions.values():
            reaction_view["count"] = int(reaction_view["discord_count"]) + int(
                reaction_view["web_count"]
            )

        messages.append(
            web_message_view(
                message,
                reply_id=reply_id,
                reply_preview=reply_preview,
                reactions=list(reactions.values()),
            )
        )
    result: dict[str, object] = {
        "room_id": room.id,
        "history_limit": 64,
        "source_revision": repo.sources.revision(room_scope(room)),
        "messages": messages,
    }
    if include_outbox:
        result["outbox"] = [item.model_dump(mode="json") for item in repo.outbox(room_id, user_id)]
    return result


@router.get("/rooms/{room_id}/messages")
async def messages(
    room_id: str, request: Request, user: CurrentUserDependency
) -> dict[str, object]:
    return await asyncio.to_thread(_snapshot, _repo(request), room_id, user.id)


def agent_reading_no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.get(
    "/rooms/{room_id}/agent-reading/{profile_id}",
    response_model=AgentReadingStatus,
    dependencies=[Depends(agent_reading_no_store)],
)
def agent_reading_status(
    room_id: str,
    profile_id: str,
    request: Request,
    context: AuthContextDependency,
) -> AgentReadingStatus:
    assert context.session_id is not None  # real_session dependency
    return AgentReadingRepository(_repo(request)).status(
        room_id,
        context.user.id,
        profile_id,
        session_id=context.session_id,
    )


@router.post(
    "/rooms/{room_id}/agent-reading/{profile_id}/gap",
    response_model=AgentReadingStatus,
    dependencies=[Depends(agent_reading_no_store)],
)
def agent_reading_gap(
    room_id: str,
    profile_id: str,
    payload: AgentReadingGap,
    request: Request,
    context: AuthContextDependency,
) -> AgentReadingStatus:
    assert context.session_id is not None
    return AgentReadingRepository(_repo(request)).gap(
        room_id,
        context.user.id,
        profile_id,
        session_id=context.session_id,
        event_id=payload.event_id,
    )


@router.post(
    "/rooms/{room_id}/agent-reading/{profile_id}/batch",
    response_model=AgentReadingStatus,
    dependencies=[Depends(agent_reading_no_store)],
)
def agent_reading_batch(
    room_id: str,
    profile_id: str,
    payload: AgentReadingStart,
    request: Request,
    context: AuthContextDependency,
) -> AgentReadingStatus:
    assert context.session_id is not None
    return AgentReadingRepository(_repo(request)).batch(
        room_id,
        context.user.id,
        profile_id,
        session_id=context.session_id,
    )


@router.post(
    "/rooms/{room_id}/agent-reading/{profile_id}/complete",
    response_model=AgentReadingStatus,
    dependencies=[Depends(agent_reading_no_store)],
)
def agent_reading_complete(
    room_id: str,
    profile_id: str,
    payload: AgentReadingComplete,
    request: Request,
    context: AuthContextDependency,
) -> AgentReadingStatus:
    assert context.session_id is not None
    return AgentReadingRepository(_repo(request)).complete(
        room_id,
        context.user.id,
        profile_id,
        session_id=context.session_id,
        batch_id=payload.batch_id,
    )


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


@router.post("/rooms/{room_id}/attachments", response_model=WebAttachmentView, status_code=201)
async def upload_attachment(
    room_id: str, request: Request, user: CurrentUserDependency
) -> WebAttachmentView:
    content = await _read_bounded_attachment(request)
    mime_type, filename = _validated_web_attachment(
        content,
        request.headers.get("x-character-relay-filename", ""),
        request.headers.get("content-type", ""),
    )
    return await asyncio.to_thread(
        _repo(request).create_attachment,
        user.id,
        room_id,
        filename=filename,
        mime_type=mime_type,
        content=content,
    )


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
                except Exception:
                    # A malformed historical source must not create an endless EventSource
                    # reconnect loop. Preserve the client's last snapshot and stop cleanly.
                    yield 'event: unavailable\ndata: {"reason":"snapshot_unavailable"}\n\n'
                    break
                data = json.dumps(snapshot, ensure_ascii=False)
                digest = hashlib.sha256(data.encode()).hexdigest()
                if digest != previous:
                    # Client replaces its bounded view; the ID is neither
                    # authorization nor a raw transcript.
                    yield f"id: {digest}\nevent: snapshot\ndata: {data}\n\n"
                    previous = digest
                else:
                    yield "event: heartbeat\ndata: {}\n\n"
                await asyncio.sleep(1)
            else:
                if not await request.is_disconnected():
                    yield "event: rollover\ndata: {}\n\n"
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


@connector_router.get("/outbox/{message_id}/attachments/{attachment_id}")
def fetch_attachment(
    message_id: str,
    attachment_id: str,
    connection_id: str,
    claim_nonce: str,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    _authorize_connector(request, authorization)
    artifact = _repo(request).attachment_for_claim(
        connection_id, message_id, claim_nonce, attachment_id
    )
    return Response(
        content=artifact.content,
        media_type=artifact.mime_type,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": (
                "attachment; filename*=UTF-8''" + quote(artifact.filename, safe="")
            ),
        },
    )


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
