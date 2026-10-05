"""Device approval and independently authenticated read-only CLI routes."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from collections.abc import AsyncIterator
from typing import Annotated, Literal, cast
from urllib.parse import parse_qs
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, StreamingResponse
from starlette.types import ASGIApp

from echo_masque.api.cli_auth_schemas import (
    CliBrowserContextView,
    CliDecisionView,
    CliGrantsView,
    CliIdentityView,
    CliReviewView,
    CliRoomsView,
    CliSnapshotView,
    CliTokenView,
    DeviceAuthorizationView,
)
from echo_masque.auth import AuthContext
from echo_masque.cli_auth import CliAuthError, CliAuthService, CliPrincipal, digest
from echo_masque.cli_auth_policy import allowed_cli_route, restricted_credential
from echo_masque.security_controls import QuotaExceeded
from echo_masque.web_rooms import WebRoomError

router = APIRouter(tags=["CLI read-only integration"])
NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}
CLI_STREAM_IO_TIMEOUT = 5.0
_bearer = HTTPBearer(
    auto_error=False,
    scheme_name="CliReadOnlyGrant",
    description="Short-lived device-approved restricted grant; never a login session.",
)


class CliCredentialBoundary(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, cookie_name: str) -> None:
        super().__init__(app)
        self.cookie_name = cookie_name

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        parts = request.headers.get("authorization", "").split(maxsplit=1)
        raw = parts[-1] if parts else ""
        cookie = request.cookies.get(self.cookie_name, "")
        if (restricted_credential(raw) or restricted_credential(cookie)) and not allowed_cli_route(
            request.method, request.url.path
        ):
            return JSONResponse(
                {"error": "restricted_credential"}, status_code=403, headers=NO_STORE
            )
        return await call_next(request)


def service(request: Request) -> CliAuthService:
    return cast(CliAuthService, request.app.state.cli_auth_service)


def limit(request: Request, category: str, identity: str, count: int) -> None:
    try:
        request.app.state.quota_service.consume_cli_request(category, digest(identity), count)
    except QuotaExceeded as exc:
        raise CliAuthError("rate_limit_exceeded", 429) from exc


def browser(request: Request) -> AuthContext:
    service(request).enabled()
    settings = request.app.state.settings
    # Only a real browser Cookie, never a CLI or ordinary Bearer, can approve/manage grants.
    token = request.cookies.get(settings.auth_cookie_name, "")
    context = request.app.state.auth_service.resolve(token) if token else None
    if context is None or context.session_id is None or context.user.id == "public-demo":
        raise CliAuthError("browser_login_required", 401)
    if request.headers.get("authorization"):
        raise CliAuthError("browser_login_required", 401)
    return cast(AuthContext, context)


def csrf(request: Request, context: AuthContext) -> str:
    token = request.cookies.get(request.app.state.settings.auth_cookie_name, "")
    return hmac.new(token.encode(), b"character-relay-cli-approval-v1", hashlib.sha256).hexdigest()


def browser_write(
    request: Request, context: Annotated[AuthContext, Depends(browser)]
) -> AuthContext:
    settings = request.app.state.settings
    origins = {settings.cli_auth_public_origin}
    if settings.environment != "production":
        origins.add(str(request.base_url).rstrip("/"))
    supplied = request.headers.get("x-csrf-token", "")
    if request.headers.get("origin") not in origins or not hmac.compare_digest(
        supplied, csrf(request, context)
    ):
        raise CliAuthError("csrf_rejected", 403)
    return context


def principal(
    request: Request, credential: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]
) -> CliPrincipal:
    if credential is None:
        raise CliAuthError("invalid_token", 401)
    actor = service(request).resolve(credential.credentials.strip())
    limit(request, "read", actor.user_id, request.app.state.settings.request_limit_per_minute)
    return actor


def require_scope(actor: CliPrincipal, scope: str, room_id: str | None = None) -> None:
    if scope not in actor.scopes:
        raise CliAuthError("insufficient_scope", 403)
    if room_id is not None and room_id not in actor.room_ids:
        raise CliAuthError("room_not_granted", 403)


class DeviceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_id: str = Field(min_length=1, max_length=80)
    scopes: list[str] = Field(min_length=1, max_length=3)
    room_ids: list[str] = Field(min_length=1, max_length=32)


class UserCodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_code: str = Field(min_length=1, max_length=32)


class DecisionRequest(UserCodeRequest):
    decision: Literal["approve", "deny"]


@router.post("/api/cli-auth/device-authorizations", response_model=DeviceAuthorizationView)
def device_authorization(
    payload: DeviceRequest, request: Request, response: Response
) -> dict[str, object]:
    service(request).enabled()
    limit(request, "device-global", "all", 1000)
    limit(request, "device", request.client.host if request.client else "unknown", 20)
    response.headers.update(NO_STORE)
    return service(request).create_device(payload.client_id, payload.scopes, payload.room_ids)


@router.post(
    "/api/cli-auth/token",
    response_model=CliTokenView,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/x-www-form-urlencoded": {
                    "schema": {
                        "type": "object",
                        "required": ["client_id", "device_code", "grant_type"],
                        "properties": {
                            "client_id": {"type": "string"},
                            "device_code": {"type": "string", "writeOnly": True},
                            "grant_type": {
                                "type": "string",
                                "enum": ["urn:ietf:params:oauth:grant-type:device_code"],
                            },
                        },
                    }
                }
            },
        }
    },
)
async def token(request: Request, response: Response) -> dict[str, object]:
    service(request).enabled()
    limit(request, "token", request.client.host if request.client else "unknown", 120)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 2048:
            raise CliAuthError("invalid_request")
    if request.headers.get("content-type", "").split(";")[0] != "application/x-www-form-urlencoded":
        raise CliAuthError("invalid_request")
    try:
        fields = parse_qs(body.decode("utf-8"), strict_parsing=True, max_num_fields=3)
    except (UnicodeError, ValueError):
        raise CliAuthError("invalid_request") from None
    if set(fields) != {"grant_type", "client_id", "device_code"} or any(
        len(value) != 1 for value in fields.values()
    ):
        raise CliAuthError("invalid_request")
    if fields["grant_type"][0] != "urn:ietf:params:oauth:grant-type:device_code":
        raise CliAuthError("unsupported_grant_type")
    response.headers.update(NO_STORE)
    return await asyncio.to_thread(
        service(request).exchange, fields["client_id"][0], fields["device_code"][0]
    )


def account(context: AuthContext) -> dict[str, str]:
    return {
        "user_id": context.user.id,
        "display_name": context.user.display_name,
        "email": context.user.email,
    }


@router.get("/api/cli-auth/browser-context", response_model=CliBrowserContextView)
def browser_context(
    request: Request, response: Response, context: Annotated[AuthContext, Depends(browser)]
) -> dict[str, object]:
    response.headers.update(NO_STORE)
    return {"csrf_token": csrf(request, context), "account": account(context)}


@router.post("/api/cli-auth/authorizations/review", response_model=CliReviewView)
def review(
    payload: UserCodeRequest,
    request: Request,
    response: Response,
    context: Annotated[AuthContext, Depends(browser_write)],
) -> dict[str, object]:
    limit(request, "review", context.user.id, 20)
    response.headers.update(NO_STORE)
    return {
        **service(request).review(payload.user_code, context.user.id),
        "account": account(context),
    }


@router.post("/api/cli-auth/authorizations/decision", response_model=CliDecisionView)
def decision(
    payload: DecisionRequest,
    request: Request,
    response: Response,
    context: Annotated[AuthContext, Depends(browser_write)],
) -> dict[str, object]:
    limit(request, "decision", context.user.id, 20)
    response.headers.update(NO_STORE)
    return service(request).decide(
        payload.user_code, context.user.id, payload.decision == "approve"
    )


@router.get("/api/cli-auth/grants", response_model=CliGrantsView)
def grants(
    request: Request, response: Response, context: Annotated[AuthContext, Depends(browser)]
) -> dict[str, object]:
    response.headers.update(NO_STORE)
    return {"grants": service(request).list_grants(context.user.id)}


@router.delete("/api/cli-auth/grants/{grant_id}", status_code=204)
def revoke_browser(
    grant_id: str, request: Request, context: Annotated[AuthContext, Depends(browser_write)]
) -> Response:
    service(request).revoke(grant_id, context.user.id)
    return Response(status_code=204, headers=NO_STORE)


@router.get("/api/cli-auth/me", response_model=CliIdentityView)
def me(
    request: Request, response: Response, actor: Annotated[CliPrincipal, Depends(principal)]
) -> dict[str, object]:
    require_scope(actor, "identity:read")
    response.headers.update(NO_STORE)
    return {"user_id": actor.user_id, "display_name": actor.display_name, **actor.metadata}


@router.post("/api/cli-auth/revoke", status_code=204)
def revoke_cli(
    request: Request, credential: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]
) -> Response:
    if credential is None:
        raise CliAuthError("invalid_token", 401)
    actor = service(request).resolve(credential.credentials.strip(), check_rooms=False)
    service(request).revoke(actor.grant_id, actor.user_id)
    return Response(status_code=204, headers=NO_STORE)


@router.get("/api/cli/rooms", response_model=CliRoomsView)
def rooms(
    request: Request, response: Response, actor: Annotated[CliPrincipal, Depends(principal)]
) -> dict[str, object]:
    require_scope(actor, "rooms:read")
    result = [
        service(request).rooms.require(room, actor.user_id, fresh=True) for room in actor.room_ids
    ]
    response.headers.update(NO_STORE)
    return {"rooms": [{"id": room.id, "name": room.name} for room in result]}


def snapshot(svc: CliAuthService, token_value: str, room_id: str) -> dict[str, object]:
    from echo_masque.api.routes.web_chat import _snapshot

    actor = svc.resolve(token_value)
    require_scope(actor, "messages:read", room_id)
    result = _snapshot(svc.rooms, room_id, actor.user_id, include_outbox=False)
    # Revalidate after snapshot I/O, immediately before handing data to the response.
    svc.resolve(token_value)
    return result


@router.get("/api/cli/rooms/{room_id}/messages", response_model=CliSnapshotView)
def messages(
    room_id: str,
    request: Request,
    response: Response,
    actor: Annotated[CliPrincipal, Depends(principal)],
) -> dict[str, object]:
    require_scope(actor, "messages:read", room_id)
    response.headers.update(NO_STORE)
    return snapshot(
        service(request), request.headers["authorization"].partition(" ")[2].strip(), room_id
    )


def encoded_snapshot(svc: CliAuthService, token_value: str, room_id: str) -> str:
    data = json.dumps(snapshot(svc, token_value, room_id), ensure_ascii=False)
    svc.resolve(token_value)
    return data


async def stream(
    svc: CliAuthService, token_value: str, room_id: str, request: Request
) -> AsyncIterator[str]:
    previous = ""
    started = time.monotonic()
    while time.monotonic() - started < 60 and not await request.is_disconnected():
        try:
            data = await asyncio.wait_for(
                asyncio.to_thread(encoded_snapshot, svc, token_value, room_id),
                timeout=CLI_STREAM_IO_TIMEOUT,
            )
        except (CliAuthError, WebRoomError):
            yield 'event: revoked\ndata: {"reason":"authorization_unavailable"}\n\n'
            return
        except Exception:
            yield 'event: unavailable\ndata: {"reason":"snapshot_unavailable"}\n\n'
            return
        fingerprint = hashlib.sha256(data.encode()).hexdigest()
        if fingerprint != previous:
            yield f"id: {fingerprint}\nevent: snapshot\ndata: {data}\n\n"
            previous = fingerprint
        else:
            yield ": keepalive\n\n"
        await asyncio.sleep(1)


@router.get("/api/cli/rooms/{room_id}/events")
async def events(
    room_id: str, request: Request, actor: Annotated[CliPrincipal, Depends(principal)]
) -> StreamingResponse:
    require_scope(actor, "messages:read", room_id)
    leases: dict[str, tuple[str, float]] = request.app.state.cli_streams
    now = time.monotonic()
    for key, (_, deadline) in tuple(leases.items()):
        if deadline <= now:
            leases.pop(key, None)
    if len(leases) >= 128 or sum(owner == actor.user_id for owner, _ in leases.values()) >= 3:
        raise CliAuthError("stream_capacity", 429)
    lease_id = uuid4().hex
    leases[lease_id] = (actor.user_id, now + 70)

    async def leased_stream() -> AsyncIterator[str]:
        try:
            async for event in stream(
                service(request),
                request.headers["authorization"].partition(" ")[2].strip(),
                room_id,
                request,
            ):
                yield event
        finally:
            leases.pop(lease_id, None)

    return StreamingResponse(
        leased_stream(),
        media_type="text/event-stream",
        headers={**NO_STORE, "X-Accel-Buffering": "no", "X-Content-Type-Options": "nosniff"},
    )
